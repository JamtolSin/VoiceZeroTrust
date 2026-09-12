"""Locked Korean test and predeclared robustness subset; no refitting."""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["HF_HOME"] = str(ROOT / ".runtime/detection/models")


def main():
    import numpy as np
    import torch
    from transformers import pipeline
    from scripts.prepare_dsd import json_once
    from scripts.train_dsd_korean import read_audio
    from src.detection.aasist import AASISTDetector, linear_score
    from src.detection.audio import AcousticDetector, MODEL_ID
    from src.evaluation.augmentation import augment
    from src.evaluation.metrics import summarize
    from src.evaluation.pipeline import write_json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    data = args.data.resolve()
    output = data / "experiment-v4"
    selection_path = output / "selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    manifest = data / "manifest.jsonl"
    if selection["manifest_sha256"] != hashlib.sha256(manifest.read_bytes()).hexdigest():
        raise ValueError("Test manifest changed")
    test = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if json.loads(line)["split"] == "test"]
    buckets = defaultdict(list)
    for row in test:
        buckets[(row["source"], row["label"])].append(row)
    subset = {r["sha256"] for rows in buckets.values() for r in sorted(rows, key=lambda r: r["sha256"])[:16]}
    v2 = json.loads((ROOT / "src/detection/profiles/v2-candidate.json").read_text(encoding="utf-8"))
    selected = selection["candidates"][selection["selected"]]
    thresholds = {"xlsr": .5, "v2": v2["threshold"], "v4": selected["threshold"]}
    lock = {"selection_sha256": hashlib.sha256(selection_path.read_bytes()).hexdigest(),
            "v2_profile_sha256": hashlib.sha256((ROOT / "src/detection/profiles/v2-candidate.json").read_bytes()).hexdigest(),
            "thresholds": thresholds, "robustness_subset": sorted(subset), "subset_policy": "first 16 SHA sorted per source x label",
            "conditions": ["original", "bandlimit-8k", "noise-20db", "first-2s", "first-3s", "first-5s"],
            "test_count": len(test), "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    json_once(output / "test-lock.json", lock)
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    baseline = AcousticDetector(pipeline("audio-classification", model=MODEL_ID,
        revision="f7050b586236dc910d1157f430def2d0647b02b4", device=0 if device != "cpu" else -1, trust_remote_code=False))
    encoder = AASISTDetector(device=device)
    target = output / "test-predictions.json"
    results = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
    expected = [(r, c) for r in test for c in lock["conditions"] if c == "original" or r["sha256"] in subset]
    if len(results) > len(expected) or any((r["sha256"], r["condition"]) != (e[0]["sha256"], e[1]) for r, e in zip(results, expected)):
        raise ValueError("Test checkpoint mismatch")
    last_sha, pcm = None, None
    for row, condition in expected[len(results):]:
        record = {k: row[k] for k in ("id", "label", "source", "group", "sha256")}
        record.update(condition=condition, scores={}, errors={})
        try:
            if last_sha != row["sha256"]:
                pcm = read_audio(row)
                last_sha = row["sha256"]
            samples = pcm
            if condition.startswith("first-"):
                seconds = int(condition.split("-")[1][:-1])
                if len(pcm) < seconds * 16000:
                    record["skipped"] = "input_too_short_for_condition"
                    results.append(record)
                    continue
                samples = pcm[:seconds * 16000]
            elif condition != "original":
                samples = augment(pcm, condition, row["sha256"])
            try:
                record["scores"]["xlsr"] = baseline.analyze(samples, 16000)["fake_score"]
            except Exception as exc:
                record["scores"]["xlsr"] = None
                record["errors"]["xlsr"] = type(exc).__name__
            try:
                if len(samples) < 16000 or float(np.sqrt(np.mean(samples[:64600] ** 2))) < .003:
                    record["scores"].update(v2=None, v4=None)
                else:
                    features, _ = encoder.features(samples)
                    record["scores"].update(v2=float(linear_score(features, v2["head"])), v4=float(linear_score(features, selected["head"])))
            except Exception as exc:
                for name in ("v2", "v4"):
                    record["scores"][name] = None
                    record["errors"][name] = type(exc).__name__
        except Exception as exc:
            for name in thresholds:
                record["scores"][name] = None
                record["errors"][name] = type(exc).__name__
        results.append(record)
        if len(results) % 200 == 0 or len(results) == len(expected):
            write_json(target, results)
            print(f"Korean test {len(results)}/{len(expected)}", flush=True)
    write_json(target, results)
    def metrics(rows):
        return {name: summarize([{"label": r["label"], "score": r["scores"].get(name), "error": r["errors"].get(name)} for r in rows], t) for name, t in thresholds.items()}
    original = [r for r in results if r["condition"] == "original"]
    report = {"population": "DSD Korean grouped holdout; not verified text-disjoint, noncommercial research", "overall": metrics(original),
              "by_source": {s: metrics([r for r in original if r["source"] == s]) for s in sorted({r["source"] for r in original})},
              "robustness": {}, "promotion_passed": False, "default_changed": False}
    for condition in lock["conditions"]:
        rows = [r for r in results if r["condition"] == condition and r["sha256"] in subset]
        report["robustness"][condition] = {"skipped": sum(bool(r.get("skipped")) for r in rows), "metrics": metrics([r for r in rows if not r.get("skipped")])}
    candidate = report["overall"]["v4"]
    unseen = [models["v4"] for source, models in report["by_source"].items() if source not in ("AIHUB", "VITS-AIHUB")]
    report["quality_gate"] = {
        "rule": "test all-synthetic detection >= .80, FPR <= .05, each unseen-generator detection >= .50, errors 0, coverage 1",
        "passed": candidate["fpr"] is not None and candidate["fpr"] <= .05 and candidate["synthetic_detection_rate_all"] >= .80
                  and {"Elevenlabs", "MeloTTS", "SeamlessM4T-TTS", "MMSTTS"}.issubset(report["by_source"])
                  and all(m["synthetic_detection_rate_all"] is not None and m["synthetic_detection_rate_all"] >= .50 for m in unseen)
                  and candidate["errors"] == 0 and candidate["coverage"] == 1.0}
    json_once(output / "test-report.json", report)
    print(json.dumps(report["overall"], indent=2), flush=True)


if __name__ == "__main__":
    main()
