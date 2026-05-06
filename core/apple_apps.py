"""Wrappers for tricky Apple apps (Notes, Reminders) with open-first pattern.

These apps are notoriously slow over AppleScript when invoked cold —
osascript times out (>30s) waiting for iCloud sync if the app isn't running.
Pattern: open app + small wait + script.
"""
from __future__ import annotations

import subprocess
import time
from typing import Optional

from . import safety, intent


def _osascript(code: str, timeout: float = 25.0) -> dict:
    return safety.safe_exec_apple_script(code, timeout=timeout, allow_dangerous=False)


def _open_app(name: str, settle_s: float = 1.5) -> None:
    subprocess.run(["open", "-a", name], check=False, timeout=10)
    time.sleep(settle_s)


def create_note(title: str, body: str, *, folder: str = "Notes",
                account: Optional[str] = None) -> dict:
    """Create a note in Apple Notes. Pre-opens app to avoid TCC timeout."""
    _open_app("Notes", settle_s=2.0)
    # Escape body for AppleScript
    safe_title = title.replace('"', '\\"')
    safe_body = body.replace('"', '\\"')
    if account:
        script = (
            f'tell application "Notes" to tell account "{account}" '
            f'to make new note at folder "{folder}" with properties '
            f'{{name:"{safe_title}", body:"{safe_body}"}}'
        )
    else:
        script = (
            f'tell application "Notes" to make new note '
            f'with properties {{name:"{safe_title}", body:"{safe_body}"}}'
        )
    res = _osascript(script, timeout=30)
    intent.log("argus.notes.create", target=title,
               outcome="ok" if res.get("ok") else "fail",
               observation={"body_chars": len(body), "error": res.get("error")})
    return {"ok": res.get("ok", False), "title": title,
            "via": "notes", **{k: v for k, v in res.items() if k not in ("stdout",)}}


def create_reminder(title: str, *, notes: str = "", list_name: Optional[str] = None,
                     due_date: Optional[str] = None) -> dict:
    """Create a reminder. Pre-opens app to avoid TCC timeout."""
    _open_app("Reminders", settle_s=2.0)
    safe_title = title.replace('"', '\\"')
    safe_notes = notes.replace('"', '\\"')
    props = [f'name:"{safe_title}"']
    if notes: props.append(f'body:"{safe_notes}"')
    if due_date: props.append(f'due date:date "{due_date}"')
    inner = "{" + ", ".join(props) + "}"
    if list_name:
        script = (f'tell application "Reminders" to tell list "{list_name}" '
                  f'to make new reminder with properties {inner}')
    else:
        script = f'tell application "Reminders" to make new reminder with properties {inner}'
    res = _osascript(script, timeout=30)
    intent.log("argus.reminder.create", target=title,
               outcome="ok" if res.get("ok") else "fail",
               observation={"error": res.get("error")})
    return {"ok": res.get("ok", False), "title": title, "via": "reminders",
            **{k: v for k, v in res.items() if k not in ("stdout",)}}
