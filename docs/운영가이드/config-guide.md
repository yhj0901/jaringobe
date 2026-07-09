# 환경 변수 설정 가이드 (.env)

> 템플릿: `.env.example` (커밋 대상). 실제 `.env` 는 커밋 금지. 시크릿은 여기로만 관리.

| 키 | 사용처 | 설명 | 로컬 기본 | 배포 시 |
|----|--------|------|-----------|---------|
| `POSTGRES_USER/PASSWORD/DB` | docker | postgres 초기화 | jaringobe/…/jaringobe | 강한 비밀번호 필수 |
| `DATABASE_URL` | backend | asyncpg 접속 문자열 | localhost:5432 | compose 내부는 host=db |
| `JWT_SECRET` | backend | JWT·OAuth state 서명 | (빈값 불가 — 생성 필요) | `openssl rand -hex 32` |
| `KAKAO_CLIENT_ID/SECRET` | backend | 카카오 OAuth | 빈값(로그인 불가) | 카카오 개발자 콘솔 |
| `GOOGLE_CLIENT_ID/SECRET` | backend | 구글 OAuth | 빈값(로그인 불가) | 구글 클라우드 콘솔 |
| `FRONTEND_ORIGIN` | backend | Origin 검증 + OAuth 복귀 리다이렉트 베이스 | http://localhost:3000 | **프론트 실제 도메인** (불일치 시 403/리다이렉트 오류) |
| `COOKIE_SECURE` | backend | 쿠키 Secure 플래그 | false | **true 필수** (https) |
| `BACKEND_URL` | frontend | rewrites 프록시 대상 | http://localhost:8000 | 백엔드 공개 https 주소 (Vercel env) |
| `ANTHROPIC_API_KEY` / `LLM_MODEL` | backend | AI 식단(추후) — 빈값이면 mock 표시 | 빈값 | 식단 기능 도입 시 |

- 애플 로그인(P1) 도입 시 추가 예정: `APPLE_CLIENT_ID / APPLE_TEAM_ID / APPLE_KEY_ID / APPLE_PRIVATE_KEY_PATH`
- 키 추가/변경은 인프라 에이전트가 `.env.example` 과 이 문서를 함께 갱신한다
