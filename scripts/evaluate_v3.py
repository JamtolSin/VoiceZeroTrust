"""Predeclared grouped development comparison. Never promotes a model."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CONFIGS = (
    {"name": "clean-C1-fpr5", "C": 1., "augment": False, "cap": .05},
    {"name": "clean-C001-fpr5", "C": .01, "augment": False, "cap": .05},
    {"name": "clean-C001-fpr1", "C": .01, "augment": False, "cap": .01},
    {"name": "aug-C001-fpr1", "C": .01, "augment": True, "cap": .01},
)


def grouped_splits(labels, groups):
    """Outer test untouched by both fitting and threshold calibration."""
    import numpy as np
    from sklearn.model_selection import GroupKFold
    y, g = np.asarray(labels), np.asarray(groups)
    indices = np.arange(len(y))
    for development, test in GroupKFold(5).split(indices, y, g):
        fit_local, calibration_local = next(GroupKFold(3).split(development, y[development], g[development]))
        fit, calibration = development[fit_local], development[calibration_local]
        for subset in (fit, calibration, test):
            if len(set(y[subset])) != 2:
                raise ValueError("Each partition needs both classes")
        if set(g[fit]) & set(g[calibration]) or set(g[fit]) & set(g[test]) or set(g[calibration]) & set(g[test]):
            raise ValueError("Group leakage")
        yield fit, calibration, test


def fit_head(features, labels, indices, conditions, c):
    import numpy as np
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    x = np.concatenate([features[condition][indices] for condition in conditions])
    y = np.tile(labels[indices], len(conditions))
    scaler = StandardScaler().fit(x)
    # Repeated augmented views must not triple each source's training weight.
    model = LogisticRegression(C=c, class_weight="balanced", solver="liblinear", random_state=0, max_iter=2000)
    model.fit(scaler.transform(x), y, sample_weight=np.full(len(y), 1 / len(conditions)))
    return {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
            "coef": model.coef_[0].tolist(), "intercept": float(model.intercept_[0])}


def main():
    import numpy as np
    from scripts.select_detector import split_groups, choose_threshold
    from src.detection.aasist import linear_score
    from src.evaluation.augmentation import CONDITIONS
    from src.evaluation.metrics import summarize
    from src.evaluation.pipeline import write_json
    folder = ROOT / ".runtime/evaluation/detection-v3"
    source = folder / "features.json"
    rows = json.loads(source.read_text(encoding="utf-8"))
    original = json.loads((ROOT / ".runtime/evaluation/public-stafford-v4/predictions.json").read_text(encoding="utf-8"))
    mapping = split_groups(original)
    if len({r["sha256"] for r in rows}) != len(rows) or set(mapping) != {r["sha256"] for r in rows}:
        raise ValueError("Development population mismatch")
    groups = np.array([mapping[r["sha256"]] for r in rows])
    y = np.array([r["label"] == "synthetic" for r in rows], dtype=int)
    features = {c: np.asarray([r["features"][c] for r in rows]) for c in CONDITIONS}
    if any(x.ndim != 2 or not np.isfinite(x).all() for x in features.values()):
        raise ValueError("Invalid cached features")
    splits = list(grouped_splits(y, groups))
    lock = {"configs": CONFIGS, "features_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "protocol": "5 GroupKFold outer tests; first of 3 inner group folds for calibration; no test threshold tuning",
            "conditions": CONDITIONS, "promotion_passed": False,
            "limitations": "Previously inspected development corpus; correlated source groups, not verified speakers. No independent final test or Korean validation."}
    lock_path = folder / "evaluation-lock.json"
    if lock_path.exists():
        raise RuntimeError("Evaluation already locked; do not overwrite results")
    write_json(lock_path, lock)
    predictions, models, partitions = [], [], []
    for fold, (fit, calibration, test) in enumerate(splits):
        for role, indices in [("fit", fit), ("calibration", calibration), ("test", test)]:
            partitions.extend({"fold": fold, "sha256": rows[i]["sha256"], "group": str(groups[i]), "role": role} for i in indices)
        for config in CONFIGS:
            conditions = CONDITIONS if config["augment"] else ("original",)
            head = fit_head(features, y, fit, conditions, config["C"])
            # Conservative across calibration conditions, not across outer test.
            try:
                threshold = max(choose_threshold(linear_score(features[c][calibration], head), y[calibration], config["cap"]) for c in conditions)
            except ValueError:
                threshold = None  # Fail closed: abstain, never force a valid-looking threshold.
            models.append({"fold": fold, "config": config["name"], "threshold": threshold, "head": head})
            for condition in CONDITIONS:
                scores = linear_score(features[condition][test], head)
                for i, score in zip(test, scores):
                    predictions.append({"fold": fold, "config": config["name"], "condition": condition,
                                        "sha256": rows[i]["sha256"], "group": str(groups[i]), "label": rows[i]["label"],
                                        "score": float(score), "threshold": threshold,
                                        "decision": None if threshold is None else int(score >= threshold)})
        print(f"Grouped outer fold {fold + 1}/5 completed", flush=True)
    report = {"population": "Stafford development grouped out-of-fold; not fresh external performance", "promotion_passed": False, "results": {}}
    for config in CONFIGS:
        report["results"][config["name"]] = {}
        for condition in CONDITIONS:
            selected = [r for r in predictions if r["config"] == config["name"] and r["condition"] == condition]
            # Different fold thresholds: summarize binary decisions, not raw scores at .5.
            metrics = summarize([{"label": r["label"], "score": r["decision"]} for r in selected])
            metrics["threshold"] = "per-fold calibrated; see predictions"
            metrics["folds"] = {str(fold): summarize([{"label": r["label"], "score": r["decision"]} for r in selected if r["fold"] == fold]) for fold in range(5)}
            report["results"][config["name"]][condition] = metrics
    write_json(folder / "partitions.json", partitions)
    write_json(folder / "fold-models.json", models)
    write_json(folder / "predictions.json", predictions)
    write_json(folder / "report.json", report)
    for name, conditions in report["results"].items():
        for condition, m in conditions.items():
            print(f"{name} {condition}: recall={m['recall']:.4f} FPR={m['fpr']:.4f} coverage={m['coverage']:.4f}", flush=True)


if __name__ == "__main__":
    main()
