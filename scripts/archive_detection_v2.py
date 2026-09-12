"""Publish auditable v2 research results, not audio or voice embeddings."""
import hashlib
import json
from pathlib import Path
import sys
from importlib.metadata import version

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RUN = "2026-09-12/aasist-head-a04c986__deepvoice-50b1b3b"
RELEASE = "v0.2.0-detection.1"


def pct(value):
    return "—" if value is None else f"{value*100:.2f}%"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    import numpy as np
    from src.evaluation.pipeline import write_json
    from src.evaluation.metrics import summarize
    from src.detection.aasist import REVISION, FILES, LICENSE
    source = ROOT / ".runtime/evaluation/detection-v2"
    dest = ROOT / "experiments" / RUN
    dest.mkdir(parents=True,exist_ok=True)
    selection = json.loads((source/"selection.json").read_text(encoding="utf-8"))
    holdout = json.loads((source/"holdout-report.json").read_text(encoding="utf-8"))
    rows = json.loads((source/"holdout-predictions.json").read_text(encoding="utf-8"))
    robustness = json.loads((source/"robustness-report.json").read_text(encoding="utf-8"))
    sha = hashlib.sha256((source/"selection.json").read_bytes()).hexdigest()
    if sha != holdout["lock"]["selection_sha256"] or sha != robustness["spec"]["selection_sha256"] or len(rows)!=5053:
        raise ValueError("Incomplete/mismatched experiment")
    for name, candidate in holdout["candidates"].items():
        measured = summarize([{"label":r["label"],"score":r["scores"][name],"error":r["errors"].get(name)} for r in rows],selection["candidate_policies"][name]["threshold"])
        if measured != candidate["at_validation_threshold"]:
            raise ValueError("Archived metrics do not match predictions")
    name = selection["selected"]
    baseline = holdout["candidates"]["xlsr"]["at_0.5"]
    candidate = holdout["candidates"][name]["at_validation_threshold"]
    profile = {**selection["policy"], "release":RELEASE, "promotion_passed":holdout["promotion_gate"]["passed"],
               "limitations":["한국어 추가 학습 및 성능은 미검증", "실험용이며 기본 프로필로 자동 승격하지 않음", "처음 약 4초만 분석; 음성 신원 인증이 아님"],
               "source_selection_sha256":sha,"backbone_revision":REVISION}
    profile_path = ROOT / "src/detection/profiles/v2-candidate.json"
    profile_path.parent.mkdir(parents=True,exist_ok=True)
    write_json(profile_path,profile)
    # Small-group bootstrap: source speaker (8 groups), not independent clips.
    group_names = sorted({r["source_speaker_id"] for r in rows})
    vectors=[]
    for group in group_names:
        vectors.append([])
        for model, threshold in [("xlsr",.5),(name,selection["policy"]["threshold"])]:
            m=summarize([{"label":r["label"],"score":r["scores"][model],"error":r["errors"].get(model)} for r in rows if r["source_speaker_id"]==group],threshold)
            vectors[-1].append([m["confusion"][k] for k in ["tp","fn","fp","tn"]])
    values=np.asarray(vectors)
    rng=np.random.default_rng(20260912)
    intervals=[]
    for _ in range(2000):
        confusion=values[rng.integers(0,len(values),len(values))].sum(axis=0)
        tp,fn,fp,tn=confusion.T
        intervals.append([*(tp/(tp+fn)),*(fp/(fp+tn))])
    bounds=np.percentile(intervals,[2.5,97.5],axis=0)
    bootstrap={"groups":len(group_names),"grouping":"source speaker inferred from filename", "repetitions":2000,"seed":20260912,
               "warning":"Only eight correlated source speakers; exploratory intervals, not population guarantees",
               "baseline_recall_95":bounds[:,0].tolist(),"selected_recall_95":bounds[:,1].tolist(),
               "baseline_fpr_95":bounds[:,2].tolist(),"selected_fpr_95":bounds[:,3].tolist()}
    write_json(dest/"group-bootstrap.json",bootstrap)
    metadata={"release":RELEASE,"experiment_date":"2026-09-12","timezone":"Asia/Seoul","timestamp_precision":"date",
              "selected_candidate":name,"baseline_revision":"f7050b586236dc910d1157f430def2d0647b02b4",
              "backbone_revision":REVISION,"official_assets_sha256":FILES,"policy_sha256":sha,
              "development_dataset":"garystafford/deepfake-audio-detection","development_revision":"fcf5344bb7f82b54b6b932291326d29750ef1e82",
              "holdout_dataset":holdout["dataset"]["dataset"],"holdout_revision":holdout["dataset"]["revision"],
              "versions":{p:version(p) for p in ["torch","transformers","numpy","scipy","scikit-learn","soundfile","pyarrow"]},
              "hardware":"NVIDIA RTX 3080; Windows; Python 3.13", "default_profile":"baseline",
              "promotion_gate":holdout["promotion_gate"],"pending":["Korean corpus authorization/adaptation","unseen Korean final test","codec/noise/real rerecording training","ensemble if justified by independent evidence"],
              "script_sha256":{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ["scripts/compare_detectors.py","scripts/select_detector.py","scripts/evaluate_holdout.py","scripts/evaluate_robustness.py","src/detection/aasist.py"]}}
    write_json(dest/"metadata.json",metadata)
    for filename in ["selection.json","development-split.json","holdout-report.json","holdout-lock.json","robustness-report.json","robustness-spec.json","robustness-predictions.json"]:
        write_json(dest/filename,json.loads((source/filename).read_text(encoding="utf-8")))
    # Already path-free; do not archive embeddings from development scorer.
    (dest/"holdout-predictions.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in rows),encoding="utf-8")
    (dest/"AASIST-LICENSE.txt").write_text(LICENSE,encoding="utf-8")
    (dest/"DATASET-LICENSE.txt").write_text((ROOT/".runtime/evaluation/deepvoice-holdout/LICENSE.txt").read_text(encoding="utf-8"),encoding="utf-8")
    lines=[f"# 탐지 {RELEASE} — 후보 학습과 독립 코퍼스 평가", "", "## 외부 평가 결과", "",
           "DeepVoice 5,053개(실제 628 / RVC 합성 4,425), 중복 0. 후보/임계값을 고정한 후 전체 평가했습니다. 한국어 평가가 아닙니다.", "",
           "| 모델/운영점 | 검출률(분류분) | 검출률(전체 합성) | 미탐률(분류분) | 오탐률 | 정확도 | 전체 보류(거절 포함) |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    comparisons=[("기존 XLS-R · 0.5",baseline),("XLS-R · validation 임계값",holdout["candidates"]["xlsr"]["at_validation_threshold"])]
    comparisons += [(n+ (" **선택 후보**" if n==name else ""),r["at_validation_threshold"]) for n,r in holdout["candidates"].items() if n!="xlsr"]
    for label,m in comparisons:
        lines.append(f"| {label} | {pct(m['recall'])} | {pct(m['synthetic_detection_rate_all'])} | {pct(m['fnr'])} | {pct(m['fpr'])} | {pct(m['accuracy'])} | {sum(m['abstained'].values())} |")
    lines += ["", "1초 미만 입력 3개(0.358초 2개, 0.69초 1개)가 공통 입력 거절로 기록됐습니다. 모델 추론 예외는 0개입니다. 전체 보류는 이 입력 거절 및 낮은 음량/유효 구간 부족을 포함합니다. 검출률(전체 합성)은 모든 4,425개를 분모로 합니다. 오탐률·정확도는 분류된 파일 기준이며 모델별 보류 수가 달라집니다.",
              f"승격 기준 통과: **{holdout['promotion_gate']['passed']}**. 기준은 외부 FPR≤5%, 검출률이 기존 0.5보다 높음, 오류0, 커버리지100%였습니다.",
              "결과를 보고 다른 후보로 재선택하거나 임계값을 재조정하지 않았습니다. UI 기본 모델은 유지하고 후보는 명시적으로 선택하도록 제공됩니다.", "", "## 개발 validation (최종 test 아님)", "",
              f"기존에 분석한 Stafford 데이터에서 train {selection['split_counts']['train']}개 / validation {selection['split_counts']['validation']}개. 원본 숫자 ID와 중복 해시를 묶어 분리했습니다. 실제 화자/문장 단위 분리 보장은 없으므로 외부 평가와 구분합니다.", "",
              "| 후보 | validation 검출률 | validation 오탐률 | AUC | 임계값 |","|---|---:|---:|---:|---:|"]
    for n,r in selection["reports"].items():
        m=r["validation"]
        lines.append(f"| {n} | {pct(m['recall'])} | {pct(m['fpr'])} | {r['validation_auc']:.4f} | {m['threshold']:.9f} |")
    lines += ["", "분류기만 StandardScaler + L2 LogisticRegression으로 학습했습니다. AASIST 본체는 동결했습니다. train이 포함된 개발 전체의 높은 점수는 일반화 성능으로 제시하지 않습니다.", "", "## 짧은 입력/대역 제한 진단", "",
              "source speaker × 정답별 SHA 정렬 첫 8개로 사전 정의한 부분집합입니다. 같은 코퍼스의 파생 실험이며 독립 표본이 아닙니다. 길이가 부족한 조건은 제외합니다.", "",
              "| 조건 | 평가 / 길이부족 | 기존 검출률 | 후보 검출률 | 기존 오탐률 | 후보 오탐률 |", "|---|---:|---:|---:|---:|---:|"]
    for condition,r in robustness["conditions"].items():
        lines.append(f"| {condition} | {r['eligible']} / {r['skipped']} | {pct(r['baseline']['recall'])} | {pct(r['selected']['recall'])} | {pct(r['baseline']['fpr'])} | {pct(r['selected']['fpr'])} |")
    lines += ["", "8kHz 왕복은 대역 제한 실험일 뿐 실제 통화 코덱/잡음/스피커 재녹음을 대표하지 않습니다.", "", "## 한계 / 미완료", "",
              "- DeepVoice는 영어 8명 원본의 연관 클립이고 RVC 변환만 포함합니다. 모델의 과거 학습 데이터 중복 여부는 완전히 확인되지 않았습니다.",
              "- 실제 사람의 사기 의도는 정답 라벨에 없으므로 보이스피싱 검출률로 해석하지 않습니다.",
              "- 한국어 데이터 추가 학습은 이용 권한이 확인된 코퍼스가 필요해 미수행입니다. 한국어 개선/상용 안전성을 주장하지 않습니다.",
              "- 코덱·잡음·실제 재녹음 증강 학습과 앙상블은 후속 검증 단계입니다. 현재 holdout을 보며 재학습하지 않습니다.",
              "- 그룹 부트스트랩은 group-bootstrap.json에 보관했지만 8개 source group의 탐색적 구간입니다.", "", "## 출처 / 재현", "",
              "AASIST: NAVER Corp., MIT, https://github.com/clovaai/aasist", "",
              "개발: Gary Stafford v4, CC-BY-4.0, https://huggingface.co/datasets/garystafford/deepfake-audio-detection", "",
              "외부 평가: DEEP-VOICE / SpeechAntiSpoofingBenchmarks, 게시 MIT, https://huggingface.co/datasets/SpeechAntiSpoofingBenchmarks/DeepVoice", "",
              "metadata.json에 전체 revision·환경·스크립트 해시를 기록했습니다. selection.json은 holdout 이전 고정 정책입니다. 음성·전사·음성 임베딩·개인 절대 경로는 게시하지 않습니다."]
    text="\n".join(lines)+"\n"
    (dest/"README.md").write_text(text,encoding="utf-8")
    release_dir=ROOT/"releases"
    (release_dir/f"{RELEASE}.md").write_text(text,encoding="utf-8")
    checksums={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.is_file() and p.name!="checksums.json"}
    write_json(dest/"checksums.json",checksums)
    print(text,flush=True)


if __name__=="__main__":
    main()
