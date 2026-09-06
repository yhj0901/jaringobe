"""QA 재판정 하네스(2026-09-05) — GATE 4 수정분(BUG-001~005·008·009) 잔여 경로 탐색.

qa_loop.py 의 대역·가상 시계·픽스처를 그대로 가져와 쓴다. 실행:
  cd backend && DATABASE_URL=...jaringobe_qa2 uv run python ../docs/테스트/harness/qa_rejudge.py
qa_loop.py 와 같은 DB 에 이어서 돌려도 된다(닉네임 접두 R-).
"""
import asyncio
import os
import sys
import traceback
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_loop as H  # noqa: E402  (import 시 대역·가상 시계 설치)

from sqlalchemy import func, select  # noqa: E402

from app.domains.budget import service as budget_service  # noqa: E402
from app.domains.cycle import scheduler as cycle_scheduler  # noqa: E402
from app.domains.cycle import service as cycle_service  # noqa: E402
from app.domains.cycle.models import UserCycleSettings  # noqa: E402
from app.domains.fridge.models import FridgeItem  # noqa: E402
from app.domains.order import service as order_service  # noqa: E402
from app.domains.order.models import Order  # noqa: E402
from app.domains.auth.models import User  # noqa: E402

C = date(2026, 9, 13)
D5 = datetime(2026, 9, 8, 0, 5, tzinfo=UTC)
D2 = datetime(2026, 9, 11, 0, 5, tzinfo=UTC)
D1 = datetime(2026, 9, 12, 0, 10, tzinfo=UTC)
check, get, tick, SessionLocal, CART_MODE, CART_CALLS = H.check, H.get, H.tick, H.SessionLocal, H.CART_MODE, H.CART_CALLS


async def seed(nick, **kw):
    async with SessionLocal() as db:
        H.Clock.set(datetime(2026, 9, 8, 0, 0, tzinfo=UTC))
        user, *_ = await H.make_user(db, nick, prev_cycle_start=date(2026, 9, 6), **kw)
        return user.id


async def order_of(db, uid):
    rows = await get(db, Order, user_id=uid, cycle_start=C)
    return rows[0] if rows else None


