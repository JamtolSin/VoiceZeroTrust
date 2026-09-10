"""Bounded decoding of local recordings; never modifies the original file."""
from pathlib import Path
import subprocess

import imageio_ffmpeg
import numpy as np
import soundfile as sf


def prepare_audio(source: str, destination: Path, sample_rate: int = 22050) -> float:
    path = Path(source)
    if not path.is_file():
        raise ValueError("업로드 파일이 없거나 만료되었습니다. 파일을 다시 넣어 주세요.")
    if path.suffix.lower() not in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".webm", ".flac"}:
        raise ValueError(f"지원하지 않는 확장자입니다: {path.suffix or '(없음)'}. MP3, WAV, M4A, AAC, OGG, WebM, FLAC을 넣어 주세요.")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("파일은 20MB 이하여야 합니다.")
    try:
        subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-v", "error", "-y",
             "-protocol_whitelist", "file,pipe", "-i", str(path.resolve()),
             "-t", "31", "-vn", "-ac", "1", "-ar", str(sample_rate),
             "-c:a", "pcm_s16le", str(destination)],
            capture_output=True, timeout=30, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise ValueError("음성을 디코딩하지 못했습니다. 손상되지 않은 오디오 파일을 다시 넣어 주세요.") from exc
    samples, rate = sf.read(destination, dtype="float32")
    duration = len(samples) / rate
    if not 2 <= duration <= 30:
        raise ValueError("2~30초 음성을 사용해 주세요. 첫 시도는 6~10초를 권장합니다.")
    if not np.isfinite(samples).all() or np.sqrt(np.mean(samples ** 2)) < 0.003:
        raise ValueError("음성이 없거나 너무 작습니다. 마이크 가까이에서 다시 녹음해 주세요.")
    return duration
