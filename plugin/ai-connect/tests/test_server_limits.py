"""TokenBucket: per-connection rate limit with an injected clock."""

import test_server_harness as h

import pytest

from server.limits import Limits, TokenBucket


def test_burst_then_refuse():
    clock = h.FrozenClock()
    bucket = TokenBucket(rate=10, capacity=10, clock=clock)
    assert all(bucket.allow() for _ in range(10))
    assert not bucket.allow()


def test_refills_with_time():
    clock = h.FrozenClock()
    bucket = TokenBucket(rate=10, capacity=10, clock=clock)
    for _ in range(10):
        bucket.allow()
    clock.now += 0.1
    assert bucket.allow()
    assert not bucket.allow()


def test_refill_capped_at_capacity():
    clock = h.FrozenClock()
    bucket = TokenBucket(rate=10, capacity=3, clock=clock)
    clock.now += 3600
    assert sum(bucket.allow() for _ in range(10)) == 3


def test_clock_going_backwards_does_not_add_tokens():
    clock = h.FrozenClock()
    bucket = TokenBucket(rate=1, capacity=1, clock=clock)
    assert bucket.allow()
    clock.now -= 100
    assert not bucket.allow()


@pytest.mark.parametrize(("rate", "capacity"), [(0, 1), (1, 0), (-1, 5)])
def test_invalid_parameters(rate, capacity):
    with pytest.raises(ValueError):
        TokenBucket(rate=rate, capacity=capacity)


def test_limits_defaults():
    limits = Limits()
    assert limits.max_message_bytes == 64 * 1024
    assert limits.rate_per_second == 10
    assert limits.rate_burst == 10
    assert limits.max_stored_per_peer > 0
