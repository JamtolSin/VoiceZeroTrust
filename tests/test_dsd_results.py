"""Recompute released metrics and verify no split leakage."""
import hashlib
import json
from pathlib import Path
import pytest

from src.evaluation.metrics import summarize

FOLDER = Path(__file__).resolve().parents[1] / "experiments/2026-09-13/aasist-korean__dsd-v1-grouped"
pytestmark = pytest.mark.skipif(not (FOLDER / "checksums.json").exists(), reason="Korean run not yet archived")


def read(name):
    return json.loads((FOLDER / name).read_text(encoding="utf-8"))


def test_korean_archive_integrity():
    for name, checksum in read("checksums.json").items():
        assert hashlib.sha256((FOLDER / name).read_bytes()).hexdigest() == checksum
    assert read("test-lock.json")["selection_sha256"] == hashlib.sha256((FOLDER / "selection.json").read_bytes()).hexdigest()
    assert read("test-report.json")["default_changed"] is False
    root = FOLDER.parents[2]
    for name, checksum in read("metadata.json")["script_sha256"].items():
        assert hashlib.sha256((root / "scripts" / name).read_bytes()).hexdigest() == checksum
    profile = json.loads((root / "src/detection/profiles/v4-korean-research.json").read_text(encoding="utf-8"))
    selection = read("selection.json")
    assert profile["head"] == selection["candidates"][selection["selected"]]["head"]
    assert profile["threshold"] == read("test-lock.json")["thresholds"]["v4"]
    assert profile["research_only"] is True


def test_korean_test_metrics_recompute():
    predictions = read("test-predictions.json")
    rows = [r for r in predictions if r["condition"] == "original"]
    assert len({r["sha256"] for r in rows}) == len(rows) == read("test-lock.json")["test_count"]
    for name, threshold in read("test-lock.json")["thresholds"].items():
        actual = summarize([{"label": r["label"], "score": r["scores"].get(name), "error": r["errors"].get(name)} for r in rows], threshold)
        assert actual == read("test-report.json")["overall"][name]
    report = read("test-report.json")
    subset = set(read("test-lock.json")["robustness_subset"])
    populations = [(models, [r for r in rows if r["source"] == source])
                   for source, models in report["by_source"].items()]
    for condition, block in report["robustness"].items():
        selected = [r for r in predictions if r["condition"] == condition and r["sha256"] in subset]
        assert block["skipped"] == sum(bool(r.get("skipped")) for r in selected)
        populations.append((block["metrics"], [r for r in selected if not r.get("skipped")]))
    for expected, population in populations:
        for name, threshold in read("test-lock.json")["thresholds"].items():
            actual = summarize([{"label": r["label"], "score": r["scores"].get(name), "error": r["errors"].get(name)} for r in population], threshold)
            assert actual == expected[name]


def test_korean_groups_and_pcm_are_disjoint():
    rows = [json.loads(line) for line in (FOLDER / "split-manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    allowed = {"id", "sha256", "pcm_sha256", "label", "source", "group", "split", "duration", "sample_rate", "channels"}
    assert all(set(row) == allowed for row in rows)
    for key in ("group", "sha256", "pcm_sha256"):
        roles = {}
        for row in rows:
            roles.setdefault(row[key], set()).add(row["split"])
        assert all(len(values) == 1 for values in roles.values())
    assert all(r["split"] == "test" for r in rows if r["source"] not in ("AIHUB", "VITS-AIHUB"))
