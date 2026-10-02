"""Enrollment logic: signed links, Zulip key validation, cool-off, storage.

This module is transport-agnostic (no HTTP objects) so it can be unit-tested
directly. The web routes in ``enrollment_routes.py`` are a thin shell over it.

Flow:
1. A user makes an authenticated (OAuth) tool call but has no stored key.
2. We mint a short-lived, HMAC-signed enrollment link bound to their email
   and hand it back in the error message.
3. They open the link, read the instructions, and submit their Zulip API key.
4. We validate the key against Zulip, require the key's own Zulip email to
   match the signed email, then store it in the vault and warm the cache.
5. Wrong keys are rejected and never stored; after N failures the email is
   put in a cool-off period.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import threading
import time
from dataclasses import dataclass
from enum import Enum

import httpx

from ..utils.logging import get_logger
from . import hosted_config
from .key_cache import SlidingKeyCache
from .secret_store import SecretStore, SecretStoreError

logger = get_logger(__name__)


class ZulipValidationError(RuntimeError):
    """Raised when Zulip cannot be reached to validate a key (not a bad key)."""


# --- signed enrollment links ----------------------------------------------


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64u_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def mint_enrollment_token(
    email: str, *, secret: str | None = None, ttl_seconds: int | None = None
) -> str:
    """Create a signed ``email|expiry`` token for the enrollment link."""
    secret = secret if secret is not None else hosted_config.enroll_secret()
    ttl = (
        ttl_seconds
        if ttl_seconds is not None
        else hosted_config.enroll_token_ttl_seconds()
    )
    expiry = int(time.time()) + ttl
    payload = f"{email.strip().lower()}|{expiry}".encode()
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    return f"{_b64u(payload)}.{_b64u(sig)}"


def verify_enrollment_token(token: str, *, secret: str | None = None) -> str | None:
    """Return the email if the token is valid and unexpired, else None."""
    secret = secret if secret is not None else hosted_config.enroll_secret()
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload = _b64u_decode(payload_b64)
        sig = _b64u_decode(sig_b64)
    except Exception:
        return None
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        email, expiry_s = payload.decode().rsplit("|", 1)
        expiry = int(expiry_s)
    except ValueError:
        return None
    if time.time() >= expiry:
        return None
    return email


def enrollment_token_expiry(token: str) -> int | None:
    """Expiry (epoch seconds) encoded in a token, or None if unparseable.

    Does not check the signature — call ``verify_enrollment_token`` first. Used
    to bound how long a consumed-token record must be kept (see UsedTokens).
    """
    try:
        payload_b64, _sig_b64 = token.split(".", 1)
        _email, expiry_s = _b64u_decode(payload_b64).decode().rsplit("|", 1)
        return int(expiry_s)
    except Exception:
        return None


# --- single-use enrollment links ------------------------------------------


class UsedTokens:
    """Records enrollment tokens already consumed, so each link enrolls once.

    A token is consumed only on a *successful* enrollment; page views and failed
    submissions do not consume it, so a user can still retry a wrong key within
    the link's lifetime. Each record is kept until the token's own expiry (after
    which the token is rejected anyway) and swept lazily, so the map stays small.

    In-memory and per-process, like CoolOff. Two caveats follow from that, both
    fixed only by a shared/persistent store (e.g. Redis):

    - **Multi-replica:** a token consumed on one replica is not known to the
      others, so the same link can be used once per replica.
    - **Restart:** these records are lost on restart. With a random per-process
      ``ZULIPCHAT_ENROLL_SECRET`` that is harmless (every old token also fails
      signature verification after restart). But with a *stable* secret — the
      recommended production setting so links survive restarts — an
      already-consumed link that is still within its TTL becomes usable again
      after a restart, for the remainder of that window.

    A narrow race remains even with a shared store: two submissions of the same
    link that overlap in time can both succeed, because consumption is recorded
    only after enrollment succeeds. This guards against sequential reuse (link
    replay), which is the real threat.
    """

    def __init__(self) -> None:
        self._used: dict[str, float] = {}  # token id -> token expiry (epoch)
        self._lock = threading.Lock()

    @staticmethod
    def _id(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _sweep_locked(self, now: float) -> None:
        stale = [tid for tid, exp in self._used.items() if now >= exp]
        for tid in stale:
            del self._used[tid]

    def is_used(self, token: str) -> bool:
        """True if ``token`` was already consumed and has not itself expired."""
        now = time.time()
        tid = self._id(token)
        with self._lock:
            exp = self._used.get(tid)
            if exp is None:
                return False
            if now >= exp:
                del self._used[tid]
                return False
            return True

    def mark_used(self, token: str, expiry: float) -> None:
        """Record ``token`` as consumed until ``expiry`` (epoch seconds)."""
        now = time.time()
        with self._lock:
            self._sweep_locked(now)
            self._used[self._id(token)] = expiry


# --- cool-off (brute-force guard) -----------------------------------------


@dataclass
class _Attempts:
    count: int = 0
    locked_until: float = 0.0


class CoolOff:
    """Per-email failed-attempt counter with a lockout window.

    In-memory and per-process. For multi-replica deployments this should be
    backed by a shared store (e.g. Redis) so the limit holds across replicas.
    """

    def __init__(
        self, *, max_attempts: int | None = None, cooloff_seconds: int | None = None
    ) -> None:
        self._max = max_attempts or hosted_config.enroll_max_attempts()
        self._cooloff = cooloff_seconds or hosted_config.enroll_cooloff_seconds()
        self._state: dict[str, _Attempts] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _norm(email: str) -> str:
        return email.strip().lower()

    def seconds_remaining(self, email: str) -> int:
        """Seconds left in the cool-off for ``email`` (0 if not locked)."""
        now = time.monotonic()
        with self._lock:
            state = self._state.get(self._norm(email))
            if state is None or now >= state.locked_until:
                return 0
            return int(state.locked_until - now)

    def record_failure(self, email: str) -> int:
        """Count a failed attempt; lock when the limit is reached. Returns remaining tries (0 = locked)."""
        with self._lock:
            key = self._norm(email)
            state = self._state.setdefault(key, _Attempts())
            state.count += 1
            if state.count >= self._max:
                state.locked_until = time.monotonic() + self._cooloff
                state.count = 0
                return 0
            return self._max - state.count

    def reset(self, email: str) -> None:
        with self._lock:
            self._state.pop(self._norm(email), None)


# --- Zulip key validation --------------------------------------------------


async def validate_zulip_key(site: str, email: str, api_key: str) -> str | None:
    """Validate a key against Zulip; return the account's canonical email or None.

    Returns the Zulip account email on success, None if the credentials are
    rejected. Raises ZulipValidationError if Zulip cannot be reached.
    """
    url = f"{site.rstrip('/')}/api/v1/users/me"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, auth=(email, api_key))
    except httpx.HTTPError as e:
        raise ZulipValidationError(str(e)) from e
    if resp.status_code in (401, 403):
        return None
    if resp.status_code >= 400:
        raise ZulipValidationError(f"Zulip returned {resp.status_code}")
    data = resp.json()
    return str(data.get("delivery_email") or data.get("email") or "") or None


# --- enrollment orchestration ---------------------------------------------


class EnrollOutcome(str, Enum):
    SUCCESS = "success"
    INVALID_KEY = "invalid_key"
    EMAIL_MISMATCH = "email_mismatch"
    LOCKED = "locked"
    UPSTREAM_ERROR = "upstream_error"


@dataclass
class EnrollResult:
    outcome: EnrollOutcome
    message: str
    remaining_tries: int | None = None
    cooloff_seconds: int | None = None


async def try_enroll(
    *,
    email: str,
    api_key: str,
    site: str,
    store: SecretStore,
    cache: SlidingKeyCache,
    cooloff: CoolOff,
) -> EnrollResult:
    """Validate and store a submitted API key, applying the cool-off policy."""
    locked = cooloff.seconds_remaining(email)
    if locked:
        return EnrollResult(
            EnrollOutcome.LOCKED,
            "Too many failed attempts. Please wait before trying again.",
            cooloff_seconds=locked,
        )

    try:
        confirmed = await validate_zulip_key(site, email, api_key)
    except ZulipValidationError as e:
        logger.warning("Zulip validation unavailable for %s: %s", email, e)
        return EnrollResult(
            EnrollOutcome.UPSTREAM_ERROR,
            "Could not reach Zulip to validate the key. Please try again shortly.",
        )

    if confirmed is None:
        remaining = cooloff.record_failure(email)
        return EnrollResult(
            EnrollOutcome.INVALID_KEY,
            "That API key was rejected by Zulip.",
            remaining_tries=remaining,
        )

    if confirmed.strip().lower() != email.strip().lower():
        remaining = cooloff.record_failure(email)
        logger.warning(
            "Enrollment email mismatch: link=%s key-belongs-to=%s", email, confirmed
        )
        return EnrollResult(
            EnrollOutcome.EMAIL_MISMATCH,
            "That key belongs to a different Zulip account than your login.",
            remaining_tries=remaining,
        )

    try:
        await store.set_api_key(email, api_key)
    except SecretStoreError as e:
        logger.error("Failed to store key for %s: %s", email, e)
        return EnrollResult(
            EnrollOutcome.UPSTREAM_ERROR,
            "Could not save the key right now. Please try again shortly.",
        )

    cache.set(email, api_key)
    cooloff.reset(email)
    logger.info("Stored Zulip API key for %s", email)
    return EnrollResult(EnrollOutcome.SUCCESS, "Your Zulip API key has been saved.")
