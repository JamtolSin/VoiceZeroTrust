import numpy as np
import pytest

from scripts.evaluate_v3 import fit_head, grouped_splits
from src.detection.aasist import linear_score
from src.evaluation.augmentation import augment


def test_augmentation_deterministic_length_and_no_mutation():
    x = np.sin(np.arange(32001) / 10).astype(np.float32) * .2
    original = x.copy()
    for condition in ("original", "bandlimit-8k", "noise-20db"):
        first = augment(x, condition, "sample")
        np.testing.assert_array_equal(first, augment(x, condition, "sample"))
        assert first.shape == x.shape
        assert np.isfinite(first).all()
    np.testing.assert_array_equal(x, original)
    assert not np.array_equal(augment(x, "noise-20db", "a"), augment(x, "noise-20db", "b"))


def test_noise_has_requested_snr():
    x = np.ones(32000, dtype=np.float32) * .1
    error = augment(x, "noise-20db", "sample") - x
    assert 20 * np.log10(np.linalg.norm(x) / np.linalg.norm(error)) == pytest.approx(20, abs=.001)


@pytest.mark.parametrize("x", [[], [[1]], [np.nan], [np.inf]])
def test_augmentation_invalid(x):
    with pytest.raises(ValueError):
        augment(x, "noise-20db", "sample")


def test_groups_and_every_test_sample_once():
    labels = np.tile([0, 1], 30)
    groups = np.repeat(np.arange(15), 4)
    seen = []
    for fit, calibration, test in grouped_splits(labels, groups):
        assert not set(groups[fit]) & set(groups[calibration])
        assert not set(groups[fit]) & set(groups[test])
        assert not set(groups[calibration]) & set(groups[test])
        assert len(fit) + len(calibration) + len(test) == len(labels)
        seen.extend(test)
    assert sorted(seen) == list(range(len(labels)))


def test_fit_does_not_observe_calibration_or_test_features():
    x = np.arange(24, dtype=float).reshape(12, 2)
    y = np.tile([0, 1], 6)
    fit = np.arange(8)
    head = fit_head({"original": x}, y, fit, ("original",), .01)
    changed = x.copy()
    changed[8:] = 1e6
    assert head == fit_head({"original": changed}, y, fit, ("original",), .01)
    np.testing.assert_allclose(head["mean"], x[fit].mean(axis=0))
    assert np.isfinite(linear_score(x, head)).all()
