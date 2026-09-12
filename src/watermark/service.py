"""Bounded file workflow for educational output tagging and detection."""
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import json
import math
import threading

import numpy as np
import soundfile as sf

from src.audio_io import prepare_audio
from .backend import AudioSealBackend, EDUCATION_TAG, SAMPLE_RATE

CAVEAT = "미검출은 진짜 음성이라는 뜻이 아닙니다. 표식은 신원·사기 여부를 증명하지 않으며 복제 후 보존도 보장하지 않습니다."


@dataclass(frozen=True)
class DetectionResult:
    score: float
    detected: bool
    education_tag_matches: bool
    decoded_tag: int | None
    threshold: float = 0.5
    caveat: str = CAVEAT

    def to_dict(self):
        return asdict(self)


class WatermarkService:
    def __init__(self, runtime: Path, backend=None):
        self.runtime = Path(runtime)
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.backend = backend if backend is not None else AudioSealBackend()
        self.lock = threading.Lock()

    def _detect(self, samples):
        score, tag = self.backend.detect(samples)
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("워터마크 모델이 유효하지 않은 점수를 반환했습니다.")
        detected = score >= 0.5
        return DetectionResult(score, detected, detected and tag == EDUCATION_TAG,
                               int(tag) if detected else None)

    def detect_file(self, source):
        if not source:
            raise ValueError("음성 파일을 넣어 주세요.")
        with self.lock, TemporaryDirectory(dir=self.runtime) as temp:
            decoded = Path(temp) / "input.wav"
            prepare_audio(source, decoded, SAMPLE_RATE)
            samples, _ = sf.read(decoded, dtype="float32")
            return self._detect(samples)

    def embed_file(self, source, confirmed=False):
        if not confirmed:
            raise ValueError("교육용 합성 결과물임을 확인해 주세요.")
        if not source:
            raise ValueError("음성 파일을 넣어 주세요.")
        with self.lock, TemporaryDirectory(dir=self.runtime) as temp:
            decoded = Path(temp) / "input.wav"
            duration = prepare_audio(source, decoded, SAMPLE_RATE)
            samples, _ = sf.read(decoded, dtype="float32")
            # Reserve modest headroom before embedding; never clip the watermark.
            peak = float(np.max(np.abs(samples)))
            if peak > 0.95:
                samples = samples * (0.95 / peak)
            output = np.asarray(self.backend.embed(samples), dtype=np.float32)
            if output.shape != samples.shape or not np.isfinite(output).all():
                raise ValueError("워터마크 모델이 유효하지 않은 오디오를 반환했습니다.")
            if float(np.max(np.abs(output))) >= 1:
                raise ValueError("워터마크 삽입 후 음량이 초과했습니다. 입력 음량을 낮춰 다시 시도하세요.")
            destination = self.runtime / f"education-{uuid4().hex}.wav"
            manifest = destination.with_suffix(".json")
            try:
                sf.write(destination, output, SAMPLE_RATE, subtype="PCM_16")
                # Verify the saved PCM, not merely the in-memory floating point result.
                saved, _ = sf.read(destination, dtype="float32")
                result = self._detect(saved)
                manifest.write_text(json.dumps({"purpose": "educational_generated_output",
                    "backend": "audioseal_wm_16bits", "duration_seconds": duration,
                    "public_tag": EDUCATION_TAG, "verification": result.to_dict()},
                    ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                destination.unlink(missing_ok=True)
                manifest.unlink(missing_ok=True)
                raise
            return str(destination), result
