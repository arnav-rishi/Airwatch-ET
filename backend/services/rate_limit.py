import time
from collections import defaultdict, deque
from threading import Lock

# In-memory sliding-window limiter, per client IP. Same trade-off as the
# station cache (services/cache.py): per-process, not shared across
# serverless invocations/workers — good enough to blunt runaway LLM cost
# from a single caller, not a substitute for a real gateway-level limiter
# in front of a multi-instance production deployment.
WINDOW_SECONDS = 60
MAX_REQUESTS = 10

_hits: dict[str, deque] = defaultdict(deque)
_lock = Lock()


def check_rate_limit(client_id: str) -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds)."""
    now = time.monotonic()
    with _lock:
        q = _hits[client_id]
        while q and now - q[0] > WINDOW_SECONDS:
            q.popleft()
        if len(q) >= MAX_REQUESTS:
            retry_after = int(WINDOW_SECONDS - (now - q[0])) + 1
            return False, retry_after
        q.append(now)
        return True, 0