# ====================================================================== BUG-001 재판정
async def r_bug001():
    # R-01: 초안 ≤ 한도, D-1 재계산 > 한도 → 차단이 확정·inbound '이전'에 일어나는가 + 스냅샷 최신화 + 재판정 없음
    uid = await seed("R-001a-drift", locked=True)
    await tick(D5); await tick(D2)
    async with SessionLocal() as db:
        o = await order_of(db, uid)
        draft_total, draft_items = o.estimated_total, len((await H.load_order(db, o.id)).items)
        u = (await get(db, User, id=uid))[0]
        H.Clock.set(D1)
        limit = await budget_service.cycle_limit(db, u, C, 7, timezone_name="Asia/Seoul")
    CART_MODE["multiplier"] = Decimal("4")
    H.PUSH_CALLS.clear()
    await tick(D1)
    async with SessionLocal() as db:
        o = await H.load_order(db, (await order_of(db, uid)).id)
        fridge_rows = await get(db, FridgeItem, order_id=o.id)
        check("R-01a [BUG-001] 재계산 322,000 > 한도 → awaiting_user/BUDGET_EXCEEDED, 확정 전이 없음",
              o.status == "awaiting_user" and o.blocked_reason == "BUDGET_EXCEEDED" and o.confirmed_at is None
              and o.auto_confirmed is False, f"status={o.status} reason={o.blocked_reason} draft={draft_total} limit={limit}")
        check("R-01b [BUG-001] 차단이 inbound 이전 — inbound_at NULL, delivery_eta NULL, 배송분 냉장고 0행",
              o.inbound_at is None and o.delivery_eta is None and not fridge_rows,
              f"inbound_at={o.inbound_at} eta={o.delivery_eta} fridge_rows={len(fridge_rows)}")
        check("R-01c [BUG-001] 차단 시 초안 스냅샷이 재계산가(322,000)로 갱신되고 라인 수 유지(설계 3-9-5 v1.10)",
              o.estimated_total == Decimal("322000") and len(o.items) == draft_items and o.auto_confirm_at is None,
              f"total={o.estimated_total} items={len(o.items)}/{draft_items} auto_confirm_at={o.auto_confirm_at}")
        check("R-01d [BUG-001] 차단 시 재알림(order_approval) 1회", sum(1 for p in H.PUSH_CALLS if p[0] == uid) == 1, f"{len(H.PUSH_CALLS)}")
    CART_CALLS.clear(); H.PUSH_CALLS.clear()
    r = await tick(D1 + timedelta(hours=1))
    async with SessionLocal() as db:
        o = await order_of(db, uid)
        check("R-01e [BUG-001] 차단 후 다음 tick 재판정·재계산·재알림 없음(멱등)",
              o.status == "awaiting_user" and r["autoConfirmed"] == 0 and not CART_CALLS and not H.PUSH_CALLS,
              f"status={o.status} naver_calls={len(CART_CALLS)} push={len(H.PUSH_CALLS)}")
        n = await db.scalar(select(func.count(Order.id)).where(Order.user_id == uid, Order.status == "confirmed"))
        check("R-01f [BUG-001] 락 사용자 confirmed 0건(어떤 경로로도 한도 초과 자동확정 없음)", n == 0, f"confirmed={n}")
        # 사용자 명시 승인(시세 정상화) → 확정 허용, 총액 = 승인 시점 재계산
        u = (await get(db, User, id=uid))[0]
        CART_MODE["multiplier"] = Decimal("1")
        resp = await order_service.approve_order(db, u, o.id, exclude_names=None, timezone_name="Asia/Seoul", lead_days=1, local_hour=9)
        check("R-01g awaiting_user → 명시 승인 → confirmed(auto_confirmed=false), 총액=승인 시점 재계산(80,500)",
              resp.status == "confirmed" and resp.auto_confirmed is False and Decimal(resp.estimated_total.amount) == Decimal("80500"),
              f"{resp.status} {resp.estimated_total.amount}")
    CART_MODE["multiplier"] = Decimal("1")

    # R-02: 반대 방향 — 초안 > 한도(×4), D-1 재계산 ≤ 한도(×1) → 재계산가 기준으로 통과해야 함(초안 스냅샷으로 판정하면 차단됨)
    uid2 = await seed("R-001b-drop", locked=True)
    await tick(D5)
    CART_MODE["multiplier"] = Decimal("4")
    await tick(D2)
    CART_MODE["multiplier"] = Decimal("1")
    async with SessionLocal() as db:
        d = await order_of(db, uid2); draft_total = d.estimated_total
    await tick(D1)
    async with SessionLocal() as db:
        o = await order_of(db, uid2)
        check("R-02 [BUG-001] 초안 322,000 > 한도지만 D-1 재계산 80,500 ≤ 한도 → 재계산가로 자동확정(게이트가 초안 스냅샷을 쓰지 않음)",
              o.status == "confirmed" and o.auto_confirmed and o.estimated_total == Decimal("80500"),
              f"draft={draft_total} status={o.status} total={o.estimated_total} reason={o.blocked_reason}")

    # R-03: 미매칭 비율 게이트 ④도 재계산 라인 기준인가 (초안 전량 매칭, D-1 시세에서 6/15 미매칭 = 40%)
    uid3 = await seed("R-001c-unmatched", locked=True)
    await tick(D5); await tick(D2)
    CART_MODE["unmatched"] = {"두부", "된장", "애호박", "쌀", "양파", "고추장"}
    await tick(D1)
    CART_MODE["unmatched"] = set()
    async with SessionLocal() as db:
        o = await H.load_order(db, (await order_of(db, uid3)).id)
        um = sum(1 for l in o.items if l.line_type == "needed" and not l.matched)
        check("R-03 [BUG-001] 미매칭 게이트 ④가 재계산 라인 기준 — D-1 미매칭 40% → UNMATCHED_RATIO, 스냅샷에 미매칭 라인 반영",
              o.status == "awaiting_user" and o.blocked_reason == "UNMATCHED_RATIO" and um >= 6,
              f"status={o.status} reason={o.blocked_reason} unmatched_lines={um}")

    # R-04: D-1 자동확정 중 시세 조회 자체가 실패하면? (재계산이 게이트 안으로 들어온 뒤의 장애 거동 관찰)
    uid4 = await seed("R-001d-d1down", locked=True)
    await tick(D5); await tick(D2)
    CART_MODE["mode"] = "raise"; CART_CALLS.clear()
    for i in range(3):
        await tick(D1 + timedelta(minutes=i))
    async with SessionLocal() as db:
        o = await order_of(db, uid4)
        check("R-04a [관찰] D-1 시세 장애 3 tick → 초안 유지(draft), 잘못된 확정·awaiting 전이 없음",
              o.status == "draft" and o.auto_confirm_at is not None, f"status={o.status} reason={o.blocked_reason}")
        record_note = f"3 tick 동안 네이버 호출 {len(CART_CALLS)}회, auto_confirm_at={o.auto_confirm_at}"
        check("R-04b [관찰] D-1 시세 장애 시 재시도가 백오프를 따르는가(매 tick 재호출이면 FAIL — 기획 5-4 는 초안 단계만 명시)",
              len(CART_CALLS) <= 1, record_note)
    CART_MODE["mode"] = "match"
    await tick(D1 + timedelta(minutes=3))
    async with SessionLocal() as db:
        o = await order_of(db, uid4)
        check("R-04c D-1 시세 복구 → 다음 tick 자동확정(루프 지속)", o.status == "confirmed" and o.auto_confirmed, f"status={o.status}")


