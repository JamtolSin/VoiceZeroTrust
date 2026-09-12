import json
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from src.detection.audio import AcousticDetector, decode
from src.detection.patterns import analyze_patterns
from src.detection.service import DetectionService
from src.detection.transcription import Transcriber


def test_combinations_and_education_not_global_bypass():
    result = analyze_patterns("보안 교육입니다. 경찰 담당입니다. 지금 당장 돈 보내 주세요. 가족에게 알리지 마세요.")
    assert result["level"] == "확인 권고"
    assert len(result["evidence"]) >= 3
    assert analyze_patterns("송금하세요라는 사기 사례입니다.")["level"] == "근거 부족"
    assert analyze_patterns("앱을 설치하지 마세요.")["level"] == "근거 부족"
    assert analyze_patterns("오늘 점심은 맛있었어요.")["level"] == "근거 부족"
    assert analyze_patterns("")["status"] == "판단 보류"
    assert analyze_patterns("보이스피싱 예방 교육 담당입니다 지금 당장 안전계좌로 이체하세요")["level"] == "확인 권고"
    assert analyze_patterns("은행은 인증번호를 알려달라고 요구하지 않습니다")["level"] == "근거 부족"


def test_weighting_silence_and_labels():
    scores = iter([0.2, 0.8])
    detector = AcousticDetector(lambda *_args, **_kwargs: [{"label": "fake", "score": next(scores)}, {"label": "real", "score": 0.1}])
    result = detector.analyze(np.ones(16000 * 7, dtype=np.float32) * 0.1, 16000)
    assert result["fake_score"] == pytest.approx((0.2 * 5 + 0.8 * 2) / 7)
    assert result["coverage_seconds"] == 7
    assert AcousticDetector().analyze(np.zeros(32000), 16000)["fake_score"] is None
    invalid = AcousticDetector(lambda *_args, **_kwargs: [{"label": "LABEL_0", "score": 0.8}])
    with pytest.raises(ValueError):
        invalid.analyze(np.ones(32000), 16000)


def test_decode_and_service_failure_is_independent(tmp_path):
    path = tmp_path / "tone.wav"
    sf.write(path, np.sin(np.arange(32000) * 0.1) * 0.1, 16000)
    class Broken:
        def analyze(self, *args):
            raise RuntimeError("private path must not escape")
    result = DetectionService(acoustic=Broken()).analyze(path, "지금 당장 돈 보내 주세요", enable_acoustic=True)
    assert result["acoustic"]["status"] == "사용 불가"
    assert result["acoustic"]["fake_score"] is None
    assert result["content"]["level"] == "확인 권고"
    assert result["transcription"]["source"] == "사용자 입력"
    assert "private path" not in json.dumps(result)
    assert result["audio"]["duration_seconds"] == 2
    with pytest.raises(ValueError):
        decode(tmp_path / "absent.wav", tmp_path / "out.wav")
    short = tmp_path / "short.wav"
    sf.write(short, np.zeros(1600), 16000)
    with pytest.raises(ValueError):
        decode(short, tmp_path / "out.wav")


def test_asr_generator_and_empty_speech():
    class Model:
        def transcribe(self, *args, **kwargs):
            return iter([SimpleNamespace(text=" 테스트 ", no_speech_prob=0.1),
                         SimpleNamespace(text="무음 환각", no_speech_prob=0.9)]), None
    assert Transcriber(Model()).transcribe("unused")["text"] == "테스트"
