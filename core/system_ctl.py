"""macOS system controls: lock screen, sleep, log out, restart, shutdown.

All require confirmed=true (anti-misfire). Audit logged.
"""
from __future__ import annotations

import subprocess

from . import intent


def _osa(script: str, *, timeout: float = 8.0) -> dict:
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=timeout)
        return {"ok": r.returncode == 0,
                "stderr": (r.stderr or "").strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def lock_screen(*, confirmed: bool = False) -> dict:
    if not confirmed:
        return {"ok": False, "blocked": "lock_screen requires confirmed=true"}
    intent.log("argus.system.lock_screen", outcome="ok")
    # Cmd+Ctrl+Q triggers Lock Screen on macOS
    return _osa('tell application "System Events" to keystroke "q" using {command down, control down}')


def sleep(*, confirmed: bool = False) -> dict:
    if not confirmed:
        return {"ok": False, "blocked": "sleep requires confirmed=true"}
    intent.log("argus.system.sleep", outcome="ok")
    return _osa('tell application "System Events" to sleep')


def logout(*, confirmed: bool = False, no_confirm_dialog: bool = False) -> dict:
    if not confirmed:
        return {"ok": False, "blocked": "logout requires confirmed=true"}
    intent.log("argus.system.logout", outcome="ok")
    cmd = "log out" if no_confirm_dialog else "log out"
    return _osa(f'tell application "System Events" to {cmd}')


def restart(*, confirmed: bool = False) -> dict:
    if not confirmed:
        return {"ok": False, "blocked": "restart requires confirmed=true"}
    intent.log("argus.system.restart", outcome="ok")
    return _osa('tell application "System Events" to restart')


def shutdown(*, confirmed: bool = False) -> dict:
    if not confirmed:
        return {"ok": False, "blocked": "shutdown requires confirmed=true"}
    intent.log("argus.system.shutdown", outcome="ok")
    return _osa('tell application "System Events" to shut down')
