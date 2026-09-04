"""HTTP 레벨 시나리오·보안 테스트 — QA 백엔드(localhost:8011, jaringobe_qa) 대상."""
import json
import os
import subprocess
import sys

import time

import httpx

BASE = os.environ.get("QA_BASE", "http://localhost:8011")
ORIGIN = "http://localhost:3000"
USERS = json.load(open(os.path.join(os.path.dirname(__file__), "http_users.json")))
RESULTS = []


def check(tid, ok, note=""):
    RESULTS.append((tid, "PASS" if ok else "FAIL", note))
    print(f"[{'PASS' if ok else 'FAIL'}] {tid} {note}")


def client(user=None, origin=ORIGIN):
    headers = {"Origin": origin} if origin else {}
    cookies = {"jaringobe_access": USERS[user]["token"]} if user else {}
    return httpx.Client(base_url=BASE, headers=headers, cookies=cookies, timeout=30)


def code(r):
    try:
        return r.json().get("detail", {}).get("code")
    except Exception:
        return None


QA_DB = os.environ.get("QA_DB", "jaringobe_qa")  # 재판정(2026-09-05): 하드코딩 DB 명 → 환경변수. 다른 DB 를 쓰면 H-13/H-41 이 빈 결과로 오판됐다


def psql(sql):
    return subprocess.run(["docker", "exec", "jaringobe-db", "psql", "-U", "jaringobe", "-d", QA_DB, "-Atc", sql],
                          capture_output=True, text=True).stdout.strip()


A, B, C, D, E = "A", "B", "C", "D", "E"
draft = USERS[A]["draft_id"]
draft_e = USERS[E]["draft_id"]

# ---------------------------------------------------------------- 인증
with client() as c:
    for path in ("/api/v1/cycle", "/api/v1/orders/preview", "/api/v1/orders/latest"):
        r = c.get(path)
        check(f"H-01 미인증 GET {path} → 401 AUTH_REQUIRED", r.status_code == 401 and code(r) == "AUTH_REQUIRED", f"{r.status_code} {code(r)}")
    r = c.post(f"/api/v1/orders/{draft}/approve", json={})
    check("H-02 미인증 POST approve → 401", r.status_code == 401, f"{r.status_code}")
    r = c.get("/api/v1/cycle", cookies={"jaringobe_access": "eyJ.garbage.token"})
    check("H-03 위조 토큰 → 401 (스택 트레이스 없음)", r.status_code == 401 and "Traceback" not in r.text, r.text[:120])

# ---------------------------------------------------------------- IDOR (CWE-639)
with client(B) as c:
    for verb in ("approve", "cancel", "delivery", "recalculate"):
        body = {"received": True} if verb == "delivery" else ({} if verb == "approve" else None)
        r = c.post(f"/api/v1/orders/{draft}/{verb}", json=body)
        check(f"H-04 타인 주문 {verb} → 403 FORBIDDEN", r.status_code == 403 and code(r) == "FORBIDDEN", f"{r.status_code} {code(r)}")
    r = c.post("/api/v1/orders/00000000-0000-0000-0000-000000000000/approve", json={})
    check("H-05 존재하지 않는 주문 → 404 ORDER_NOT_FOUND", r.status_code == 404 and code(r) == "ORDER_NOT_FOUND", f"{r.status_code} {code(r)}")
    r = c.get("/api/v1/orders/latest")
    check("H-06 GET /orders/latest 는 본인 행만(B 는 주문 없음 → 404)", r.status_code == 404 and code(r) == "ORDER_NOT_FOUND", f"{r.status_code}")
    r = c.get("/api/v1/cycle")
    check("H-07 GET /cycle 은 본인 상태만(B: draftOrder null)", r.status_code == 200 and r.json()["draftOrder"] is None and r.json()["simulation"] is True, f"{r.status_code}")

# ---------------------------------------------------------------- Origin 검증 (CWE-352) — v1.9 recalculate 포함
with client(A, origin="https://evil.example") as c:
    r = c.post(f"/api/v1/orders/{draft}/recalculate")
    check("H-08 POST /orders/{id}/recalculate Origin 불일치 → 403 FORBIDDEN_ORIGIN", r.status_code == 403 and code(r) == "FORBIDDEN_ORIGIN", f"{r.status_code} {code(r)}")
    r = c.put("/api/v1/cycle/settings", json={"autoConfirm": True})
    check("H-09 PUT /cycle/settings Origin 불일치 → 403", r.status_code == 403 and code(r) == "FORBIDDEN_ORIGIN", f"{r.status_code}")
    r = c.post(f"/api/v1/orders/{draft}/approve", json={})
    check("H-10 POST approve Origin 불일치 → 403", r.status_code == 403, f"{r.status_code}")
    r = c.post("/api/v1/cycle/skip")
    check("H-11 POST /cycle/skip Origin 불일치 → 403", r.status_code == 403, f"{r.status_code}")
    r = c.get("/api/v1/cycle")
    check("H-12 GET 은 Origin 검증 대상 아님(200)", r.status_code == 200, f"{r.status_code}")

