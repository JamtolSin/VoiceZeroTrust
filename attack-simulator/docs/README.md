# VoiceShield Attack Simulator 문서

이 디렉터리는 VoiceZeroTrust의 기존 탐지·방어 구현과 분리된 Attack Simulator의 제품 및 기술 문서를 관리한다.

## 문서 원칙

- 현재 구현과 목표 설계를 구분해서 기록한다.
- 확인하지 않은 외부 API 기능이나 제한은 사실처럼 작성하지 않는다.
- 음성 복제 성능 수치와 처리 시간은 실제 측정값만 사용한다.
- 사용자의 본인 음성, 명시적 동의, 고정된 안전 문구만 MVP 입력으로 허용한다.
- 원본·생성 음성과 Provider의 복제 자원은 가능한 가장 짧은 시간만 보관한다.
- 방어 전후 비교는 동일한 Attack Engine과 동일한 생성 조건을 사용한다.

## 문서 목록

| 문서 | 역할 | 상태 |
|---|---|---|
| [MVP 기획서](mvp-plan.md) | 제품 범위, 사용자 흐름, 시스템 구조, API, 보안, 개발 순서와 완료 기준 | Draft v0.1 |
| [구현 상태](implementation-status.md) | 완료된 범위와 외부 조건 때문에 남은 검증 항목 | 구현 중 |

## 이후 분리할 문서

통합 기획서가 확정되고 구현이 시작되면 아래 문서를 필요에 따라 분리한다.

- `architecture.md`: 확정된 런타임 구성과 주요 기술 결정
- `api-contract.md`: 실제 요청·응답 스키마와 오류 코드
- `privacy-and-abuse.md`: 동의, 보관 기간, 삭제, 레이트 제한과 운영 정책
- `test-plan.md`: 브라우저·API·Provider 통합·배포 검증 절차
- `decision-log.md`: Provider, 임시 저장소, 비동기 작업 방식 선택 근거

초기 단계에서는 문서를 너무 일찍 쪼개지 않고 `mvp-plan.md`를 단일 기준 문서로 사용한다.
