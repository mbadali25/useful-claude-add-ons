"""Limits of the Bridge: message size, per-connection rate, stored messages per peer."""

import time
from collections.abc import Callable
from dataclasses import dataclass

from config_loader import DEFAULT_MAX_MESSAGE_BYTES, DEFAULT_MAX_STORED_PER_PEER, DEFAULT_RATE_PER_SECOND

DEFAULT_MAX_UNREAD_PER_PEER = 500
DEFAULT_MAX_UNREAD_BYTES_PER_PEER = 8 * 1024 * 1024


@dataclass(frozen=True)
class Limits:
    max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES
    rate_per_second: float = DEFAULT_RATE_PER_SECOND
    # Messages a connection may send at once before the rate applies
    rate_burst: int = int(DEFAULT_RATE_PER_SECOND)
    # Per sender; the oldest are deleted beyond it. 0 = no cap
    max_stored_per_peer: int = DEFAULT_MAX_STORED_PER_PEER
    # Per recipient: undelivered direct messages waiting for it to come
    # online. A send beyond either is refused (recipient_queue_full)
    max_unread_per_peer: int = DEFAULT_MAX_UNREAD_PER_PEER
    max_unread_bytes_per_peer: int = DEFAULT_MAX_UNREAD_BYTES_PER_PEER


class TokenBucket:
    """Allows capacity messages at once, refilled at rate per second."""

    def __init__(self, rate: float, capacity: int, clock: Callable[[], float] = time.monotonic):
        if rate <= 0 or capacity < 1:
            raise ValueError("TokenBucket needs a positive rate and a capacity of at least 1")
        self._rate = rate
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._clock = clock
        self._last = clock()

    def allow(self) -> bool:
        now = self._clock()
        # A clock that goes back adds nothing
        elapsed = max(0.0, now - self._last)
        self._last = max(self._last, now)
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False
