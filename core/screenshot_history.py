"""Track recent screenshots for state monitoring + diff playback.

Each entry: ts, path, surface, app, sha256 (for dedup).
Capped at MAX_ENTRIES, oldest evicted.
"""
from __future__ import annotations

import collections
import hashlib
import os
import threading
import time
from pathlib import Path
from typing import Optional

MAX_ENTRIES = 100
HISTORY: "collections.deque[dict]" = collections.deque(maxlen=MAX_ENTRIES)
_LOCK = threading.RLock()


def _sha256(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except Exception:
        return ""


def record(path: str, *, surface: Optional[str] = None,
           app: Optional[dict] = None) -> dict:
    if not os.path.isfile(path):
        return {"ok": False, "error": "file not found"}
    entry = {
        "ts": time.time(),
        "path": path,
        "size": os.path.getsize(path),
        "surface": surface,
        "app": app,
        "sha256": _sha256(path),
    }
    with _LOCK:
        HISTORY.append(entry)
    return {"ok": True, **entry}


def list_recent(limit: int = 20) -> list[dict]:
    with _LOCK:
        return list(reversed(list(HISTORY)))[:limit]


def diff_last_two() -> dict:
    """Quick: diff the two most-recent entries."""
    with _LOCK:
        if len(HISTORY) < 2:
            return {"ok": False, "error": "need at least 2 entries"}
        a, b = HISTORY[-2], HISTORY[-1]
    if a["sha256"] and a["sha256"] == b["sha256"]:
        return {"ok": True, "identical": True,
                "before": a["ts"], "after": b["ts"]}
    try:
        from . import diff_screens
        return {"ok": True, "identical": False,
                "before": a, "after": b,
                "diff": diff_screens.compare(a["path"], b["path"])}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def clear() -> dict:
    with _LOCK:
        n = len(HISTORY)
        HISTORY.clear()
    return {"ok": True, "cleared": n}
