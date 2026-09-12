# 탐지 백엔드

`DetectionService.analyze(path, transcript=None, enable_asr=False, enable_acoustic=False)`는 JSON 직렬화 가능한 `audio`, `acoustic`, `transcription`, `content`, `recommendation` 채널을 반환합니다. 모델은 선택된 분석을 처음 실행할 때 다운로드하고 CPU에 로드합니다. 녹음은 외부 추론 API로 전송하지 않습니다. 다운로드에는 인터넷이 필요하며 모델 캐시는 디스크에 남습니다. 입력 오디오는 20MB, 1~180초로 제한하고 임시 WAV는 요청 종료 때 삭제합니다. 호출자가 제공한 원본 파일은 삭제하지 않습니다.

음향 분류는 [Gustking 모델](https://huggingface.co/Gustking/wav2vec2-large-xlsr-deepfake-audio-classification)을 사용합니다. [공식 config](https://huggingface.co/Gustking/wav2vec2-large-xlsr-deepfake-audio-classification/blob/main/config.json)의 라벨은 0=real, 1=fake입니다. 실제 반환 라벨이 다르면 실패합니다. 5초 구간별 추론 후 분석된 길이로 가중 평균합니다. 1초 미만 꼬리 구간과 RMS 0.003 미만 구간은 제외합니다. fake_score는 보정되지 않은 모델 출력이며 사기 확률이 아닙니다. 한국어, 새 생성기, 재녹음·압축 음성에 대한 성능은 측정하지 않았습니다. 음량 검사는 VAD가 아니므로 음악·잡음도 분류될 수 있습니다.

전사는 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)의 small, CPU int8, 한국어, VAD 설정을 사용합니다. 선택 의존성 `faster-whisper>=1.1,<2`가 필요합니다. 수동 대사를 입력하면 자동 전사보다 우선하며 오디오와 일치한다고 보장하지 않습니다.

내용 분석은 학습 모델이 아닌 공개된 한국어 정규식 규칙입니다. 기관 주장·압박·확인 차단과 자금·설치·인증 정보 요구의 조합을 표시합니다. 인접한 부정·사례 문구는 별도 맥락으로 남기며 문서 전체에 교육이라는 단어가 있어도 모두 무시하지 않습니다. 반어법·인용·다양한 표현과 장거리 문맥은 처리하지 못합니다. 결과의 근거 부족은 정상 판정이 아닙니다. 음향 점수와 내용 신호를 합친 사기 확률을 생성하지 않습니다.

단위 테스트는 다운로드 없이 주입한 모델로 실패 격리, 구간 가중 평균, 잘못된 라벨, 전사 생성기, 내용 조합·부정 표현과 실제 FFmpeg 디코딩을 확인합니다. 이 테스트는 실제 탐지 성능 검증이 아닙니다.
