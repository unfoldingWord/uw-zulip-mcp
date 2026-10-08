"""Starlette routes for the browser-based API-key enrollment page.

Served by the MCP server itself (FastMCP ``custom_route``). Identity is carried
by the signed enrollment token minted for an authenticated user, so these pages
need no separate login: a valid token proves which email is enrolling. The
Zulip site is always taken from server config, never from the client.
"""

from __future__ import annotations

import html
import math
import time
from datetime import datetime, timezone

from starlette.requests import Request
from starlette.responses import HTMLResponse

from ..config import get_config_manager
from ..utils.logging import get_logger
from . import hosted_config, hosted_runtime
from .enrollment import (
    EnrollOutcome,
    enrollment_token_expiry,
    try_enroll,
    verify_enrollment_token,
)

logger = get_logger(__name__)

# unfoldingWord brand colors
_OCEAN = "#014263"
_INSPIRE = "#31ADE3"
_TECH = "#231F20"

_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}

# Static browser-tab title for every enrollment page. The per-page `title`
# argument is used only for the visible <h1> heading.
_PAGE_TITLE = "ZulipChat MCP — Enrollment"


def _page(title: str, body: str, *, status: int = 200) -> HTMLResponse:
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(_PAGE_TITLE)}</title>
<style>
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         color: {_TECH}; background: #f5f7f9; margin: 0; padding: 2rem; }}
  .card {{ max-width: 34rem; margin: 2rem auto; background: #fff; border-radius: 12px;
          box-shadow: 0 2px 12px rgba(1,66,99,.12); overflow: hidden; }}
  .head {{ background: {_OCEAN}; color: #fff; padding: 1.25rem 1.5rem; }}
  .head h1 {{ margin: 0; font-size: 1.25rem; }}
  .body {{ padding: 1.5rem; line-height: 1.5; }}
  ol {{ padding-left: 1.2rem; }}
  code {{ background: #eef2f5; padding: .1rem .3rem; border-radius: 4px; }}
  input[type=text] {{ width: 100%; box-sizing: border-box; padding: .7rem;
         font-size: 1rem; border: 1px solid #cdd7de; border-radius: 8px; }}
  button {{ background: {_INSPIRE}; color: #fff; border: 0; border-radius: 8px;
           padding: .7rem 1.2rem; font-size: 1rem; cursor: pointer; margin-top: 1rem; }}
  .ok {{ color: {_OCEAN}; }} .err {{ color: #b3261e; }}
  .muted {{ color: #5c6b75; font-size: .9rem; }}
</style>
</head>
<body><div class="card"><div class="head"><h1>{html.escape(title)}</h1></div>
<div class="body">{body}</div></div></body></html>"""
    return HTMLResponse(doc, status_code=status, headers=_SECURITY_HEADERS)


def _invalid_link_page() -> HTMLResponse:
    return _page(
        "Link expired or invalid",
        "<p class='err'>This enrollment link is invalid or has expired.</p>"
        "<p>Return to your MCP client and run any Zulip tool again to get a "
        "fresh link.</p>",
        status=400,
    )


def _used_link_page() -> HTMLResponse:
    return _page(
        "Link already used",
        "<p class='err'>This enrollment link has already been used.</p>"
        "<p>Each link works once. To add or update your key, return to your MCP "
        "client and run any Zulip tool again to get a fresh link.</p>",
        status=400,
    )


def _not_allowed_page() -> HTMLResponse:
    return _page(
        "Not authorized",
        "<p class='err'>Your account is not authorized to use this server.</p>"
        "<p>If you believe this is a mistake, contact your administrator.</p>",
        status=403,
    )


def _expiry_notice(token: str) -> str:
    """A muted line stating when this link expires, or '' if not determinable."""
    expiry = enrollment_token_expiry(token)
    if expiry is None:
        return ""
    remaining = expiry - time.time()
    if remaining <= 0:
        return ""
    mins = math.ceil(remaining / 60)
    at = datetime.fromtimestamp(expiry, tz=timezone.utc).strftime("%H:%M UTC")
    return (
        f"<p class='muted'>This link expires at {at} "
        f"(in about {mins} minute{'s' if mins != 1 else ''}). After that, run any "
        "Zulip tool again to get a fresh one.</p>"
    )


def _form_page(email: str, token: str, *, error: str | None = None) -> HTMLResponse:
    err_html = f"<p class='err'>{html.escape(error)}</p>" if error else ""
    body = f"""
    <p>Signed in as <strong>{html.escape(email)}</strong>.</p>
    <p>To let this server act in Zulip as you, add your personal Zulip API key.</p>
    {_expiry_notice(token)}
    <ol>
      <li>In Zulip, open <strong>Personal settings → Account &amp; privacy</strong>.</li>
      <li>Under <strong>API key</strong>, click <strong>Show/change your API key</strong>.</li>
      <li>Copy the key and paste it below.</li>
    </ol>
    {err_html}
    <form method="post" action="/enroll" autocomplete="off">
      <input type="hidden" name="token" value="{html.escape(token)}">
      <label for="api_key">Zulip API key</label>
      <input type="text" id="api_key" name="api_key" required
             pattern="[A-Za-z0-9]{{20,64}}" placeholder="your 32-character key">
      <br><button type="submit">Validate and save</button>
    </form>
    <p class="muted">Your key is validated against Zulip, then stored encrypted
    in the server's secret vault. It is never shown again.</p>
    """
    return _page("Add your Zulip API key", body)


async def enroll_get(request: Request) -> HTMLResponse:
    token = request.query_params.get("token", "")
    email = verify_enrollment_token(token)
    if not email:
        return _invalid_link_page()
    if not hosted_config.is_identity_allowed(email):
        return _not_allowed_page()
    if hosted_runtime.get_used_tokens().is_used(token):
        return _used_link_page()
    return _form_page(email, token)


async def enroll_post(request: Request) -> HTMLResponse:
    form = await request.form()
    token = str(form.get("token", ""))
    api_key = str(form.get("api_key", "")).strip()
    email = verify_enrollment_token(token)
    if not email:
        return _invalid_link_page()
    if not hosted_config.is_identity_allowed(email):
        return _not_allowed_page()
    if hosted_runtime.get_used_tokens().is_used(token):
        return _used_link_page()

    if not api_key:
        return _form_page(email, token, error="Please enter your API key.")

    site = get_config_manager().config.site
    if not site:
        logger.error("Enrollment attempted but ZULIP_SITE is not configured")
        return _page(
            "Server not configured",
            "<p class='err'>The server is missing its Zulip site configuration. "
            "Contact your administrator.</p>",
            status=500,
        )

    result = await try_enroll(
        email=email,
        api_key=api_key,
        site=site,
        store=hosted_runtime.get_secret_store(),
        cache=hosted_runtime.get_key_cache(),
        cooloff=hosted_runtime.get_cooloff(),
    )

    if result.outcome is EnrollOutcome.SUCCESS:
        # Consume the link so it cannot be replayed. Bound the record by the
        # token's own expiry; if that cannot be parsed, skip (the token will
        # still expire on its own and verify will then reject it).
        expiry = enrollment_token_expiry(token)
        if expiry is not None:
            hosted_runtime.get_used_tokens().mark_used(token, expiry)
        return _page(
            "All set",
            "<p class='ok'>Your Zulip API key has been saved.</p>"
            "<p>Return to your MCP client and run your Zulip command again.</p>",
        )

    if result.outcome is EnrollOutcome.LOCKED:
        mins = ((result.cooloff_seconds or 0) + 59) // 60
        return _page(
            "Too many attempts",
            f"<p class='err'>Too many failed attempts. Please wait about "
            f"{mins} minute(s) and try again.</p>",
            status=429,
        )

    if result.outcome is EnrollOutcome.UPSTREAM_ERROR:
        return _form_page(email, token, error=result.message)

    # invalid key or email mismatch — let them retry, show remaining tries
    hint = result.message
    if result.remaining_tries is not None:
        hint += f" {result.remaining_tries} attempt(s) left before a cool-off."
    return _form_page(email, token, error=hint)


def register_enrollment_routes(mcp: object) -> None:
    """Register /enroll GET and POST on the FastMCP server."""
    mcp.custom_route("/enroll", methods=["GET"])(enroll_get)  # type: ignore[attr-defined]
    mcp.custom_route("/enroll", methods=["POST"])(enroll_post)  # type: ignore[attr-defined]
