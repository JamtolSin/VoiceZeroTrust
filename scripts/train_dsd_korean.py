"""Train a research-only Korean head, with no access to test audio scores."""
import argparse
import hashlib
import json
from math import gcd
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def read_audio(row):
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    blob = Path(row["path"]).read_bytes()
    if hashlib.sha256(blob).hexdigest() != row["sha256"]:
        raise ValueError("Audio checksum changed")
    x, rate = sf.read(row["path"], dtype="float32", always_2d=True)
    mono = x.mean(axis=1)
    div = gcd(rate, 16000)
    pcm = resample_poly(mono, 16000 // div, rate // div).astype("<f4") if rate != 16000 else mono.astype("<f4")
    if not np.isfinite(pcm).all() or hashlib.sha256(pcm.tobytes()).hexdigest() != row["pcm_sha256"]:
        raise ValueError("Decoded PCM changed")
    # Use the same final inference PCM path as the application. The SciPy PCM
    # above is retained only as the corpus's duplicate-integrity fingerprint.
    from tempfile import TemporaryDirectory
    from src.detection.audio import decode
    with TemporaryDirectory(dir=Path(row["path"]).parent) as temporary:
        inference_pcm, _ = decode(row["path"], Path(temporary) / "input.wav")
    return inference_pcm


def main():
    import numpy as np
    import torch
    from scripts.prepare_dsd import json_once
    from scripts.evaluate_v3 import fit_head
    from scripts.select_detector import choose_threshold
    from src.detection.aasist import AASISTDetector, linear_score, REVISION
    from src.evaluation.augmentation import augment, CONDITIONS
    from src.evaluation.pipeline import write_json
    from src.evaluation.metrics import summarize
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    data = args.data.resolve()
    output = data / "experiment-v4"
    output.mkdir(exist_ok=True)
    if (output / "selection.json").exists():
        raise RuntimeError("Selection frozen; no refitting after final test")
    manifest = data / "manifest.jsonl"
    all_rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    split = json.loads((data / "split-lock.json").read_text(encoding="utf-8"))
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != split["manifest_sha256"]:
        raise ValueError("Manifest changed")
    rows = [r for r in all_rows if r["split"] in ("train", "calibration")]
    plan = {"manifest_sha256": split["manifest_sha256"], "backbone_revision": REVISION,
            "configs": [{"name": "clean", "C": .01, "augment": False}, {"name": "augmented", "C": .01, "augment": True}],
            "selection": "maximum calibration recall subject to calibration FPR <= .05; tie clean first",
            "conditions": list(CONDITIONS), "test_conditions": ["original", "bandlimit-8k", "noise-20db", "first-2s", "first-3s", "first-5s"],
            "promotion_rule": "research only regardless of score; no commercial or production promotion",
            "quality_gate": "test all-synthetic detection >= .80, FPR <= .05, each unseen-generator detection >= .50, errors 0, coverage 1",
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    json_once(output / "training-lock.json", plan)
    detector = AASISTDetector(device="cuda:0" if torch.cuda.is_available() else "cpu")
    feature_path = output / "development-features.json"
    extracted = json.loads(feature_path.read_text(encoding="utf-8")) if feature_path.exists() else []
    for row, cached in zip(rows, extracted):
        if cached["sha256"] != row["sha256"]:
            raise ValueError("Feature checkpoint mismatch")
    if len(extracted) > len(rows):
        raise ValueError("Oversized checkpoint")
    for row in rows[len(extracted):]:
        pcm = read_audio(row)
        features = {c: detector.features(augment(pcm, c, row["sha256"]))[0].tolist() for c in CONDITIONS}
        extracted.append({"sha256": row["sha256"], "features": features})
        if len(extracted) % 500 == 0 or len(extracted) == len(rows):
            write_json(feature_path, extracted)
            print(f"Development features {len(extracted)}/{len(rows)}", flush=True)
    y = np.array([r["label"] == "synthetic" for r in rows], dtype=int)
    train = np.array([i for i, r in enumerate(rows) if r["split"] == "train"])
    calibration = np.array([i for i, r in enumerate(rows) if r["split"] == "calibration"])
    x = {c: np.asarray([r["features"][c] for r in extracted]) for c in CONDITIONS}
    candidates = {}
    for config in plan["configs"]:
        conditions = CONDITIONS if config["augment"] else ("original",)
        head = fit_head(x, y, train, conditions, config["C"])
        scores = linear_score(x["original"][calibration], head)
        try:
            threshold = choose_threshold(scores, y[calibration], .05)
        except ValueError:
            continue
        metrics = summarize([{"label": rows[i]["label"], "score": float(s)} for i, s in zip(calibration, scores)], threshold)
        candidates[config["name"]] = {"head": head, "threshold": threshold, "calibration": metrics}
    if not candidates:
        raise RuntimeError("No eligible model; retain default")
    selected = max(candidates, key=lambda name: candidates[name]["calibration"]["recall"])
    json_once(output / "selection.json", {"selected": selected, "candidates": candidates, "manifest_sha256": split["manifest_sha256"],
                                          "research_only": True, "license_scope": "noncommercial research/evaluation", "promotion_passed": False})
    print(json.dumps({"selected": selected, "calibration": {k: v["calibration"] for k, v in candidates.items()}}, indent=2), flush=True)


if __name__ == "__main__":
    main()
