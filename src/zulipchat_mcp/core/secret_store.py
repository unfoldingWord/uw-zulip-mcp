"""OpenBao / HashiCorp Vault client for per-user Zulip API keys.

Each user's Zulip API key is stored as a KV v2 secret keyed by a SHA-256 hash
of the lowercased email. The hash keeps the path free of ``@``/``.`` and
avoids listing everyone's email to anyone who can list the mount; because the
hash is unsalted and deterministic, operators can still map an email to its
path by hashing the address the same way.

Only the operations this server needs are implemented: AppRole login (with
token caching) and KV v2 read / write / delete of a single-field secret. The
API surface is OpenBao's, which is wire-compatible with HashiCorp Vault, so no
third-party client library is required.

All calls are async (httpx) so the event loop is never blocked while talking
to the vault.
"""

from __future__ import annotations

import asyncio
import hashlib
import time

import httpx

from ..utils.logging import get_logger
from . import hosted_config

logger = get_logger(__name__)

_FIELD = "api_key"
_EMAIL_FIELD = "email"
# Renew the AppRole token a little before it actually expires.
_TOKEN_RENEW_MARGIN_SECONDS = 60


class SecretStoreError(RuntimeError):
    """Raised when the vault is unreachable or returns an unexpected error."""


class SecretStore:
    """Minimal async OpenBao/Vault KV v2 client for user API keys."""

    def __init__(
        self,
        *,
        addr: str | None = None,
        namespace: str | None = None,
        role_id: str | None = None,
        secret_id: str | None = None,
        token: str | None = None,
        kv_mount: str | None = None,
        kv_path: str | None = None,
        verify_tls: bool | None = None,
    ) -> None:
        self._addr = (addr or hosted_config.openbao_addr()).rstrip("/")
        self._namespace = (
            namespace if namespace is not None else hosted_config.openbao_namespace()
        )
        self._role_id = (
            role_id if role_id is not None else hosted_config.openbao_role_id()
        )
        self._secret_id = (
            secret_id if secret_id is not None else hosted_config.openbao_secret_id()
        )
        self._static_token = (
            token if token is not None else hosted_config.openbao_token()
        )
        self._kv_mount = kv_mount or hosted_config.openbao_kv_mount()
        self._kv_path = kv_path or hosted_config.openbao_kv_path()
        self._verify_tls = (
            verify_tls if verify_tls is not None else hosted_config.openbao_tls_verify()
        )

        self._client: httpx.AsyncClient | None = None
        self._token: str | None = None
        self._token_expiry: float = 0.0
        self._auth_lock = asyncio.Lock()

    # -- internals ----------------------------------------------------------

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {}
            if self._namespace:
                headers["X-Vault-Namespace"] = self._namespace
            self._client = httpx.AsyncClient(
                base_url=self._addr,
                headers=headers,
                verify=self._verify_tls,
                timeout=10.0,
            )
        return self._client

    def user_path(self, email: str) -> str:
        """KV v2 logical path for a user's secret (without the /data/ segment)."""
        digest = hashlib.sha256(email.strip().lower().encode()).hexdigest()
        return f"{self._kv_path}/{digest}"

    async def _ensure_token(self) -> str:
        if self._static_token:
            return self._static_token
        now = time.monotonic()
        if self._token and now < self._token_expiry - _TOKEN_RENEW_MARGIN_SECONDS:
            return self._token
        async with self._auth_lock:
            now = time.monotonic()
            if self._token and now < self._token_expiry - _TOKEN_RENEW_MARGIN_SECONDS:
                return self._token
            if not (self._role_id and self._secret_id):
                raise SecretStoreError(
                    "OpenBao is not configured: set OPENBAO_TOKEN or both "
                    "OPENBAO_ROLE_ID and OPENBAO_SECRET_ID."
                )
            try:
                resp = await self._http().post(
                    "/v1/auth/approle/login",
                    json={"role_id": self._role_id, "secret_id": self._secret_id},
                )
                resp.raise_for_status()
            except httpx.HTTPError as e:
                raise SecretStoreError(f"OpenBao AppRole login failed: {e}") from e
            auth = resp.json().get("auth") or {}
            token = auth.get("client_token")
            if not token:
                raise SecretStoreError("OpenBao login returned no client_token")
            lease = int(auth.get("lease_duration") or 0)
            self._token = token
            self._token_expiry = time.monotonic() + (lease or 3600)
            logger.info("OpenBao AppRole login succeeded (lease %ss)", lease or 3600)
            return token

    async def _headers(self) -> dict[str, str]:
        return {"X-Vault-Token": await self._ensure_token()}

    def _data_url(self, email: str) -> str:
        return f"/v1/{self._kv_mount}/data/{self.user_path(email)}"

    # -- public API ---------------------------------------------------------

    async def get_api_key(self, email: str) -> str | None:
        """Return the stored API key for ``email``, or None if not stored."""
        try:
            resp = await self._http().get(
                self._data_url(email), headers=await self._headers()
            )
        except httpx.HTTPError as e:
            raise SecretStoreError(f"OpenBao read failed: {e}") from e
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise SecretStoreError(
                f"OpenBao read returned {resp.status_code}: {resp.text[:200]}"
            )
        data = ((resp.json().get("data") or {}).get("data")) or {}
        key = data.get(_FIELD)
        return str(key) if key else None

    async def set_api_key(self, email: str, api_key: str) -> None:
        """Store ``api_key`` (and the email, for operator readability)."""
        payload = {"data": {_FIELD: api_key, _EMAIL_FIELD: email.strip().lower()}}
        try:
            resp = await self._http().post(
                self._data_url(email), headers=await self._headers(), json=payload
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise SecretStoreError(f"OpenBao write failed: {e}") from e

    async def delete_api_key(self, email: str) -> None:
        """Delete all versions of a user's secret (metadata + data)."""
        url = f"/v1/{self._kv_mount}/metadata/{self.user_path(email)}"
        try:
            resp = await self._http().delete(url, headers=await self._headers())
            if resp.status_code not in (200, 204, 404):
                resp.raise_for_status()
        except httpx.HTTPError as e:
            raise SecretStoreError(f"OpenBao delete failed: {e}") from e

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
