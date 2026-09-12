import json

import numpy as np
import pytest
import soundfile as sf

from src.protection.experiment import RATE, run_experiment


class FakeBackend:
    def mark(self, samples):
        return samples + np.float32(0.001)

    def metadata(self):
        return {"package": "test_double", "version": "1"}

    def score(self, samples):
        return 0.25


@pytest.fixture
def recording(tmp_path):
    path = tmp_path / "private-person-name.wav"
    time = np.arange(6 * RATE) / RATE
    sf.write(path, 0.1 * np.sin(2 * np.pi * 220 * time), RATE)
    return str(path)


def test_matched_controls_transforms_and_private_report(recording):
    report, marked = run_experiment(recording, True, recording, FakeBackend())
    assert len(report["trials"]) == 13
    assert marked.shape == (6 * RATE,)
    assert "private-person-name" not in json.dumps(report)
    assert report["trials"][-1]["lineage"] == "unverified_no_transfer_conclusion"
    for role in ("unmarked_control", "watermarked"):
        trials = [r for r in report["trials"] if r["role"] == role]
        assert len(trials) == 6
        assert {r["duration_seconds"] for r in trials if r["transform"].startswith("crop")} == {2, 3, 5}
        assert all(r["raw_presence_score"] == 0.25 for r in trials)


def test_consent_is_required(recording):
    with pytest.raises(ValueError, match="동의"):
        run_experiment(recording, False, backend=FakeBackend())


def test_short_input_skips_long_crops(tmp_path):
    source = tmp_path / "short.wav"
    sf.write(source, np.full(RATE * 2, 0.05), RATE)
    report, _ = run_experiment(str(source), True, backend=FakeBackend())
    assert sum(r.get("status") == "skipped_input_too_short" for r in report["trials"]) == 4


def test_invalid_model_output_is_rejected(recording):
    class Invalid(FakeBackend):
        def mark(self, samples):
            return np.full_like(samples, np.nan)
    with pytest.raises(ValueError, match="유효하지"):
        run_experiment(recording, True, backend=Invalid())


def test_invalid_score_is_rejected(recording):
    class Invalid(FakeBackend):
        def score(self, samples):
            return float("nan")
    with pytest.raises(ValueError, match="점수"):
        run_experiment(recording, True, backend=Invalid())
