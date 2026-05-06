"""Clipboard read/write/history.

Wraps pbcopy/pbpaste. Maintains an in-process LRU history (last 50 entries).
Doesn't touch macOS Universal Clipboard sync.
"""
from __future__ import annotations

import collections
import subprocess
import threading
import time
from typing import Optional

_HISTORY = collections.deque(maxlen=50)
_LOCK = threading.RLock()


def read_text() -> dict:
    try:
        r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=3)
        return {"ok": True, "text": r.stdout, "chars": len(r.stdout)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def read_image(out_path: str = "/tmp/argus_clipboard.png") -> dict:
    """If clipboard contains an image, save it to out_path."""
    script = (
        f'set png_data to (the clipboard as «class PNGf»)\n'
        f'set f to open for access POSIX file "{out_path}" with write permission\n'
        f'set eof of f to 0\n'
        f'write png_data to f\n'
        f'close access f\n'
    )
    r = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True, timeout=5)
    if r.returncode == 0:
        try:
            import os
            return {"ok": True, "path": out_path,
                    "bytes": os.path.getsize(out_path)}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": r.stderr.strip() or "no image in clipboard"}


def write_text(text: str) -> dict:
    try:
        subprocess.run(["pbcopy"], input=text, text=True, check=True, timeout=5)
        with _LOCK:
            _HISTORY.append({"ts": time.time(), "kind": "text",
                              "preview": text[:200], "len": len(text)})
        return {"ok": True, "chars": len(text)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def history(limit: int = 20) -> list[dict]:
    with _LOCK:
        items = list(_HISTORY)
    return list(reversed(items))[:limit]


def clear_history() -> dict:
    with _LOCK:
        n = len(_HISTORY)
        _HISTORY.clear()
    return {"ok": True, "cleared_entries": n}
