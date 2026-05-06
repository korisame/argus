"""Bring an app or specific window to the front.

Different from open_app: this targets a SPECIFIC window (by title substring
or window id), useful when an app has multiple open windows.
"""
from __future__ import annotations

import subprocess
import time
from typing import Optional

from . import screen as _screen


def focus_app(app_name: str) -> dict:
    """Activate an app (open it if not running)."""
    subprocess.run(["open", "-a", app_name], check=False, timeout=10)
    time.sleep(0.4)
    return {"ok": True, "app": app_name}


def focus_window(*, app: Optional[str] = None, title: Optional[str] = None,
                  bundle_id: Optional[str] = None, wid: Optional[int] = None) -> dict:
    """Bring a specific window forward.

    Strategy:
      1. If wid is provided, AppleScript-raise it via ProcessID.
      2. Else find the window via screen.find_windows + AppleScript activate.
    """
    if wid is None:
        wins = _screen.find_windows(app=app, title=title, bundle_id=bundle_id)
        if not wins:
            return {"ok": False, "error": "no matching window"}
        win = wins[0]
        wid = win["wid"]
        owner = win["owner"]
        win_title = win["title"]
    else:
        wins = [w for w in _screen.list_windows() if w["wid"] == wid]
        if not wins:
            return {"ok": False, "error": f"wid {wid} not visible"}
        win = wins[0]
        owner = win["owner"]
        win_title = win["title"]

    # Activate app first
    subprocess.run(["osascript", "-e",
                    f'tell application "{owner}" to activate'],
                   capture_output=True, timeout=5)
    # Then raise the specific window via AppleScript (if title is unique)
    if win_title:
        safe = win_title.replace('"', '\\"')
        script = (
            f'tell application "System Events" to tell process "{owner}"\n'
            f'  perform action "AXRaise" of (window "{safe}")\n'
            f'end tell'
        )
        subprocess.run(["osascript", "-e", script],
                       capture_output=True, timeout=5)
    return {"ok": True, "wid": wid, "owner": owner, "title": win_title}
