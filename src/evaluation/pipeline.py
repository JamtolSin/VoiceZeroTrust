"""Build consented pairs and evaluate without equating synthesis with fraud."""
import hashlib
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import soundfile as sf

from src.audio_io import prepare_audio
from src.detection.audio import MODEL_ID
from src.detection.service import DetectionService
from src.service import DemoService, PHRASE
from .metrics import summarize


def collect_local(directory, output, *, consent=False, rights="", source=""):
    """Import speaker folders; transcripts come from same-stem UTF-8 .txt files."""
    if consent is not True or not rights.strip() or not source.strip():
        raise ValueError("Explicit consent, rights and source are required")
    directory, output = Path(directory).resolve(), Path(output).resolve()
    rows = []
    for speaker in sorted(directory.iterdir()):
        if not speaker.is_dir():
            continue
        # Stable speaker-level split, independent of file ordering or corpus size.
        split = "validation" if int(hashlib.sha256(speaker.name.encode()).hexdigest(), 16) % 5 == 0 else "test"
        for audio in sorted(speaker.iterdir()):
            if audio.suffix.lower() not in {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".webm"}:
                continue
            transcript = audio.with_suffix(".txt")
            if not transcript.is_file() or not transcript.read_text(encoding="utf-8-sig").strip():
                raise ValueError(f"Exact transcript .txt missing for {audio.name}")
            rows.append({"id": f"source-{len(rows):06d}", "path": str(audio.resolve()), "label": "real",
                         "speaker_id": speaker.name, "split": split, "consent": True, "rights": rights,
                         "source": source, "transcript": transcript.read_text(encoding="utf-8-sig").strip()})
    if not rows:
        raise ValueError("No audio found under speaker subfolders")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        handle.write("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    read_manifest(output)
    return output


def read_manifest(path):
    path = Path(path).resolve()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not rows:
        raise ValueError("Manifest is empty")
    ids, hashes, speakers = set(), {}, {}
    for row in rows:
        if not isinstance(row.get("id"), str) or not row["id"] or row["id"] in ids:
            raise ValueError("Each row needs a unique nonempty id")
        ids.add(row["id"])
        for key in ("speaker_id", "source", "rights"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f"Missing provenance: {key}")
        if row.get("consent") is not True or row.get("label") not in {"real", "synthetic"}:
            raise ValueError("Explicit consent and real/synthetic label required")
        if row.get("split") not in {"smoke", "validation", "test"}:
            raise ValueError("split must be smoke, validation or test")
        audio = (path.parent / row["path"]).resolve()
        if not audio.is_file() or audio.stat().st_size > 20 * 1024 * 1024:
            raise ValueError(f"Missing or oversized audio: {row['id']}")
        digest = hashlib.sha256(audio.read_bytes()).hexdigest()
        if row.get("sha256") and row["sha256"] != digest:
            raise ValueError("Audio checksum changed")
        if digest in hashes:
            raise ValueError("Duplicate audio would inflate evaluation")
        hashes[digest] = row["split"]
        if row["speaker_id"] in speakers and speakers[row["speaker_id"]] != row["split"]:
            raise ValueError("Speaker leakage across splits")
        speakers[row["speaker_id"]] = row["split"]
        row.update(path=str(audio), sha256=digest)
    return rows


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def build_pairs(manifest, output, engine, *, license_confirmed=False):
    sources = read_manifest(manifest)
    if not license_confirmed:
        raise ValueError("Confirm model license before generation")
    if any(r["label"] != "real" or not r.get("transcript", "").strip() for r in sources):
        raise ValueError("Pair sources must be real with exact reference transcript")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows, failures = [], []
    service = DemoService(engine, output / "requests")
    for index, source in enumerate(sources):
        try:
            print(f"Generating {index + 1}/{len(sources)}: {source['id']}", flush=True)
            result = service.generate_demo(source["path"], True, True, reference_text=source["transcript"])
            # Identical PCM sample rate/encoding on both labels avoids a codec-label shortcut.
            real = output / f"{index:06d}-real.wav"
            synthetic = output / f"{index:06d}-synthetic.wav"
            prepare_audio(source["path"], real, sample_rate=16000)
            with TemporaryDirectory(dir=output) as temporary:
                raw = Path(temporary) / "generated.wav"
                rate, samples = result.audio
                sf.write(raw, samples, rate)
                prepare_audio(raw, synthetic, sample_rate=16000)
            pair = []
            for label, audio in (("real", real), ("synthetic", synthetic)):
                pair.append({**source, "id": f"{index:06d}-{label}", "path": audio.name,
                             "label": label, "source_id": source["id"], "source_sha256": source["sha256"],
                             "sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
                             "generator": result.model if label == "synthetic" else None,
                             "transcript": PHRASE if label == "synthetic" else source["transcript"],
                             "content_matched": source["transcript"].strip() == PHRASE,
                             "fraud_intent": "not_labelled"})
            rows.extend(pair)
        except Exception as exc:
            failures.append({"id": source["id"], "error": f"{type(exc).__name__}: {exc}"})
        # Checkpoint after each source; failed pairs never enter the labelled manifest.
        (output / "manifest.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        write_json(output / "build.json", {"requested": len(sources), "completed_pairs": len(rows)//2, "failures": failures})
    return output / "manifest.jsonl", failures


def evaluate(manifest, output, *, threshold=0.5, split="test", service=None):
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Threshold must be finite and between 0 and 1")
    sources = read_manifest(manifest)
    selected = [r for r in sources if r["split"] == split]
    if not selected:
        raise ValueError(f"No rows for split {split}")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    service = service or DetectionService(workdir=output / "requests")
    rows = []
    for source in selected:
        start = perf_counter()
        row = {**source, "score": None, "prediction": "abstain", "correct": None, "ox": "보류", "error": None}
        try:
            result = service.analyze(source["path"], enable_acoustic=True)
            score = result["acoustic"]["fake_score"]
            if score is not None:
                if not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("Invalid model score")
                prediction = "synthetic" if score >= threshold else "real"
                row.update(score=score, prediction=prediction, correct=prediction == source["label"],
                           ox="O" if prediction == source["label"] else "X")
            elif result["acoustic"]["status"] == "사용 불가":
                row["error"] = result["acoustic"].get("message", "Detector unavailable")
            row["details"] = result["acoustic"]
            row["duration_seconds"] = result["audio"]["duration_seconds"]
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        row["elapsed_seconds"] = perf_counter() - start
        rows.append(row)
        print(f"{source['id']}: {row['ox']} ({row['prediction']}, score={row['score']})", flush=True)
        write_json(output / "predictions.json", rows)
    report = {"task": "synthetic_audio_not_fraud", "model": MODEL_ID, "threshold": threshold,
              "split": split, "pipeline_ok": all(r["error"] is None for r in rows),
              "all_classified": all(r["score"] is not None for r in rows),
              "errors": sum(r["error"] is not None for r in rows), "metrics": summarize(rows, threshold),
              "by_label": {label: summarize([r for r in rows if r["label"] == label], threshold)
                           for label in ("real", "synthetic")},
              "warnings": ["Synthetic is not synonymous with phishing.", "Threshold is not calibrated; never tune on test results.",
                           "Smoke tests do not establish general accuracy. Report speaker/model/language diversity.",
                           "Pairs may differ in spoken content, language and duration. Use matched educational readings for controlled tests."]}
    write_json(output / "report.json", report)
    return report
