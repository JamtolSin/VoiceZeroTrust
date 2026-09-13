"""Archive Korean research metrics with provenance, no audio/embeddings."""
import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from scripts.prepare_dsd import json_once, write_once
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    data = args.data.resolve()
    source = data / "experiment-v4"
    dest = ROOT / "experiments/2026-09-13/aasist-korean__dsd-v1-grouped"
    dest.mkdir(parents=True, exist_ok=True)
    report = json.loads((source / "test-report.json").read_text(encoding="utf-8"))
    selection = json.loads((source / "selection.json").read_text(encoding="utf-8"))
    chosen = selection["candidates"][selection["selected"]]
    profile = {"kind": "aasist", "variant": "AASIST", "head": chosen["head"], "threshold": chosen["threshold"],
               "release": "v0.4.0-detection.1", "promotion_passed": False, "research_only": True,
               "limitations": ["비상업 연구·평가 전용", "DSD 한국어 그룹 시험; 문장 독립성 및 최신 생성기 일반화 미보장", "처음 약 4초 분석; 신원 인증이 아님"]}
    json_once(ROOT / "src/detection/profiles/v4-korean-research.json", profile)
    split = json.loads((data / "split-lock.json").read_text(encoding="utf-8"))
    for name in ("training-lock.json", "selection.json", "test-lock.json", "test-predictions.json", "test-report.json"):
        write_once(dest / name, (source / name).read_bytes())
    for name in ("split-lock.json", "excluded.json"):
        write_once(dest / name, (data / name).read_bytes())
    manifest = [json.loads(line) for line in (data / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    sanitized = [{k: r[k] for k in ("id", "sha256", "pcm_sha256", "label", "source", "group", "split", "duration", "sample_rate", "channels")} for r in manifest]
    write_once(dest / "split-manifest.jsonl", "".join(json.dumps(r) + "\n" for r in sanitized).encode())
    write_once(dest / "download-receipts.json", (data.parent / "download-receipts.json").read_bytes())
    meta = {"release": "v0.4.0-detection.1", "created_at": datetime.now(timezone.utc).isoformat(),
            "dataset": "DSD-Corpus v1", "dataset_url": "https://zenodo.org/records/13788455",
            "authors": "AISRC, Soongsil University; Doan et al., Trident of Poseidon (ACM CCS 2024)",
            "license_scope": "CC-BY-NC-4.0 dataset; this experiment and candidate restricted to noncommercial research/evaluation",
            "model": "NAVER AASIST a04c9863f63d44471dde8a6abcb3b082b07cd1d1 frozen + Korean trained logistic head",
            "versions": {p: version(p) for p in ("torch", "numpy", "scipy", "scikit-learn", "soundfile", "transformers")},
            "promotion_passed": False, "default_changed": False,
            "script_sha256": {name: hashlib.sha256((ROOT / "scripts" / name).read_bytes()).hexdigest() for name in (
                "prepare_dsd.py", "prepare_dsd_korean.py", "train_dsd_korean.py", "evaluate_dsd_korean.py")}}
    json_once(dest / "metadata.json", meta)
    def pct(x):
        return "—" if x is None else f"{x:.2%}"
    lines = ["# v0.4.0-detection.1 — 한국어 DSD 연구 평가", "",
             "비상업 연구·평가 전용입니다. 데이터 라이선스: [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). 기본 모델은 교체하지 않았습니다. 합성 음성 판별이지 보이스피싱 의도나 신원 인증이 아닙니다.", "",
             "## 데이터 검증 / 분할", "", f"디코딩 {split['decoded']:,}개, PCM 중복 제거 후 {split['unique']:,}개, 제외 {split['excluded']:,}개.", "",
             "제외 내역: SNS 출처 1,733개, 길이 1초 미만 VITS-AIHUB 239개(메타데이터 0.688–0.992초). PCM 중복은 AIHUB 1개와 SeamlessM4T-TTS 47개입니다. 검출률의 분모는 이 정제를 통과한 고정 test이며 제외 표본까지 평가했다고 주장하지 않습니다.", "",
             "| 분할/정답 | 파일 수 |", "|---|---:|"]
    lines += [f"| {k} | {v:,} |" for k, v in split["counts"].items()]
    lines += ["", "AIHUB와 VITS-AIHUB는 화자 식별자 및 중복 연결 그룹을 묶어 70/15/15 해시 분할합니다. 나머지 생성기는 전부 test에 배치했습니다. 원문 관계가 불완전해 문장 독립성을 보장하지 않습니다. SNS 출처는 제외했습니다. 메타데이터 MeloTTS_와 실제 MellowTTS_의 철자 불일치 100개는 숫자 ID를 유지해 연결했습니다.", "",
              "## 전체 한국어 test 성능", "", "| 모델 | 전체 수 | 합성 탐지율(전체 합성) | 오탐률(판별 실제) | 정확도(판별분) | 보류 | 오류 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name, m in report["overall"].items():
        lines.append(f"| {name} | {m['total']} | {pct(m['synthetic_detection_rate_all'])} | {pct(m['fpr'])} | {pct(m['accuracy'])} | {sum(m['abstained'].values())} | {m['errors']} |")
    lines += ["", "xlsr는 기존 기본 정책(0.5), v2는 고정 영어 학습 후보, v4는 한국어 train만 학습하고 calibration에서 후보와 임계값을 고정한 결과입니다. test를 보고 다시 선택하지 않았습니다.", "", "## 출처별", "",
              "| 출처 | 모델 | 수 | 합성 탐지율(전체) | 오탐률 |", "|---|---|---:|---:|---:|"]
    for s, models in report["by_source"].items():
        for name, m in models.items():
            lines.append(f"| {s} | {name} | {m['total']} | {pct(m['synthetic_detection_rate_all'])} | {pct(m['fpr'])} |")
    lines += ["", "각 출처가 한 정답만 포함하면 해당하지 않는 지표는 —입니다. 생성기별 성능을 전체 평균과 함께 봐야 합니다.", "", "## 고정 소규모 강건성 시험", "",
              "출처×정답별 SHA 정렬 첫 16개. 별도 독립 코퍼스가 아닙니다. 길이가 부족한 crop은 제외합니다.", "",
              "| 조건 | 모델 | 평가 수 | 길이부족 제외 | 전체 합성 탐지율 | 오탐률 |", "|---|---|---:|---:|---:|---:|"]
    for c, block in report["robustness"].items():
        for name, m in block["metrics"].items():
            lines.append(f"| {c} | {name} | {m['total']} | {block['skipped']} | {pct(m['synthetic_detection_rate_all'])} | {pct(m['fpr'])} |")
    lines += ["", "## 한계 / 배포 판단", "", f"사전 정의 품질 기준 통과: {report['quality_gate']['passed']}. 기준: 전체 합성 탐지율≥80%, 오탐≤5%, 각 미학습 생성기 탐지율≥50%, 오류0, 판별비율100%. 품질 기준과 별개로 비상업 연구 후보이며 기본 모델은 유지합니다.", "",
              "- 비상업 연구용으로만 사용합니다. 새로운 기본 프로필로 자동 승격하지 않습니다.",
              "- VITS-AIHUB가 합성 표본의 대부분입니다. 2024년 자료로 최신 한국어 생성기를 모두 대표하지 않습니다.",
              "- 메타데이터 화자 ID만 사용했으며 실제 화자 신원과 문장·합성 참조 관계를 독립 검증하지 못했습니다. 사전학습 데이터 중복도 불명확합니다.",
              "- 8kHz 왕복과 백색 잡음은 실제 통화 코덱·재녹음이 아닙니다. 실제 통화 환경 검증은 남아 있습니다.",
              "- 원본 음성·임베딩·개인 절대 경로는 공개하지 않았습니다. 작은 학습 분류기와 예측·분할·환경·체크섬만 공개합니다.", "",
              "## 재현", "", "D:의 로컬 음성 데이터를 사용해 prepare_dsd.py → prepare_dsd_korean.py → train_dsd_korean.py → evaluate_dsd_korean.py → archive_dsd_korean.py 순으로 실행합니다. 각 단계의 잠금 파일을 삭제해 결과를 덮어쓰지 마세요.", "",
              "출처: [DSD-Corpus](https://zenodo.org/records/13788455), [NAVER AASIST](https://github.com/clovaai/aasist). 메타데이터와 다운로드 해시는 metadata.json 및 download-receipts.json을 참고하세요."]
    body = ("\n".join(lines) + "\n").encode("utf-8")
    write_once(dest / "README.md", body)
    write_once(ROOT / "releases/v0.4.0-detection.1.md", body)
    json_once(dest / "checksums.json", {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.name != "checksums.json"})
    print(body.decode("utf-8"), flush=True)


if __name__ == "__main__":
    main()
