import hashlib
import json
from pathlib import Path

from src.evaluation.metrics import summarize

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "experiments/2026-09-12/aasist-head-a04c986__deepvoice-50b1b3b"


def test_v2_archive_checksums_and_locked_selection():
    checksums = json.loads((FOLDER / "checksums.json").read_text(encoding="utf-8"))
    for filename, digest in checksums.items():
        assert Path(filename).name == filename
        assert hashlib.sha256((FOLDER / filename).read_bytes()).hexdigest() == digest
    lock = json.loads((FOLDER / "holdout-lock.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((FOLDER / "selection.json").read_bytes()).hexdigest() == lock["selection_sha256"]
    profile = json.loads((ROOT / "src/detection/profiles/v2-candidate.json").read_text(encoding="utf-8"))
    selection = json.loads((FOLDER / "selection.json").read_text(encoding="utf-8"))
    assert profile["head"] == selection["policy"]["head"]
    assert profile["threshold"] == selection["policy"]["threshold"]
    assert profile["promotion_passed"] is False


def test_all_external_predictions_recompute_and_no_private_paths():
    raw = (FOLDER / "holdout-predictions.jsonl").read_text(encoding="utf-8")
    assert "C:\\" not in raw and "OneDrive" not in raw and '"path"' not in raw
    rows = [json.loads(line) for line in raw.splitlines()]
    assert len(rows) == 5053
    assert len({r["sha256"] for r in rows}) == len(rows)
    report = json.loads((FOLDER / "holdout-report.json").read_text(encoding="utf-8"))
    for name, data in report["candidates"].items():
        metric_rows = [{"label": r["label"], "score": r["scores"][name], "error":r["errors"].get(name)} for r in rows]
        assert summarize(metric_rows, data["at_validation_threshold"]["threshold"]) == data["at_validation_threshold"]
    assert sum("input_error" in r for r in rows) == 3


def test_development_groups_do_not_cross_splits():
    rows = json.loads((FOLDER / "development-split.json").read_text(encoding="utf-8"))
    assert len(rows) == 1650
    groups = {}
    for row in rows:
        groups.setdefault(row["group"], set()).add(row["split"])
    assert all(len(splits) == 1 for splits in groups.values())
