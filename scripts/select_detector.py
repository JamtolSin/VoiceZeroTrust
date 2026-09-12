"""Fit lightweight frozen-feature heads on development train; lock on validation."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def split_groups(original):
    """Conservatively join same numeric source IDs and byte-identical files."""
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]
    seen = {}
    for row in original:
        group = row["original_path"].split("_")[1]
        find(group)
        if row["sha256"] in seen:
            parent[find(group)] = find(seen[row["sha256"]])
        seen[row["sha256"]] = group
    return {r["sha256"]: find(r["original_path"].split("_")[1]) for r in original}


def choose_threshold(scores, labels, max_fpr=.05):
    import numpy as np
    scores, labels = np.asarray(scores), np.asarray(labels)
    if scores.ndim != 1 or scores.shape != labels.shape or not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1)):
        raise ValueError("Invalid validation scores")
    if not np.isfinite(max_fpr) or not 0 <= max_fpr <= 1 or not np.isin(labels, [0, 1]).all():
        raise ValueError("Invalid FPR cap or labels")
    real = scores[labels == 0]
    if not len(real) or not np.any(labels == 1):
        raise ValueError("Validation needs both labels")
    # Lowest representable threshold meeting the empirical validation FPR cap.
    options = sorted(set([0., 1.] + scores.tolist() + np.nextafter(scores, np.inf).tolist()))
    for threshold in options:
        if threshold <= 1 and np.mean(real >= threshold) <= max_fpr:
            return float(threshold)
    raise ValueError("No valid threshold")


def main():
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score
    from src.evaluation.metrics import summarize
    from src.evaluation.pipeline import write_json
    from src.detection.aasist import linear_score
    folder = ROOT / ".runtime/evaluation/detection-v2"
    selection_path = folder / "selection.json"
    if selection_path.exists():
        raise RuntimeError("Selection is frozen. Do not refit after viewing holdout.")
    original = json.loads((ROOT / ".runtime/evaluation/public-stafford-v4/predictions.json").read_text(encoding="utf-8"))
    data = {name: json.loads((folder / f"stafford-{name}.json").read_text(encoding="utf-8")) for name in ["AASIST", "AASIST-L"]}
    rows = data["AASIST"]
    if [r["sha256"] for r in rows] != [r["sha256"] for r in data["AASIST-L"]]:
        raise ValueError("Candidate row mismatch")
    groups = split_groups(original)
    validation = np.array([int(hashlib.sha256(("vzt-v2-20260912:" + groups[r["sha256"]]).encode()).hexdigest(), 16) % 10 < 3 for r in rows])
    train = ~validation
    y = np.array([r["label"] == "synthetic" for r in rows], dtype=int)
    if len(set(y[train])) != 2 or len(set(y[validation])) != 2:
        raise ValueError("Both labels required in each split")
    candidates = {"xlsr": {"scores": np.array([r["xlsr"] for r in rows]), "kind": "xlsr"}}
    for variant in data:
        candidates[variant] = {"scores": np.array([r["score"] for r in data[variant]]), "kind": "aasist", "variant": variant}
        x = np.array([r["features"] for r in data[variant]])
        scaler = StandardScaler().fit(x[train])
        model = LogisticRegression(C=1., class_weight="balanced", random_state=0, solver="liblinear", max_iter=2000).fit(scaler.transform(x[train]), y[train])
        head = {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(), "coef": model.coef_[0].tolist(), "intercept": float(model.intercept_[0])}
        candidates[f"{variant}-head"] = {"scores": linear_score(x, head), "kind": "aasist", "variant": variant, "head": head}
    reports = {}
    for name, candidate in candidates.items():
        try:
            threshold = choose_threshold(candidate["scores"][validation], y[validation])
            eligible = True
        except ValueError:
            threshold, eligible = 1.0, False
        metrics = summarize([{"label": row["label"], "score": float(score)} for row, score, selected in zip(rows, candidate["scores"], validation) if selected], threshold)
        candidate["threshold"] = threshold
        reports[name] = {"eligible": eligible, "validation": metrics, "validation_auc": float(roc_auc_score(y[validation], candidate["scores"][validation])),
                         "all_development_at_0.5": summarize([{"label": r["label"], "score": float(s)} for r, s in zip(rows, candidate["scores"])])}
    # Selection rule fixed before scoring DeepVoice: max recall at validation FPR <=5%, AUC tie-break.
    selected = max([name for name in reports if reports[name]["eligible"]], key=lambda name: (reports[name]["validation"]["recall"], reports[name]["validation_auc"]))
    record = {"selected": selected, "policy": {key:value for key,value in candidates[selected].items() if key != "scores"},
              "candidate_policies": {name:{key:value for key,value in candidate.items() if key != "scores"} for name,candidate in candidates.items()},
              "selection_rule": "maximize validation recall under empirical FPR <= 0.05; AUC tie-break; no holdout access",
              "development": "Stafford v4 previously inspected benchmark, NOT fresh test", "reports": reports,
              "split_counts": {"train": int(sum(train)), "validation": int(sum(validation)),
                               "train_groups": len({groups[r['sha256']] for r, flag in zip(rows, train) if flag}),
                               "validation_groups": len({groups[r['sha256']] for r, flag in zip(rows, validation) if flag})},
              "grouping_limit": "Numeric source IDs conservatively joined across platforms and duplicate hashes; actual speaker/text identity unavailable",
              "training": "Only StandardScaler + L2 logistic head fit on frozen official AASIST embeddings. No encoder training or Korean adaptation.",
              "pending_holdout": "DeepVoice 50b1b3b92f37dadcec3c4f0a1f9a9c3f577605d0"}
    write_json(folder / "development-split.json", [{"sha256": r["sha256"], "group":groups[r["sha256"]], "split":"validation" if flag else "train"} for r,flag in zip(rows,validation)])
    write_json(selection_path, record)
    print(json.dumps({"selected":selected,"split_counts":record["split_counts"],"reports":reports}, indent=2), flush=True)


if __name__ == "__main__":
    main()
