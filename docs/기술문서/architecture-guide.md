# 아키텍처 가이드 (개발자용)

> 원본 설계: `docs/설계/architecture.md` (계약서) — 이 문서는 신규 개발자 온보딩용 요약이다.

## 전체 구조 (v0.1.0 기준)

```
브라우저 ──(동일 오리진, httpOnly 쿠키)── Next.js 14 (frontend/)
                                            │ rewrites: /api/v1/* → BACKEND_URL
                                          FastAPI (backend/) ── 카카오/구글 OAuth
                                            │ SQLAlchemy 2.0 async
                                          PostgreSQL 16 (docker)
```

- **CORS 를 쓰지 않는다**: 프론트가 `/api/v1/*` 를 백엔드로 프록시(rewrites)해 동일 오리진을 만든다. 백엔드는 Origin 검증 미들웨어로 상태 변경 요청을 방어
- **홈 셸 공유**: `/` 는 게스트(정적 샘플 매트릭스)와 회원이 같은 `HomeShell` 컴포넌트를 쓰고 `HomeViewModel` 데이터만 교체 주입
- **게스트 로직은 100% 클라이언트**: 게스트 입력은 서버로 보내지 않는다 (가입 시 `POST /budget/plans` 이전 1회 제외)

## 디렉토리 규칙

| 위치 | 규칙 |
|------|------|
| `backend/app/domains/{도메인}/` | router(HTTP) → service(비즈니스) → models(SQLAlchemy). 라우터에 비즈니스 로직 금지 |
| `backend/app/api/v1/router.py` | 도메인 라우터 집결점 — 새 도메인 라우터는 여기 include |
| `backend/app/core/` | config(Settings)/security(JWT·state·쿠키)/deps/errors/ratelimit/schema(CamelModel) |
| `backend/alembic/` | 마이그레이션 단일 경로 — **인프라 에이전트 전담**, DDL 직접 실행 금지 |
| `frontend/src/features/{도메인}/` | 도메인 분류(auth/budget/…) 준수, 컴포넌트+로직+테스트 동거 |
| `frontend/src/shared/` | api(fetch 래퍼)/ui(공용 컴포넌트)/config(상수) |

## 도메인 현황 (v0.1.0)

| 도메인 | backend | frontend | 비고 |
|--------|---------|----------|------|
| auth | ✅ 구현 | ✅ 구현 | 카카오/구글 (애플 P1: 어댑터 인터페이스 확정, 404 응답) |
| budget | v0 (plans 생성만) | 이전 클라이언트만 | budget 본설계에서 확장 |
| household/mealplan/fridge/order/store/subscription | 미구현 | 홈 위젯 프리뷰만 | 후속 기획 |

## 새 기능 추가 시 흐름
1. `/기획시작` → GATE 1 → `/설계시작` → GATE 2 (api-spec.md 갱신은 설계 변경 프로세스 필수)
2. DB 변경 시 `/인프라시작` (GATE 3) — 모델은 마이그레이션과 1:1 유지
3. `/API시작` + `/UI시작` → `/QA시작` (GATE 4) → `/문서시작`

---

## v0.2.0 증분 — 모바일 앱 쉘 + 푸시 알림 (2026-07-16)

> 상세: `docs/설계/architecture.md` 3-5~3-8, `docs/설계/mobile-app.md`

- **mobile/ (Expo 쉘)**: 배포 웹 오리진을 웹뷰 1장으로 로드 — 제품 UI 는 웹 배포만으로 갱신. 네이티브는 스플래시·푸시·브리지·딥링크·커스텀 탭만
- **앱 로그인**: 구글의 웹뷰 OAuth 차단 → 3사 공통 커스텀 탭 + 원타임 코드(60초·단일사용) → 웹뷰가 `/auth/app/session` 에서 쿠키 수령
- **식단 생성 비동기**: 202 접수 → FastAPI BackgroundTasks → 완료/실패 푸시. 화면 폴링이 기본, 푸시는 보조
- **리마인더 스케줄러**: lifespan asyncio 30초 주기, `notification_settings.next_send_at`(UTC) partial index 스캔 → 최신 활성 플랜에서 당일(사용자 타임존)·미완료 끼니만 발송
- 단일 인스턴스 전제 (BackgroundTasks·스케줄러) — 멀티 인스턴스 시 워커/큐·스케줄러 분리
