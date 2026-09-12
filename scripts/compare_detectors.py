"""Development-only candidate scoring. Holdout must not be used here."""
import os
from pathlib import Path
import sys
import json
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["HF_HOME"] = str(ROOT / ".runtime/detection/models")


def main():
    import numpy as np
    import soundfile as sf
    import torch
    from src.detection.aasist import AASISTDetector, REVISION
    from src.detection.audio import decode
    from tempfile import TemporaryDirectory
    from src.evaluation.pipeline import write_json
    source = ROOT / ".runtime/evaluation/public-stafford-v4"
    output = ROOT / ".runtime/evaluation/detection-v2"
    output.mkdir(parents=True, exist_ok=True)
    original = json.loads((source / "predictions.json").read_text(encoding="utf-8"))
    rows = list({r["sha256"]: r for r in original}.values())
    for variant in ["AASIST", "AASIST-L"]:
        detector = AASISTDetector(variant, device="cuda:0" if torch.cuda.is_available() else "cpu")
        target = output / f"stafford-{variant}.json"
        scored = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
        for index, old in enumerate(scored):
            if old["sha256"] != rows[index]["sha256"]:
                raise ValueError("Checkpoint mismatch")
        start = time.perf_counter()
        for row in rows[len(scored):]:
            with TemporaryDirectory(dir=output) as temporary:
                samples, rate = decode(row["path"], Path(temporary) / "input.wav")
            embedding, score = detector.features(samples)
            scored.append({"id": row["id"], "sha256": row["sha256"], "original_path": row["original_path"],
                           "label": row["label"], "xlsr": row["score"], "score": score, "features": embedding.tolist()})
            if len(scored) % 100 == 0 or len(scored) == len(rows):
                write_json(target, scored)
                print(f"{variant} {len(scored)}/{len(rows)} {time.perf_counter()-start:.1f}s", flush=True)
        del detector
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
