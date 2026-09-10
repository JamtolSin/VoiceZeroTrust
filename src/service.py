from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from time import perf_counter

import numpy as np
import soundfile as sf

from src.audio_io import prepare_audio

PHRASE = "이 음성은 인공지능으로 생성된 보안 교육용 합성 음성입니다. 목소리만으로 상대방의 신원을 판단하지 마세요."


@dataclass
class GenerationResult:
    audio: tuple[int, np.ndarray]
    input_seconds: float
    elapsed_seconds: float
    model: str


class DemoService:
    def __init__(self, engine, workdir: Path):
        self.engine = engine
        self.workdir = workdir
        self._lock = Lock()

    def generate_demo(self, reference_audio_path, consent_confirmed,
                      license_confirmed, phrase_id="security_notice", reference_text=""):
        if consent_confirmed is not True:
            raise ValueError("음성 사용 동의를 확인해 주세요.")
        if license_confirmed is not True:
            raise ValueError("모델 이용 조건을 확인하고 동의해 주세요.")
        if phrase_id != "security_notice":
            raise ValueError("지원하지 않는 교육 문장입니다.")
        if not reference_audio_path:
            raise ValueError("파일을 넣거나 마이크로 녹음해 주세요.")
        if getattr(self.engine, "requires_transcript", False) and not reference_text.strip():
            raise ValueError("녹음에서 실제로 말한 내용을 입력해 주세요.")
        if len(reference_text) > 1000:
            raise ValueError("참조 대사는 1,000자 이하여야 합니다.")
        with self._lock:
            start = perf_counter()
            self.workdir.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix="request-", dir=self.workdir) as folder:
                reference = Path(folder) / "reference.wav"
                output = Path(folder) / "generated.wav"
                duration = prepare_audio(reference_audio_path, reference,
                                         getattr(self.engine, "sample_rate", 22050))
                self.engine.synthesize(reference, PHRASE, output, reference_text=reference_text)
                samples, rate = sf.read(output, dtype="float32")
                if not len(samples) or not np.isfinite(samples).all():
                    raise RuntimeError("모델이 유효한 음성을 생성하지 못했습니다.")
                return GenerationResult((rate, samples), duration,
                                        perf_counter() - start, self.engine.name)
