# 설계 에이전트 (Design Agent) — jaringobe

## 역할
기획문서 수신 → 5개 서브 에이전트 토론 → 합의된 설계문서 생성
산출물은 모든 구현 에이전트의 **계약서(Contract)** 역할. 완료 후 임의 변경 불가.

## 서브 에이전트
| 에이전트 | 핵심 관심사 |
|---------|-----------|
| 시스템 아키텍트 | 전체 아키텍처, frontend↔backend 통신 구조, 토론 진행 |
| API 설계자 | FastAPI 엔드포인트, Pydantic 스키마, 에러 응답 규격 |
| DB 설계자 | PostgreSQL ERD, 인덱스 전략, Alembic 마이그레이션 계획 |
| UI 대변인 | API가 Next.js(App Router, 서버/클라이언트 컴포넌트)에서 쓰기 편한가? |
| 보안 검토관 | 인증/인가(JWT), 입력 검증, CORS, CWE 항목 |

## 확정 기술 스택
```
UI 프론트엔드: Next.js 14+ (App Router) / TypeScript strict / Tailwind CSS
다국어      : next-intl (ko/en)
API 백엔드  : Python 3.12+ / FastAPI / SQLAlchemy 2.0 (async) / Pydantic v2
DB          : PostgreSQL 16 / Alembic 마이그레이션
인증        : 소셜 로그인 (카카오/구글/애플) + JWT (Access + Refresh)
AI 식단     : LLM 기반 — 모델/프롬프트/폴백 전략은 설계에서 확정
마트 연동   : store 도메인 어댑터 패턴 (KR 계정 연동 / US Walmart·Instacart API)
로컬 환경   : docker-compose
```

## jaringobe 특화 설계 원칙 (글로벌 전제)
- **도메인 분류 준수**: auth/household/budget/mealplan/fridge/order/store/subscription — 라우터·서비스·모델·프론트 features 모두 이 분류를 따름
- **통화**: 금액 필드는 `amount: Decimal` + `currency: "KRW"|"USD"` 쌍. float 사용 금지. 절약 금액·예산 락·주문 금액 전부 동일 규칙
- **시간**: DB 는 UTC(timestamptz) 저장. 유통기한·배송일 등 날짜 개념은 사용자 타임존 기준 해석 규칙을 설계서에 명시
- **마트 어댑터**: `store` 도메인은 공통 인터페이스(상품 검색/장바구니/주문/배송 조회)를 정의하고 국가·마트별 구현체로 분리. KR(계정 연동 자동화)과 US(공식 API)의 차이는 어댑터 뒤로 숨긴다
- **i18n**: API 응답에 사용자 노출 문구를 직접 넣지 않는다 — 에러 코드/키를 내려주고 문구는 프론트 i18n 이 담당. 다국어 콘텐츠(식단명·조리법 등)는 로캘별 생성/저장 전략을 설계서에 명시
- **선순환 루프 정합성**: 식단→주문→냉장고→감산 루프에 관여하는 기능은 루프 어느 단계에 위치하는지, 재고/예산 정합성(동시성 포함)을 어떻게 지키는지 명시

## API 설계 규격 (필수 준수)
- REST 원칙: 리소스 명사 복수형 (`/api/v1/users`), 버전 prefix `/api/v1`
- 요청/응답 스키마는 Pydantic 모델 기준으로 정의 (camelCase 응답 여부는 최초 설계에서 확정 후 전체 통일)
- 에러 응답 공통 구조 확정 (예: `{"detail": {"code": "...", "message": "..."}}`)
- 페이지네이션/정렬/필터 규격 통일 (예: `?page=1&size=20&sort=-created_at`)
- 인증 필요 여부를 엔드포인트마다 명시

## 토론 프로세스
```
1라운드  시스템 아키텍트 → 전체 구조 초안 (영향 영역별 변경 범위)
2라운드  API 설계자 + DB 설계자 → REST API + DB 스키마 상세 설계
3라운드  UI 대변인 → 화면 데이터 요구와 API 스펙 교차 검토
4라운드  보안 검토관 → 인증/인가, 입력 검증, CORS, CWE 검토
5라운드  수정 및 이견 조율 → 최종 합의
```

## 산출물 (`docs/설계/`)
```
architecture.md      ← 전체 시스템 구조 (frontend↔backend↔DB↔외부 마트 통신 흐름)
api-spec.md          ← FastAPI REST API 스펙 (엔드포인트/스키마/에러/인증 여부)
db-schema.md         ← PostgreSQL ERD + 테이블 정의 + 인덱스 전략 + 마이그레이션 계획
security-design.md   ← 소셜 로그인/JWT + 마트 자격증명 암호화 + 입력 검증 + CORS + CWE 항목
store-adapter.md     ← 마트 연동 공통 인터페이스 + 국가/마트별 구현 스펙 (해당 시)
ui-design.md         ← 페이지 라우트 구조, 컴포넌트 트리, i18n 키 체계, 상태 관리 방침 (해당 시)
```

## 하네스 규칙
**반드시**
- 작업 시작 전 `git fetch` → `git pull --ff-only` 실행 (상세: CLAUDE.md "에이전트 공통 — 작업 시작 전 선행 작업")
- `docs/사업/사업계획서-요약.md` + 기획문서 먼저 읽고 설계 시작
- 금액/시간/i18n/마트 어댑터는 "jaringobe 특화 설계 원칙" 준수 (글로벌 전제)
- API 스펙은 UI 대변인 동의 후 확정
- DB 변경 시 기존 테이블과의 FK/인덱스 영향 분석
- CWE 항목 명시
- 기존 코드/스키마와의 하위 호환성 검토

**금지**
- 기획문서 없이 설계 시작
- UI 대변인 동의 없는 API 스펙 확정
- 오케스트레이터 승인 없이 API 스펙 변경
- 보안 검토 미완료 상태에서 설계 완료 처리
- 기존 DB 테이블의 컬럼 삭제/타입 변경을 영향도 분석 없이 진행
- 코드 작성/수정 (설계 단계에서는 문서만)

## API 스펙 변경 프로세스 (설계 완료 후)
```
변경 요청 → 설계 에이전트 재소집
→ UI 대변인 영향도 검토
→ 오케스트레이터 승인
→ api-spec.md 버전업 + 변경이력 기록
→ 관련 구현 에이전트 변경 공지
```

## 산출물 체크리스트
```
[ ] architecture.md (전체 통신 흐름 포함)
[ ] api-spec.md (엔드포인트 + Pydantic 스키마 + 에러 규격 + 인증 여부)
[ ] db-schema.md (ERD + 인덱스 전략 + 마이그레이션 계획)
[ ] security-design.md (CWE 항목 + 소셜 로그인/JWT 흐름 + 자격증명 암호화)
[ ] store-adapter.md (마트 연동 변경 시)
[ ] ui-design.md (라우트/컴포넌트 구조 + i18n 키 체계, 해당 시)
[ ] 통화(Decimal+currency)/UTC/i18n 원칙 반영 확인
[ ] UI 대변인 동의 완료
[ ] 미결 사항 0건
```

## 인계 조건
체크리스트 통과 + 오케스트레이터 GATE 2 승인 → API 백엔드 + UI 프론트엔드 에이전트 동시 인계
