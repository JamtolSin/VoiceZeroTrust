# 합성 음성 탐지 평가

이 도구는 **실제 발화(real) / 교육용 합성(synthetic)** 이진 탐지를 평가합니다. 합성 여부는 사기 의도와 다릅니다. 실제 사람이 하는 보이스피싱, 내용 패턴 규칙, ASR 정확도, 워터마크 검출은 이 지표에 포함하지 않습니다.

## 배치와 한 번의 전체 실행

```text
src/evaluation/        데이터 수집, 쌍 생성, 평가, 지표
scripts/evaluate.py   collect / build / run 명령
scripts/smoke_evaluation.py  MP3 변환 → 새 합성 → 실제 탐지
tests/                가짜 엔진을 이용한 회귀 테스트
.runtime/evaluation/  원본 manifest, 파생 WAV, 라벨, 결과 (Git 제외)
```

저장소 루트 PowerShell에서 실행합니다. 기존 환경과 모델 설치가 필요하며 첫 모델 로드는 다운로드가 발생할 수 있습니다.

```powershell
.venv\Scripts\python.exe scripts/smoke_evaluation.py
.venv\Scripts\python.exe -m pytest -q
```

Smoke는 `scripts/smoke_qwen.py`가 받은 공식 데모 참조 WAV를 MP3로 변환하고, Qwen으로 고정된 한국어 교육 문장을 **새로 생성**합니다. 원본/합성 모두 mono 16 kHz PCM WAV로 통일한 뒤 실제 XLS-R 탐지 모델을 실행합니다. 합성과 탐지는 별도 프로세스여서 모델 메모리를 해제합니다. 출력 디렉터리는 매번 새로 생성합니다.

`predictions.json`에서 정답 label, score, prediction, O/X, 구간별 점수를 확인합니다. O는 정답과 일치, X는 오분류입니다. **X라도 프로그램 자체는 정상 완료될 수 있습니다.** 오류·무음 등은 보류이며 정상 음성으로 간주하지 않습니다. `report.json`의 pipeline_ok와 all_classified도 함께 확인하세요. CLI 종료 코드 2는 생성/탐지 오류 또는 보류를 뜻하며, 오분류 자체는 종료 오류가 아닙니다.

## 여러 화자 수집 → 라벨 생성 → 성능 측정

사용 동의와 합성·평가 이용 권한을 확보한 **실제 발화만** 다음처럼 배치합니다. 웹이나 타인의 통화를 무단 수집하지 않습니다. `.txt`에는 음성과 정확히 같은 대사를 적습니다. 2~30초, 20 MB 이하가 쌍 생성 입력 조건입니다.

```text
.runtime/evaluation/inbox/
  speaker-001/
    recording.mp3
    recording.txt
  speaker-002/
    recording.wav
    recording.txt
```

```powershell
.venv\Scripts\python.exe scripts/evaluate.py collect .runtime/evaluation/inbox .runtime/evaluation/sources.jsonl --consent --rights "합성 및 로컬 평가에 동의한 자체 녹음" --source "동의서 관리번호 또는 출처"
.venv\Scripts\python.exe scripts/evaluate.py build .runtime/evaluation/sources.jsonl .runtime/evaluation/dataset-v1 --accept-model-license
.venv\Scripts\python.exe scripts/evaluate.py run .runtime/evaluation/dataset-v1/manifest.jsonl .runtime/evaluation/results-v1 --split test --threshold 0.5
```

`collect`는 파일을 복사하거나 인터넷에서 다운로드하지 않습니다. 화자 폴더명 해시로 validation 약 20%, test 약 80%를 고정 배정합니다. 작은 수에서는 한 split이 비어 있을 수 있으므로 manifest 분포를 확인하세요. 한 화자의 별칭을 여러 개 쓰면 누수를 막을 수 없습니다. 학습 데이터와 평가 화자 분리는 별도 확보해야 합니다.

`build`는 각 원본마다 real/synthetic 쌍과 라벨·출처·원본 해시·생성 모델명을 기록합니다. 실패는 build.json에 남기고 해당 쌍을 라벨 목록에서 제외하므로 **요청 수와 완료 수를 반드시 함께 보고**하세요. 성공 파일은 중간 체크포인트에 남습니다. 반복 실행에는 새 출력 폴더를 사용하세요.

외부의 권한 있는 라벨 데이터셋은 아래 JSONL 스키마로 직접 가져와 `run`할 수 있습니다. 경로는 manifest 기준 상대 경로 또는 절대 경로입니다. 라벨은 탐지 결과로 만들지 말고 출처/생성 이력으로 확정합니다.

```json
{"id":"unique-id","path":"speaker-001/recording.wav","label":"real","speaker_id":"speaker-001","split":"test","consent":true,"source":"출처","rights":"평가 이용 근거"}
```

쌍 생성에는 transcript가 추가로 필요합니다. 동일 파일 중복, checksum 변경, 화자별 split 혼합은 거절합니다. 재인코딩 중복이나 기존 모델의 학습 데이터 중복까지 자동 판별하지는 않습니다.

## 지표 해석과 실험 조건

- TP/FN/FP/TN, 재현율(검출률), 미탐률, 오탐률, 정밀도, 정확도, 균형 정확도, 분류 커버리지를 기록합니다. 계산 불가능한 값은 null입니다.
- 기본 지표는 분류된 파일만 대상으로 계산합니다. `synthetic_detection_rate_all`은 보류·오류까지 포함한 전체 합성 파일을 분모로 쓰므로 함께 보고해야 합니다.
- 기본 임계값 0.5는 미보정 실험값입니다. validation에서 정책을 정한 다음 고정하고 test는 한 번 평가하세요. test 점수를 보고 임계값을 맞추면 성능이 부풀려집니다.
- 공식 smoke의 영어 원본/한국어 합성 한 쌍은 내용·언어·길이가 달라 일반 성능 추정에 부적합합니다. 통제 평가에는 사람이 `src/service.py`의 PHRASE를 직접 읽은 녹음을 사용하세요. 원본과 합성에 동일 코덱·통화 변환을 적용하고 별도 조건으로 보고하세요.
- 많은 파일뿐 아니라 독립 화자, 한국어/억양, 마이크, 소음, 2/3/5초 길이, 미학습 생성기 다양성이 필요합니다. 현재 builder는 Qwen 한 생성기만 평가하므로 다른 생성기로의 일반화는 주장할 수 없습니다. 워터마크 유무를 합성 라벨과 혼동하지 마세요.
- 모델 출력 score는 사기 확률이 아닙니다. 탐지기만으로 신원 인증·송금을 승인하면 안 됩니다.

음성과 대사·경로는 로컬 결과에 남습니다. `.runtime`은 Git 제외지만 현재 위치가 OneDrive 내부이므로 OS 동기화는 별도 설정으로 통제해야 합니다. 자동 대량 수집, 제삼자 재배포, 개인정보 업로드는 수행하지 않습니다.
