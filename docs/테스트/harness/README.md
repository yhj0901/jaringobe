# QA 하네스 (2026-09-04 루프 완결 GATE 4)

`docs/테스트/시나리오테스트.md` 의 S1~S8 / H / LIVE 결과를 만든 스크립트. 코드가 아니라 QA 증거물이며 `backend/tests` 회귀 스위트와 별개다.

```bash
docker exec jaringobe-db psql -U jaringobe -d postgres -c "CREATE DATABASE jaringobe_qa"
cd backend
DATABASE_URL=postgresql+asyncpg://jaringobe:jaringobe@localhost:5433/jaringobe_qa uv run alembic upgrade head
DATABASE_URL=postgresql+asyncpg://jaringobe:jaringobe@localhost:5433/jaringobe_qa uv run python ../docs/테스트/harness/qa_loop.py      # S1~S8 (가상 시계)
DATABASE_URL=... JWT_SECRET=qa-secret CYCLE_SCHEDULER_ENABLED=false uv run uvicorn app.main:app --port 8011 &                      # HTTP 대상
DATABASE_URL=... uv run python ../docs/테스트/harness/http_setup.py > ../docs/테스트/harness/http_users.json
uv run python ../docs/테스트/harness/http_tests.py                                                                                  # H-01~48
DATABASE_URL=... JWT_SECRET=qa-secret CYCLE_SCHEDULER_ENABLED=true CYCLE_SCHEDULER_INTERVAL_SECONDS=5 uv run uvicorn app.main:app --port 8012 &
DATABASE_URL=... uv run python ../docs/테스트/harness/live_check.py                                                                 # LIVE-01
```

- 외부 경계 대역: `store_service.build_cart`(시세 3모드), `generate_meals`(mock 캡처/실패), `sender.send_to_user`(발송 기록). 실키·실결제 사용 없음.
- `[결함 탐지]` 라벨 항목은 FAIL 이 곧 버그 재현이다 → `버그리포트.md` BUG-001~005 회귀에 사용.
