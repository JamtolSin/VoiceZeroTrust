"""Lazy XTTS adapter. Only the service's fixed educational phrase is exposed."""
import os
from pathlib import Path
from threading import Lock


class XTTSSynthesizer:
    name = "XTTS-v2"

    def __init__(self):
        self._model = None
        self._lock = Lock()
        self.device = "미로딩"

    def synthesize(self, reference: Path, text: str, output: Path, reference_text=""):
        with self._lock:
            if self._model is None:
                import torch
                from TTS.api import TTS

                # The service calls this only after explicit model-license acceptance.
                os.environ["COQUI_TOS_AGREED"] = "1"
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
                model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(self.device)
                self._model = model
            self._model.tts_to_file(
                text=text, speaker_wav=str(reference), language="ko",
                file_path=str(output), split_sentences=True,
            )


class QwenSynthesizer:
    name = "Qwen3-TTS 1.7B Base"
    model_id = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    requires_transcript = True
    sample_rate = 24000

    def __init__(self):
        self._model = None
        self._lock = Lock()
        self.device = "미로딩"

    def load(self):
        if self._model is None:
            import torch
            from qwen_tts import Qwen3TTSModel

            self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
            self._model = Qwen3TTSModel.from_pretrained(
                self.model_id, device_map=self.device,
                dtype=torch.bfloat16 if self.device != "cpu" else torch.float32,
                attn_implementation="sdpa",
            )
        return self._model

    def synthesize(self, reference: Path, text: str, output: Path, reference_text=""):
        import soundfile as sf
        import torch

        if not reference_text.strip():
            raise ValueError("녹음에서 실제로 말한 내용을 입력해 주세요.")
        with self._lock, torch.inference_mode():
            model = self.load()
            # Supply a decoded waveform to avoid extra path/codec dependencies.
            samples, rate = sf.read(reference, dtype="float32")
            wavs, output_rate = model.generate_voice_clone(
                text=text, language="Korean", ref_audio=(samples, rate),
                ref_text=reference_text.strip(), x_vector_only_mode=False,
                max_new_tokens=600,
            )
            sf.write(output, wavs[0], output_rate)
