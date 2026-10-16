"""
Unit Tests for Redis Distributed Rate Limiter.
Verifies atomicity, token exhaustion, multi-threaded concurrency, and fail-closed safety.
"""
import pytest
import time
import threading
from backend.rate_limiter import RedisDistributedRateLimiter


@pytest.mark.integration
def test_rate_limiter_allowed_within_quota():
    """Verify standard rate limiting behavior within configured quota."""
    limiter = RedisDistributedRateLimiter(host="localhost", port=6379)
    test_key = f"test_quota_{time.time_ns()}"
    limit = 5
    window = 10

    # First 5 calls must pass
    for i in range(1, limit + 1):
        res = limiter.check_limit(test_key, limit=limit, window_seconds=window)
        assert res["status"] == "LIVE"
        assert res["allowed"] is True
        assert res["current_tokens"] == i
        assert res["remaining_tokens"] == limit - i

    # 6th call must be blocked
    res_blocked = limiter.check_limit(test_key, limit=limit, window_seconds=window)
    assert res_blocked["status"] == "LIVE"
    assert res_blocked["allowed"] is False
    assert res_blocked["remaining_tokens"] == 0


@pytest.mark.integration
def test_rate_limiter_multithreaded_concurrency():
    """Verify atomic token accounting under concurrent worker threads."""
    limiter = RedisDistributedRateLimiter(host="localhost", port=6379)
    test_key = f"test_concurrent_{time.time_ns()}"
    limit = 20
    window = 10
    total_calls = 50

    allowed_results = []
    blocked_results = []
    lock = threading.Lock()

    def worker():
        res = limiter.check_limit(test_key, limit=limit, window_seconds=window)
        with lock:
            if res["allowed"]:
                allowed_results.append(res)
            else:
                blocked_results.append(res)

    threads = [threading.Thread(target=worker) for _ in range(total_calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(allowed_results) == limit
    assert len(blocked_results) == total_calls - limit


def test_rate_limiter_fail_closed_when_redis_down():
    """Verify financial fail-closed safety when Redis connection fails."""
    # Point to invalid port to simulate Redis outage
    dead_limiter = RedisDistributedRateLimiter(host="localhost", port=59999, fail_closed=True, socket_timeout=0.2)
    res = dead_limiter.check_limit("critical_payment_gateway", limit=10, window_seconds=60)

    assert res["status"] == "UNAVAILABLE"
    assert res["allowed"] is False
    assert res["remaining_tokens"] == 0
    assert "error" in res