# ---------------------------------------------------------------- GET 부작용 제거 (CWE-650)
snap_before = psql(f"SELECT updated_at, estimated_total, blocked_reason, status FROM orders WHERE id='{draft}'")
items_before = psql(f"SELECT string_agg(name||':'||quantity||':'||line_type, ',' ORDER BY name) FROM order_items WHERE order_id='{draft}'")
with client(A) as c:
    r1 = c.get("/api/v1/orders/preview?refresh=true")
    r2 = c.get("/api/v1/orders/preview?refresh=1")
    r3 = c.get("/api/v1/orders/preview")
snap_after = psql(f"SELECT updated_at, estimated_total, blocked_reason, status FROM orders WHERE id='{draft}'")
items_after = psql(f"SELECT string_agg(name||':'||quantity||':'||line_type, ',' ORDER BY name) FROM order_items WHERE order_id='{draft}'")
check("H-13 GET /orders/preview?refresh=true 가 저장 초안을 변경하지 않음(행·라인 동일, refresh 무시)",
      r1.status_code == 200 and snap_before == snap_after and items_before == items_after and r1.json()["orderId"] == draft and r1.json()["status"] == "draft",
      f"before={snap_before} after={snap_after}")
check("H-14 저장 초안 preview 는 스냅샷 반환(orderId/status/cycleStart 포함)", r3.json().get("orderId") == draft and r3.json().get("cycleStart") == USERS[A]["cycle_start"])

# ---------------------------------------------------------------- 레이트리밋 (CWE-307/770)
with client(A) as c:
    codes = [c.get("/api/v1/orders/preview").status_code for _ in range(8)]
    check("H-15 저장 초안이 있는 preview 는 8회 연속 200 (값싼 경로 리미터 미적용)", codes == [200] * 8, f"{codes}")
with client(C) as c:  # 저장 초안 없음 → 즉석 계산(네이버 키 없음 → unmatched)
    codes = [c.get("/api/v1/orders/preview").status_code for _ in range(4)]
    check("H-16 저장 초안 없는 preview(즉석 계산) 4회 → 4번째 429 RATE_LIMITED", codes == [200, 200, 200, 429], f"{codes}")
    r = c.get("/api/v1/orders/preview")
    check("H-17 429 응답 규격 detail.code=RATE_LIMITED", code(r) == "RATE_LIMITED", r.text[:120])
with client(A) as c:
    codes = [c.post(f"/api/v1/orders/{draft}/recalculate").status_code for _ in range(4)]
    check("H-18 POST recalculate 4회 → 4번째 429 (3회/분)", codes == [200, 200, 200, 429], f"{codes}")
with client(D) as c:  # 예산안·식단 없는 사용자: 액션 리미터 5회/분 (approve/cancel/delivery/settings/skip 합산)
    codes = [c.put("/api/v1/cycle/settings", json={"autoConfirm": True}).status_code for _ in range(6)]
    check("H-19 PUT /cycle/settings 6회 → 6번째 429 (5회/분)", codes[:5] == [200] * 5 and codes[5] == 429, f"{codes}")
    r = c.post("/api/v1/cycle/skip")
    check("H-20 [관찰] cycle/settings 와 skip·approve·cancel·delivery 가 리미터 버킷을 공유(5회 합산)하는가 — 스펙은 엔드포인트별 5회/분", r.status_code == 200,
          f"settings 5회 소진 직후 skip → {r.status_code} (429 면 공유 버킷)")

