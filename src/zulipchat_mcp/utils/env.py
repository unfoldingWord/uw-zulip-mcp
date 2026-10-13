"""Shared environment-variable parsing helpers.

One definition of "truthy" for every boolean env var, so they all accept the
same spellings (case-insensitive ``1``/``true``/``yes``/``on``) and behave
consistently.
"""

from __future__ import annotations

import os

_TRUTHY = ("1", "true", "yes", "on")


def env_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable.

    Returns ``default`` when the variable is unset or empty. Otherwise true
    for ``1``/``true``/``yes``/``on`` (any case), false for anything else.
    """
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in _TRUTHY
