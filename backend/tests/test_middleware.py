"""Origin 검증 / rate limit 미들웨어 + health 테스트."""

from tests.conftest import FRONTEND, login

VALID_PAYLOAD = {
    "householdSize": 2,
    "budget": {"amount": "300000", "currency": "KRW"},
    "mealDirection": "health",
    "source": "guest",
}


class TestOriginVerification:
    async def test_post_with_mismatched_origin_403(self, client):
        res = await client.post("/api/v1/auth/refresh", headers={"Origin": "https://evil.example"})
        assert res.status_code == 403
        assert res.json()["detail"]["code"] == "FORBIDDEN_ORIGIN"

    async def test_post_with_matching_origin_passes(self, client):
        res = await client.post("/api/v1/auth/refresh", headers={"Origin": FRONTEND})
        assert res.status_code == 401  # Origin 통과 → 쿠키 없음 401

    async def test_post_without_origin_passes(self, client):
        res = await client.post("/api/v1/auth/refresh")
        assert res.status_code == 401  # SameSite=Lax 1차 방어 전제 — 비브라우저 허용

    async def test_get_ignores_origin(self, client):
        res = await client.get("/api/v1/users/me", headers={"Origin": "https://evil.example"})
        assert res.status_code == 401  # 403 이 아니라 인증 오류

    async def test_budget_post_with_mismatched_origin_403(self, client, respx_mock):
        await login(client, respx_mock)
        res = await client.post(
            "/api/v1/budget/plans",
            json=VALID_PAYLOAD,
            headers={"Origin": "http://localhost:9999"},
        )
        assert res.status_code == 403
        assert res.json()["detail"]["code"] == "FORBIDDEN_ORIGIN"


class TestRateLimit:
    async def test_auth_ip_limit_10_per_minute(self, client):
        for i in range(10):
            res = await client.post("/api/v1/auth/refresh")
            assert res.status_code == 401, f"request {i}"
        res = await client.post("/api/v1/auth/refresh")
        assert res.status_code == 429
        assert res.json()["detail"]["code"] == "RATE_LIMITED"

    async def test_auth_limit_does_not_affect_users_me(self, client):
        for _ in range(11):
            await client.post("/api/v1/auth/refresh")
        res = await client.get("/api/v1/users/me")
        assert res.status_code == 401  # 429 아님 — /users/me 는 auth rate limit 대상 아님

    async def test_budget_user_limit_5_per_minute(self, client, respx_mock):
        await login(client, respx_mock)
        statuses = []
        for _ in range(6):
            res = await client.post("/api/v1/budget/plans", json=VALID_PAYLOAD)
            statuses.append(res.status_code)
        assert statuses[0] == 201
        assert statuses[1:5] == [409, 409, 409, 409]
        assert statuses[5] == 429
        assert res.json()["detail"]["code"] == "RATE_LIMITED"

    async def test_budget_limit_requires_auth_first(self, client):
        # 미인증 요청은 401 — 유저 rate limit 카운트 대상 아님
        for _ in range(6):
            res = await client.post("/api/v1/budget/plans", json=VALID_PAYLOAD)
        assert res.status_code == 401


class TestHealth:
    async def test_health_ok(self, client):
        res = await client.get("/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["db"] is True

    async def test_health_db_down(self, client, monkeypatch):
        import app.main as main_mod

        class BrokenEngine:
            def connect(self):
                raise RuntimeError("db down")

        monkeypatch.setattr(main_mod, "engine", BrokenEngine())
        res = await client.get("/health")
        assert res.status_code == 200
        body = res.json()
        assert body["db"] is False
        assert body["detail"] == "db down"


class TestRateLimiterUnit:
    def test_window_expiry_allows_again(self):
        import time

        from app.core.ratelimit import InMemoryRateLimiter

        limiter = InMemoryRateLimiter(limit=1, window_seconds=0.05)
        assert limiter.allow("k") is True
        assert limiter.allow("k") is False
        time.sleep(0.06)
        assert limiter.allow("k") is True  # 윈도우 경과분 제거 후 재허용
