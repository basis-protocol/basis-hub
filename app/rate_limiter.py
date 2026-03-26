"""
Rate Limiter — sliding window, in-memory.
Two tiers:
  - No valid API key: 10 req/min per IP
  - Valid API key:    120 req/min per key

The in-memory store resets on every restart. This is intentional —
DB-backed counters would add latency to every request. A restart gives
everyone a fresh window.
"""

import time
import threading
from collections import defaultdict

PUBLIC_RATE_LIMIT = 10
KEYED_RATE_LIMIT = 120
WINDOW_SECONDS = 60


class RateLimiter:
    def __init__(self):
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, identifier: str, limit: int) -> tuple[bool, int]:
        """Returns (allowed, remaining) for the given identifier and limit."""
        now = time.time()
        window_start = now - WINDOW_SECONDS

        with self._lock:
            self._requests[identifier] = [
                t for t in self._requests[identifier] if t > window_start
            ]
            count = len(self._requests[identifier])

            if count >= limit:
                return False, 0

            self._requests[identifier].append(now)
            return True, limit - count - 1

    def cleanup(self):
        """Remove stale entries. Safe to call periodically from a background thread."""
        now = time.time()
        window_start = now - WINDOW_SECONDS
        with self._lock:
            stale = [
                k for k, v in self._requests.items()
                if not v or all(t <= window_start for t in v)
            ]
            for k in stale:
                del self._requests[k]


rate_limiter = RateLimiter()
