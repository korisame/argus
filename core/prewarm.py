"""Pre-warm vision when an app becomes active.

Pattern:
  - argus_open_app fires prewarm.kick(app_name)
  - background thread waits ~1.5s for the app to settle, screenshots, runs OCR,
    stores the result in a per-app cache so the first argus_click against that
    app gets instant OCR results.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from . import intent as _intent
from . import screen as _screen

# (app_name_lower → {"ts": ..., "screenshot_path": ..., "ocr_boxes": [...]})
_CACHE: dict[str, dict] = {}
_LOCK = threading.RLock()
TTL_S = 30.0


def kick(app_name: str, *, settle_s: float = 1.5) -> None:
    """Schedule a prewarm in the background. Non-blocking."""
    if not app_name:
        return
    t = threading.Thread(target=_run, args=(app_name, settle_s), daemon=True)
    t.start()


def _run(app_name: str, settle_s: float) -> None:
    try:
        time.sleep(settle_s)
        # Capture window for the named app
        if not _screen.available():
            return
        cap = _screen.capture_window(app=app_name,
                                     out_path=f"/tmp/argus_prewarm_{abs(hash(app_name))}.png")
        if not cap.get("ok"):
            return
        path = cap["path"]
        ocr_boxes = []
        try:
            from adapters import ocr as _ocr
            if _ocr.available():
                ocr_boxes = _ocr.all_text(path, fast=True)
        except Exception:
            pass
        with _LOCK:
            _CACHE[app_name.lower()] = {
                "ts": time.time(),
                "screenshot_path": path,
                "ocr_boxes": ocr_boxes,
                "window": cap.get("window"),
            }
        _intent.log("argus.prewarm", target=app_name, outcome="ok",
                    observation={"ocr_count": len(ocr_boxes)})
    except Exception as e:
        _intent.log("argus.prewarm", target=app_name, outcome="fail",
                    observation={"error": str(e)})


def get(app_name: str) -> Optional[dict]:
    """Return prewarm cache entry if fresh, else None."""
    if not app_name:
        return None
    key = app_name.lower()
    with _LOCK:
        e = _CACHE.get(key)
    if not e:
        return None
    if time.time() - e["ts"] > TTL_S:
        return None
    return e


def status() -> dict:
    with _LOCK:
        return {
            "entries": len(_CACHE),
            "ttl_s": TTL_S,
            "apps": [{"app": k, "age_s": round(time.time() - v["ts"], 1),
                      "ocr_boxes": len(v.get("ocr_boxes") or [])}
                     for k, v in _CACHE.items()],
        }
