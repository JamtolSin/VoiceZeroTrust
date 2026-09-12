"""Lazy official AudioSeal adapter. No heuristic or synthetic fallback."""
import os

EDUCATION_TAG = 0x565A
SAMPLE_RATE = 16000


class AudioSealBackend:
    def __init__(self):
        self.generator = None
        self.detector = None

    def _load(self, generation=False):
        # AudioSeal's own switch avoids requiring a C++ compiler on local CPU setups.
        os.environ.setdefault("NO_TORCH_COMPILE", "1")
        try:
            from audioseal import AudioSeal
        except ImportError as exc:
            raise RuntimeError("AudioSeal이 설치되지 않았습니다. pip install 'audioseal>=0.2,<0.3' 실행 후 다시 시도하세요.") from exc
        if generation and self.generator is None:
            self.generator = AudioSeal.load_generator("audioseal_wm_16bits").cpu().eval()
        if self.detector is None:
            self.detector = AudioSeal.load_detector("audioseal_detector_16bits").cpu().eval()

    def embed(self, samples):
        import torch
        self._load(generation=True)
        waveform = torch.from_numpy(samples).float()[None, None, :]
        message = torch.tensor([[(EDUCATION_TAG >> shift) & 1 for shift in range(15, -1, -1)]])
        with torch.inference_mode():
            watermark = self.generator.get_watermark(waveform, sample_rate=SAMPLE_RATE, message=message)
            result = (waveform + watermark)[0, 0].cpu().numpy()
        return result

    def detect(self, samples):
        import torch
        self._load()
        waveform = torch.from_numpy(samples).float()[None, None, :]
        with torch.inference_mode():
            score, message = self.detector.detect_watermark(waveform, sample_rate=SAMPLE_RATE)
        value = 0
        for bit in message.reshape(-1).tolist():
            value = (value << 1) | int(bit)
        return float(score), value
