# 모바일 앱 설계서 — Expo 웹뷰 쉘 + 푸시 (v1)

> 대상 기획: `docs/기획/앱-웹뷰-푸시알림.md` / 흐름 원본: `architecture.md` 3-5~3-8
> 담당: UI 프론트엔드 에이전트 (관할 확장 — CLAUDE.md 갱신은 문서 에이전트)
> 스택: Expo SDK(최신 stable) / react-native-webview / expo-notifications / EAS Build·Submit

## 1. 원칙

- **쉘은 얇게**: 화면은 웹뷰 1장. 네이티브 코드는 스플래시·푸시·브리지·딥링크·커스텀 탭으로 한정. 제품 UI 변경은 웹 배포만으로 반영
- **웹이 진실의 원본**: 앱은 세션·상태를 소유하지 않는다. 인증은 웹뷰 쿠키(httpOnly), 앱은 쿠키에 접근하지 않음
- **하위 호환**: 앱 배포는 심사로 느림 — 웹은 구버전 앱(브리지 v)을 항상 지원

## 2. 프로젝트 구조 (`mobile/`)

```
mobile/
  app.json            # name/slug/scheme(jaringobe)/아이콘·스플래시/iOS·Android 식별자
  eas.json            # dev/preview/production 빌드 프로필 (WEB_URL 등 env)
  App.tsx             # SplashScreen → <AppWebView/> 단일 루트
  src/
    webview.tsx       # WebView 래퍼: 오리진 allowlist, UA 접미사, 뒤로가기, 오프라인 화면
    bridge.ts         # 프로토콜 정의 + onMessage 라우팅 (3장)
    push.ts           # 권한 요청·Expo 토큰 발급·포그라운드/탭 핸들러
    deeplink.ts       # jaringobe:// 파서 (auth 코드 / 푸시 path)
    login.ts          # 커스텀 탭 오픈 (expo-web-browser)
  __tests__/          # bridge 프로토콜·deeplink 파서 단위 테스트 (vitest 아님 — jest-expo)
```

## 3. 브리지 프로토콜 (웹·앱 공용 계약 — 본 문서가 원본)

전 메시지 공통: `{ "v": 1, "type": "...", "payload": { ... } }` — 알 수 없는 `type`/상위 `v` 는 **무시**(에러 금지, 전방 호환).

**앱 → 웹** (`webViewRef.postMessage` → 웹 `message` 이벤트)
| type | payload | 시점 |
|------|---------|------|
| `BRIDGE_READY` | `{ appVersion, platform }` | 웹뷰 로드 완료 직후 1회 |
| `PERMISSION_STATUS` | `{ status: "granted"\|"denied"\|"undetermined" }` | READY 직후 + 변경 시 |
| `PUSH_TOKEN` | `{ token, platform, locale, timezone, appVersion }` | 권한 granted 후 발급/변경 시 |

**웹 → 앱** (`window.ReactNativeWebView.postMessage`)
| type | payload | 동작 |
|------|---------|------|
| `REQUEST_PUSH_PERMISSION` | `{}` | OS 권한 다이얼로그 → 결과를 PERMISSION_STATUS(+granted 면 PUSH_TOKEN) 로 회신 |
| `OPEN_OS_SETTINGS` | `{}` | OS 앱 알림 설정 화면 오픈 |
| `LOGIN_PROVIDER` | `{ provider: "kakao"\|"google"\|"apple", next }` | 커스텀 탭으로 `authorize?client=app&next=` 오픈 |
| `SYNC_REQUEST` | `{}` | **(v1 증보 — BUG-006)** 앱 상태 재발신 요청: BRIDGE_READY → PERMISSION_STATUS → (granted 면) PUSH_TOKEN 순서로 재전송 |

- **초기 동기화 규칙 (BUG-006)**: 앱의 onLoadEnd 시점 1회 발신은 웹 리스너 구독 전 유실될 수 있다 → 웹은 브리지 구독 완료 직후 `SYNC_REQUEST` 를 보내고, 앱은 수신 시마다 상태를 재발신한다(멱등). 구버전 앱은 미지 type 무시 원칙으로 안전(웹은 응답 부재를 오류로 취급하지 않음)

