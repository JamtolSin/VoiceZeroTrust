# 실험 결과 인덱스

폴더 규칙: `YYYY-MM-DD/<model-short-name>-<model-revision>__<dataset-version>-<dataset-revision>/`.
성능 수치와 원시 예측을 함께 보존하며, 모델·데이터셋 revision은 각 metadata.json에 전체 SHA로 기록합니다.
음성 원본, 전사문, 로컬 절대 경로는 게시하지 않습니다.

| 실험 날짜 (KST) | 탐지 버전 | 모델 | 데이터셋 | 결과 |
|---|---|---|---|---|
| 2026-09-12 | v0.1.0-detection.1 (사전 릴리스) | XLS-R / f7050b5 | Stafford v4 / fcf5344 | [1,866개 실측](2026-09-12/xlsr-f7050b5__stafford-v4-fcf5344/README.md) |
| 2026-09-12 | v0.2.0-detection.1 (연구용, 기본 승격 실패) | AASIST + 학습 head / a04c986 | DeepVoice / 50b1b3b | [5,053개 외부 평가 및 짧은 입력 비교](2026-09-12/aasist-head-a04c986__deepvoice-50b1b3b/README.md) |
