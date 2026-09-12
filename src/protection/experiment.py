"""Bounded AudioSeal robustness trials with matched unmarked controls."""
from importlib.metadata import version
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import imageio_ffmpeg
import numpy as np
import soundfile as sf

from src.audio_io import prepare_audio

RATE = 16000


class AudioSealBackend:
    def __init__(self):
        self.generator = self.detector = None

    def _load(self):
        if self.generator is None:
            try:
                from audioseal import AudioSeal
            except ImportError as exc:
                raise ValueError("AudioSeal이 필요합니다. pip install 'audioseal>=0.2,<0.3'") from exc
            generator = AudioSeal.load_generator("audioseal_wm_16bits").cpu().eval()
            detector = AudioSeal.load_detector("audioseal_detector_16bits").cpu().eval()
            self.generator, self.detector = generator, detector

    def metadata(self):
        self._load()
        return {"package": "audioseal", "version": version("audioseal"),
                "generator": "audioseal_wm_16bits", "detector": "audioseal_detector_16bits",
                "device": "cpu"}

    def mark(self, samples):
        import torch
        self._load()
        from audioseal.libs.moshi.utils.compile import no_compile
        audio = torch.from_numpy(samples.copy())[None, None, :]
        with torch.inference_mode(), no_compile():
            message = torch.zeros((1, 16), dtype=torch.int64)
            marked = audio + self.generator.get_watermark(audio, sample_rate=RATE, message=message)
        return marked[0, 0].numpy()

    def score(self, samples):
        import torch
        self._load()
        from audioseal.libs.moshi.utils.compile import no_compile
        with torch.inference_mode(), no_compile():
            # Raw mean positive frame probability, not a calibrated fraud probability.
            result, _ = self.detector(torch.from_numpy(samples.copy())[None, None, :], sample_rate=RATE)
        return float(result[:, 1, :].mean().item())


def _transcode(samples, directory, variant):
    source = directory / "transform.wav"
    output = directory / ("transform.mp3" if variant == "mp3_64k" else "resampled.wav")
    sf.write(source, samples, RATE, subtype="FLOAT")
    options = ["-c:a", "libmp3lame", "-b:a", "64k"] if variant == "mp3_64k" else ["-ar", "8000"]
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-v", "error", "-y", "-i", str(source), *options, str(output)]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=30,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        decoded = directory / "transformed.wav"
        prepare_audio(str(output), decoded, RATE)
        return sf.read(decoded, dtype="float32")[0]
    except (subprocess.SubprocessError, OSError) as exc:
        raise ValueError("오디오 변환 실험을 완료하지 못했습니다.") from exc


def run_experiment(source, consent, external=None, backend=None):
    if not consent:
        raise ValueError("본인 또는 동의받은 음성인지 확인해 주세요.")
    if not source:
        raise ValueError("원본 음성을 넣어 주세요.")
    backend = backend or AudioSealBackend()
    with TemporaryDirectory(prefix="vzt-protection-") as temporary:
        directory = Path(temporary)
        prepare_audio(source, directory / "original.wav", RATE)
        original = sf.read(directory / "original.wav", dtype="float32")[0]
        # Leave headroom for watermark; controls receive identical input normalization.
        original = original * min(1.0, 0.9 / max(float(np.abs(original).max()), 1e-8))
        marked = np.asarray(backend.mark(original), dtype=np.float32)
        if marked.shape != original.shape or not np.isfinite(marked).all():
            raise ValueError("워터마크 모델이 유효하지 않은 음성을 반환했습니다.")
        peak = max(float(np.abs(marked).max()), 1.0)
        marked = marked / peak
        original = original / peak
        report = {"schema_version": 1, "backend": backend.metadata(),
                  "settings": {"sample_rate": RATE, "message_bits": "0" * 16,
                               "headroom_peak": 0.9, "shared_peak_scale": peak,
                               "score": "mean_positive_frame_probability", "threshold": 0.5,
                               "threshold_calibrated": False, "crop_start_seconds": 0},
                  "limitations": ["워터마크는 학습 방지를 보장하지 않습니다.",
                                  "unmarked_control은 이번 실행에서 표식을 추가하지 않은 대조군입니다. 기존 표식이 없음을 인증하지 않으며 높은 점수는 기존 표식 또는 오탐일 수 있습니다.",
                                  "복제를 통한 표식 전달은 검증되지 않았습니다.",
                                  "표식 점수는 보이스피싱 확률 또는 신원 인증이 아닙니다.",
                                  "대조군 한 파일은 모집단 오탐률을 추정하지 못합니다."], "trials": []}

        def record(name, samples, role, lineage):
            score = float(backend.score(samples))
            if not np.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("검출 모델이 유효하지 않은 점수를 반환했습니다.")
            report["trials"].append({"transform": name, "role": role,
                                      "duration_seconds": len(samples) / RATE,
                                      "raw_presence_score": score, "above_experimental_threshold": score >= 0.5,
                                      "lineage": lineage})

        for role, samples in (("unmarked_control", original), ("watermarked", marked)):
            record("identity", samples, role, "local_known_transform")
            for variant in ("mp3_64k", "resample_8k_then_16k"):
                record(variant, _transcode(samples, directory, variant), role, "local_known_transform")
            for seconds in (2, 3, 5):
                if len(samples) >= seconds * RATE:
                    record(f"crop_{seconds}s", samples[:seconds * RATE], role, "local_known_transform")
                else:
                    report["trials"].append({"transform": f"crop_{seconds}s", "role": role,
                                              "status": "skipped_input_too_short"})
        if external:
            prepare_audio(external, directory / "external.wav", RATE)
            record("user_supplied_external", sf.read(directory / "external.wav", dtype="float32")[0],
                   "unknown", "unverified_no_transfer_conclusion")
        return report, marked.copy()
