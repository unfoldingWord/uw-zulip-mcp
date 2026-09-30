"""Process-wide singletons for OAuth2-only (vault-backed) hosted mode.

The middleware and the enrollment web routes must share the same SecretStore,
key cache, and cool-off state, so they live here behind lazy getters. Tests
can inject fakes via the ``set_*`` helpers and restore with ``reset``.
"""

from __future__ import annotations

from . import hosted_config
from .enrollment import CoolOff
from .key_cache import SlidingKeyCache
from .secret_store import SecretStore

_store: SecretStore | None = None
_cache: SlidingKeyCache | None = None
_cooloff: CoolOff | None = None


def get_secret_store() -> SecretStore:
    global _store
    if _store is None:
        _store = SecretStore()
    return _store


def get_key_cache() -> SlidingKeyCache:
    global _cache
    if _cache is None:
        _cache = SlidingKeyCache(ttl_seconds=hosted_config.key_cache_ttl_seconds())
    return _cache


def get_cooloff() -> CoolOff:
    global _cooloff
    if _cooloff is None:
        _cooloff = CoolOff()
    return _cooloff


def set_secret_store(store: SecretStore | None) -> None:
    global _store
    _store = store


def set_key_cache(cache: SlidingKeyCache | None) -> None:
    global _cache
    _cache = cache


def set_cooloff(cooloff: CoolOff | None) -> None:
    global _cooloff
    _cooloff = cooloff


def reset() -> None:
    """Clear all singletons (used by tests)."""
    global _store, _cache, _cooloff
    _store = None
    _cache = None
    _cooloff = None
