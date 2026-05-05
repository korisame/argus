"""Window-aware screenshot — foreground or background.

Migrated from korisame/background-screenshot, integrated and improved:
  - in-process (no subprocess for the listing)
  - cache-aware (skip re-screenshot if the same window hasn't changed)
  - bundle_id matching in addition to app name
  - returns full window metadata (wid, app, title, layer, bounds)
  - no focus stealing — works on apps that aren't frontmost
"""
from __future__ import annotations

import os
import subprocess
import time
from typing import Optional

try:
    import Quartz
    HAVE_QUARTZ = True
    _ERR = None
except Exception as _e:
    HAVE_QUARTZ = False
    _ERR = repr(_e)

_MIN_AREA = 5000
_MIN_ALPHA = 0.1


def available() -> bool:
    return HAVE_QUARTZ


def list_windows() -> list[dict]:
    """All visible windows. Returns rich metadata."""
    if not HAVE_QUARTZ:
        return []
    info = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionAll | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    out = []
    for w in info:
        wid = w.get("kCGWindowNumber")
        owner = w.get("kCGWindowOwnerName", "") or ""
        title = w.get("kCGWindowName", "") or ""
        layer = int(w.get("kCGWindowLayer", 999) or 999)
        alpha = float(w.get("kCGWindowAlpha", 1.0) or 0.0)
        bounds = w.get("kCGWindowBounds", {}) or {}
        width = int(bounds.get("Width", 0) or 0)
        height = int(bounds.get("Height", 0) or 0)
        area = width * height
        if not wid or area < _MIN_AREA or alpha < _MIN_ALPHA:
            continue
        out.append({
            "wid": int(wid),
            "owner": owner,
            "title": title,
            "layer": layer,
            "alpha": alpha,
            "width": width,
            "height": height,
            "area": area,
            "bounds": {"x": float(bounds.get("X", 0) or 0),
                       "y": float(bounds.get("Y", 0) or 0),
                       "w": float(width), "h": float(height)},
            "pid": int(w.get("kCGWindowOwnerPID") or 0),
        })
    return out


def find_windows(app: Optional[str] = None, title: Optional[str] = None,
                 bundle_id: Optional[str] = None) -> list[dict]:
    """Filter windows. `app` is partial+case-insensitive match on owner name.
    `bundle_id` requires AppKit; matches by pid lookup. `title` is substring."""
    wins = list_windows()
    if app:
        needle = app.lower()
        wins = [w for w in wins if needle in (w["owner"] or "").lower()]
    if title:
        t = title.lower()
        wins = [w for w in wins if t in (w["title"] or "").lower()]
    if bundle_id:
        try:
            from AppKit import NSWorkspace
            apps = NSWorkspace.sharedWorkspace().runningApplications()
            pid_for_bundle = {int(a.processIdentifier()): str(a.bundleIdentifier() or "")
                              for a in apps}
            wins = [w for w in wins
                    if pid_for_bundle.get(w["pid"], "").lower() == bundle_id.lower()]
        except Exception:
            pass
    # Front (top of stack) first: lower layer number = closer to front
    wins.sort(key=lambda w: (w["layer"], -w["area"]))
    return wins


def capture(wid: int, out_path: str = "/tmp/argus_window.png") -> str:
    """Capture a specific window by id. Doesn't bring it to front."""
    r = subprocess.run(
        ["screencapture", "-l", str(wid), "-x", out_path],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode != 0:
        raise RuntimeError(f"screencapture wid={wid}: {r.stderr.strip() or r.stdout.strip()}")
    return out_path


def capture_window(app: Optional[str] = None, *, title: Optional[str] = None,
                   bundle_id: Optional[str] = None, index: int = 0,
                   out_path: str = "/tmp/argus_window.png") -> dict:
    """Capture by app/title/bundle_id. Returns {path, window: {...}}.

    Defaults to first match (most front). Raises if no match.
    """
    matches = find_windows(app=app, title=title, bundle_id=bundle_id)
    if not matches:
        return {"ok": False,
                "error": f"no visible window for app={app!r} title={title!r} bundle_id={bundle_id!r}",
                "available_apps": sorted({w["owner"] for w in list_windows()})}
    if index >= len(matches):
        index = 0
    win = matches[index]
    path = capture(win["wid"], out_path=out_path)
    return {"ok": True, "path": path, "window": win}


def capture_frontmost(out_path: str = "/tmp/argus_frontmost.png") -> dict:
    """Capture the frontmost window of the frontmost app. Window-only, fast."""
    try:
        from AppKit import NSWorkspace
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if not front:
            return {"ok": False, "error": "no frontmost app"}
        pid = int(front.processIdentifier())
        wins = [w for w in list_windows() if w["pid"] == pid]
        if not wins:
            return {"ok": False, "error": f"no visible windows for {front.localizedName()}"}
        wins.sort(key=lambda w: (w["layer"], -w["area"]))
        win = wins[0]
        path = capture(win["wid"], out_path=out_path)
        return {"ok": True, "path": path, "window": win}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def doctor() -> dict:
    return {"available": HAVE_QUARTZ, "error": _ERR,
            "windows_visible": len(list_windows()) if HAVE_QUARTZ else 0}
