"""Evaluate the complete Gary Stafford v4 public corpus; no voice generation."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from importlib.metadata import version

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["HF_HOME"] = str(ROOT / ".runtime/detection/models")
os.environ["MPLCONFIGDIR"] = str(ROOT / ".runtime/matplotlib")


def main():
    import requests
    import pyarrow.parquet as pq
    import torch
    from transformers import pipeline
    from src.detection.audio import AcousticDetector, MODEL_ID
    from src.detection.service import DetectionService
    from src.evaluation.metrics import summarize
    from src.evaluation.pipeline import write_json

    folder = ROOT / ".runtime/evaluation/public-stafford-v4"
    folder.mkdir(parents=True, exist_ok=True)
    repo = "garystafford/deepfake-audio-detection"
    session = requests.Session()
    revision = "fcf5344bb7f82b54b6b932291326d29750ef1e82"
    expected_model_revision = "f7050b586236dc910d1157f430def2d0647b02b4"
    config_path = folder / "config.json"
    config = {"dataset": repo, "revision": revision, "license": "CC-BY-4.0", "author": "Gary Stafford",
              "threshold": 0.5, "model": MODEL_ID, "device": "cuda:0" if torch.cuda.is_available() else "cpu",
              "versions": {name: version(name) for name in ["torch", "transformers", "pyarrow"]},
              "scope": "Complete published train split used for external evaluation; no training or threshold fitting",
              "limitations": ["English only", "Speaker identities unavailable; clips are not independent speakers",
                              "Detector training overlap cannot be ruled out", "Not phishing-intent detection",
                              "Publisher license relied upon; individual speaker consent not independently verified"]}
    if config_path.exists():
        old = json.loads(config_path.read_text(encoding="utf-8"))
        if old != config:
            raise RuntimeError("Configuration changed; use a new output directory")
    write_json(config_path, config)
    rows = []
    audio_folder = folder / "audio"
    audio_folder.mkdir(exist_ok=True)
    for shard in range(2):
        name = f"train-{shard:05d}-of-00002.parquet"
        target = folder / name
        if not target.exists():
            print(f"Downloading {name}", flush=True)
            with session.get(f"https://huggingface.co/datasets/{repo}/resolve/{revision}/data/{name}", stream=True, timeout=120) as response:
                response.raise_for_status()
                temporary = target.with_suffix(".partial")
                with temporary.open("wb") as handle:
                    for chunk in response.iter_content(1024*1024):
                        handle.write(chunk)
                temporary.replace(target)
        table = pq.ParquetFile(target)
        for batch in table.iter_batches(batch_size=32):
            for item in batch.to_pylist():
                index = len(rows)
                audio = item["audio"]
                data = audio["bytes"]
                path = audio_folder / f"{index:05d}.flac"
                if not path.exists():
                    path.write_bytes(data)
                elif hashlib.sha256(path.read_bytes()).hexdigest() != hashlib.sha256(data).hexdigest():
                    raise RuntimeError("Extracted audio changed; refusing stale checkpoint reuse")
                label = {0: "real", 1: "synthetic"}[item["label"]]
                rows.append({"id": index, "label": label, "path": str(path), "original_path": audio["path"],
                             "sha256": hashlib.sha256(data).hexdigest()})
    write_json(folder / "manifest.json", rows)
    if len(rows) != 1866 or sum(r["label"] == "real" for r in rows) != 933:
        raise RuntimeError("Published v4 counts do not match; inspect the corpus before evaluation")
    for row in rows:
        if row["original_path"].startswith("yt_") != (row["label"] == "real"):
            raise RuntimeError("Filename provenance contradicts dataset label")
    print(f"Loaded {len(rows)} clips; labels: { {label:sum(r['label']==label for r in rows) for label in ['real','synthetic']} }", flush=True)
    # Match the application classifier and chunking, changing only inference device.
    classifier = pipeline("audio-classification", model=MODEL_ID, revision=expected_model_revision,
                          device=0 if torch.cuda.is_available() else -1, trust_remote_code=False)
    model_revision = getattr(classifier.model.config, "_commit_hash", None)
    if model_revision != expected_model_revision:
        raise RuntimeError("Detector revision does not match the benchmark")
    service = DetectionService(acoustic=AcousticDetector(classifier), workdir=folder / "requests")
    predictions_path = folder / "predictions.json"
    results = json.loads(predictions_path.read_text(encoding="utf-8")) if predictions_path.exists() else []
    for index, row in enumerate(rows[:len(results)]):
        if any(results[index][key] != row[key] for key in ("id", "sha256", "label")):
            raise RuntimeError("Checkpoint mismatch")
    start = time.perf_counter()
    for row in rows[len(results):]:
        result = {**row, "score": None, "error": None, "prediction": "abstain", "ox": "보류"}
        try:
            response = service.analyze(row["path"], enable_acoustic=True)
            result["details"] = response["acoustic"]
            result["duration_seconds"] = response["audio"]["duration_seconds"]
            score = response["acoustic"]["fake_score"]
            result["score"] = score
            if score is not None:
                result["prediction"] = "synthetic" if score >= .5 else "real"
                result["ox"] = "O" if result["prediction"] == row["label"] else "X"
            elif response["acoustic"]["status"] == "사용 불가":
                result["error"] = "Detector unavailable"
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        results.append(result)
        if len(results) % 25 == 0 or len(results) == len(rows):
            write_json(predictions_path, results)
            print(f"{len(results)}/{len(rows)}, elapsed={time.perf_counter()-start:.1f}s, {summarize(results)['confusion']}", flush=True)
    counts = {}
    for row in rows:
        counts[row["sha256"]] = counts.get(row["sha256"], 0) + 1
    unique = list({r["sha256"]: r for r in results}.values())
    for digest in counts:
        if len({r["label"] for r in results if r["sha256"] == digest}) != 1:
            raise RuntimeError("Identical audio has conflicting labels")
    groups = {r["original_path"].split("_")[0] for r in results}
    report = {"config": config, "model_revision": model_revision, "total": len(rows),
              "duplicate_files": len(rows)-len(counts), "metrics": summarize(results),
              "unique_metrics": summarize(unique), "by_label": {label: summarize([r for r in results if r["label"] == label]) for label in ["real", "synthetic"]},
              "unique_by_source": {group: summarize([r for r in unique if r["original_path"].startswith(group + "_")]) for group in sorted(groups)},
              "by_source": {group: summarize([r for r in results if r["original_path"].startswith(group + "_")]) for group in sorted(groups)}}
    write_json(folder / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
