from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import subprocess
import imageio_ffmpeg

from src.service import DemoService, PHRASE


class FakeEngine:
    name = "test-double-not-real-synthesis"

    def synthesize(self, reference, text, output, reference_text=""):
        assert text == PHRASE
        samples, rate = sf.read(reference)
        sf.write(output, samples, rate)


@pytest.fixture
def fixture(tmp_path):
    source = tmp_path / "input.wav"
    t = np.arange(3 * 22050) / 22050
    sf.write(source, 0.1 * np.sin(2 * np.pi * 220 * t), 22050)
    return DemoService(FakeEngine(), tmp_path / "work"), source


def test_pipeline_and_cleanup(fixture):
    service, source = fixture
    result = service.generate_demo(str(source), True, True)
    assert result.input_seconds == 3
    assert len(result.audio[1]) == 3 * 22050
    assert list(service.workdir.iterdir()) == []
    assert source.exists()


@pytest.mark.parametrize("consent,license_ok,phrase", [(False, True, "security_notice"),
    (True, False, "security_notice"), (True, True, "arbitrary")])
def test_reject_before_engine(fixture, consent, license_ok, phrase):
    service, source = fixture
    with pytest.raises(ValueError):
        service.generate_demo(str(source), consent, license_ok, phrase)


@pytest.mark.parametrize("seconds,amplitude", [(1, 0.1), (31, 0.1), (3, 0)])
def test_invalid_audio(fixture, seconds, amplitude):
    service, source = fixture
    sf.write(source, np.ones(seconds * 22050) * amplitude, 22050)
    with pytest.raises(ValueError):
        service.generate_demo(str(source), True, True)
    assert list(service.workdir.iterdir()) == []


def test_corrupt_audio(fixture):
    service, source = fixture
    source.write_bytes(b"not an audio file")
    with pytest.raises(ValueError):
        service.generate_demo(str(source), True, True)
    assert list(service.workdir.iterdir()) == []


@pytest.mark.parametrize("extension", [".mp3", ".m4a", ".webm"])
def test_encoded_input(fixture, extension):
    service, source = fixture
    mp3 = source.with_suffix(extension)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y",
                    "-i", str(source), str(mp3)], check=True)
    result = service.generate_demo(str(mp3), True, True)
    assert result.input_seconds == pytest.approx(3, abs=0.1)


def test_missing_file_message(fixture):
    service, source = fixture
    with pytest.raises(ValueError, match="없거나 만료"):
        service.generate_demo(str(source.with_name("missing.mp3")), True, True)


def test_engine_failure_cleans_files(fixture):
    service, source = fixture
    def fail(*args, **kwargs):
        raise RuntimeError("simulated model failure")
    service.engine.synthesize = fail
    with pytest.raises(RuntimeError):
        service.generate_demo(str(source), True, True)
    assert list(service.workdir.iterdir()) == []


def test_qwen_requires_transcript(fixture):
    service, source = fixture
    service.engine.requires_transcript = True
    with pytest.raises(ValueError, match="실제로 말한"):
        service.generate_demo(str(source), True, True)


def test_reference_text_forwarded(fixture):
    service, source = fixture
    captured = []
    original = service.engine.synthesize
    def record(*args, reference_text=""):
        captured.append(reference_text)
        return original(*args, reference_text=reference_text)
    service.engine.synthesize = record
    service.generate_demo(str(source), True, True, reference_text="참조 대사")
    assert captured == ["참조 대사"]
