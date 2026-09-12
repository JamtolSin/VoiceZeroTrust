"""Export a path-free, verifiable snapshot of the completed public benchmark."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "2026-09-12/xlsr-f7050b5__stafford-v4-fcf5344"
RELEASE = "v0.1.0-detection.1"


def export(source, destination):
    report = json.loads((source / "report.json").read_text(encoding="utf-8"))
    predictions = json.loads((source / "predictions.json").read_text(encoding="utf-8"))
    if len(predictions) != report["total"] or len(predictions) != 1866:
        raise ValueError("Incomplete benchmark")
    from src.evaluation.metrics import summarize
    if summarize(predictions) != report["metrics"]:
        raise ValueError("Metrics do not match predictions")
    destination.mkdir(parents=True, exist_ok=True)
    allowed = ("id", "label", "original_path", "sha256", "score", "prediction", "ox", "duration_seconds")
    public = [{key: row[key] for key in allowed} for row in predictions]
    if any(row.get("error") for row in predictions):
        raise ValueError("This release snapshot expects the verified error-free run")
    metadata = {"run_id": RUN_ID, "experiment_date": "2026-09-12", "timezone": "Asia/Seoul",
                "timestamp_precision": "date; exact original start time was not recorded", "detector_release": RELEASE,
                "model_id": report["config"]["model"], "model_revision": report["model_revision"],
                "dataset_id": report["config"]["dataset"], "dataset_revision": report["config"]["revision"],
                "dataset_license": report["config"]["license"], "dataset_author": "Gary Stafford",
                "threshold": .5, "inference_loop_seconds": 108.7, "hardware": "NVIDIA RTX 3080",
                "audio_seconds": sum(row["duration_seconds"] for row in predictions),
                "source_predictions_sha256": hashlib.sha256((source / "predictions.json").read_bytes()).hexdigest(),
                "privacy": "Audio, transcripts, local absolute paths and cache files excluded",
                "version_meaning": "Version of detection pipeline snapshot, not a newly trained model"}
    for name, value in (("metadata.json", metadata), ("report.json", report)):
        (destination / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (destination / "predictions.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in public), encoding="utf-8")
    (destination / "RESULTS.md").write_text((ROOT / "docs/evaluation-public-result.md").read_text(encoding="utf-8"), encoding="utf-8")
    payload = ["metadata.json", "report.json", "predictions.jsonl", "RESULTS.md", "README.md"]
    checksums = {name: hashlib.sha256((destination / name).read_bytes()).hexdigest() for name in payload}
    (destination / "checksums.json").write_text(json.dumps(checksums, indent=2) + "\n", encoding="utf-8")
    return payload + ["checksums.json"]


def main():
    destination = ROOT / "experiments" / RUN_ID
    files = export(ROOT / ".runtime/evaluation/public-stafford-v4", destination)
    release_dir = ROOT / ".runtime/releases"
    release_dir.mkdir(parents=True, exist_ok=True)
    archive = release_dir / f"{RELEASE}-benchmark.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in files:
            bundle.write(destination / name, arcname=f"{RUN_ID}/{name}")
    print(archive)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    main()
