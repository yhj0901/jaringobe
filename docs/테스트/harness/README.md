# QA 하네스 (2026-09-04 루프 완결 GATE 4 · 2026-09-05 재판정)

`docs/테스트/시나리오테스트.md` 의 S1~S8 / R / H / LIVE 결과를 만든 스크립트. 코드가 아니라 QA 증거물이며 `backend/tests` 회귀 스위트와 별개다.

```bash
docker exec jaringobe-db psql -U jaringobe -d postgres -c "CREATE DATABASE jaringobe_qa2"
cd backend
export DATABASE_URL=postgresql+asyncpg://jaringobe:jaringobe@localhost:5433/jaringobe_qa2
uv run alembic upgrade head
uv run python ../docs/테스트/harness/qa_loop.py         # S1~S8 (가상 시계) — 같은 DB 에 반복 실행 가능(닉네임 유니크 없음)
uv run python ../docs/테스트/harness/qa_rejudge.py      # R-01~R-09 재판정 추가 시나리오 (qa_loop 의 대역·픽스처를 import)
JWT_SECRET=qa-secret CYCLE_SCHEDULER_ENABLED=false NAVER_CLIENT_ID= NAVER_CLIENT_SECRET= uv run uvicorn app.main:app --port 8011 &   # HTTP 대상
uv run python ../docs/테스트/harness/http_setup.py > ../docs/테스트/harness/http_users.json
QA_DB=jaringobe_qa2 uv run python ../docs/테스트/harness/http_tests.py                              # H-01~48 (★ QA_DB 를 DATABASE_URL 의 DB 명과 맞출 것)
JWT_SECRET=qa-secret CYCLE_SCHEDULER_ENABLED=true CYCLE_SCHEDULER_INTERVAL_SECONDS=5 uv run uvicorn app.main:app --port 8012 &
uv run python ../docs/테스트/harness/live_check.py                                                  # LIVE-01
```

- 외부 경계 대역: `store_service.build_cart`(시세 3모드: match / multiplier / unmatched / raise), `generate_meals`(mock 캡처/실패), `sender.send_to_user`(발송 기록). 실키·실결제 사용 없음.
- `[결함 탐지]` 라벨 항목은 FAIL 이 곧 버그 재현이다 → `버그리포트.md` 회귀에 사용.

## 재판정(2026-09-05) 에서 하네스를 고친 곳과 이유

| 파일 | 변경 | 이유 |
|------|------|------|
| `qa_loop.py` S8-04 | 기대 stage 를 `confirmed` 고정 → 주문 `inbound_at` 유무에 따라 `confirmed`/`delivered` 동적. `drafted` 는 여전히 FAIL | 시나리오의 수동 확정이 9/9 00:00Z 라 `delivery_eta`=9/10 00:00Z 이고, 검증 시점인 D-2 tick(9/11) 의 스캔 ③이 eta 도달을 **정상** 처리해 `delivered` 가 된다. DB 직접 조회로 확인(confirmed 1건, inbound 15행, 초안 없음). 결함의 본질("초안이 덧씌워 `drafted`") 은 유지하며 잘못된 고정 기대만 고쳤다. 수정 워커의 주장을 검증한 결과 사실이었다. |
| `qa_rejudge.py` R-05 (신규) | 수동 확정을 9/10 23:00Z 에 수행(eta 9/12) → D-2 tick 에서 `stage=confirmed` 를 순수 재현 | S8-04 의 원래 의도(eta 이전 시점 confirmed 유지)를 시점 충돌 없이 검증하기 위해 |
| `http_tests.py` `psql()` | DB 명 `jaringobe_qa` 하드코딩 → `QA_DB` 환경변수(기본값 유지) | 다른 DB(`jaringobe_qa2`)를 대상으로 돌리면 psql 검증이 빈 결과를 돌려 H-41 이 오탐 FAIL, H-13 은 빈 문자열 동치로 공허 PASS 가 됐다. 환경변수화 후 두 항목 모두 실값으로 PASS |
| `qa_rejudge.py` (신규) | BUG-001 잔여 경로(R-01~R-04: 차단 시점·스냅샷 갱신·멱등·역방향·미매칭 게이트·D-1 시세 장애), BUG-003 변형(R-06), BUG-004 역방향(R-07), BUG-008/009 단위 경계(R-08/09) | 수정된 게이트가 "초안 스냅샷을 안 쓰는가", "차단이 inbound 이전인가" 를 1차 하네스보다 촘촘히 보기 위해. R-04b 에서 신규 BUG-012(Low) 발견 |

1차 결과 재현이 필요하면 `git show 591463c:docs/테스트/harness/qa_loop.py`.
