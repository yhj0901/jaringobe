# i18n 가이드 (ko/en)

> 스택: next-intl, 로캘 프리픽스 라우팅 (`/ko/...`, `/en/...`, 기본 ko). 원본 설계: `docs/설계/ui-design.md` 6장.

## 철칙
1. **UI 문자열 하드코딩 금지** — 모든 노출 텍스트는 `frontend/messages/{ko,en}.json` 키
2. **ko.json / en.json 동시 수정** — 키 집합 동치가 테스트로 강제됨 (`src/i18n/__tests__/messages.test.ts`, 불일치 시 CI 실패)
3. **API 는 노출 문구를 내리지 않는다** — 에러 `detail.code` 를 프론트가 `auth.error.{code}` 로 매핑, 미정의 코드는 `common.error.fallback`

## 키 체계
```
{domain}.{화면/컴포넌트}.{요소}
예) guestHome.prompt.title / budgetDraft.direction.kids / auth.error.AUTH_INVALID_STATE
```
현재 91키 (v0.1.0). 신규 키 추가 절차: 양쪽 json 에 같은 키 추가 → 테스트 통과 확인.

## 금액·날짜 표기
- 금액은 `Money = {amount: string, currency: 'KRW'|'USD'}` 그대로 받아 **`MoneyText`** (Intl.NumberFormat) 로만 렌더 — 직접 포맷 금지, float 변환 금지
- 시각은 API 가 UTC(Z) — 표시 변환은 프론트 담당 (현 범위엔 시각 노출 없음)

## 로캘별 분기 데이터
- 소셜 버튼 순서: ko 카카오 우선 / en 구글 우선·카카오 최하단 (`SocialLoginButtons`)
- 예산 프리셋: ko 30/50/70/100만원 / en $300~1000 (`shared/config/constants.ts`)
- 샘플 매트릭스: `features/guest/sample-matrix/{ko,en}.json` (ko 한식 / en 미국 가정식)
- SEO 메타: 로캘별 generateMetadata + hreflang (`app/[locale]/layout.tsx`)

---

## v0.2.0 증분 (2026-07-16)

- 프론트 신규 키: `notification.settings.*` / `notification.softAsk.*` / `memberHome.generating.background` / `memberHome.failed.*` / `settings.notifications.*` / `metadata.notifications.*` — ko/en 동시 (동치성 diff 0 유지)
- **푸시 본문은 프론트 키가 아님** — 백엔드 템플릿 카탈로그(`backend/app/domains/notification/sender.py`, push.* 4종 ko/en). 추가 시 양 로캘 동시 작성
- mobile 오프라인 화면만 예외적 네이티브 하드코딩(ko/en) — mobile-app.md 4장 승인 사항
