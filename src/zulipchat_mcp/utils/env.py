"""Shared environment-variable parsing helpers.

One definition of "truthy" for every boolean env var, so they all accept the
same spellings (case-insensitive ``1``/``true``/``yes``/``on``) and behave
consistently.
"""

from __future__ import annotations

import os

_TRUTHY = ("1", "true", "yes", "on")
_FALSY = ("0", "false", "no", "off")


def env_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable.

    Returns ``default`` when the variable is unset or empty. Otherwise true
    for ``1``/``true``/``yes``/``on`` (any case), false for anything else.
    """
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in _TRUTHY


def parse_bool(raw: str | None, default: bool) -> bool:
    """Parse a boolean from an arbitrary string (e.g. an HTTP header value).

    True for ``1``/``true``/``yes``/``on`` and false for ``0``/``false``/``no``/
    ``off`` (any case). Returns ``default`` for ``None``, empty, or any
    unrecognized value — never raises, so a malformed client header falls back
    to the server default instead of failing the request.
    """
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    return default
