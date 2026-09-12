"""Bounded local decoding and optional acoustic classification."""
from pathlib import Path
import subprocess

import imageio_ffmpeg
import numpy as np
import soundfile as sf

MODEL_ID = "Gustking/wav2vec2-large-xlsr-deepfake-audio-classification"
RATE = 16000


def decode(source, destination):
    path = Path(source or "")
    if not path.is_file():
        raise ValueError("음성 파일을 업로드해 주세요.")
    if path.suffix.lower() not in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".webm", ".flac"}:
        raise ValueError("MP3, WAV, M4A, AAC, OGG, WebM, FLAC 파일을 사용해 주세요.")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("파일은 20MB 이하여야 합니다.")
    try:
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-v", "error", "-y",
                        "-protocol_whitelist", "file,pipe", "-i", str(path.resolve()),
                        "-t", "181", "-vn", "-ac", "1", "-ar", str(RATE),
                        "-c:a", "pcm_s16le", str(destination)],
                       capture_output=True, check=True, timeout=45,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        samples, rate = sf.read(destination, dtype="float32")
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        raise ValueError("음성을 읽지 못했습니다. 손상되지 않은 파일을 사용해 주세요.") from exc
    if not 1 <= len(samples) / rate <= 180:
        raise ValueError("1~180초 음성을 사용해 주세요.")
    if not np.isfinite(samples).all():
        raise ValueError("유효하지 않은 오디오입니다.")
    return samples, rate


class AcousticDetector:
    def __init__(self, predictor=None):
        self.predictor = predictor

    def analyze(self, samples, rate):
        chunks = []
        for start in range(0, len(samples), rate * 5):
            chunk = samples[start:start + rate * 5]
            if len(chunk) < rate or float(np.sqrt(np.mean(chunk ** 2))) < 0.003:
                continue
            if self.predictor is None:
                from transformers import pipeline
                self.predictor = pipeline("audio-classification", model=MODEL_ID,
                                          device=-1, trust_remote_code=False)
            predictions = self.predictor({"array": chunk, "sampling_rate": rate}, top_k=None)
            labels = {item["label"].lower(): float(item["score"]) for item in predictions}
            if set(labels) != {"real", "fake"} or not all(np.isfinite(v) and 0 <= v <= 1 for v in labels.values()):
                raise ValueError("모델 라벨 또는 점수를 확인할 수 없습니다.")
            chunks.append({"start_seconds": start / rate, "duration_seconds": len(chunk) / rate,
                           "fake_score": labels["fake"]})
        if not chunks:
            return {"status": "판단 보류", "fake_score": None, "chunks": [],
                    "coverage_seconds": 0, "skipped_seconds": len(samples) / rate,
                    "message": "분석 가능한 길이와 음량의 구간이 없습니다."}
        score = sum(c["fake_score"] * c["duration_seconds"] for c in chunks) / sum(c["duration_seconds"] for c in chunks)
        return {"status": "분석 완료", "model": MODEL_ID, "fake_score": score, "chunks": chunks,
                "coverage_seconds": sum(c["duration_seconds"] for c in chunks),
                "skipped_seconds": max(0.0, len(samples) / rate - sum(c["duration_seconds"] for c in chunks)),
                "message": "실험용 합성 클래스 점수이며 사기 확률이 아닙니다. 한국어·미학습 생성기·통화 환경 성능은 미검증입니다. 소리의 존재만 검사하며 사람의 발화 여부는 보장하지 않습니다."}
