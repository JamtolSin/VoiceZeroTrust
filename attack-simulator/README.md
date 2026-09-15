# VoiceShield Attack Simulator

본인 음성 10초로 Voice Cloning 위험을 확인하는 보안 교육용 Next.js 애플리케이션이다. 기존 VoiceZeroTrust의 Python 탐지·방어 구현과 독립적으로 설치, 테스트, 빌드 및 배포한다.

## 현재 구현

- 본인 음성 및 외부 Provider 처리 동의
- 브라우저 마이크 10초 자동 녹음
- 16kHz 모노 PCM WAV 변환
- 서버의 WAV 구조, 크기, 길이, RMS 및 peak 검증
- 서버 고정 안전 문장 3개
- 실제 처리 단계 NDJSON 스트리밍
- 교체 가능한 Fish Audio/Mock Provider
- Fish Audio private fast clone, TTS 및 Clone 삭제 재시도
- 원본/생성 음성 A/B 재생과 실제 처리 시간
- 동일 출처 검사, 요청 제한, 민감정보를 제외한 오류 로그
- 모바일/데스크톱 반응형 UI

Mock Provider는 실제 음성을 복제하지 않고 합성 톤을 반환한다. UI와 API 전체 흐름을 비용 없이 검증하기 위한 개발 모드다.

## 로컬 실행

Node.js 22.12 이상이 필요하다.

```bash
cd attack-simulator
npm install
cp .env.example .env.local
npm run dev
```

브라우저에서 `http://localhost:3000`을 열고 마이크 권한을 허용한다. 로컬 HTTP의 마이크 접근은 `localhost`에서 지원된다.

## Fish Audio 실제 모드

`.env.local`에 다음 값을 설정한다.

```dotenv
VOICE_PROVIDER=fish-audio
FISH_AUDIO_API_KEY=replace_me
FISH_AUDIO_MODEL=s2.1-pro-free
FISH_AUDIO_TIMEOUT_MS=120000
```

API Key는 [Fish Audio API Keys](https://fish.audio/app/api-keys/)에서 발급하며 저장소에 커밋하지 않는다. 현재 연동은 공식 API의 private fast model 생성, TTS, model 삭제 엔드포인트를 사용한다.

## 검증

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

Health endpoint는 `GET /api/health`다. 실제 Provider 호출에는 API Key와 동의된 본인 음성이 필요하므로 자동 테스트는 Provider 대역을 사용한다.

## 데이터 흐름

브라우저는 녹음을 WAV로 변환하고 단일 `POST /api/attack/run` 요청으로 전송한다. 서버는 상태를 NDJSON으로 스트리밍하며, Fish Audio에서 생성 결과를 받은 뒤 private Clone을 삭제한다. 원본과 생성 음성을 애플리케이션 파일시스템이나 DB에 저장하지 않는다.

브라우저는 응답으로 받은 생성 음성을 메모리 Blob URL로 재생한다. 사용자가 종료하거나 페이지를 닫으면 Blob URL을 해제한다.

## 문서

- [MVP 기획서](docs/mvp-plan.md)
- [구현 상태와 미완료 항목](docs/implementation-status.md)