# ---------------------------------------------------------------- 입력 검증 (CWE-20/602)
with client(C) as c:
    r = c.put("/api/v1/cycle/settings", json={"timezone": "Mars/Olympus"})
    check("H-21 timezone IANA 화이트리스트 위반 → 422", r.status_code == 422 and code(r) == "VALIDATION_ERROR", f"{r.status_code} {code(r)}")
    r = c.put("/api/v1/cycle/settings", json={"anchorWeekday": 7})
    check("H-22 anchorWeekday 7 → 422", r.status_code == 422, f"{r.status_code}")
    r = c.put("/api/v1/cycle/settings", json={"frequency": "daily"})
    check("H-23 frequency enum 위반 → 422", r.status_code == 422, f"{r.status_code}")
    r = c.put("/api/v1/cycle/settings", json={"enabled": True, "cycleStart": "2020-01-01"})
    check("H-24 extra 필드(cycleStart) → 422 (서버 부여 필드 클라이언트 설정 불가)", r.status_code == 422, f"{r.status_code}")
    r = c.post("/api/v1/orders", json={"store": "kurly", "items": [{"name": "x", "price": 1}]})
    check("H-25 POST /orders 에 items 전달 → 422 (CWE-602)", r.status_code == 422, f"{r.status_code}")
    r = c.post("/api/v1/orders", json={"store": "walmart"})
    check("H-26 KR 사용자 store=walmart → 404 STORE_NOT_SUPPORTED", r.status_code == 404 and code(r) == "STORE_NOT_SUPPORTED", f"{r.status_code} {code(r)}")
    r = c.post("/api/v1/orders", json={"store": "coupang"})
    check("H-27 미연동 store → 422 STORE_NOT_CONNECTED", r.status_code == 422 and code(r) == "STORE_NOT_CONNECTED", f"{r.status_code} {code(r)}")
with client(E) as c:
    draft_a, draft = draft, draft_e
    r = c.post(f"/api/v1/orders/{draft}/approve", json={"items": [{"name": "계란", "unitPrice": "1"}]})
    check("H-28 approve 에 라인·가격 전달 → 422", r.status_code == 422, f"{r.status_code}")
    r = c.post(f"/api/v1/orders/{draft}/approve", json={"excludeNames": ["x"] * 41})
    check("H-29 excludeNames 41개 → 422", r.status_code == 422, f"{r.status_code}")
    r = c.post(f"/api/v1/orders/{draft}/delivery", json={})
    check("H-30 delivery body 누락 → 422", r.status_code == 422, f"{r.status_code}")
    r = c.post(f"/api/v1/orders/{draft}/delivery", json={"received": "yes"})
    check("H-31 [관찰] received=\"yes\" 문자열 → 422 (pydantic lax 강제변환으로 통과하면 FAIL)", r.status_code == 422, f"{r.status_code} {code(r)}")
    time.sleep(61)  # E 액션 리미터(5회/분) 회복
    r = c.post(f"/api/v1/orders/{draft}/cancel")
    check("H-32 draft 취소 → 409 ORDER_INVALID_STATE (상태 머신)", r.status_code == 409 and code(r) == "ORDER_INVALID_STATE", f"{r.status_code} {code(r)}")
    r = c.post(f"/api/v1/orders/{draft}/delivery", json={"received": True})
    check("H-33 draft 배송 보정 → 409 ORDER_INVALID_STATE", r.status_code == 409 and code(r) == "ORDER_INVALID_STATE", f"{r.status_code} {code(r)}")
    # SQLi / XSS 입력 (excludeNames 는 이름 필터만)
    r = c.post(f"/api/v1/orders/{draft}/approve", json={"excludeNames": ["'; DROP TABLE orders; --", "<script>alert(1)</script>"]})
    tables = psql("SELECT count(*) FROM orders")
    check("H-34 excludeNames SQLi/XSS 페이로드 → 무해(파라미터 바인딩), orders 테이블 유지", r.status_code in (200, 409, 422) and tables.isdigit() and int(tables) > 0,
          f"{r.status_code} {code(r)} orders={tables}")

