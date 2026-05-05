"""macOS mouse + keyboard via CGEvent.

Thin wrapper. Defers to the underlying argus core when available so we don't
re-implement keysym tables.
"""
from __future__ import annotations

import subprocess
from typing import Optional

try:
    import argus  # type: ignore
    HAVE_ARGUS = True
except Exception:
    HAVE_ARGUS = False


def screenshot(path: str = "/tmp/argus_prime_shot.png") -> str:
    """Use `screencapture -x` (silent, no shutter sound)."""
    if HAVE_ARGUS:
        try:
            return argus.see(path)
        except Exception:
            pass
    subprocess.run(["screencapture", "-x", path], check=True, timeout=10)
    return path


def click(x: float, y: float, double: bool = False) -> dict:
    if HAVE_ARGUS:
        return argus.click("", vision=False, coords=(int(x), int(y)), double=double)
    # Fallback via osascript / cliclick — skip for now: argus is required
    raise RuntimeError("argus core not importable; cannot click")


def type_text(text: str) -> dict:
    if HAVE_ARGUS:
        return argus.type_text(text)
    raise RuntimeError("argus core not importable; cannot type")


def key(name: str, modifiers: Optional[str] = None) -> dict:
    if HAVE_ARGUS:
        return argus.key(name, modifiers=modifiers)
    raise RuntimeError("argus core not importable; cannot send key")


def scroll(direction: str, amount: int = 5,
           coords: Optional[tuple] = None) -> dict:
    if HAVE_ARGUS:
        return argus.scroll(direction, amount=amount, coords=coords)
    raise RuntimeError("argus core not importable; cannot scroll")


def open_app(name: str) -> dict:
    if HAVE_ARGUS:
        return argus.open_app(name)
    subprocess.run(["open", "-a", name], check=False, timeout=10)
    return {"opened": name, "via": "open -a"}


def quit_app(name: str) -> dict:
    script = f'tell application "{name}" to quit'
    if HAVE_ARGUS:
        argus.exec_apple_script(script)
    else:
        subprocess.run(["osascript", "-e", script], check=False, timeout=10)
    return {"quit": name}


def exec_apple_script(code: str) -> dict:
    if HAVE_ARGUS:
        return argus.exec_apple_script(code)
    r = subprocess.run(["osascript", "-e", code], capture_output=True,
                       text=True, timeout=30)
    return {"ok": r.returncode == 0, "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip()}


def doctor() -> dict:
    return {"argus_core_importable": HAVE_ARGUS,
            "argus_module": getattr(argus, "__file__", None) if HAVE_ARGUS else None}
