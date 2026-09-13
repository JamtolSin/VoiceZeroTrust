# 한국어 연구 파이프라인

비상업 연구·평가 전용입니다. 사용자 승인에 따라 원본 데이터는 `D:\VoiceZeroTrust-data\dsd-corpus-v1`에 보관하며, Git과 릴리즈에는 음성 및 음성 임베딩을 포함하지 않습니다.

## 재현 순서

```powershell
.venv\Scripts\python.exe scripts/prepare_dsd.py --noncommercial-research --download-audio --output D:\VoiceZeroTrust-data\dsd-corpus-v1
.venv\Scripts\python.exe scripts/prepare_dsd_korean.py --root D:\VoiceZeroTrust-data\dsd-corpus-v1
.venv\Scripts\python.exe scripts/train_dsd_korean.py --data D:\VoiceZeroTrust-data\dsd-corpus-v1\korean-v4
.venv\Scripts\python.exe scripts/evaluate_dsd_korean.py --data D:\VoiceZeroTrust-data\dsd-corpus-v1\korean-v4
.venv\Scripts\python.exe scripts/archive_dsd_korean.py --data D:\VoiceZeroTrust-data\dsd-corpus-v1\korean-v4
.venv\Scripts\python.exe scripts/smoke_dsd_korean.py --data D:\VoiceZeroTrust-data\dsd-corpus-v1\korean-v4 --device cuda:0
```

동일 출력 경로에서 동시에 두 프로세스를 실행하지 마세요. 다운로드는 검증한 부분 파일을 이어받지만, split/selection/test 잠금이 생긴 뒤 설정을 바꿔 같은 실험에 덮어쓰는 것은 거절합니다.

## 구조와 평가 범위

- 다운로드: 6개 병렬 HTTP 범위 요청, 제공 MD5와 로컬 SHA-256 검증. 기존 파일은 자동 덮어쓰지 않습니다.
- 압축 해제: 분할 ZIP 안의 저장형 ZIP을 읽기 전용으로 연결해 한국어 후보만 추출. 경로 순회·크기·디코딩 검사와 ZIP CRC 검증을 수행합니다.
- 자료 정제: SNS 출처 제외. 실제 데이터의 파일·PCM 중복 및 라벨 충돌을 검사합니다. 파일명이 모호하거나 누락되면 제외 목록에 기록합니다.
- 분할: AIHUB/VITS-AIHUB 화자 식별자 및 중복 연결 그룹으로 70/15/15 해시 분할. 다른 생성기는 모두 test. 실제 화자와 텍스트 관계를 독립 확인한 것은 아닙니다.
- 학습: 공식 AASIST 본체 고정. 깨끗한 음성 분류기와 잡음/대역 제한 증강 분류기를 train에서만 학습. calibration에서 오탐 5% 이내 최고 탐지율 후보를 선택합니다.
- 최종 시험: 기존 XLS-R, v2, 고정 v4 후보를 동일한 테스트 음성으로 비교. 학습·추론은 앱과 같은 FFmpeg 16kHz mono 변환을 사용합니다. SciPy PCM 해시는 데이터 중복 검사에만 사용합니다. 서로 다른 코퍼스의 수치를 직접 비교하지 않습니다.
- 강건성: 출처×라벨별 SHA 정렬 첫 16개로 소규모 고정 부분집합을 만듭니다. 8kHz 왕복·20dB 백색 잡음·2/3/5초 입력을 시험합니다.

현재 작업은 상용 모델·완전한 보이스피싱 방지 시스템을 완성하는 것이 아닙니다. 실제 통화 코덱·현장 재녹음·최신 생성기 독립 시험 및 출처 권리 추가 확인은 별도 과제입니다. 연구 결과가 좋아도 기본 모델을 자동 교체하지 않습니다.

앱에서는 한국어 연구 후보 v4를 명시적으로 선택하고 비상업 연구·평가 사용 범위를 확인해야 실행할 수 있습니다. 기본값은 기존 XLS-R입니다.

마지막 smoke 검사는 실제·합성 시험 음성 각 1개를 앱의 서비스 경로로 실행해 WAV 점수가 벤치마크와 일치하는지 확인하고, 임시 MP3 변환 파일도 정상 분석하는지 확인합니다. 두 파일의 기능 확인이며 추가 정확도 측정은 아닙니다. 변환 파일은 종료 시 삭제합니다.

## 2026-09-13 실행 결과

| 같은 한국어 test 4,660개 | 합성 탐지율 | 실제 음성 오탐률 | 정확도 |
|---|---:|---:|---:|
| 기존 XLS-R | 53.72% | 0.00% | 77.55% |
| 영어 학습 v2 | 37.65% | 86.46% | 25.24% |
| 한국어 학습 v4 | 91.24% | 3.29% | 94.06% |

원본 전체 시험에서는 세 모델 모두 오류·보류 0입니다. v4가 전체 평균에서는 개선됐지만 MMSTTS 합성 탐지율이 13%여서 사전 품질 기준에 실패했습니다. 잡음 20dB 부분집합에서는 실제 음성 오탐률이 75%(12/16)입니다. 연구 후보로만 공개하며 사용자를 보호하는 실전 차단 모델로 승격하지 않습니다.

짧은 입력 시험은 길이 부족 표본을 제외하므로 2/3/5초별 구성이 다릅니다. 특히 AASIST는 첫 약 4초만 분석하므로 5초 표의 하락을 "더 길면 나빠진다"고 해석하면 안 됩니다. 각 길이의 표본 수·보류를 포함한 상세 값은 [잠긴 실험 결과](../experiments/2026-09-13/aasist-korean__dsd-v1-grouped/README.md)를 참고하세요.

검증: 127개 자동 테스트 통과. 실제·합성 각 1개 WAV의 앱 서비스 점수와 벤치마크 점수 차이는 0이었고, 두 파일의 MP3 변환본도 정상 분석됐습니다. 학습·보정·시험 자료의 그룹 및 PCM 중복 검사, 전체/출처별/강건성 지표 재계산, 공개 파일 체크섬 및 연구 사용 확인을 검증했습니다.

다음 연구는 MMSTTS처럼 현재 약한 생성기와 잡음 있는 실제 음성을 **새 학습·보정 자료**로 확보하는 것입니다. 현재 test는 회귀 시험으로 고정하고, 추가 개선의 최종 성능은 별도 새 holdout에서 측정해야 합니다. 현재 시험 결과에 맞춰 후보나 임계값을 다시 고르지 않았습니다.
