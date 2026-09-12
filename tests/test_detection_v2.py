"""Offline checks for pinned inference and leakage-aware model selection."""
import numpy as np
import pytest

from src.detection.aasist import AASISTDetector, linear_score, official_window
from scripts.select_detector import choose_threshold, split_groups


def test_official_window_repeats_and_truncates():
    np.testing.assert_array_equal(official_window([1, 2, 3], size=8), [1, 2, 3, 1, 2, 3, 1, 2])
    np.testing.assert_array_equal(official_window(np.arange(10), size=4), [0, 1, 2, 3])
    assert official_window([1]).shape == (64600,)
    assert official_window([1]).dtype == np.float32


@pytest.mark.parametrize("samples", [[], [np.nan], [np.inf], [[1, 2]]])
def test_official_window_rejects_invalid_audio(samples):
    with pytest.raises(ValueError):
        official_window(samples)


def head(**changes):
    return {"mean": [1., 2.], "scale": [2., 1.], "coef": [2., -1.], "intercept": 0., **changes}


def test_linear_score_scalar_batch_and_saturation():
    assert linear_score([1., 2.], head()) == pytest.approx(.5)
    np.testing.assert_allclose(linear_score([[1., 2.], [3., 2.]], head()), [.5, 1 / (1 + np.exp(-2))])
    assert np.isfinite(linear_score([1e100, 2.], head()))


@pytest.mark.parametrize("features, changes", [
    ([1.], {}), ([1., 2.], {"coef": [1.]}),
    ([1., 2.], {"scale": [0., 1.]}), ([1., 2.], {"scale": [-1., 1.]}),
    ([np.nan, 2.], {}), ([1., 2.], {"intercept": np.inf}),
    ([1., 2.], {"scale": [np.inf, 1.]}),
])
def test_linear_score_rejects_invalid_numeric_head(features, changes):
    with pytest.raises(ValueError):
        linear_score(features, head(**changes))


def mock_detector(monkeypatch, score=.8, fitted_head=None):
    detector = AASISTDetector(head=fitted_head)
    monkeypatch.setattr(detector, "load", lambda: pytest.fail("Must not load a model"))
    monkeypatch.setattr(detector, "features", lambda samples: (np.array([1., 2.]), score))
    return detector


def test_analyze_coverage_and_optional_head(monkeypatch):
    samples = np.ones(80000, dtype=np.float32) * .1
    detector = mock_detector(monkeypatch)
    report = detector.analyze(samples, 16000)
    assert report["fake_score"] == .8
    assert report["coverage_seconds"] == pytest.approx(64600 / 16000)
    assert report["skipped_seconds"] == pytest.approx((80000 - 64600) / 16000)
    assert report["chunks"][0]["duration_seconds"] == report["coverage_seconds"]
    detector.head = head()
    assert detector.analyze(samples, 16000)["fake_score"] == pytest.approx(.5)


@pytest.mark.parametrize("samples", [np.zeros(32000), np.ones(15999) * .1])
def test_analyze_abstains_without_features(monkeypatch, samples):
    detector = mock_detector(monkeypatch)
    monkeypatch.setattr(detector, "features", lambda samples: pytest.fail("Abstained audio must not infer"))
    result = detector.analyze(samples, 16000)
    assert result["fake_score"] is None
    assert result["chunks"] == []
    assert result["coverage_seconds"] == 0
    assert result["skipped_seconds"] == len(samples) / 16000


def test_analyze_rejects_wrong_rate_and_invalid_audio(monkeypatch):
    detector = mock_detector(monkeypatch)
    with pytest.raises(ValueError):
        detector.analyze(np.ones(16000), 8000)
    for samples in ([], [np.nan], [[1, 2]]):
        with pytest.raises(ValueError):
            detector.analyze(samples, 16000)


def test_split_groups_conservatively_joins_source_ids_and_transitive_duplicates():
    rows = [
        {"original_path": "yt_01_a.wav", "sha256": "a"},
        {"original_path": "tts_01_b.wav", "sha256": "b"},
        {"original_path": "tts_02_c.wav", "sha256": "b"},
        {"original_path": "tts_02_d.wav", "sha256": "c"},
        {"original_path": "tts_03_e.wav", "sha256": "c"},
        {"original_path": "yt_04_f.wav", "sha256": "d"},
    ]
    groups = split_groups(rows)
    assert groups["a"] == groups["b"] == groups["c"]
    assert groups["a"] != groups["d"]
    assert set(groups) == {"a", "b", "c", "d"}


def test_threshold_ties_do_not_exceed_fpr_cap():
    scores = np.array([.2, .2, .2, .8, .9, .95])
    labels = np.array([0, 0, 0, 0, 1, 1])
    threshold = choose_threshold(scores, labels, max_fpr=.25)
    assert threshold == np.nextafter(.2, np.inf)
    assert np.mean(scores[labels == 0] >= threshold) <= .25
    assert np.mean(scores[labels == 1] >= threshold) == 1


def test_threshold_rejects_impossible_probability_threshold():
    # The public metric/decision contract restricts thresholds to [0, 1].
    with pytest.raises(ValueError, match="No valid threshold"):
        choose_threshold([1., 1.], [0, 1], max_fpr=0.)


@pytest.mark.parametrize("labels", [[0, 0], [1, 1]])
def test_threshold_requires_both_classes(labels):
    with pytest.raises(ValueError, match="both labels"):
        choose_threshold([.1, .9], labels)
