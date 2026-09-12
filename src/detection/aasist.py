"""Pinned official NAVER AASIST inference, optional frozen-feature head."""
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

REVISION = "a04c9863f63d44471dde8a6abcb3b082b07cd1d1"
FILES = {
    "models/AASIST.py": "9e0d3e80937dd0577beea7883098465a479da23a198ebc0d712abcc59b0bec50",
    "config/AASIST.conf": "c25023331685027cce90e1b9a0d2df10aa04b2a27d9b27d5afa36e6815b0fe76",
    "config/AASIST-L.conf": "9e2e2610b2260b421bf2083646dde4747a6a5cdd138015066d83bc61b6b214cf",
    "models/weights/AASIST.pth": "51d2d9cf0738172f61e2a384ec50a54a55363240f67c971ed55a92435bc1a1c0",
    "models/weights/AASIST-L.pth": "814331d088032bb4c3fa61cc014789eadeed464209dd094ab3a2dd6ffbdce27a",
}
LICENSE = """Copyright (c) 2021-present NAVER Corp.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""


def official_window(samples, size=64600):
    """Official evaluation: first 64600 samples; repeat short waveforms."""
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim != 1 or not len(samples) or not np.isfinite(samples).all():
        raise ValueError("Expected nonempty finite mono audio")
    if len(samples) >= size:
        return samples[:size]
    return np.tile(samples, size // len(samples) + 1)[:size]


def linear_score(features, head):
    x = np.asarray(features, dtype=np.float64)
    mean, scale, coef = (np.asarray(head[key], dtype=np.float64) for key in ("mean", "scale", "coef"))
    if x.shape[-1:] != mean.shape or scale.shape != mean.shape or coef.shape != mean.shape or np.any(scale <= 0):
        raise ValueError("Invalid frozen head dimensions/scales")
    if not all(np.isfinite(value).all() for value in [x, mean, scale, coef]) or not np.isfinite(float(head["intercept"])):
        raise ValueError("Nonfinite frozen head parameters")
    logit = ((x - mean) / scale) @ coef + float(head["intercept"])
    if not np.isfinite(logit).all():
        raise ValueError("Invalid frozen head result")
    return 1 / (1 + np.exp(-np.clip(logit, -700, 700)))


class AASISTDetector:
    def __init__(self, variant="AASIST", cache=None, device="cpu", head=None):
        if variant not in {"AASIST", "AASIST-L"}:
            raise ValueError("Unsupported AASIST variant")
        self.variant, self.device, self.head = variant, device, head
        self.cache = Path(cache) if cache else Path(__file__).resolve().parents[2] / ".runtime/aasist-pinned" / REVISION
        self.model = None

    def load(self):
        if self.model is not None:
            return
        import requests
        import torch
        needed = ["models/AASIST.py", f"config/{self.variant}.conf", f"models/weights/{self.variant}.pth"]
        for name in needed:
            path = self.cache / name
            if not path.exists():
                response = requests.get(f"https://raw.githubusercontent.com/clovaai/aasist/{REVISION}/{name}", timeout=60)
                response.raise_for_status()
                if hashlib.sha256(response.content).hexdigest() != FILES[name]:
                    raise RuntimeError("Official AASIST download checksum mismatch")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(response.content)
            if hashlib.sha256(path.read_bytes()).hexdigest() != FILES[name]:
                raise RuntimeError("AASIST cache checksum mismatch")
        (self.cache / "LICENSE").write_text(LICENSE, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("vzt_pinned_aasist", self.cache / "models/AASIST.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        config = json.loads((self.cache / f"config/{self.variant}.conf").read_text())
        model = module.Model(config["model_config"])
        model.load_state_dict(torch.load(self.cache / f"models/weights/{self.variant}.pth", map_location="cpu", weights_only=True))
        self.model = model.to(self.device).eval()

    def features(self, samples):
        import torch
        self.load()
        tensor = torch.from_numpy(official_window(samples).copy()).unsqueeze(0).to(self.device)
        with torch.inference_mode():
            hidden, logits = self.model(tensor)
            # Official training label map: spoof=0, bonafide=1.
            score = torch.softmax(logits, dim=-1)[0, 0].item()
        return hidden[0].cpu().numpy(), score

    def analyze(self, samples, rate):
        if rate != 16000:
            raise ValueError("AASIST requires 16kHz audio")
        samples = np.asarray(samples, dtype=np.float32)
        if samples.ndim != 1 or not len(samples) or not np.isfinite(samples).all():
            raise ValueError("Invalid mono audio")
        available = min(len(samples), 64600)
        if available < 16000 or float(np.sqrt(np.mean(samples[:available] ** 2))) < .003:
            return {"status": "판단 보류", "fake_score": None, "chunks": [], "coverage_seconds": 0,
                    "skipped_seconds": len(samples)/rate, "message": "분석 가능한 발화 길이 또는 음량이 부족합니다."}
        features, score = self.features(samples)
        if self.head is not None:
            score = float(linear_score(features, self.head))
        return {"status": "분석 완료", "model": f"clovaai/{self.variant}", "revision": REVISION,
                "fake_score": score, "coverage_seconds": available/rate, "skipped_seconds": (len(samples)-available)/rate,
                "chunks": [{"start_seconds": 0, "duration_seconds": available/rate, "fake_score": score}],
                "message": "실험용 합성 점수이며 사기 확률이 아닙니다. 공식 방식으로 처음 약 4초를 분석합니다. 한국어 성능 미검증."}
