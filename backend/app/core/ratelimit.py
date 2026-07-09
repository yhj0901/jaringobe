"""인메모리 rate limit — security-design.md CWE-307.

- /api/v1/auth/* : IP 기준 10회/분
- POST /api/v1/budget/plans : 유저 기준 5회/분
단일 프로세스 전제의 MVP 구현 (멀티 인스턴스 배포 시 Redis 등으로 교체).
"""

import time
from collections import defaultdict, deque


class InMemoryRateLimiter:
    """슬라이딩 윈도우 카운터."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        cutoff = now - self.window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


auth_ip_limiter = InMemoryRateLimiter(limit=10, window_seconds=60)
budget_user_limiter = InMemoryRateLimiter(limit=5, window_seconds=60)
