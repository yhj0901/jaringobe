# 장애 대응 가이드 (troubleshoot)

> v0.1.0 범위(게스트 홈 + 소셜 로그인) 기준. 증상 → 원인 → 조치.

| 증상 | 유력 원인 | 조치 |
|------|-----------|------|
| `/health` 에서 `"db": false` | postgres 미기동 / DATABASE_URL 불일치 | `docker compose up -d db`, `.env` 의 URL 확인 (로컬 host=localhost, compose 내부 host=db) |
| 소셜 버튼 클릭 시 provider 오류 페이지 | client id 미설정 / 콜백 URL 미등록 | `.env` 의 KAKAO/GOOGLE 키, provider 콘솔에 `{FRONTEND_ORIGIN}/api/v1/auth/{provider}/callback` 등록 |
| 로그인 후 `/login?error=AUTH_INVALID_STATE` | state 만료(10분 초과) / JWT_SECRET 변경·서버 재시작 후 이전 state | 재시도. 반복 시 서버 시계·JWT_SECRET 일관성 확인 |
| 모든 POST 가 403 FORBIDDEN_ORIGIN | `FRONTEND_ORIGIN` 이 실제 접속 도메인과 불일치 | backend `.env` 수정 후 재시작 |
| 로그인 직후 401 반복 / 쿠키 미저장 | https 인데 `COOKIE_SECURE=false`, 또는 http 인데 true | 프로토콜에 맞게 `COOKIE_SECURE` 설정 |
| 401 `AUTH_TOKEN_REVOKED` | refresh 재사용 감지 → 전 세션 폐기 (정상 방어 동작) | 재로그인 안내. 빈발 시 토큰 탈취 의심 — 로그 확인 |
| 429 RATE_LIMITED | /auth/* IP 10회/분 초과 | 정상 방어. 프록시 뒤 배포 시 실클라이언트 IP 전달(X-Forwarded-For) 구성 확인 |
| 프론트에서 /api/v1 이 404/HTML 응답 | rewrites 대상(`BACKEND_URL`) 오설정 / 백엔드 다운 | Vercel env·백엔드 상태 확인 |
| 게스트 예산안이 사라짐 | localStorage 30일 만료 / 브라우저 데이터 삭제 (정상 동작) | 재작성 안내 — 서버 저장은 가입 후에만 |
| 마이그레이션 오류 `gen_random_uuid` | pgcrypto 확장 없음 (수동 생성 DB) | `alembic upgrade head` 가 확장 생성 포함 — 권한 있는 계정으로 실행 |

## 로그 확인
```bash
docker compose logs -f db
# 백엔드: uvicorn 표준 출력 (토큰·이메일 원문은 로그에 남기지 않는 것이 규칙)
```

## 에스컬레이션
- 인증 우회·토큰 탈취 의심 → 보안 이슈: 해당 유저 refresh_tokens 전체 revoke 후 원인 분석
- 스키마 불일치 → 인프라 에이전트 (`alembic history` 와 `docs/설계/db-schema.md` 대조)
