"""Binary synthetic-audio metrics; abstentions are never silently real."""

import math
from numbers import Real


def _probability(value, name):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number between 0 and 1")
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be a finite number between 0 and 1")
    return value


def classify(score, threshold=0.5):
    """Return synthetic at or above the threshold, real below, or None."""
    threshold = _probability(threshold, "threshold")
    if score is None:
        return None
    return "synthetic" if _probability(score, "score") >= threshold else "real"


def summarize(rows, threshold=0.5):
    """Calculate conditional metrics plus all-sample synthetic detection rate.

    All conventional classification metrics exclude abstentions. Coverage and
    synthetic_detection_rate_all expose their impact. An error forces abstention
    even if a stale numeric score exists. Undefined ratios are JSON null (None).
    """
    threshold = _probability(threshold, "threshold")
    confusion = {"tp": 0, "fn": 0, "fp": 0, "tn": 0}
    abstained = {"real": 0, "synthetic": 0}
    totals = {"real": 0, "synthetic": 0}
    errors = 0
    for row in rows:
        label = row.get("label")
        if label not in totals:
            raise ValueError("label must be real or synthetic")
        prediction = classify(row.get("score"), threshold)
        totals[label] += 1
        if row.get("error"):
            errors += 1
            prediction = None
        if prediction is None:
            abstained[label] += 1
        elif label == "synthetic":
            confusion["tp" if prediction == "synthetic" else "fn"] += 1
        else:
            confusion["fp" if prediction == "synthetic" else "tn"] += 1

    tp, fn, fp, tn = (confusion[key] for key in ("tp", "fn", "fp", "tn"))
    total = sum(totals.values())
    classified = sum(confusion.values())

    def ratio(numerator, denominator):
        return numerator / denominator if denominator else None

    recall = ratio(tp, tp + fn)
    specificity = ratio(tn, tn + fp)
    return {
        "threshold": threshold,
        "positive_label": "synthetic",
        "total": total,
        "classified": classified,
        "coverage": ratio(classified, total),
        "class_totals": totals,
        "confusion": confusion,
        "abstained": abstained,
        "errors": errors,
        "precision": ratio(tp, tp + fp),
        "recall": recall,
        "specificity": specificity,
        "fpr": ratio(fp, fp + tn),
        "fnr": ratio(fn, fn + tp),
        "accuracy": ratio(tp + tn, classified),
        "balanced_accuracy": (
            (recall + specificity) / 2
            if recall is not None and specificity is not None else None
        ),
        "synthetic_detection_rate_all": ratio(tp, totals["synthetic"]),
        "metrics_population": "classified_only_except_coverage_and_synthetic_detection_rate_all",
    }