# ====================================================================== BUG-003 재판정 (S8-04 정밀)
async def r_bug003():
    # eta 도달 '이전' 시점에 D-2 스캔이 지나가도록 수동 확정을 9/10 23:00Z 에 수행(eta = 로컬 9/11 +1일 09:00 KST = 9/12 00:00Z)
    uid = await seed("R-003-manual-late")
    await tick(D5)
    async with SessionLocal() as db:
        u = (await get(db, User, id=uid))[0]
        H.Clock.set(datetime(2026, 9, 10, 23, 0, tzinfo=UTC))
        resp = await order_service.confirm_order(db, u, "kurly", cycle_start=C, frequency="weekly", timezone_name="Asia/Seoul", lead_days=1, local_hour=9)
        check("R-05a 사전조건: D-2 직전 수동 확정, eta=9/12 00:00Z", resp.status == "confirmed" and resp.delivery_eta == datetime(2026, 9, 12, 0, 0, tzinfo=UTC), f"{resp.status} eta={resp.delivery_eta}")
    H.PUSH_CALLS.clear()
    await tick(D2)
    async with SessionLocal() as db:
        orders = await get(db, Order, user_id=uid, cycle_start=C)
        s = (await get(db, UserCycleSettings, user_id=uid))[0]
        u = (await get(db, User, id=uid))[0]
        st = await cycle_service.build_cycle_state(db, u, s, now=H.Clock.now)
        check("R-05b [BUG-003] eta 이전 D-2 스캔 → 초안 추가 없음, GET /cycle stage=confirmed(순수 재현 — S8-04 원래 의도)",
              sorted(o.status for o in orders) == ["confirmed"] and st.stage == "confirmed" and s.last_stage == "drafted",
              f"orders={[o.status for o in orders]} stage={st.stage} last_stage={s.last_stage}")
        check("R-05c [BUG-003] 확정 사이클에는 order_approval 승인 알림이 나가지 않음", not [p for p in H.PUSH_CALLS if p[0] == uid], f"{len(H.PUSH_CALLS)}")
    await tick(datetime(2026, 9, 12, 0, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        o = await order_of(db, uid)
        u = (await get(db, User, id=uid))[0]; s = (await get(db, UserCycleSettings, user_id=uid))[0]
        st = await cycle_service.build_cycle_state(db, u, s, now=H.Clock.now)
        check("R-05d eta 도달 → inbound → stage=delivered (S8-04 의 'delivered' 는 정상 전이)", o.inbound_at is not None and st.stage == "delivered", f"inbound={o.inbound_at} stage={st.stage}")

    # 재현 B 변형: awaiting_user 상태에서 타임존 변경 → next_run 이 과거 D-2 로 되돌아가지 않고, 초안 중복 없음
    uid2 = await seed("R-003-tz-awaiting", budget=Decimal("30000"), locked=True)
    await tick(D5); await tick(D2); await tick(D1)
    from app.domains.cycle.schemas import CycleSettingsUpdateRequest
    async with SessionLocal() as db:
        u = (await get(db, User, id=uid2))[0]
        H.Clock.set(datetime(2026, 9, 12, 2, 0, tzinfo=UTC))
        await cycle_service.update_settings(db, u, CycleSettingsUpdateRequest(timezone="Asia/Tokyo"))
        s = (await get(db, UserCycleSettings, user_id=uid2))[0]
        check("R-06a [BUG-003] awaiting_user 사이클 타임존 변경 → next_run_at 미래(다음 사이클 D-5)", s.next_run_at > H.Clock.now, f"next={s.next_run_at}")
    await tick(datetime(2026, 9, 12, 2, 1, tzinfo=UTC))
    async with SessionLocal() as db:
        orders = await get(db, Order, user_id=uid2, cycle_start=C)
        check("R-06b [BUG-003] 변경 후 초안 중복 없음, awaiting_user 유지", [o.status for o in orders] == ["awaiting_user"], f"{[o.status for o in orders]}")


# ====================================================================== BUG-004 재판정 (월 경계 양방향)
async def r_bug004():
    # 9월 마지막 사이클(9/27) 을 9/26 에 확정 → 9월 한도에서 차감되고 10월 한도(10/4) 에는 미차감
    async with SessionLocal() as db:
        H.Clock.set(datetime(2026, 9, 22, 0, 0, tzinfo=UTC))
        user, *_ = await H.make_user(db, "R-004-septail", prev_cycle_start=date(2026, 9, 20))
        uid = user.id
    await tick(datetime(2026, 9, 22, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 25, 0, 5, tzinfo=UTC)); await tick(datetime(2026, 9, 26, 0, 10, tzinfo=UTC))
    async with SessionLocal() as db:
        o = await get(db, Order, user_id=uid, cycle_start=date(2026, 9, 27))
        total = o[0].estimated_total if o else Decimal(0)
        u = (await get(db, User, id=uid))[0]
        H.Clock.set(datetime(2026, 10, 3, 0, 10, tzinfo=UTC))
        lim_oct4 = await budget_service.cycle_limit(db, u, date(2026, 10, 4), 7, timezone_name="Asia/Seoul")
        exp_oct4 = (Decimal("400000") * 10 / 31).quantize(Decimal("0.01"))
        check("R-07 [BUG-004] 9/27 사이클 확정액은 10월 한도(10/4)에서 차감되지 않음(월 귀속 = cycle_start)",
              bool(o) and o[0].status == "confirmed" and lim_oct4 == exp_oct4, f"sep_total={total} limit_oct4={lim_oct4} exp={exp_oct4}")


# ====================================================================== BUG-009 · BUG-008 · BUG-005 (단위 경계)
async def r_low():
    from pydantic import ValidationError
    from app.domains.order.schemas import DeliveryUpdateRequest
    bad = []
    for v in ("yes", "true", 1, 0, "1", None):
        try:
            DeliveryUpdateRequest(received=v); bad.append(repr(v))
        except ValidationError:
            pass
    ok = DeliveryUpdateRequest(received=True).received is True and DeliveryUpdateRequest(received=False).received is False
    check("R-08 [BUG-009] received 는 StrictBool — 'yes'/'true'/1/0/'1'/None 전부 422, true/false 만 수용", not bad and ok, f"accepted={bad}")
    import subprocess
    r = subprocess.run(["grep", "-rn", "NAVER_CLIENT_ID/SECRET", os.path.join(os.path.dirname(__file__), "../../../backend/app")], capture_output=True, text=True)
    check("R-09 [BUG-008] 사용자 응답 경로(app/)에 '.env NAVER_CLIENT_ID/SECRET' 안내 문구 잔존 0건", r.stdout.strip() == "", r.stdout[:200])


async def main():
    for fn in (r_bug001, r_bug003, r_bug004, r_low):
        CART_MODE.update({"mode": "match", "multiplier": Decimal("1"), "unmatched": set()})
        H.GEN_MODE["mode"] = "mock"
        try:
            await fn()
        except Exception:
            H.record(f"{fn.__name__} EXC", False, traceback.format_exc()[-1500:])
    print("\n==== SUMMARY (rejudge) ====")
    p = sum(1 for r in H.RESULTS if r[1] == "PASS"); f = len(H.RESULTS) - p
    print(f"PASS {p} / FAIL {f}")
    for r in H.RESULTS:
        if r[1] == "FAIL":
            print("  FAIL", r[0], r[2][:400])


if __name__ == "__main__":
    asyncio.run(main())
