from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from src.watermark.backend import EDUCATION_TAG
from src.watermark.service import WatermarkService


class Backend:
    def __init__(self, score=0.95, tag=EDUCATION_TAG):
        self.score, self.tag = score, tag

    def embed(self, samples):
        return samples + 0.0001

    def detect(self, samples):
        return self.score, self.tag


@pytest.fixture
def recording(tmp_path):
    path = tmp_path / "input.wav"
    sf.write(path, np.sin(np.arange(48000) * 0.1) * 0.1, 16000)
    return str(path)


def test_embed_verifies_saved_output_and_preserves_input(tmp_path, recording):
    original = Path(recording).read_bytes()
    service = WatermarkService(tmp_path / "runtime", Backend())
    output, result = service.embed_file(recording, True)
    assert Path(output).exists()
    assert Path(output).with_suffix(".json").exists()
    assert result.detected and result.education_tag_matches
    assert Path(recording).read_bytes() == original
    assert len(list(service.runtime.iterdir())) == 2


def test_undetected_message_is_not_reported(tmp_path, recording):
    result = WatermarkService(tmp_path / "runtime", Backend(0.1)).detect_file(recording)
    assert not result.detected
    assert not result.education_tag_matches
    assert result.decoded_tag is None


def test_other_tag_does_not_claim_education_origin(tmp_path, recording):
    result = WatermarkService(tmp_path / "runtime", Backend(tag=1)).detect_file(recording)
    assert result.detected and not result.education_tag_matches


def test_requires_generated_output_confirmation(tmp_path, recording):
    with pytest.raises(ValueError, match="교육용"):
        WatermarkService(tmp_path, Backend()).embed_file(recording)


def test_invalid_model_score_cleans_temporary_files(tmp_path, recording):
    service = WatermarkService(tmp_path / "runtime", Backend(float("nan")))
    with pytest.raises(ValueError, match="점수"):
        service.embed_file(recording, True)
    assert list(service.runtime.iterdir()) == []


def test_silent_input_rejected(tmp_path):
    path = tmp_path / "silence.wav"
    sf.write(path, np.zeros(48000), 16000)
    with pytest.raises(ValueError, match="너무 작습니다"):
        WatermarkService(tmp_path / "runtime", Backend()).detect_file(str(path))
