import hashlib
import json
from pathlib import Path

from src.evaluation.metrics import summarize


FOLDER = Path(__file__).resolve().parents[1] / "experiments/2026-09-12/xlsr-f7050b5__stafford-v4-fcf5344"


def test_archive_checksums_and_privacy():
    checksums = json.loads((FOLDER / "checksums.json").read_text(encoding="utf-8"))
    for name, digest in checksums.items():
        assert Path(name).name == name
        assert hashlib.sha256((FOLDER / name).read_bytes()).hexdigest() == digest
    rows = [json.loads(line) for line in (FOLDER / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1866
    for row in rows:
        assert "path" not in row and "transcript" not in row
        assert ":" not in row["original_path"] and "\\" not in row["original_path"] and "/" not in row["original_path"]


def test_archived_metrics_recompute_exactly():
    rows = [json.loads(line) for line in (FOLDER / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    report = json.loads((FOLDER / "report.json").read_text(encoding="utf-8"))
    assert summarize(rows) == report["metrics"]
    unique = list({row["sha256"]: row for row in rows}.values())
    assert len(unique) == 1650
    assert summarize(unique) == report["unique_metrics"]
    for row in rows:
        assert row["prediction"] == ("synthetic" if row["score"] >= .5 else "real")
        assert row["ox"] == ("O" if row["prediction"] == row["label"] else "X")
