# Attack Simulator 구현 상태

> 기준일: 2026-09-16

## 완료

- 독립 Next.js 애플리케이션 구조
- Next.js 16, React 19, TypeScript 6, Tailwind CSS 4 고정
- 10초 마이크 녹음과 브라우저 WAV 변환
- 서버 오디오 길이·크기·무음 검사
- 고정 안전 문장과 서버 허용 목록 검증
- 실제 단계 이벤트 스트리밍 API
- Fish Audio Provider Adapter
- Mock Provider 기반 전체 흐름
- Provider Clone 삭제 및 제한된 재시도
- 오류, 취소, 요청 제한과 동일 출처 검사
- 원본/생성 음성 비교 및 실제 시간 표시 UI
- 모바일/데스크톱 반응형 화면
- 단위 테스트, 린트 및 Production 빌드 구성
- 변경 경로에 한정된 GitHub Actions 검증

## 외부 조건 때문에 확인하지 못한 항목

| 항목 | 현재 상태 | 완료에 필요한 조건 |
|---|---|---|
| Fish Audio 실호출 | 미검증 | 유효한 `FISH_AUDIO_API_KEY`, API 사용 가능 크레딧, 동의된 본인 음성 |
| 실제 음성 유사도 | 미측정 | 여러 동의 화자의 평가 샘플과 평가 기준 |
| Vercel Production 배포 | 미배포 | 대상 Vercel 프로젝트와 배포 권한 |
| GitHub Actions 원격 실행 | 미실행 | 변경 사항을 브랜치에 push하거나 PR 생성 |
| 실제 모바일 Safari 마이크 | 미검증 | iPhone 실기기 수동 테스트 |
| 실제 Android Chrome 마이크 | 미검증 | Android 실기기 수동 테스트 |
| Provider 삭제 실패 영구 재시도 | 미구현 | 외부 영속 Queue/KV와 운영 알림 서비스 선택 |
| 분산 환경의 강제 요청 제한 | 개발용 수준 | Vercel WAF/Rate Limit 또는 외부 Redis/KV 선택 |
| 개인정보·서비스 정책 검토 | 미검토 | 공개 지역과 운영 주체 확정 후 법률·정책 검토 |

## 의도적으로 다음 단계로 넘긴 항목

- Speaker Similarity와 공격 성공률 지표
- Original/Protected 동시 비교 UI
- 결과 공유 이미지
- 추가 Provider Adapter
- 관리자, 회원가입, 결제, 전화망 연동

Mock Provider 결과는 합성 톤이며 Voice Clone 성공으로 표시하지 않는다. Fish Audio 실호출과 실제 기기 검증 전에는 Production 공개 준비 완료로 판단하지 않는다.

## 로컬 검증 결과

2026-09-16 현재 다음 검증을 통과했다.

- `npm test`: 6개 파일, 16개 테스트 통과
- `npm run lint`: 경고와 오류 없음
- `npm run typecheck`: 타입 오류 없음
- `npm run build`: Next.js Production 빌드 통과
- `npm audit --omit=dev --audit-level=high`: 알려진 취약점 없음
- Mock Provider HTTP smoke: WAV 검증부터 네 단계 이벤트, 결과 음성과 cleanup 완료까지 확인
- 브라우저 시각 확인: 첫 화면, 동의 활성화, 녹음 화면과 콘솔 오류 없음 확인
