"""Environment-driven configuration for OAuth2-only (vault-backed) hosted mode.

Central place for every env var the OAuth2 + OpenBao/Vault credential flow
reads, so defaults live in one file. Nothing here holds secrets in memory
beyond process lifetime; values are read on demand.

    OpenBao / Vault
      OPENBAO_ADDR         Address (default http://127.0.0.1:8200)
      OPENBAO_NAMESPACE    Optional namespace header
      OPENBAO_ROLE_ID      AppRole role_id  (with OPENBAO_SECRET_ID)
      OPENBAO_SECRET_ID    AppRole secret_id
      OPENBAO_TOKEN        Direct token (dev/testing; bypasses AppRole)
      OPENBAO_KV_MOUNT     KV v2 mount (default "secret")
      OPENBAO_KV_PATH      Base path for user secrets (default "zulip-mcp/users")
      OPENBAO_TLS_VERIFY   "false" disables TLS verification (dev only)

    Key cache
      ZULIPCHAT_KEY_CACHE_TTL_SECONDS   Sliding inactivity TTL (default 86400)
      ZULIPCHAT_REENROLL_ON_AUTH_FAILURE  On a Zulip auth rejection, clear the
                                        stored key and re-enroll (default true)

    Enrollment web flow
      ZULIPCHAT_ENROLL_MAX_ATTEMPTS     Failed tries before cool-off (default 6)
      ZULIPCHAT_ENROLL_COOLOFF_SECONDS  Cool-off duration (default 900)
      ZULIPCHAT_ENROLL_TOKEN_TTL_SECONDS Signed-link lifetime (default 900)
      ZULIPCHAT_ENROLL_SECRET           HMAC secret for enrollment links
      ZULIPCHAT_PUBLIC_URL              Public URL of this server (for links);
                                        falls back to ZULIPCHAT_AUTH_BASE_URL
"""

from __future__ import annotations

import os
import secrets

from ..utils.env import env_bool
from ..utils.logging import get_logger

logger = get_logger(__name__)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %d", name, raw, default)
        return default
    return value if value > 0 else default


# --- OpenBao / Vault -------------------------------------------------------


def openbao_addr() -> str:
    return os.getenv("OPENBAO_ADDR", "http://127.0.0.1:8200").rstrip("/")


def openbao_namespace() -> str | None:
    return os.getenv("OPENBAO_NAMESPACE", "").strip() or None


def openbao_role_id() -> str | None:
    return os.getenv("OPENBAO_ROLE_ID", "").strip() or None


def openbao_secret_id() -> str | None:
    return os.getenv("OPENBAO_SECRET_ID", "").strip() or None


def openbao_token() -> str | None:
    return os.getenv("OPENBAO_TOKEN", "").strip() or None


def openbao_kv_mount() -> str:
    return os.getenv("OPENBAO_KV_MOUNT", "secret").strip("/") or "secret"


def openbao_kv_path() -> str:
    return os.getenv("OPENBAO_KV_PATH", "zulip-mcp/users").strip("/") or (
        "zulip-mcp/users"
    )


def openbao_tls_verify() -> bool:
    return env_bool("OPENBAO_TLS_VERIFY", True)


def openbao_cacert() -> str | None:
    """Path to a PEM CA bundle used to verify OpenBao's TLS certificate.

    Set this when OpenBao uses a certificate signed by a private/internal CA.
    The file must contain the root CA and any intermediate CAs. It must not
    contain OpenBao's own leaf certificate, which OpenBao presents during the
    TLS handshake. Ignored when OPENBAO_TLS_VERIFY is disabled.
    """
    return os.getenv("OPENBAO_CACERT", "").strip() or None


def openbao_startup_required() -> bool:
    """When true, a failed OpenBao self-check aborts startup (fail fast).

    Default false: a transient OpenBao outage should not stop the server from
    booting. Enable in strict environments where a broken vault must fail the
    deploy.
    """
    return env_bool("OPENBAO_STARTUP_REQUIRED", False)


def vault_enabled() -> bool:
    """True when OpenBao credentials are configured (AppRole or direct token)."""
    if openbao_token():
        return True
    return bool(openbao_role_id() and openbao_secret_id())


# --- Key cache -------------------------------------------------------------


def key_cache_ttl_seconds() -> int:
    return _int_env("ZULIPCHAT_KEY_CACHE_TTL_SECONDS", 86_400)


def reenroll_on_auth_failure() -> bool:
    """When true, a Zulip auth rejection clears the stored key and re-enrolls.

    If Zulip rejects a user's stored API key (they rotated or revoked it), drop
    the cached copy, delete the vault secret, and hand back an enrollment link
    on that same call. Default true. Set false to keep the stale key in the
    vault and only surface Zulip's error (no automatic deletion).
    """
    return env_bool("ZULIPCHAT_REENROLL_ON_AUTH_FAILURE", True)


# --- Enrollment ------------------------------------------------------------


def enroll_max_attempts() -> int:
    return _int_env("ZULIPCHAT_ENROLL_MAX_ATTEMPTS", 6)


def enroll_cooloff_seconds() -> int:
    return _int_env("ZULIPCHAT_ENROLL_COOLOFF_SECONDS", 900)


def enroll_token_ttl_seconds() -> int:
    return _int_env("ZULIPCHAT_ENROLL_TOKEN_TTL_SECONDS", 900)


_generated_enroll_secret: str | None = None


def enroll_secret() -> str:
    """HMAC secret for signing enrollment links.

    Prefer ZULIPCHAT_ENROLL_SECRET so links survive restarts and are valid
    across replicas. If unset, generate a per-process secret and warn once —
    links then break on restart and do not work behind a multi-replica load
    balancer.
    """
    configured = os.getenv("ZULIPCHAT_ENROLL_SECRET", "").strip()
    if configured:
        return configured
    global _generated_enroll_secret
    if _generated_enroll_secret is None:
        _generated_enroll_secret = secrets.token_urlsafe(32)
        logger.warning(
            "ZULIPCHAT_ENROLL_SECRET is not set — using a random per-process "
            "secret. Enrollment links will not survive a restart or work "
            "across multiple replicas. Set ZULIPCHAT_ENROLL_SECRET in "
            "production."
        )
    return _generated_enroll_secret


def public_base_url() -> str | None:
    """Public base URL of this server, used to build enrollment links."""
    url = (
        os.getenv("ZULIPCHAT_PUBLIC_URL", "").strip()
        or os.getenv("ZULIPCHAT_AUTH_BASE_URL", "").strip()
    )
    return url.rstrip("/") or None
