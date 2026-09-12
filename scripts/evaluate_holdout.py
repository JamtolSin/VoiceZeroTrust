"""One locked external evaluation; never change the selected policy from this output."""
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["HF_HOME"] = str(ROOT / ".runtime/detection/models")


def main():
    import numpy as np
    import torch
    from transformers import pipeline
    from src.detection.aasist import AASISTDetector, linear_score
    from src.detection.audio import AcousticDetector, decode, MODEL_ID
    from src.evaluation.metrics import summarize
    from src.evaluation.pipeline import write_json
    folder = ROOT / ".runtime/evaluation/detection-v2"
    selection_path = folder / "selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selection_sha = hashlib.sha256(selection_path.read_bytes()).hexdigest()
    source = ROOT / ".runtime/evaluation/deepvoice-holdout"
    rows = [json.loads(line) for line in (source / "manifest-unique.jsonl").read_text(encoding="utf-8").splitlines()]
    development_hashes = {r["sha256"] for r in json.loads((folder / "stafford-AASIST.json").read_text(encoding="utf-8"))}
    if any(row["sha256"] in development_hashes for row in rows):
        raise ValueError("Exact audio leakage from development to holdout")
    lock = {"selection_sha256": selection_sha, "manifest_sha256": hashlib.sha256((source / "manifest-unique.jsonl").read_bytes()).hexdigest(),
            "selected": selection["selected"], "thresholds": {name:p["threshold"] for name,p in selection["candidate_policies"].items()},
            "comparison": "Full external corpus, locked policies; no model reselection from this output"}
    lock_path = folder / "holdout-lock.json"
    if lock_path.exists() and json.loads(lock_path.read_text(encoding="utf-8")) != lock:
        raise ValueError("Holdout policy lock changed")
    write_json(lock_path, lock)
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    baseline = AcousticDetector(pipeline("audio-classification", model=MODEL_ID,
                 revision="f7050b586236dc910d1157f430def2d0647b02b4", device=0 if device != "cpu" else -1, trust_remote_code=False))
    models = {name:AASISTDetector(name,device=device) for name in ["AASIST", "AASIST-L"]}
    target = folder / "holdout-predictions.json"
    results = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
    if len(results) > len(rows):
        raise ValueError("Invalid checkpoint length")
    for i, result in enumerate(results):
        if result["sha256"] != rows[i]["sha256"]:
            raise ValueError("Holdout checkpoint mismatch")
    start = perf_counter()
    for row in rows[len(results):]:
        result = {key:row[key] for key in ["id", "label", "sha256", "source_speaker_id", "speaker_id", "source_group"]}
        result.update(scores={}, errors={}, elapsed_seconds={})
        try:
            if hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("Holdout audio changed")
            with TemporaryDirectory(dir=folder) as temporary:
                samples, rate = decode(row["path"], Path(temporary) / "input.wav")
            result["duration_seconds"] = len(samples)/rate
            tick = perf_counter()
            try:
                result["scores"]["xlsr"] = baseline.analyze(samples, rate)["fake_score"]
            except Exception as exc:
                result["errors"]["xlsr"] = type(exc).__name__
                result["scores"]["xlsr"] = None
            result["elapsed_seconds"]["xlsr"] = perf_counter() - tick
            for variant, model in models.items():
                tick = perf_counter()
                try:
                    if len(samples) < 16000 or float(np.sqrt(np.mean(samples[:64600]**2))) < .003:
                        result["scores"][variant] = result["scores"][variant+"-head"] = None
                    else:
                        features, score = model.features(samples)
                        result["scores"][variant] = score
                        result["scores"][variant+"-head"] = float(linear_score(features, selection["candidate_policies"][variant+"-head"]["head"]))
                except Exception as exc:
                    for name in [variant, variant+"-head"]:
                        result["errors"][name] = type(exc).__name__
                        result["scores"][name] = None
                result["elapsed_seconds"][variant] = perf_counter() - tick
        except Exception as exc:
            result["input_error"] = type(exc).__name__
            for name in selection["candidate_policies"]:
                result["scores"][name] = None
                result["errors"][name] = type(exc).__name__
        results.append(result)
        if len(results) % 100 == 0 or len(results) == len(rows):
            write_json(target, results)
            print(f"Holdout {len(results)}/{len(rows)} elapsed {perf_counter()-start:.1f}s", flush=True)
    report = {"lock":lock,"dataset":json.loads((source/"config.json").read_text(encoding="utf-8")), "candidates": {}}
    for name, policy in selection["candidate_policies"].items():
        metric_rows = [{"label":r["label"],"score":r["scores"][name],"error":r["errors"].get(name)} for r in results]
        report["candidates"][name] = {"at_validation_threshold":summarize(metric_rows,policy["threshold"]),"at_0.5":summarize(metric_rows)}
    selected_metrics = report["candidates"][selection["selected"]]["at_validation_threshold"]
    baseline_metrics = report["candidates"]["xlsr"]["at_0.5"]
    # Predeclared conservative promotion gate; failure is a research result, not hidden.
    report["promotion_gate"] = {"rule":"selected external FPR <= 5%, recall > baseline at 0.5, no inference errors, full coverage",
                                "passed": selected_metrics["fpr"] is not None and selected_metrics["fpr"] <= .05 and selected_metrics["recall"] > baseline_metrics["recall"] and selected_metrics["errors"] == 0 and selected_metrics["coverage"] == 1.0}
    write_json(folder / "holdout-report.json", report)
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__ == "__main__":
    main()
