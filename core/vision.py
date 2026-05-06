"""Process-wide Moondream singleton.

ALL callers (cascade resolver, app-skill autotune, debug overlay) go through
this. One model, one warm session, one LRU. Replaces the two separate vision
caches that argus and browser-harness used to keep.

Backends, in priority order:
  1. argus.vision (in-process, MPS-backed) — preferred when available
  2. moondream cloud SDK (https://moondream.ai)  — fallback
  3. None (returns dict with error so callers can degrade gracefully)
"""
from __future__ import annotations

import os
import threading
import time
from typing import Optional


class _VisionSingleton:
    def __init__(self, idle_timeout_s: float = 300.0):
        self.idle_timeout_s = idle_timeout_s
        self._lock = threading.RLock()
        self._mode: Optional[str] = None        # "argus" | "cloud" | None
        self._argus_v = None                    # argus.vision module (lazy)
        self._cloud = None                      # moondream cloud client (lazy)
        self._last_use = 0.0
        self._timer: Optional[threading.Timer] = None
        self._pinned = False
        self._import_error: Optional[str] = None

    # ---- backend selection ----
    def _ensure(self) -> str:
        with self._lock:
            if self._mode is not None:
                return self._mode
            # Prefer in-process argus.vision
            try:
                import argus.vision as v  # type: ignore
                self._argus_v = v
                self._mode = "argus"
                return self._mode
            except Exception as e:
                self._import_error = repr(e)
            # Fallback to cloud SDK
            try:
                key = os.environ.get("MOONDREAM_API_KEY")
                if key:
                    import moondream as md  # type: ignore
                    self._cloud = md.vl(api_key=key)
                    self._mode = "cloud"
                    return self._mode
            except Exception as e:
                self._import_error = (self._import_error or "") + " | cloud: " + repr(e)
            self._mode = "none"
            return self._mode

    # ---- lifecycle ----
    def pin(self) -> dict:
        with self._lock:
            self._pinned = True
            self._cancel_timer()
        return self.status()

    def unpin(self, unload: bool = True) -> dict:
        with self._lock:
            self._pinned = False
            self._cancel_timer()
            if unload:
                self._unload_now()
        return self.status()

    def _cancel_timer(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _arm_timer(self):
        if self._pinned:
            return
        self._cancel_timer()
        self._timer = threading.Timer(self.idle_timeout_s, self._idle_unload)
        self._timer.daemon = True
        self._timer.start()

    def _idle_unload(self):
        with self._lock:
            if self._pinned:
                return
            self._unload_now()

    def _unload_now(self):
        if self._mode == "argus" and self._argus_v is not None:
            fn = getattr(self._argus_v, "vision_unload", None)
            if callable(fn):
                try: fn()
                except Exception: pass

    # ---- inference ----
    def find(self, target: str, screenshot_path: Optional[str]) -> Optional[dict]:
        """Return {x, y, bbox, confidence, source: 'vision'} or None."""
        mode = self._ensure()
        if mode == "none":
            return None
        try:
            if mode == "argus":
                self._last_use = time.monotonic()
                self._arm_timer()
                return self._argus_v.find(target, screenshot_path) if hasattr(self._argus_v, "find") else None
            if mode == "cloud":
                if not screenshot_path:
                    return None
                from PIL import Image
                img = Image.open(screenshot_path)
                self._last_use = time.monotonic()
                # Cloud SDK exposes `point` for point-grounding
                pt = self._cloud.point(img, target)
                if not pt or "points" not in pt or not pt["points"]:
                    return None
                p = pt["points"][0]
                W, H = img.size
                x, y = float(p["x"]) * W, float(p["y"]) * H
                return {"x": x, "y": y, "source": "vision",
                        "confidence": float(p.get("confidence", 0.5)),
                        "bbox": [x - 16, y - 16, 32, 32]}
        except Exception:
            return None
        return None

    def ask(self, screenshot_path: str, question: str) -> Optional[str]:
        """Visual Q&A over a screenshot. Returns textual answer or None."""
        mode = self._ensure()
        if mode == "none":
            return None
        try:
            if mode == "argus":
                fn = (getattr(self._argus_v, "query", None)
                      or getattr(self._argus_v, "ask", None))
                if not callable(fn):
                    return None
                self._last_use = time.monotonic()
                self._arm_timer()
                return fn(screenshot_path, question)
            if mode == "cloud":
                from PIL import Image
                img = Image.open(screenshot_path)
                self._last_use = time.monotonic()
                res = self._cloud.query(img, question)
                return (res or {}).get("answer")
        except Exception:
            return None
        return None

    def status(self) -> dict:
        with self._lock:
            return {
                "mode": self._ensure(),
                "pinned": self._pinned,
                "idle_timeout_s": self.idle_timeout_s,
                "seconds_since_use": (round(time.monotonic() - self._last_use, 1)
                                      if self._last_use else None),
                "import_error": self._import_error,
            }


VISION = _VisionSingleton()
