"""
Account Pool and Proxy Pool for LLM API load balancing.

Thread-safe round-robin pools with rate-limit awareness and failure tracking.
"""

import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Account:
    """A single API account with tracking metadata."""

    api_key: str
    base_url: str | None = None
    org_id: str | None = None
    rate_limited_until: float = field(default=0.0, repr=False)
    consecutive_errors: int = field(default=0, repr=False)
    total_requests: int = field(default=0, repr=False)


class AccountPool:
    """Thread-safe round-robin pool of API accounts with rate-limit awareness.

    Rotates through accounts to distribute load. When an account hits a rate
    limit, it's temporarily skipped in favor of others. If all accounts are
    rate-limited, the one with the earliest recovery time is returned.
    """

    def __init__(self, accounts: list[dict]):
        if not accounts:
            raise ValueError("At least one account is required")
        self._accounts = [Account(**a) if isinstance(a, dict) else a for a in accounts]
        self._index = 0
        self._lock = threading.Lock()

    def get_next(self) -> Account:
        """Get the next available account, skipping rate-limited ones."""
        with self._lock:
            now = time.monotonic()
            n = len(self._accounts)
            for _ in range(n):
                account = self._accounts[self._index % n]
                self._index += 1
                if account.rate_limited_until <= now:
                    account.total_requests += 1
                    return account
            earliest = min(self._accounts, key=lambda a: a.rate_limited_until)
            wait_time = earliest.rate_limited_until - now
            if wait_time > 0:
                logger.warning(f"All accounts rate-limited, using one with {wait_time:.1f}s remaining")
            earliest.total_requests += 1
            return earliest

    def mark_rate_limited(self, account: Account, retry_after: float = 60.0):
        """Mark an account as rate-limited for a duration."""
        with self._lock:
            account.rate_limited_until = time.monotonic() + retry_after
            account.consecutive_errors += 1
            logger.warning(
                f"Account rate-limited for {retry_after:.0f}s (consecutive errors: {account.consecutive_errors})"
            )

    def mark_success(self, account: Account):
        """Reset error tracking after a successful request."""
        with self._lock:
            account.consecutive_errors = 0

    @property
    def size(self) -> int:
        return len(self._accounts)


class ProxyPool:
    """Thread-safe round-robin pool of HTTP/SOCKS proxy URLs.

    Rotates through proxies to distribute traffic. Failed proxies are
    temporarily removed from rotation with a configurable cooldown.
    Supports http://, https://, socks5:// proxy URLs.
    """

    def __init__(self, proxies: list[str] | None = None):
        self._proxies = proxies or []
        self._index = 0
        self._lock = threading.Lock()
        self._failed: dict[str, float] = {}

    def get_next(self) -> str | None:
        """Get the next available proxy URL, or None if no proxies configured."""
        if not self._proxies:
            return None
        with self._lock:
            now = time.monotonic()
            n = len(self._proxies)
            for _ in range(n):
                proxy = self._proxies[self._index % n]
                self._index += 1
                if self._failed.get(proxy, 0.0) <= now:
                    return proxy
            return min(self._proxies, key=lambda p: self._failed.get(p, 0.0))

    def mark_failed(self, proxy: str, cooldown: float = 300.0):
        """Mark a proxy as temporarily unavailable."""
        with self._lock:
            self._failed[proxy] = time.monotonic() + cooldown
            logger.warning(f"Proxy {proxy} marked failed for {cooldown:.0f}s")

    def mark_success(self, proxy: str):
        """Clear failure state for a proxy."""
        with self._lock:
            self._failed.pop(proxy, None)

    @property
    def size(self) -> int:
        return len(self._proxies)
