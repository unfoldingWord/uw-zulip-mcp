"""Caching implementation for ZulipChat MCP Server."""

import difflib
import hashlib
import logging
import os
import time
from collections.abc import Callable as TypingCallable
from functools import lru_cache, wraps
from typing import Any, TypeVar, cast

logger = logging.getLogger(__name__)


def _int_env(key: str, default: int) -> int:
    """Parse an integer from env var with safe fallback."""
    val = os.getenv(key, "")
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        logger.warning(
            "Invalid value for %s: '%s' — using default %d", key, val, default
        )
        return default


def _float_env(key: str, default: float) -> float:
    """Parse a float from env var with safe fallback."""
    val = os.getenv(key, "")
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        logger.warning(
            "Invalid value for %s: '%s' — using default %s", key, val, default
        )
        return default


F = TypeVar("F", bound=TypingCallable[..., Any])


class MessageCache:
    """Simple in-memory cache for messages."""

    def __init__(self, ttl: int = 300) -> None:
        """Initialize cache.

        Args:
            ttl: Time to live in seconds (default: 5 minutes)
        """
        self.cache: dict[str, tuple[Any, float]] = {}
        self.ttl = ttl

    def _make_key(self, *args: Any, **kwargs: Any) -> str:
        """Create cache key from arguments."""
        key_data = str(args) + str(sorted(kwargs.items()))
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if expired/not found
        """
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            del self.cache[key]
        return None

    def set(self, key: str, value: Any) -> None:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        self.cache[key] = (value, time.time())

    def clear_expired(self) -> None:
        """Clear expired entries from cache."""
        now = time.time()
        expired = [k for k, (_, t) in self.cache.items() if now - t >= self.ttl]
        for key in expired:
            del self.cache[key]

    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()

    def size(self) -> int:
        """Get number of cached items."""
        return len(self.cache)


def _identity_scope() -> str:
    """Cache-key prefix for the current request identity.

    Empty in single-user (stdio) mode — keys are unchanged. In hosted mode
    each credential identity gets its own key space so data visible to one
    user (stream lists, user directories) is never served to another.
    """
    from .request_credentials import current_cache_scope

    return current_cache_scope()


class StreamCache:
    """Cache for stream information. Keys are scoped per request identity."""

    def __init__(self, ttl: int = 600) -> None:
        """Initialize stream cache.

        Args:
            ttl: Time to live in seconds (default: 10 minutes)
        """
        self.cache = MessageCache(ttl)

    def get_streams(self) -> list[Any] | None:
        """Get cached streams list."""
        return self.cache.get(f"{_identity_scope()}:streams_list")

    def set_streams(self, streams: list[Any]) -> None:
        """Cache streams list."""
        self.cache.set(f"{_identity_scope()}:streams_list", streams)

    def get_stream_info(self, stream_name: str) -> dict[str, Any] | None:
        """Get cached stream information."""
        return self.cache.get(f"{_identity_scope()}:stream_{stream_name}")

    def set_stream_info(self, stream_name: str, info: dict[str, Any]) -> None:
        """Cache stream information."""
        self.cache.set(f"{_identity_scope()}:stream_{stream_name}", info)


class UserCache:
    """Cache for user information with fuzzy name resolution.

    All entries and indexes are scoped per request identity so hosted-mode
    users never see each other's cached directory data.
    """

    def __init__(self, ttl: int = 900) -> None:
        """Initialize user cache.

        Args:
            ttl: Time to live in seconds (default: 15 minutes)
        """
        self.cache = MessageCache(ttl)
        # scope → lowercase name → email
        self._name_index: dict[str, dict[str, str]] = {}
        # scope → display email → delivery email
        self._email_to_delivery: dict[str, dict[str, str]] = {}

    def get_users(self) -> list[Any] | None:
        """Get cached users list."""
        return self.cache.get(f"{_identity_scope()}:users_list")

    def set_users(self, users: list[Any]) -> None:
        """Cache users list and build name index."""
        scope = _identity_scope()
        self.cache.set(f"{scope}:users_list", users)
        name_index = self._name_index.setdefault(scope, {})
        name_index.clear()
        email_to_delivery = self._email_to_delivery.setdefault(scope, {})
        email_to_delivery.clear()
        for user in users:
            if not user.get("is_active", True):
                continue
            email = user.get("email", "")
            delivery = user.get("delivery_email", "")
            full_name = user.get("full_name", "")
            # Map display email to delivery email for identity matching
            if email and delivery and email != delivery:
                email_to_delivery[email] = delivery
            if full_name and email:
                name_index[full_name.lower()] = email
                # Index first name too
                first = full_name.split()[0]
                if first.lower() not in name_index:
                    name_index[first.lower()] = email

    def resolve_user(self, query: str) -> dict[str, Any]:
        """Resolve a display name to email via fuzzy matching.

        Returns dict with email, full_name, matched, and confidence.
        """
        q = query.lower().strip()
        name_index = self._name_index.get(_identity_scope(), {})

        # Exact match first
        if q in name_index:
            email = name_index[q]
            return {"email": email, "matched": q, "confidence": 1.0}

        # Fuzzy match
        cutoff = _float_env("ZULIPCHAT_FUZZY_MATCH_CUTOFF", 0.6)
        cutoff = max(0.0, min(1.0, cutoff))
        matches = difflib.get_close_matches(q, name_index.keys(), n=1, cutoff=cutoff)
        if matches:
            matched = matches[0]
            email = name_index[matched]
            score = difflib.SequenceMatcher(None, q, matched).ratio()
            return {"email": email, "matched": matched, "confidence": round(score, 2)}

        return {"email": None, "matched": None, "confidence": 0.0}

    def is_same_user(self, email_a: str, email_b: str) -> bool:
        """Check if two emails (display or delivery) belong to the same user."""
        if email_a == email_b:
            return True
        email_to_delivery = self._email_to_delivery.get(_identity_scope(), {})
        # Check cross-mapping: a's delivery == b, or b's delivery == a
        delivery_a = email_to_delivery.get(email_a, email_a)
        delivery_b = email_to_delivery.get(email_b, email_b)
        return (
            delivery_a == email_b or delivery_b == email_a or delivery_a == delivery_b
        )

    def get_user_info(self, email: str) -> dict[str, Any] | None:
        """Get cached user information."""
        return self.cache.get(f"{_identity_scope()}:user_{email}")

    def set_user_info(self, email: str, info: dict[str, Any]) -> None:
        """Cache user information."""
        self.cache.set(f"{_identity_scope()}:user_{email}", info)


def cache_decorator(ttl: int = 300, key_prefix: str = "") -> TypingCallable[[F], F]:
    """Decorator for caching function results.

    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache keys

    Returns:
        Decorated function with caching
    """
    cache = MessageCache(ttl)

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Generate cache key
            cache_key = key_prefix + cache._make_key(*args, **kwargs)

            # Check cache
            result = cache.get(cache_key)
            if result is not None:
                return result

            # Call function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result)
            return result

        return cast(F, wrapper)

    return decorator


def async_cache_decorator(
    ttl: int = 300, key_prefix: str = ""
) -> TypingCallable[[F], F]:
    """Decorator for caching async function results.

    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache keys

    Returns:
        Decorated async function with caching
    """
    cache = MessageCache(ttl)

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Generate cache key
            cache_key = key_prefix + cache._make_key(*args, **kwargs)

            # Check cache
            result = cache.get(cache_key)
            if result is not None:
                return result

            # Call async function and cache result
            result = await func(*args, **kwargs)
            cache.set(cache_key, result)
            return result

        return cast(F, wrapper)

    return decorator


# Global cache instances — TTLs configurable via environment variables
message_cache = MessageCache(ttl=_int_env("ZULIPCHAT_CACHE_TTL_MESSAGES", 300))
stream_cache = StreamCache(ttl=_int_env("ZULIPCHAT_CACHE_TTL_STREAMS", 600))
user_cache = UserCache(ttl=_int_env("ZULIPCHAT_CACHE_TTL_USERS", 900))


# LRU cache for frequently accessed data
@lru_cache(maxsize=100)
def get_cached_stream_id(stream_name: str) -> int | None:
    """Get cached stream ID by name.

    Args:
        stream_name: Name of the stream

    Returns:
        Stream ID or None
    """
    # This would be populated by actual API calls
    return None


@lru_cache(maxsize=200)
def get_cached_user_id(email: str) -> int | None:
    """Get cached user ID by email.

    Args:
        email: User's email address

    Returns:
        User ID or None
    """
    # This would be populated by actual API calls
    return None
