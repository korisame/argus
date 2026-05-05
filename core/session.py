"""Unified session state.

Today wraps browser-harness's session_save/load (cookies + localStorage +
IndexedDB at v0.3.1). Native-app session (UI-state) is not yet captured;
the slot in the API is reserved for when we add it.
"""
from __future__ import annotations

from typing import Optional

from adapters import cdp


def save(name: str = "default") -> dict:
    code = (
        "import json\n"
        f"r = session_save({name!r})\n"
        "print(json.dumps(r))\n"
    )
    return cdp._run(code, timeout=30)


def load(name: str = "default") -> dict:
    code = (
        "import json\n"
        f"r = session_load({name!r})\n"
        "print(json.dumps(r))\n"
    )
    return cdp._run(code, timeout=30)


def clear(name: str = "default") -> dict:
    code = (
        "import json\n"
        f"r = session_clear({name!r})\n"
        "print(json.dumps(r))\n"
    )
    return cdp._run(code, timeout=15)


def detect_login_required() -> dict:
    code = "import json; print(json.dumps(detect_login_required()))"
    return cdp._run(code, timeout=10)


def list_saved() -> list[str]:
    """List saved session jars (browser-harness keeps them under ~/.browser-harness/sessions)."""
    import os
    base = os.path.expanduser("~/.browser-harness/sessions")
    if not os.path.isdir(base):
        return []
    return sorted(f for f in os.listdir(base)
                  if not f.startswith(".") and not f.endswith(".tmp"))
