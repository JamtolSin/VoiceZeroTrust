"""Offline smoke using the already downloaded official Qwen demonstration reference."""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]


def main():
    reference = ROOT / ".runtime/smoke-qwen/official-reference.wav"
    if not reference.is_file():
        raise SystemExit("First obtain the official reference with scripts/smoke_qwen.py, or use evaluate.py with your consented source manifest.")
    folder = ROOT / ".runtime/evaluation" / datetime.now().strftime("smoke-%Y%m%d-%H%M%S-%f")
    folder.mkdir(parents=True, exist_ok=False)
    mp3 = folder / "reference.mp3"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-v", "error", "-i", str(reference),
                    "-codec:a", "libmp3lame", "-b:a", "128k", str(mp3)], check=True, timeout=45,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    source = {"id": "official-demo", "path": "reference.mp3", "label": "real", "split": "smoke",
              "speaker_id": "qwen-official-demo", "consent": True,
              "rights": "Officially published voice-clone demonstration; local smoke only, not permission for corpus redistribution",
              "source": "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-TTS-Repo/clone.wav",
              "transcript": "Okay. Yeah. I resent you. I love you. I respect you. But you know what? You blew it! And thanks to you."}
    manifest = folder / "sources.jsonl"
    manifest.write_text(json.dumps(source) + "\n", encoding="utf-8")
    cli = ROOT / "scripts/evaluate.py"
    # Separate processes release synthesis GPU/RAM before loading the detector.
    subprocess.run([sys.executable, str(cli), "build", str(manifest), str(folder / "dataset"), "--accept-model-license"], check=True)
    subprocess.run([sys.executable, str(cli), "run", str(folder / "dataset/manifest.jsonl"), str(folder / "results"), "--split", "smoke"], check=True)
    print(f"REPORT: {folder / 'results/report.json'}", flush=True)


if __name__ == "__main__":
    main()
