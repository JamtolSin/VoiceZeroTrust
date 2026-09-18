# Vercel 웹 + 촬영용 GPU 서버

`web/`은 Vercel 정적 프런트엔드이며, `backend/web_api.py`는 기존 모델 서비스를 호출하는 인증된 비동기 API다. Android LAN 통화 서버는 기존 구성으로 유지한다.

## 실행

저장소 루트에서 Python 환경에 `backend/requirements-web.txt`를 설치한다. NVIDIA GPU에서는 torch/torchaudio 2.8.0 CUDA 12.8 빌드를 사용한다.

```powershell
$env:VZT_WEB_TOKEN = '<32자 이상 무작위 연결 키>'
$env:VZT_WEB_ORIGINS = 'https://voice-zero-trust.vercel.app'
python scripts/start_web_demo.py
cloudflared tunnel --url http://127.0.0.1:8766
```

생성된 HTTPS 주소를 `web/config.js`에 넣거나 서비스 화면의 모델 서버 주소 칸에 입력한다. 연결 키는 화면에서 입력하며 정적 파일·Git·스크린샷에 포함하지 않는다. 입력 음성은 HTTPS 터널을 거쳐 운영 PC로 전달된다. 공개 음성 자료 또는 동의된 실험용 음성만 사용한다.

```powershell
cd web
npx vercel --prod --yes
```

Vercel GitHub 앱의 저장소 접근 권한이 없으면 CLI 배포를 사용한다. 이 경우 main push의 자동 배포는 설정되지 않는다.

## 동작 및 수명

- API는 연결 키를 모든 요청에서 검증하고, 허용한 웹 출처에만 CORS를 제공한다.
- 파일은 최대 20MB, 모델 작업은 한 번에 한 개다. 실행 중 추가 요청은 409로 거절한다.
- 합성은 Qwen의 기존 고정 교육 문장만 사용한다. 정확한 참조 대사와 음성·모델 조건 확인이 필요하다.
- 탐지는 기본 XLS-R, 영어 후보 v2, 명시적으로 연구 용도를 확인한 한국어 후보 v4를 제공한다.
- 입력 임시 파일은 작업 종료 시 제거한다. 결과는 서버 메모리에 보관하며 15분 경과 후 다음 요청에서 정리된다. 서버 종료 시 결과가 사라진다.
- 브라우저의 연결 키는 페이지 메모리에만 존재한다. 결과 음성은 페이지를 닫을 때까지 브라우저에서 재생할 수 있다.
- Quick Tunnel은 촬영용 임시 주소다. PC·API·터널이 종료되면 실시간 기능은 연결되지 않으며 웹 화면과 저장된 평가 결과는 계속 열린다.
- 촬영 종료 후 API와 터널 프로세스를 종료한다. 재시작 시 새 주소를 웹에 설정하고 연결 키를 새로 생성한다.

성능 비교는 2026-09-13 고정 실험 기록이다. 배포된 모델의 새 요청 결과와 별개이며 실시간 성공 결과로 대체하거나 꾸미지 않는다.
