import json
from dataclasses import FrozenInstanceError
from unittest.mock import Mock

import pytest

from src.detection import profiles


def config(**changes):
    return {"release": "v0.2.0-detection.1", "kind": "aasist", "variant": "AASIST",
            "head": {"mean": [0., 0.], "scale": [1., 1.], "coef": [1., 1.], "intercept": 0.},
            "threshold": .7, "promotion_passed": False, "limitations": ["Experimental"], **changes}


def prepare(monkeypatch, value):
    path = Mock()
    path.read_text.return_value = json.dumps(value)
    monkeypatch.setattr(profiles, "CANDIDATE_PATH", path)
    backend = Mock()
    monkeypatch.setattr(profiles, "AASISTDetector", Mock(return_value=backend))
    return backend


def test_default_never_loads_candidate(monkeypatch):
    monkeypatch.setattr(profiles, "AcousticDetector", Mock())
    path = Mock()
    path.read_text.side_effect = AssertionError("Do not read candidate")
    monkeypatch.setattr(profiles, "CANDIDATE_PATH", path)
    result = profiles.build_profile()
    assert result.name == "baseline"
    assert result.threshold == .5


@pytest.mark.parametrize("score, decision", [(None, "판단 보류"), (.6, "합성 근거 부족"), (.7, "합성 의심"), (.9, "합성 의심")])
def test_candidate_decisions_and_metadata(monkeypatch, score, decision):
    backend = prepare(monkeypatch, config())
    backend.analyze.return_value = {"fake_score": score, "message": "Original", "coverage_seconds": 4}
    profile = profiles.build_profile("candidate", device="cpu")
    result = profile.analyze([], 16000)
    assert result["decision"] == decision
    assert result["release"] == "v0.2.0-detection.1"
    assert result["promotion_passed"] is False
    assert result["threshold"] == .7
    assert "본인 인증" in result["identity_notice"]
    assert result["message"] == "Original"
    assert result["coverage_seconds"] == 4


def test_profile_and_head_are_immutable(monkeypatch):
    prepare(monkeypatch, config())
    profile = profiles.build_profile("candidate")
    with pytest.raises(FrozenInstanceError):
        profile.threshold = .1
    kwargs = profiles.AASISTDetector.call_args.kwargs
    with pytest.raises(TypeError):
        kwargs["head"]["intercept"] = 5
    assert isinstance(kwargs["head"]["mean"], tuple)


@pytest.mark.parametrize("changes", [
    {"threshold": float("nan")}, {"threshold": -1}, {"threshold": 2}, {"threshold": True},
    {"promotion_passed": "false"}, {"variant": "other"}, {"kind": "other"},
    {"limitations": "not-list"}, {"release": ""},
    {"head": {"mean": [0], "scale": [float("inf")], "coef": [1], "intercept": 0}},
    {"head": {"mean": [0], "scale": [0], "coef": [1], "intercept": 0}},
    {"head": {"mean": [0], "scale": [1], "coef": [1, 2], "intercept": 0}},
])
def test_invalid_config_fails_before_model_creation(monkeypatch, changes):
    prepare(monkeypatch, config(**changes))
    with pytest.raises(ValueError):
        profiles.build_profile("candidate")
    profiles.AASISTDetector.assert_not_called()


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -.1, 1.1, True, "0.5"])
def test_invalid_detector_score_rejected(monkeypatch, score):
    backend = prepare(monkeypatch, config())
    backend.analyze.return_value = {"fake_score": score}
    with pytest.raises(ValueError):
        profiles.build_profile("candidate").analyze([], 16000)


def test_missing_candidate_is_not_silent_baseline(monkeypatch):
    path = Mock()
    path.read_text.side_effect = FileNotFoundError("Missing profile")
    monkeypatch.setattr(profiles, "CANDIDATE_PATH", path)
    with pytest.raises(FileNotFoundError):
        profiles.build_profile("candidate")


def test_unknown_profile_rejected():
    with pytest.raises(ValueError):
        profiles.build_profile("automatic")
