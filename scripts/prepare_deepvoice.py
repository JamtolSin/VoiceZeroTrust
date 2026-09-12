"""Prepare a pinned public DeepVoice holdout; never fit or run a detector."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "SpeechAntiSpoofingBenchmarks/DeepVoice"
REVISION = "50b1b3b92f37dadcec3c4f0a1f9a9c3f577605d0"
SHARDS = {
    "test-00000-of-00002.parquet": (280822155, "d626dfb8daff4ecf525062281ec5e46ade829d66cebdfa22dc62ac4e5bac94c6"),
    "test-00001-of-00002.parquet": (269593868, "e70c8242f508c530013453c014e22cc8ecc5ebdb7c409958398a1168b3d9297e"),
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save_checked(path, data):
    """Do not overwrite an existing, different artifact."""
    if path.exists():
        if path.read_bytes() != data:
            raise RuntimeError(f"Existing artifact differs: {path}")
    else:
        path.write_bytes(data)


def download(session, url, target, size, sha):
    if not target.exists():
        partial = target.with_suffix(target.suffix + ".partial")
        print(f"Downloading {target.name}: {size:,} bytes", flush=True)
        with session.get(url, stream=True, timeout=(30, 120)) as response:
            response.raise_for_status()
            count = 0
            with partial.open("wb") as stream:
                for block in response.iter_content(1024 * 1024):
                    count += len(block)
                    if count > size:
                        raise RuntimeError("Download exceeded pinned size")
                    stream.write(block)
        if count != size or digest(partial) != sha:
            raise RuntimeError("Parquet integrity check failed")
        partial.replace(target)
    if target.stat().st_size != size or digest(target) != sha:
        raise RuntimeError("Cached parquet integrity check failed")


def main():
    import requests
    import pyarrow.parquet as pq

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".runtime/evaluation/deepvoice-holdout")
    args = parser.parse_args()
    folder = args.output.resolve()
    audio_dir = folder / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    base = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}"
    session = requests.Session()
    for name in ("README.md", "LICENSE.txt"):
        response = session.get(f"{base}/{name}", timeout=60)
        response.raise_for_status()
        if len(response.content) > 100000:
            raise RuntimeError("Unexpected provenance document size")
        save_checked(folder / name, response.content)
    if b"MIT License" not in (folder / "LICENSE.txt").read_bytes():
        raise RuntimeError("Unexpected dataset license")

    rows, raw_rows, seen = [], [], {}
    duplicates = []
    for name, (size, sha) in SHARDS.items():
        target = folder / name
        download(session, f"{base}/data/{name}", target, size, sha)
        for batch in pq.ParquetFile(target).iter_batches(batch_size=32):
            for item in batch.to_pylist():
                original = item["path"]
                label = {0: "real", 1: "synthetic"}[item["label"]]
                if original.startswith("REAL/") != (label == "real") or not original.startswith(("REAL/", "FAKE/")):
                    raise RuntimeError("Path contradicts label")
                notes = json.loads(item["notes"])
                index = len(rows)
                audio = item["audio"]["bytes"]
                checksum = hashlib.sha256(audio).hexdigest()
                destination = audio_dir / f"{index:05d}.flac"
                save_checked(destination, audio)
                stem = notes["source_stem"]
                # Conversion names encode source-to-target, not independent speakers.
                source_speaker, separator, target_speaker = stem.lower().partition("-to-")
                if not separator:
                    source_speaker = source_speaker.removesuffix("-original")
                row = {
                    "id": f"deepvoice-{index:05d}", "path": str(destination),
                    "label": label, "sha256": checksum, "split": "holdout",
                    "source": "DeepVoice/RVC" if label == "synthetic" else "DeepVoice/original",
                    "original_path": original, "source_group": stem,
                    "speaker_id": target_speaker if separator else source_speaker,
                    "source_speaker_id": source_speaker,
                    "grouping_basis": "filename-derived; not independently verified speaker identity",
                    "usage_basis": "publisher MIT license; individual speaker consent not independently verified",
                }
                if checksum in seen:
                    if seen[checksum]["label"] != label:
                        raise RuntimeError("Duplicate audio has conflicting labels")
                    duplicates.append({"id": row["id"], "duplicate_of": seen[checksum]["id"]})
                else:
                    seen[checksum] = row
                rows.append(row)
                raw_rows.append({"id": row["id"], "path": original, "label": item["label"],
                                 "notes": item["notes"], "audio": {"path": item["audio"]["path"],
                                 "bytes_length": len(audio), "sha256": checksum}})
        print(f"Prepared {len(rows):,} rows", flush=True)
    if len(rows) != 5053 or Counter(row["label"] for row in rows) != {"real": 628, "synthetic": 4425}:
        raise RuntimeError("Published dataset counts differ")
    for name, entries in (("manifest.jsonl", rows), ("manifest-unique.jsonl", list(seen.values())),
                          ("source-metadata.jsonl", raw_rows)):
        save_checked(folder / name, ("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in entries)).encode("utf-8"))
    config = {"dataset": REPO, "revision": REVISION, "license": "MIT", "language": "en",
              "original_source": "https://www.kaggle.com/datasets/birdy654/deep-voice-deepfake-voice-recognition",
              "paper": "https://arxiv.org/abs/2308.12734", "label_mapping": {"0": "real", "1": "synthetic"},
              "full_counts": dict(Counter(r["label"] for r in rows)),
              "unique_counts": dict(Counter(r["label"] for r in seen.values())),
              "duplicates": duplicates, "shards": SHARDS,
              "limitations": ["English; eight public figures; correlated fragments, not independent people",
                              "RVC conversions only; not phishing intent labels",
                              "No fitting or threshold selection permitted on this holdout",
                              "Model training overlap unknown; publisher license is not verified individual consent",
                              "Group identifiers inferred from source filenames; not a validated speaker-disjoint protocol"]}
    save_checked(folder / "config.json", (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"folder": str(folder), "rows": len(rows), "unique": len(seen),
                      "completed_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
