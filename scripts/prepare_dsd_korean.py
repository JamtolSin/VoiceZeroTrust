"""Safely extract eligible Korean ZIP members and lock source-group splits."""
import bisect
from collections import Counter, defaultdict
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import struct
import sys
import zipfile
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_dsd import PARTS, json_once, verify_part, write_once


class SplitFile(io.RawIOBase):
    def __init__(self, paths):
        self.paths = paths
        self.bounds = [0]
        for path in paths:
            self.bounds.append(self.bounds[-1] + path.stat().st_size)
        self.position = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        position = offset + (self.position if whence == 1 else self.bounds[-1] if whence == 2 else 0)
        if whence not in (0, 1, 2) or position < 0:
            raise ValueError("Invalid seek")
        self.position = position
        return position

    def read(self, size=-1):
        size = max(0, self.bounds[-1] - self.position) if size < 0 else min(size, max(0, self.bounds[-1] - self.position))
        result = bytearray()
        while size:
            i = bisect.bisect_right(self.bounds, self.position) - 1
            count = min(size, self.bounds[i + 1] - self.position)
            with self.paths[i].open("rb") as stream:
                stream.seek(self.position - self.bounds[i])
                block = stream.read(count)
            if len(block) != count:
                raise ValueError("Truncated split file")
            result.extend(block)
            self.position += count
            size -= count
        return bytes(result)


class SliceFile(io.RawIOBase):
    def __init__(self, parent, offset, size):
        self.parent, self.offset, self.size, self.position = parent, offset, size, 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        position = offset + (self.position if whence == 1 else self.size if whence == 2 else 0)
        if whence not in (0, 1, 2) or position < 0:
            raise ValueError("Invalid seek")
        self.position = position
        return position

    def read(self, size=-1):
        size = max(0, self.size - self.position) if size < 0 else min(size, max(0, self.size - self.position))
        self.parent.seek(self.offset + self.position)
        result = self.parent.read(size)
        self.position += len(result)
        return result


def stored_inner(outer, stream):
    members = outer.infolist()
    if len(members) != 1 or members[0].filename != "wavs.zip" or members[0].compress_type != zipfile.ZIP_STORED:
        raise ValueError("Unexpected outer archive layout")
    member = members[0]
    stream.seek(member.header_offset)
    header = stream.read(30)
    if header[:4] != b"PK\x03\x04":
        raise ValueError("Invalid local ZIP header")
    name_len, extra_len = struct.unpack_from("<HH", header, 26)
    return SliceFile(stream, member.header_offset + 30 + name_len + extra_len, member.file_size)


def assign_groups(rows):
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]
    seen = {}
    for row in rows:
        group = "speaker:" + row["speaker_id"] if row["source"] in ("AIHUB", "VITS-AIHUB") else "generator:" + row["source"]
        if row["source"] in ("AIHUB", "VITS-AIHUB") and row["speaker_id"] in ("", "-", "unknown", "Unknown"):
            raise ValueError("Core source missing speaker identifier")
        row["source_group"] = group
        find(group)
        for key in ("sha256", "pcm_sha256"):
            identity = (key, row[key])
            if identity in seen:
                other = seen[identity]
                if other["label"] != row["label"]:
                    raise ValueError("Duplicate audio label conflict")
                parent[find(group)] = find(other["source_group"])
            seen[identity] = row
    components = defaultdict(list)
    for group in parent:
        components[find(group)].append(group)
    for row in rows:
        names = sorted(components[find(row["source_group"])])
        row["group"] = hashlib.sha256("|".join(names).encode()).hexdigest()
        bucket = int(hashlib.sha256(("vzt-ko-v4-20260913:" + row["group"]).encode()).hexdigest(), 16) % 100
        row["split"] = "test" if any(n.startswith("generator:") for n in names) else "train" if bucket < 70 else "calibration" if bucket < 85 else "test"
    return rows


def archive_filename(meta):
    """Documented publisher typo: all 100 Korean MeloTTS IDs match MellowTTS."""
    name = meta["filename"]
    if meta["source"] == "MeloTTS" and name.startswith("MeloTTS_"):
        return name.replace("MeloTTS_", "MellowTTS_", 1)
    return name


