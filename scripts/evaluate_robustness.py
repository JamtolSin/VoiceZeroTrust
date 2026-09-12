"""Predefined stratified external subset, not a new independent corpus."""
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["HF_HOME"] = str(ROOT / ".runtime/detection/models")


def main():
    import numpy as np
    from scipy.signal import resample_poly
    import torch
    from transformers import pipeline
    from src.detection.aasist import AASISTDetector
    from src.detection.audio import AcousticDetector, decode, MODEL_ID
    from src.evaluation.metrics import summarize
    from src.evaluation.pipeline import write_json
    folder = ROOT / ".runtime/evaluation/detection-v2"
    selection = json.loads((folder / "selection.json").read_text(encoding="utf-8"))
    policy = selection["policy"]
    source = ROOT / ".runtime/evaluation/deepvoice-holdout/manifest-unique.jsonl"
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    groups = {}
    for row in rows:
        groups.setdefault((row["source_speaker_id"],row["label"]),[]).append(row)
    subset = [r for group in sorted(groups) for r in sorted(groups[group],key=lambda r:r["sha256"])[:8]]
    spec = {"selection_sha256":hashlib.sha256((folder/"selection.json").read_bytes()).hexdigest(),
            "subset_ids":[r["id"] for r in subset],"selection":"first 8 SHA-sorted clips per source-speaker x label; no scores used",
            "conditions":["original","first-2s","first-3s","first-5s","8khz-roundtrip"],
            "short_input":"skip condition if actual clip shorter than requested; never pad to fake eligibility"}
    write_json(folder/"robustness-spec.json",spec)
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    baseline = AcousticDetector(pipeline("audio-classification",model=MODEL_ID,revision="f7050b586236dc910d1157f430def2d0647b02b4",device=0 if device != "cpu" else -1,trust_remote_code=False))
    selected = baseline if policy["kind"] == "xlsr" else AASISTDetector(policy["variant"],device=device,head=policy.get("head"))
    results=[]
    for i,row in enumerate(subset):
        with TemporaryDirectory(dir=folder) as temporary:
            samples,rate=decode(row["path"],Path(temporary)/"input.wav")
        for condition in spec["conditions"]:
            record={"id":row["id"],"label":row["label"],"source_speaker_id":row["source_speaker_id"],"condition":condition,"scores":{},"errors":{}}
            transformed=samples
            if condition.startswith("first-"):
                duration=int(condition.split("-")[1][:-1])
                if len(samples)<duration*rate:
                    record["skipped"]="input_too_short"
                    results.append(record)
                    continue
                transformed=samples[:duration*rate]
            elif condition=="8khz-roundtrip":
                transformed=resample_poly(resample_poly(samples,1,2),2,1).astype(np.float32)
            for name,detector in [("baseline",baseline),("selected",selected)]:
                try:
                    record["scores"][name]=detector.analyze(transformed,rate)["fake_score"]
                except Exception as exc:
                    record["scores"][name]=None
                    record["errors"][name]=type(exc).__name__
            results.append(record)
        if (i+1)%16==0 or i+1==len(subset):
            write_json(folder/"robustness-predictions.json",results)
            print(f"Robustness {i+1}/{len(subset)}",flush=True)
    report={"spec":spec,"conditions":{}}
    for condition in spec["conditions"]:
        eligible=[r for r in results if r["condition"]==condition and not r.get("skipped")]
        report["conditions"][condition]={"eligible":len(eligible),"skipped":len(subset)-len(eligible),
            **{name:summarize([{"label":r["label"],"score":r["scores"][name],"error":r["errors"].get(name)} for r in eligible],threshold)
               for name,threshold in [("baseline",.5),("selected",policy["threshold"])]}}
    write_json(folder/"robustness-report.json",report)
    print(json.dumps(report["conditions"],indent=2),flush=True)


if __name__=="__main__":
    main()
