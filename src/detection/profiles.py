"""Explicit opt-in experimental profiles; the baseline remains the default."""
from dataclasses import dataclass
import json
import math
from numbers import Real
from pathlib import Path
from types import MappingProxyType

from .aasist import AASISTDetector
from .audio import AcousticDetector

CANDIDATE_PATH = Path(__file__).with_name("profiles") / "v2-candidate.json"
KOREAN_PATH = Path(__file__).with_name("profiles") / "v4-korean-research.json"
NOTICE = "합성 근거 부족은 실제 사람 또는 본인 인증을 의미하지 않습니다. 별도 채널로 신원을 확인하세요."


def _number(value, name, probability=False):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"Invalid {name}")
    if probability and not 0 <= value <= 1:
        raise ValueError(f"Invalid {name}")
    return float(value)


def _head(value):
    if not isinstance(value, dict) or set(value) != {"mean", "scale", "coef", "intercept"}:
        raise ValueError("Invalid head schema")
    frozen = {}
    for key in ("mean", "scale", "coef"):
        if not isinstance(value[key], list) or not value[key]:
            raise ValueError("Head vectors must be nonempty lists")
        frozen[key] = tuple(_number(item, key) for item in value[key])
    if len({len(frozen[key]) for key in ("mean", "scale", "coef")}) != 1 or any(x <= 0 for x in frozen["scale"]):
        raise ValueError("Invalid head dimensions/scales")
    frozen["intercept"] = _number(value["intercept"], "intercept")
    return MappingProxyType(frozen)


@dataclass(frozen=True)
class DetectionProfile:
    detector: object
    name: str
    release: str
    threshold: float
    promotion_passed: bool
    limitations: tuple

    def analyze(self, samples, rate):
        result = dict(self.detector.analyze(samples, rate))
        if self.name == "korean-research" and isinstance(result.get("message"), str):
            result["message"] = result["message"].replace("한국어 성능 미검증.", "DSD 한국어 시험 범위만 평가; 실제 통화 미검증. 비상업 연구용.")
        score = result["fake_score"]
        if score is not None:
            score = _number(score, "detector score", probability=True)
        result.update({
            "decision": "판단 보류" if score is None else ("합성 의심" if score >= self.threshold else "합성 근거 부족"),
            "threshold": self.threshold, "profile": self.name, "release": self.release,
            "promotion_passed": self.promotion_passed, "limitations": list(self.limitations),
            "identity_notice": NOTICE,
        })
        return result


def build_profile(name="baseline", device="cpu", allow_noncommercial=False):
    if name == "baseline":
        return DetectionProfile(AcousticDetector(), "baseline", "v0.1.0-detection.1", .5, False,
                                ("기존 모델 기본 정책 유지; 한국어 성능 미검증",))
    if name not in {"candidate", "korean-research"}:
        raise ValueError("Unknown detector profile")
    if name == "korean-research" and allow_noncommercial is not True:
        raise ValueError("한국어 후보는 비상업 연구·평가 용도로만 사용할 수 있습니다. 사용 범위를 확인해 주세요.")
    path = KOREAN_PATH if name == "korean-research" else CANDIDATE_PATH
    config = json.loads(path.read_text(encoding="utf-8"))
    if name == "korean-research" and (not isinstance(config, dict) or config.get("research_only") is not True or config.get("promotion_passed") is not False):
        raise ValueError("Korean research restriction missing")
    if not isinstance(config, dict) or config.get("kind") != "aasist" or config.get("variant") not in {"AASIST", "AASIST-L"}:
        raise ValueError("Invalid candidate detector configuration")
    if not isinstance(config.get("release"), str) or not config["release"].strip():
        raise ValueError("Invalid release")
    if type(config.get("promotion_passed")) is not bool:
        raise ValueError("Invalid promotion status")
    limitations = config.get("limitations")
    if not isinstance(limitations, list) or not all(isinstance(item, str) and item.strip() for item in limitations):
        raise ValueError("Invalid limitations")
    threshold = _number(config["threshold"], "threshold", probability=True)
    frozen_head = _head(config["head"])
    detector = AASISTDetector(variant=config["variant"], device=device, head=frozen_head)
    return DetectionProfile(detector, name, config["release"], threshold, config["promotion_passed"], tuple(limitations))
