"""Deterministic development augmentation; not a real telephone simulation."""
import hashlib
import numpy as np

CONDITIONS = ("original", "bandlimit-8k", "noise-20db")


def augment(samples, condition, identity):
    x = np.asarray(samples, dtype=np.float32)
    if x.ndim != 1 or not len(x) or not np.isfinite(x).all():
        raise ValueError("Expected finite nonempty mono samples")
    if condition == "original":
        return x.copy()
    if condition == "bandlimit-8k":
        from scipy.signal import resample_poly
        return resample_poly(resample_poly(x, 1, 2), 2, 1)[:len(x)].astype(np.float32)
    if condition == "noise-20db":
        seed = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], "big")
        noise = np.random.default_rng(seed).standard_normal(len(x))
        rms = np.sqrt(np.mean(x.astype(float) ** 2))
        noise *= rms / 10 / np.sqrt(np.mean(noise ** 2))
        mixed = x + noise
        # Common gain prevents clipping without changing signal/noise ratio.
        return (mixed / max(1., float(np.max(np.abs(mixed))))).astype(np.float32)
    raise ValueError("Unknown augmentation")
