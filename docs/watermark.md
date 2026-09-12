# AudioSeal 출처 표식 실험

`python watermark_app.py`로 http://127.0.0.1:7862 에서 실행합니다.
기존 합성 앱과 독립적으로 실행되며 모델은 요청할 때 CPU에 한 번 로딩합니다.
`pip install -e .` 후 `pip install -r requirements-watermark.txt`로 선택 의존성을 설치합니다. 첫 요청은 공식 모델 가중치를 다운로드하므로 네트워크가 필요합니다.

교육용 합성 출력에 16비트 공개 태그 `0x565A`를 삽입합니다. 저장한 PCM WAV를 다시 읽어 검출하고 결과와 JSON manifest를 `.runtime/watermark`에 보관합니다. 업로드 원본은 수정하지 않으며 디코딩 임시 파일은 요청 종료 시 삭제합니다. 출력 파일은 사용자가 삭제할 때까지 남습니다. 원본 녹음·출력·캐시는 Git에 포함하지 않습니다.

검출의 `score`는 AudioSeal 고수준 API 점수이며 사기 확률이 아닙니다. 실험 임계값은 0.5이며 정상·압축·재녹음 데이터의 오경보율을 측정하기 전에는 실서비스 차단에 사용하면 안 됩니다. `education_tag_matches`는 표식 검출 및 공개 태그 일치를 뜻할 뿐 등록 사용자나 발화자의 신원을 보증하지 않습니다. 공개 태그는 누구나 복제할 수 있으며 암호학적 서명이 아닙니다. 미검출은 실제 음성이라는 증거가 아닙니다. 원본에 삽입한 일반 AudioSeal 표식이 목소리 복제 결과에 남는다는 보장도 없습니다.

현재 UI 입력은 2~30초/20MB이며 MP3, WAV, M4A, AAC, OGG, WebM, FLAC을 공통 디코더로 검사합니다. 음향 사기 탐지기와 독립되어 있어 워터마크만으로 사기 레이블을 학습하지 않습니다.

공식 구현 및 API: https://github.com/facebookresearch/audioseal
모델: `audioseal_wm_16bits`, `audioseal_detector_16bits` (AudioSeal 0.2).
단위 테스트는 주입한 backend로 파일 처리·표식 의미·오류 정리를 검사하며 모델 정확도 증거가 아닙니다.
