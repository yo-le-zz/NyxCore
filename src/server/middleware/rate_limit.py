"""Simple in-process sliding-window rate limiter."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, calls: int = 60, period: int = 60):
        super().__init__(app)
        self._calls = calls
        self._period = period
        self._buckets: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        # ─────────────────────────────────────────────
        # 1) SKIP UPLOAD CHUNKS (IMPORTANT FIX)
        # ─────────────────────────────────────────────
        if request.url.path.startswith("/api/v1/isos/upload/"):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        bucket = self._buckets[ip]

        # Remove timestamps outside the window
        while bucket and now - bucket[0] > self._period:
            bucket.popleft()

        if len(bucket) >= self._calls:
            return Response(
                content='{"detail":"Rate limit exceeded"}',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
                headers={"Retry-After": str(self._period)},
            )

        bucket.append(now)
        return await call_next(request)