"""Local optional Korean transcription; never sends audio to an API."""


class Transcriber:
    def __init__(self, model=None):
        self.model = model

    def transcribe(self, path):
        if self.model is None:
            from faster_whisper import WhisperModel
            self.model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, _ = self.model.transcribe(str(path), language="ko", vad_filter=True,
                                           beam_size=5, condition_on_previous_text=False)
        text = " ".join(segment.text.strip() for segment in segments if segment.no_speech_prob < 0.6).strip()
        return {"status": "분석 완료" if text else "판단 보류", "source": "자동 전사",
                "text": text, "message": "자동 전사에는 누락과 오인식이 있을 수 있습니다."}
