# v0.2.0-detection.1 연구 후보

이번 버전은 후보 비교·동결 분류기 학습·독립 외부 평가를 실제 수행한 연구 스냅샷입니다. 외부 데이터의 오탐률이 승격 기준을 넘었으므로 기본 XLS-R은 유지합니다. 성능 개선 완료나 한국어 추가 학습 완료를 의미하지 않습니다.

## 실행

```powershell
.venv\Scripts\python.exe detection_app.py
```

탐지 프로필에서 **기준 모델 · XLS-R** 또는 **연구 후보 · AASIST + 학습 분류기**를 선택합니다. 후보는 처음 실행할 때 고정된 공식 NAVER 코드/가중치를 다운로드하고 SHA-256을 검증합니다. Python 소스는 검증된 고정 revision만 로드하며 가중치는 weights_only=True로 읽습니다. 음성은 외부 추론 API로 전송하지 않습니다.

후보의 고정 임계값은 0.7676075931865732입니다. 출력은 '합성 의심 / 합성 근거 부족 / 판단 보류'이며, '합성 근거 부족'은 실제 사람이나 본인임을 인증하지 않습니다. 후보는 공식 AASIST 전처리대로 첫 64,600샘플(16kHz 약4초)을 사용하고 짧으면 반복 패딩합니다. 이후 구간은 분석하지 않았음을 coverage/skipped 필드에 표시합니다.

## 재현 순서

기존 Stafford 준비가 완료된 환경에서 실행합니다. 아래는 Windows/Python3.13 환경에서 검증했습니다. 평가 의존성은 `pip install -e ".[evaluation]"`로 설치할 수 있습니다.

```powershell
.venv\Scripts\python.exe scripts/prepare_deepvoice.py
.venv\Scripts\python.exe scripts/compare_detectors.py
.venv\Scripts\python.exe scripts/select_detector.py
.venv\Scripts\python.exe scripts/evaluate_holdout.py
.venv\Scripts\python.exe scripts/evaluate_robustness.py
.venv\Scripts\python.exe scripts/archive_detection_v2.py
.venv\Scripts\python.exe -m pytest -q
```

selection.json 생성 후 재학습/재선택은 거절됩니다. 결과를 본 후 같은 holdout에 맞춰 다시 학습하지 마세요. 새 실험은 새 출력 디렉터리·새 독립 최종 평가 코퍼스와 식별자가 필요합니다. 비교 도구의 checkpoint는 현재 고정된 모델/설정 전용이며 다른 설정과 섞으면 안 됩니다.

## 보관 결과

[성능표와 모든 예측](../experiments/2026-09-12/aasist-head-a04c986__deepvoice-50b1b3b/README.md)에 날짜·모델/데이터 revision·환경·분할·선택 정책·체크섬을 기록했습니다. 원본 음성, 개인 경로, 전사문, 음성 임베딩은 Git에 포함하지 않습니다. 학습한 작은 분류기 파라미터는 src/detection/profiles/v2-candidate.json에 있습니다.

## 후속 조건

- 한국어 추가 학습: 이용 권한과 합성·평가 동의를 확인한 코퍼스 확보 필요. 조사한 DSD-Corpus는 비상업 조건이며 KoAAD는 이용 조건 추가 확인 필요.
- 새 생성기·실제 통화 조건: 현재 DeepVoice는 영어 RVC이며 최신 한국어 생성기 대표성이 없습니다.
- 통화 증강 학습/앙상블: 이번 결과를 보고 바로 holdout에 맞추지 말고 새 학습·검증 데이터와 최종 test 분리 후 진행합니다.
- 이슈 #7은 완료로 닫지 않습니다. 후보의 외부 FPR 49.36%는 단독 차단에 부적합하며 새 버전은 연구용입니다.
