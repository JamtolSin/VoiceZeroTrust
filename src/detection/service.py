"""Independent channels with explicit unavailable results and ephemeral audio."""
from pathlib import Path
from tempfile import TemporaryDirectory

from .audio import AcousticDetector, decode
from .patterns import analyze_patterns
from .transcription import Transcriber


class DetectionService:
    def __init__(self, acoustic=None, transcriber=None, workdir=None):
        self.acoustic = acoustic if acoustic is not None else AcousticDetector()
        self.transcriber = transcriber if transcriber is not None else Transcriber()
        self.workdir = Path(workdir) if workdir is not None else Path(".runtime/detection/requests")

    def analyze(self, path, transcript=None, *, enable_asr=False, enable_acoustic=False):
        result = {"audio": {}, "acoustic": {"status": "미실행", "fake_score": None},
                  "transcription": {"status": "미실행", "source": "없음", "text": ""},
                  "content": analyze_patterns(""),
                  "recommendation": "목소리나 탐지 점수만으로 신원을 확인하지 마세요. 금전·인증 정보 요청은 알고 있는 번호나 별도 채널로 재확인하세요."}
        if transcript and len(transcript) > 20000:
            raise ValueError("대화 내용은 20,000자 이내로 입력해 주세요.")
        self.workdir.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="vzt-detect-", dir=self.workdir) as directory:
            wav = Path(directory) / "input.wav"
            samples, rate = decode(path, wav)
            result["audio"] = {"duration_seconds": len(samples) / rate, "sample_rate": rate}
            if enable_acoustic:
                try:
                    result["acoustic"] = self.acoustic.analyze(samples, rate)
                except Exception:
                    result["acoustic"] = {"status": "사용 불가", "fake_score": None,
                                          "message": "음향 모델 로드 또는 추론에 실패했습니다. 모델 다운로드·의존성·메모리를 확인해 주세요."}
            if transcript and transcript.strip():
                result["transcription"] = {"status": "입력됨", "source": "사용자 입력",
                                           "text": transcript.strip(), "message": "입력 내용과 실제 오디오의 일치 여부는 검증하지 않았습니다."}
            elif enable_asr:
                try:
                    result["transcription"] = self.transcriber.transcribe(wav)
                except Exception:
                    result["transcription"] = {"status": "사용 불가", "source": "자동 전사", "text": "",
                                               "message": "전사에 실패했습니다. 대화 내용을 직접 입력하거나 설치·모델 다운로드 상태를 확인해 주세요."}
            result["content"] = analyze_patterns(result["transcription"]["text"])
        return result