# ---------------------------------------------------------------- 상태 머신 (CWE-841) — 승인 후 (A 의 초안, 리미터 회복 대기)
draft = draft_a
time.sleep(61)
with client(A) as c:
    r = c.get("/api/v1/orders/latest")
    latest = r.json()
    if latest["status"] == "draft":
        r = c.post(f"/api/v1/orders/{draft}/approve", json={"excludeNames": ["두부"]})
        check("H-35 1탭 승인 → 200 confirmed, 서버 재계산 스냅샷(두부 제외 반영), deliveryEta 부여, inboundAt null",
              r.status_code == 200 and r.json()["status"] == "confirmed" and r.json()["deliveryEta"] and r.json()["inboundAt"] is None
              and all(i["name"] != "두부" for i in r.json()["items"]) and r.json()["autoConfirmed"] is False,
              f"{r.status_code} {code(r)} {r.text[:200]}")
    else:
        check("H-35 1탭 승인 (사전 승인됨 — SQLi 페이로드 승인이 200이었음)", latest["status"] == "confirmed", latest["status"])
    r = c.post(f"/api/v1/orders/{draft}/approve", json={})
    check("H-36 confirmed 재승인 → 409 ORDER_INVALID_STATE", r.status_code == 409 and code(r) == "ORDER_INVALID_STATE", f"{r.status_code} {code(r)}")
    r = c.post(f"/api/v1/orders/{draft}/recalculate")
    check("H-37 confirmed 재계산 → 409 ORDER_INVALID_STATE", r.status_code == 409 and code(r) in ("ORDER_INVALID_STATE", "RATE_LIMITED"), f"{r.status_code} {code(r)}")
    r = c.post("/api/v1/orders", json={"store": "kurly"})
    check("H-38 같은 사이클 두 번째 명시 확정(POST /orders) → 409 ORDER_ALREADY_CONFIRMED", r.status_code == 409 and code(r) == "ORDER_ALREADY_CONFIRMED", f"{r.status_code} {code(r)}")
    r = c.post("/api/v1/cycle/skip")
    check("H-39 확정된 사이클 건너뛰기 → 409 CYCLE_ALREADY_CONFIRMED", r.status_code == 409 and code(r) == "CYCLE_ALREADY_CONFIRMED", f"{r.status_code} {code(r)}")
    time.sleep(61)  # A 액션 리미터 회복
    r = c.post(f"/api/v1/orders/{draft}/delivery", json={"received": True})
    check("H-40 confirmed 주문 '받았어요' → 즉시 등록(inboundAt, delivered)", r.status_code == 200 and r.json()["inboundAt"] and r.json()["deliveryState"] == "delivered", f"{r.status_code} {code(r)}")
    rows = psql(f"SELECT count(*), string_agg(DISTINCT source, ',') FROM fridge_items WHERE order_id='{draft}'")
    check("H-41 등록 행 source=delivery, order_id FK", rows.endswith("|delivery") and int(rows.split("|")[0]) > 0, rows)
    r = c.post(f"/api/v1/orders/{draft}/delivery", json={"received": True})
    rows2 = psql(f"SELECT count(*) FROM fridge_items WHERE order_id='{draft}'")
    check("H-42 '받았어요' 재호출 → no-op (재고 불변)", r.status_code == 200 and rows2 == rows.split("|")[0], f"{rows.split('|')[0]} -> {rows2}")
    r = c.get("/api/v1/cycle")
    check("H-43 GET /cycle stage=delivered, currentOrder.inboundAt 제공, weeklyLimit Money 객체", r.json()["stage"] == "delivered" and r.json()["currentOrder"]["inboundAt"]
          and r.json()["weeklyLimit"]["currency"] == "KRW", f"{r.json()['stage']} {r.json()['weeklyLimit']}")
    r = c.post(f"/api/v1/orders/{draft}/cancel")
    check("H-44 등록 후 취소 → cancelled + 배송분 냉장고 롤백", r.status_code == 200 and r.json()["status"] == "cancelled"
          and psql(f"SELECT count(*) FROM fridge_items WHERE order_id='{draft}'") == "0", f"{r.status_code} {code(r)}")

# ---------------------------------------------------------------- 알림 설정 타입 3종
with client(B) as c:
    r = c.get("/api/v1/notifications/settings")
    payload = r.json() if r.status_code == 200 else {}
    rows = payload if isinstance(payload, list) else next((v for v in payload.values() if isinstance(v, list)), [])
    types = {s["type"] for s in rows}
    check("H-45 GET /notifications/settings 에 order_approval/fridge_inbound/cycle_paused 기본 on",
          {"order_approval", "fridge_inbound", "cycle_paused"} <= types and all(s["enabled"] for s in rows if s["type"] in {"order_approval", "fridge_inbound", "cycle_paused"}),
          f"{r.status_code} types={sorted(types)}")

# ---------------------------------------------------------------- 오류 응답 규격 / 정보 노출
with client(B) as c:
    r = c.put("/api/v1/cycle/settings", json={"timezone": "Mars/Olympus"})
    body = r.text
    check("H-46 422 응답에 스택·파일 경로 미노출", "Traceback" not in body and "/app/" not in body and ".py" not in body, body[:160])
    r = c.get("/api/v1/orders/preview")  # D? B has plan → 200
    check("H-47 응답에 자격증명 값 없음", "qa-fake" not in r.text and "jwt" not in r.text.lower(), r.text[:100])
    notes = r.json().get("notes", []) if r.status_code == 200 else []
    check("H-48 [관찰] 사용자 응답 notes 에 서버 내부 설정 안내(.env 변수명)가 노출되지 않는가", not any(".env" in n or "NAVER_CLIENT" in n for n in notes), f"notes={notes}")

print("\n==== SUMMARY ====")
p = sum(1 for r in RESULTS if r[1] == "PASS")
print(f"PASS {p} / FAIL {len(RESULTS) - p}")
for r in RESULTS:
    if r[1] == "FAIL":
        print("  FAIL", r[0], r[2][:300])
json.dump(RESULTS, open(os.path.join(os.path.dirname(__file__), "http_results.json"), "w"), ensure_ascii=False, indent=1)