- 검증: 앱 `onMessage` 는 mainFrame·오리진(`WEB_URL`) 확인 후 JSON 파싱, type 열거 외 무시 (CWE-345)
- 웹 쪽 모듈은 `frontend/src/shared/bridge/` (ui-design.md 12장)

## 4. 웹뷰 정책

| 항목 | 정책 |
|------|------|
| 로드 대상 | `WEB_URL` 오리진만 내부 내비게이션 허용. **그 외(마트·약관 등) → 시스템 브라우저 위임** (`onShouldStartLoadWithRequest`) |
| UA | 기본 UA + ` JaringobeApp/{appVersion} ({ios\|android})` 접미사 |
| 쿠키 | 네이티브 쿠키 저장소 공유(`sharedCookiesEnabled`) — httpOnly 쿠키는 JS 미노출 유지 |
| Android 뒤로가기 | 웹뷰 `canGoBack` → goBack, 루트면 앱 최소화 표준 동작 |
| 오프라인/로드 실패 | 네이티브 재시도 화면 (웹 도달 불가 시 유일한 네이티브 UI) |
| 파일/카메라 등 | 현 범위 미사용 — 권한 요청 안 함 (심사 지적 방지) |

## 5. 푸시 클라이언트 흐름

```
BRIDGE_READY 후 웹 주도:
  soft ask 수락 → REQUEST_PUSH_PERMISSION → granted → PUSH_TOKEN → 웹이 PUT /notifications/devices
앱 실행 시(이미 granted): PUSH_TOKEN 재전송 → 웹이 upsert (last_seen 갱신)
수신:
  백그라운드/종료 탭 → data.path 화이트리스트 검증(상대경로) → 웹뷰 내비게이트
  포그라운드 → 인앱 배너(expo-notifications 기본 프레젠테이션) — 탭 시 동일 라우팅
```

## 6. 딥링크 (`jaringobe://`)

| 패턴 | 처리 |
|------|------|
| `jaringobe://auth?code=&next=` | 커스텀 탭 닫기 → 웹뷰를 `/api/v1/auth/app/session?code=&next=` 로 내비게이트 |
| `jaringobe://auth?error={code}` | 웹뷰를 `/login?error={code}` 로 내비게이트 (기존 에러 배너 재사용) |
| 푸시 `data.path` | `/` 시작 상대경로만 — 실패 시 홈 `/` |

- P1: iOS Universal Links / Android App Links 전환 (security-design 5-4, CWE-939)

## 7. 빌드·배포 (EAS)

- 프로필: `preview`(내부 테스트 — WEB_URL 스테이징 가능) / `production`(스토어 제출)
- 시크릿: 서명 자격증명·`EXPO_ACCESS_TOKEN` 등은 EAS Secrets (커밋 금지)
- 선행 계정: Apple Developer($99/년, **애플 로그인 P1 완료 후 iOS 제출**), Google Play Console($25) — Android 선출시 허용(기획 확정)
- Apple 4.2 대응: 푸시+네이티브 스플래시+권한 연동이 1차, 리젝 시 Plan B 네이티브 탭바(별도 스프린트)

## 8. 테스트 방침

- bridge 프로토콜 파서/직렬화·deeplink 파서·path 화이트리스트: 단위 테스트 (jest-expo)
- 웹뷰·푸시 통합: Expo Go/개발 빌드 수동 시나리오 (QA 에이전트 시나리오 문서에 편입)
- 웹 쪽 `shared/bridge/`: vitest (기존 프론트 기준 커버리지 90% 대상)

## 변경 이력
- 2026-07-14: v1.0.1 — SYNC_REQUEST 증보 (QA BUG-006, 초기 브리지 메시지 유실 대응. 하위 호환 — 미지 type 무시 원칙)
- 2026-07-14: 최초 작성 (설계 토론 5라운드 합의 — 앱 웹뷰 래핑 + 푸시 알림)
