"""Extract development-only augmented features without touching DeepVoice."""
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import torch
    from src.detection.aasist import AASISTDetector, REVISION
    from src.detection.audio import decode
    from src.evaluation.augmentation import augment, CONDITIONS
    from src.evaluation.pipeline import write_json
    folder = ROOT / ".runtime/evaluation/detection-v3"
    folder.mkdir(parents=True, exist_ok=True)
    source = ROOT / ".runtime/evaluation/detection-v2/stafford-AASIST.json"
    originals = ROOT / ".runtime/evaluation/public-stafford-v4/predictions.json"
    base = json.loads(source.read_text(encoding="utf-8"))
    paths = {r["sha256"]: r["path"] for r in json.loads(originals.read_text(encoding="utf-8"))}
    spec = {"revision": REVISION, "conditions": list(CONDITIONS),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "augmentation_code_sha256": hashlib.sha256((ROOT / "src/evaluation/augmentation.py").read_bytes()).hexdigest(),
            "population": "Previously inspected Stafford development only; NOT fresh test"}
    spec_path = folder / "features-spec.json"
    if spec_path.exists() and json.loads(spec_path.read_text(encoding="utf-8")) != spec:
        raise ValueError("Feature specification changed; use a new experiment directory")
    write_json(spec_path, spec)
    target = folder / "features.json"
    records = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
    for i, row in enumerate(records):
        if row["sha256"] != base[i]["sha256"]:
            raise ValueError("Checkpoint order mismatch")
    detector = AASISTDetector(device="cuda:0" if torch.cuda.is_available() else "cpu")
    for row in base[len(records):]:
        if hashlib.sha256(Path(paths[row["sha256"]]).read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("Audio checksum mismatch")
        with TemporaryDirectory(dir=folder) as temp:
            samples, _ = decode(paths[row["sha256"]], Path(temp) / "input.wav")
        features = {"original": row["features"]}
        for condition in CONDITIONS[1:]:
            features[condition] = detector.features(augment(samples, condition, row["sha256"]))[0].tolist()
        records.append({"sha256": row["sha256"], "label": row["label"], "features": features})
        if len(records) % 100 == 0 or len(records) == len(base):
            write_json(target, records)
            print(f"Development features {len(records)}/{len(base)}", flush=True)


if __name__ == "__main__":
    main()