def main():
    import argparse
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    from math import gcd
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    folder = args.root.resolve()
    output = folder / "korean-v4"
    output.mkdir(exist_ok=True)
    if (output / "split-lock.json").exists():
        raise RuntimeError("Korean split already frozen")
    parts = [folder / f"wavs_2.zip.{i:03d}" for i in range(1, 10)]
    for path, (size, md5) in zip(parts, PARTS):
        verify_part(path, size, md5)
    metadata = [json.loads(line) for line in (folder / "korean-candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    stream = SplitFile(parts)
    with zipfile.ZipFile(stream) as outer, zipfile.ZipFile(stored_inner(outer, stream)) as archive:
        members = defaultdict(list)
        for member in archive.infolist():
            name = PurePosixPath(member.filename.replace("\\", "/"))
            if name.is_absolute() or ".." in name.parts or ":" in str(name):
                raise ValueError("Unsafe archive member")
            if not member.is_dir():
                members[name.name].append(member)
        json_once(output / "archive-layout.json", {"members": len(archive.infolist()), "sample_names": [m.filename for m in archive.infolist()[:25]]})
        required = sum(m.file_size for r in metadata if not r["eligibility"].startswith("excluded") for m in members[archive_filename(r)])
        if required + 10 * 1024**3 > shutil.disk_usage(output).free:
            raise RuntimeError("Insufficient extraction space with reserve")
        rows, excluded = [], []
        audio_dir = output / "audio"
        audio_dir.mkdir(exist_ok=True)
        for i, meta in enumerate(metadata):
            if meta["eligibility"].startswith("excluded"):
                excluded.append({"filename": meta["filename"], "reason": meta["eligibility"]})
                continue
            matches = members[archive_filename(meta)]
            if len(matches) != 1:
                excluded.append({"filename": meta["filename"], "reason": "ambiguous_or_missing_member", "matches": len(matches)})
                continue
            member = matches[0]
            if member.file_size > 20 * 1024**2:
                excluded.append({"filename": meta["filename"], "reason": "oversized"})
                continue
            try:
                blob = archive.read(member)  # ZIP CRC checked before use.
                info = sf.info(io.BytesIO(blob))
                if not 1 <= info.duration <= 180 or not 1 <= info.channels <= 8:
                    raise ValueError("invalid_audio_header")
                samples, rate = sf.read(io.BytesIO(blob), dtype="float32", always_2d=True)
                if not len(samples) or not np.isfinite(samples).all() or not 1 <= len(samples) / rate <= 180:
                    raise ValueError("invalid_audio_duration_or_samples")
                mono = samples.mean(axis=1)
                divisor = gcd(rate, 16000)
                pcm = resample_poly(mono, 16000 // divisor, rate // divisor).astype("<f4") if rate != 16000 else mono.astype("<f4")
                sha = hashlib.sha256(blob).hexdigest()
                path = audio_dir / (sha + ".wav")
                write_once(path, blob)
                rows.append({**meta, "id": f"dsd-ko-{i:05d}", "path": str(path), "sha256": sha,
                             "pcm_sha256": hashlib.sha256(pcm.tobytes()).hexdigest(), "sample_rate": rate,
                             "channels": samples.shape[1], "duration": len(samples) / rate, "archive_member": member.filename})
            except (ValueError, RuntimeError, zipfile.BadZipFile) as exc:
                excluded.append({"filename": meta["filename"], "reason": type(exc).__name__ + ":" + str(exc)[:100]})
            if (i + 1) % 1000 == 0:
                print(f"Validated {i + 1}/{len(metadata)} metadata rows", flush=True)
    rows = assign_groups(rows)
    unique = {}
    for row in rows:
        unique.setdefault(row["pcm_sha256"], row)
    for split_name in ("train", "calibration", "test"):
        if {r["label"] for r in unique.values() if r["split"] == split_name} != {"real", "synthetic"}:
            raise RuntimeError("Each locked split must contain both classes")
    manifest = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in unique.values()).encode("utf-8")
    write_once(output / "manifest.jsonl", manifest)
    json_once(output / "excluded.json", excluded)
    lock = {"manifest_sha256": hashlib.sha256(manifest).hexdigest(), "counts": dict(Counter(r["split"] + "/" + r["label"] for r in unique.values())),
            "source_counts": dict(Counter(r["source"] for r in unique.values())), "decoded": len(rows), "unique": len(unique),
            "duplicate_pcm": len(rows) - len(unique), "excluded": len(excluded),
            "split_rule": "core speaker + byte/PCM duplicate connected groups; seeded 70/15/15; other generators entirely test",
            "filename_alias": "MeloTTS_ -> MellowTTS_ for MeloTTS source only; numeric IDs preserved (100 Korean entries)",
            "limitations": ["Source speaker IDs not independently verified", "Text lineage unavailable; no text-disjoint claim", "Noncommercial research only", "SNS excluded", "Model pretraining overlap unknown"]}
    json_once(output / "split-lock.json", lock)
    print(json.dumps(lock, indent=2), flush=True)


if __name__ == "__main__":
    main()
