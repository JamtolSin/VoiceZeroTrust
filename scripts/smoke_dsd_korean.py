"""Check released Korean profile through the app service, with WAV and MP3."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import imageio_ffmpeg
    from src.detection.profiles import build_profile
    from src.detection.service import DetectionService
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    data = args.data.resolve()
    predictions = json.loads((data / "experiment-v4/test-predictions.json").read_text(encoding="utf-8"))
    manifest = {r["sha256"]: r for r in map(json.loads, (data / "manifest.jsonl").read_text(encoding="utf-8").splitlines())}
    service = DetectionService(acoustic=build_profile("korean-research", device=args.device, allow_noncommercial=True),
                               workdir=ROOT / ".runtime/detection/smoke-requests")
    checks = []
    with TemporaryDirectory(dir=ROOT / ".runtime") as temporary:
        for label in ("real", "synthetic"):
            expected = next(r for r in predictions if r["condition"] == "original" and r["label"] == label
                            and r["scores"].get("v4") is not None and not r["errors"])
            path = Path(manifest[expected["sha256"]]["path"])
            result = service.analyze(path, enable_acoustic=True)["acoustic"]
            assert result["status"] == "분석 완료", result
            difference = abs(result["fake_score"] - expected["scores"]["v4"])
            assert difference < 1e-4, difference
            assert result["release"] == "v0.4.0-detection.1"
            assert result["promotion_passed"] is False
            mp3 = Path(temporary) / f"{label}.mp3"
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-v", "error", "-i", str(path),
                            "-codec:a", "libmp3lame", "-b:a", "128k", str(mp3)], check=True)
            compressed = service.analyze(mp3, enable_acoustic=True)["acoustic"]
            assert compressed["status"] == "분석 완료", compressed
            assert 0 <= compressed["fake_score"] <= 1
            checks.append({"label": label, "sha256": expected["sha256"], "wav_score": result["fake_score"],
                           "benchmark_difference": difference, "mp3_score": compressed["fake_score"],
                           "mp3_status": compressed["status"]})
    # Two functional smoke samples, not an additional performance estimate.
    print(json.dumps({"passed": True, "scope": "two-sample service smoke, not accuracy", "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
