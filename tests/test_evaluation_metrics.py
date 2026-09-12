import json

import pytest

from src.evaluation.metrics import classify, summarize


def test_threshold_boundary_and_confusion():
    rows = [
        {"label": "synthetic", "score": 0.5},
        {"label": "synthetic", "score": 0.49},
        {"label": "real", "score": 0.8},
        {"label": "real", "score": 0.2},
    ]
    result = summarize(rows)
    assert result["confusion"] == {"tp": 1, "fn": 1, "fp": 1, "tn": 1}
    for key in ("precision", "recall", "specificity", "fpr", "fnr", "accuracy", "balanced_accuracy"):
        assert result[key] == 0.5
    assert result["coverage"] == 1
    assert classify(0, 0) == "synthetic"
    assert classify(1, 1) == "synthetic"
    assert classify(None) is None


def test_abstention_errors_and_unconditional_detection():
    result = summarize([
        {"label": "synthetic", "score": 0.9},
        {"label": "synthetic", "score": None},
        {"label": "synthetic", "score": 0.9, "error": "inference failed"},
        {"label": "real", "score": None},
        {"label": "real", "score": 0.1},
    ])
    assert result["total"] == 5
    assert result["classified"] == 2
    assert result["coverage"] == 0.4
    assert result["abstained"] == {"real": 1, "synthetic": 2}
    assert result["errors"] == 1
    assert result["recall"] == 1
    assert result["synthetic_detection_rate_all"] == pytest.approx(1 / 3)


@pytest.mark.parametrize("bad", [-0.1, 1.1, float("nan"), float("inf"), "0.5", True])
def test_invalid_score_and_threshold(bad):
    with pytest.raises(ValueError):
        summarize([{"label": "real", "score": bad}])
    with pytest.raises(ValueError):
        summarize([], threshold=bad)


def test_invalid_label():
    with pytest.raises(ValueError):
        summarize([{"label": "phishing", "score": 0.9}])


def test_undefined_ratios_are_json_null():
    result = summarize([])
    assert result["total"] == 0
    for key in ("coverage", "precision", "recall", "specificity", "fpr", "fnr", "accuracy", "balanced_accuracy", "synthetic_detection_rate_all"):
        assert result[key] is None
    json.dumps(result, allow_nan=False)
    result = summarize([{"label": "real", "score": 0.1}])
    assert result["accuracy"] == 1
    assert result["balanced_accuracy"] is None
    assert result["precision"] is None
