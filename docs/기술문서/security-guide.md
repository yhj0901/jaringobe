# 보안 가이드 (인증/세션)

> 원본: `docs/설계/security-design.md` (CWE 대응표 포함) + QA 결과 `docs/테스트/보안테스트.md` (10/10 PASS).

## 인증 흐름 요약
- 소셜 로그인은 **백엔드 주도 Authorization Code**: 브라우저 → `GET /auth/{provider}/authorize` → provider 동의 → 백엔드 `/callback` 이 토큰 교환·유저 upsert·쿠키 세팅 → 프론트 302. 시크릿·provider 토큰은 서버 밖으로 나가지 않고, provider access token 은 프로필 조회 후 폐기
- 계정 정책: **provider별 별도 계정** — 동일 이메일이어도 자동 통합 금지 (CWE-287), notice 안내만

## 토큰/쿠키 정책 (구현: `backend/app/core/security.py`)

| 항목 | 값 |
|------|-----|
| Access | JWT HS256, 30분, `jaringobe_access` 쿠키 |
| Refresh | 랜덤 256bit, 14일, DB 엔 SHA-256 해시만, `jaringobe_refresh` 쿠키 `Path=/api/v1/auth` |
| 쿠키 공통 | HttpOnly + SameSite=Lax (+ `COOKIE_SECURE=true` 시 Secure — **배포 필수**) |
| 회전 | refresh 사용 시 revoke+재발급, `rotated_from` 체인. **재사용 감지 시 유저 전 세션 폐기** |

## 요청 방어 (구현: `backend/app/main.py`, `core/ratelimit.py`)
- Origin 검증: 상태 변경 메서드에서 Origin 헤더가 존재하는데 `FRONTEND_ORIGIN` 과 불일치하면 403 (부재 시 통과 — SameSite=Lax 1차 방어)
- Rate limit: `/auth/*` IP 10회/분 (엔드포인트 합산), `/budget/plans` 유저 5회/분 — 인메모리 (멀티 인스턴스 시 Redis 교체 필요)
- 게스트 이전 입력은 서버 전량 재검증 (클라이언트 값 불신, CWE-20/602)

## 개발 시 지켜야 할 것
- 시크릿은 `.env` 만 (`JWT_SECRET`, provider secret) — 코드/로그/status JSON 기록 금지
- 로그에 토큰·code·이메일 원문 금지
- 프론트: localStorage 에 PII/토큰 저장 금지 (게스트 키 `jaringobe.guest.v1` 은 비식별 데이터만), `dangerouslySetInnerHTML` 금지
- `next` 류 리다이렉트 파라미터는 항상 상대경로 화이트리스트 (CWE-601)
