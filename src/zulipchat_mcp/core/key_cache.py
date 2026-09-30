"""In-memory sliding-expiry cache for per-user Zulip API keys.

Keys fetched from OpenBao/Vault are cached here so we hit the vault only on
first contact. Each entry expires after a period of *inactivity* (sliding
TTL): every successful read refreshes the timer, so an active user stays
cached while an idle user is dropped after the TTL.

Scope and lifetime:
- Process-local and in-memory only. Never written to disk or logs.
- One shared instance guards all identities; entries are keyed by the
  lowercased user email. Values are the plaintext API key.

Note for multi-replica deployments: this cache is per replica. That is fine
functionally (a cold replica simply re-fetches from the vault); it only means
the vault sees a little more read traffic. Cool-off counters, by contrast,
should be shared if you run more than one replica (see enrollment.py).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class _Entry:
    value: str
    last_access: float


class SlidingKeyCache:
    """Thread-safe cache whose entries expire after inactivity."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _norm(email: str) -> str:
        return email.strip().lower()

    def get(self, email: str) -> str | None:
        """Return the cached key for ``email`` and refresh its timer, or None."""
        now = time.monotonic()
        key = self._norm(email)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if now - entry.last_access >= self._ttl:
                del self._entries[key]
                return None
            entry.last_access = now
            return entry.value

    def set(self, email: str, api_key: str) -> None:
        """Cache ``api_key`` for ``email`` and start its inactivity timer."""
        with self._lock:
            self._entries[self._norm(email)] = _Entry(
                value=api_key, last_access=time.monotonic()
            )

    def invalidate(self, email: str) -> None:
        """Drop the cached key for ``email`` (e.g. after a Zulip 401)."""
        with self._lock:
            self._entries.pop(self._norm(email), None)

    def sweep(self) -> int:
        """Evict every entry past its inactivity TTL. Returns count removed."""
        now = time.monotonic()
        with self._lock:
            stale = [
                k for k, e in self._entries.items() if now - e.last_access >= self._ttl
            ]
            for k in stale:
                del self._entries[k]
            return len(stale)

    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
