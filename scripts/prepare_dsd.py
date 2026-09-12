"""Audit pinned DSD metadata; optionally download verified research archives.

Audio extraction, fitting, and scoring are deliberately separate stages.
"""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]
METADATA_URL = "https://drive.google.com/uc?export=download&id=1l2iywJJBYh1RI5mW_KQ5xkB_9jLsC_IC"
METADATA_SHA256 = "b12780397d0066a8023c89814b83310761dff392f968fcd1c1672f0a132ce44d"
PARTS = [
    (2097152000, "b8d130222b1d90d1d14abaa837f0a938"),
    (2097152000, "a560f4477bc1453c69240185fb6c7c5e"),
    (2097152000, "26007fd8db7163cf1a46d40e69d67cf1"),
    (2097152000, "b0c756ba93bfada57c1a2f3a42c58c71"),
    (2097152000, "c2609054762b47a2a51ea8aeb29764c7"),
    (2097152000, "2bdd9531a6c1ae2c20d3291b07c687c5"),
    (2097152000, "37a14ae75b33f9111f3f20ea1660d219"),
    (2097152000, "d9e817baaf75e42debd9ece5b116a6fa"),
    (634458079, "8848db5f75c47bd23d0714ebe217b279"),
]


def write_once(path, content):
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"Existing artifact differs: {path.name}")
    else:
        with path.open("xb") as stream:
            stream.write(content)


def json_once(path, value):
    write_once(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def audit_metadata(content):
    if hashlib.sha256(content).hexdigest() != METADATA_SHA256:
        raise ValueError("Official metadata checksum changed")
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    korean = [r for r in rows if r["Language"].strip().lower() == "korean"]
    labels = Counter(r["label"] for r in korean)
    if len(rows) != 92385 or labels != {"bonafide": 17263, "spoof": 12165}:
        raise ValueError("Unexpected pinned population")
    speakers = {s: {r["Speaker name"] for r in korean if r["subset"] == s and r["Speaker name"] not in ("", "-", "Unknown", "unknown")} for s in ("train", "dev", "eval")}
    report = {
        "dataset": "DSD-Corpus v1", "record": "https://zenodo.org/records/13788455",
        "license": "CC-BY-NC-4.0", "permitted_project_scope": "noncommercial research/evaluation only; user approved 2026-09-12",
        "metadata_sha256": METADATA_SHA256, "total_metadata_rows": len(rows),
        "korean_metadata_rows": len(korean), "korean_labels": dict(labels),
        "published_split_labels": dict(Counter(r["subset"] + "/" + r["label"] for r in korean)),
        "source_groups": dict(Counter(r["group"] for r in korean)),
        "speaker_identifier_overlaps": {a + "/" + b: len(speakers[a] & speakers[b]) for a, b in (("train", "dev"), ("train", "eval"), ("dev", "eval"))},
        "limitations": ["Metadata counts only; no decoded audio verification",
                        "Speaker strings are not independently verified identities",
                        "Do not treat publisher splits as speaker-disjoint",
                        "SNS sources excluded pending source-rights review",
                        "No permission inferred for new voice cloning or commercial use",
                        "No model fitted or scored; no test split locked yet"],
    }
    candidates = [{"filename": r["Utterence name (file name)"], "label": {"bonafide": "real", "spoof": "synthetic"}[r["label"]],
                   "source": r["group"], "speaker_id": r["Speaker name"], "publisher_split": r["subset"],
                   "split": "unassigned", "duration_metadata": r["duration"],
                   "eligibility": "excluded_source_rights" if r["group"].startswith("SNS") else "pending_audio_and_lineage_validation"} for r in korean]
    report["candidate_eligibility"] = dict(Counter(r["eligibility"] for r in candidates))
    return report, candidates


def check_download_space(folder, reserve_bytes=40 * 1024**3):
    """Keep conservative extraction headroom; this is not an exact size claim."""
    remaining = sum(size for i, (size, _) in enumerate(PARTS, 1) if not (folder / f"wavs_2.zip.{i:03d}").exists())
    free = shutil.disk_usage(folder).free
    if free < remaining + reserve_bytes:
        raise RuntimeError(f"Insufficient space: free={free:,}; archive bytes plus reserved extraction space={remaining + reserve_bytes:,}")


def verify_part(path, size, md5):
    if path.stat().st_size != size:
        raise ValueError("Archive size mismatch")
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "md5").hexdigest()
    if actual != md5:
        raise ValueError("Publisher archive MD5 mismatch")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download_ranges(session, url, partial, size, chunk_size=8 * 1024**2):
    """Resume bounded ranges; validate response before appending any bytes."""
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > size:
        raise ValueError("Partial file exceeds expected size")
    while offset < size:
        end = min(size - 1, offset + chunk_size - 1)
        for attempt in range(4):
            try:
                with session.get(url, headers={"Range": f"bytes={offset}-{end}"}, stream=True, timeout=(30, 40)) as response:
                    response.raise_for_status()
                    if response.status_code != 206 or response.headers.get("Content-Range") != f"bytes {offset}-{end}/{size}":
                        raise ValueError("Server did not honor exact download range")
                    content = bytearray()
                    for block in response.iter_content(64 * 1024):
                        content.extend(block)
                        if len(content) > end - offset + 1:
                            raise ValueError("Range response too large")
                    if len(content) != end - offset + 1:
                        raise ValueError("Truncated range response")
                break
            except (OSError, ValueError):
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        # Reject concurrently changed partials; never silently overwrite.
        with partial.open("ab") as stream:
            if stream.tell() != offset:
                raise ValueError("Partial file changed during download")
            stream.write(content)
        offset = end + 1
        if offset == size or offset // (128 * 1024**2) != (offset - len(content)) // (128 * 1024**2):
            print(f"{partial.name}: {offset:,}/{size:,} bytes", flush=True)


def main():
    import requests
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".runtime/evaluation/dsd-corpus-v1")
    parser.add_argument("--download-audio", action="store_true")
    parser.add_argument("--noncommercial-research", action="store_true", required=True)
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    meta = folder / "DSD_corpus_v1.csv"
    if meta.exists():
        content = meta.read_bytes()
    else:
        with session.get(METADATA_URL, stream=True, timeout=(30, 60)) as response:
            response.raise_for_status()
            content = bytearray()
            for block in response.iter_content(1024 * 1024):
                content.extend(block)
                if len(content) > 20_000_000:
                    raise ValueError("Metadata exceeds expected size")
        content = bytes(content)
    report, candidates = audit_metadata(content)
    write_once(meta, content)
    json_once(folder / "metadata-audit.json", report)
    write_once(folder / "korean-candidates.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in candidates).encode("utf-8"))
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if not args.download_audio:
        return
    check_download_space(folder)
    def fetch_part(item):
        i, (size, md5) = item
        part_session = requests.Session()
        name = f"wavs_2.zip.{i:03d}"
        target = folder / name
        if not target.exists():
            partial = folder / (name + ".partial")
            download_ranges(part_session, f"https://zenodo.org/records/13788455/files/{name}?download=1", partial, size)
            verify_part(partial, size, md5)
            partial.rename(target)
        sha = verify_part(target, size, md5)
        part_session.close()
        print(f"Verified part {i}/{len(PARTS)}", flush=True)
        return {"file": name, "size": size, "publisher_md5": md5, "sha256": sha}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as executor:
        receipts = list(executor.map(fetch_part, enumerate(PARTS, 1)))
    json_once(folder / "download-receipts.json", receipts)


if __name__ == "__main__":
    main()
