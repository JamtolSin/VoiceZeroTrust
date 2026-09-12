import hashlib
import json
from pathlib import Path

from src.evaluation.metrics import summarize

FOLDER = Path(__file__).resolve().parents[1] / "experiments/2026-09-12/aasist-aug-lowfpr__stafford-groupcv"


def read(name):
    return json.loads((FOLDER / name).read_text(encoding="utf-8"))


def test_v3_archive_checksums_and_no_promotion():
    for name, checksum in read("checksums.json").items():
        assert hashlib.sha256((FOLDER / name).read_bytes()).hexdigest() == checksum
    assert read("metadata.json")["fresh_external_test"] is False
    assert read("report.json")["promotion_passed"] is False


def test_v3_metrics_recomputed_from_individual_decisions():
    rows = read("predictions.json")
    for config, conditions in read("report.json")["results"].items():
        for condition, metrics in conditions.items():
            selected = [r for r in rows if r["config"] == config and r["condition"] == condition]
            assert len(selected) == len({r["sha256"] for r in selected}) == 1650
            for r in selected:
                assert r["decision"] == int(r["score"] >= r["threshold"])
            actual = summarize([{"label": r["label"], "score": r["decision"]} for r in selected])
            for key in actual:
                if key != "threshold":
                    assert metrics[key] == actual[key]


def test_v3_fold_groups_never_cross_roles():
    partitions = read("partitions.json")
    for fold in range(5):
        rows = [r for r in partitions if r["fold"] == fold]
        assert len(rows) == len({r["sha256"] for r in rows}) == 1650
        roles = {}
        for row in rows:
            roles.setdefault(row["group"], set()).add(row["role"])
        assert len(roles) == 34
        assert all(len(value) == 1 for value in roles.values())
