# XLS-R × Stafford v4 — 2026-09-12

탐지 파이프라인 버전: **v0.1.0-detection.1**, 실험용 사전 릴리스. 새로 학습한 모델 버전이 아닙니다.

| 항목 | 식별자 |
|---|---|
| 날짜 | 2026-09-12, Asia/Seoul (정확한 최초 시작 시각은 미기록) |
| 모델 | Gustking/wav2vec2-large-xlsr-deepfake-audio-classification |
| 모델 revision | f7050b586236dc910d1157f430def2d0647b02b4 |
| 데이터셋 | garystafford/deepfake-audio-detection v4 |
| 데이터 revision | fcf5344bb7f82b54b6b932291326d29750ef1e82 |
| 임계값 | 0.5, 결과 확인 후 변경하지 않음 |

- [RESULTS.md](RESULTS.md): 표, 실험 조건과 한계
- [metadata.json](metadata.json): 날짜·버전·모델·데이터·환경 식별 정보
- [report.json](report.json): 전체/중복 제거/생성 서비스별 지표
- [predictions.jsonl](predictions.jsonl): 1,866개 라벨·점수·O/X, 공개 데이터셋 파일명 및 해시 (음성/개인 경로 제외)
- [checksums.json](checksums.json): 보관 파일 SHA-256

중복 제거 기준: 1,650개, 검출률 **70.83%**, 미탐률 **29.17%**, 오탐률 **21.83%**, 정확도 **74.97%**.
영어 합성 여부 평가이며 한국어 보이스피싱 검출률이 아닙니다. 실제 음성은 14개 원본 녹음의 파생 클립이며 학습 데이터 중복 가능성을 배제하지 못합니다. 단독 차단용으로 권장하지 않습니다.

데이터 출처: Gary Stafford, [Deepfake Audio Detection Dataset v4](https://huggingface.co/datasets/garystafford/deepfake-audio-detection), CC-BY-4.0. 데이터셋 제작자의 라벨과 라이선스 표기를 근거로 평가했으며 음성 파일은 재배포하지 않습니다.
