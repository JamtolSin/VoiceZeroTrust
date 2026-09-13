"""Exercise the real phone analysis adapter; a tone checks plumbing, not accuracy."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.server import analyze_pcm

if __name__ == "__main__":
    samples = np.arange(16000 * 10, dtype=np.float64) / 16000
    pcm = (np.sin(samples * 2 * np.pi * 220) * 3000).astype("<i2").tobytes()
    report = analyze_pcm(pcm)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["acoustic"]["status"] != "분석 완료":
        raise SystemExit("Real acoustic inference did not complete")
    print("MODEL PLUMBING PASS (synthetic tone, not a speech accuracy test)")
