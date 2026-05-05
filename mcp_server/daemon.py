"""In-process argus daemon.

Tries to `import argus` directly (zero subprocess). Holds the Moondream
model warm with an LRU idle timer; explicit session_begin / session_end
override the timer.

If the argus package isn't importable, callers should fall back to the
subprocess path (server.py keeps that path intact).
"""
from __future__ import annotations

import importlib
import threading
import time
from typing import Any, Callable, Optional


class ArgusDaemon:
    def __init__(self, idle_timeout_s: float = 300.0):
        self.idle_timeout_s = idle_timeout_s
        self._lock = threading.RLock()
        self._argus = None              # module
        self._vision = None             # argus.vision module
        self._last_vision_use = 0.0
        self._session_pinned = False
        self._timer: Optional[threading.Timer] = None
        self._import_error: Optional[str] = None

    # ---- import ----
    def available(self) -> bool:
        return self._try_import() is not None

    def _try_import(self):
        if self._argus is not None:
            return self._argus
        try:
            self._argus = importlib.import_module("argus")
            try:
                self._vision = importlib.import_module("argus.vision")
            except Exception:
                self._vision = None
            return self._argus
        except Exception as e:
            self._import_error = repr(e)
            return None

    # ---- vision lifecycle ----
    def mark_vision_use(self) -> None:
        with self._lock:
            self._last_vision_use = time.monotonic()
            self._reset_timer()

    def session_begin(self) -> dict:
        with self._lock:
            self._session_pinned = True
            self._cancel_timer()
            return {"pinned": True, "idle_timeout_s": self.idle_timeout_s}

    def session_end(self, unload: bool = True) -> dict:
        with self._lock:
            self._session_pinned = False
            self._cancel_timer()
            if unload:
                self._unload_now()
            return {"pinned": False, "unloaded": unload}

    def _reset_timer(self) -> None:
        if self._session_pinned:
            return
        self._cancel_timer()
        self._timer = threading.Timer(self.idle_timeout_s, self._idle_unload)
        self._timer.daemon = True
        self._timer.start()

    def _cancel_timer(self) -> None:
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _idle_unload(self) -> None:
        with self._lock:
            if self._session_pinned:
                return
            self._unload_now()

    def _unload_now(self) -> None:
        if self._vision is None:
            return
        try:
            fn = getattr(self._vision, "vision_unload", None)
            if callable(fn):
                fn()
        except Exception:
            pass

    # ---- proxy helpers ----
    def call(self, name: str, *args, **kwargs) -> Any:
        """Call argus.<name>(*args, **kwargs) in-process."""
        m = self._try_import()
        if m is None:
            raise RuntimeError(f"argus module not importable: {self._import_error}")
        fn = getattr(m, name, None)
        if not callable(fn):
            raise AttributeError(f"argus.{name} not callable")
        return fn(*args, **kwargs)

    def vision_call(self, name: str, *args, **kwargs) -> Any:
        m = self._try_import()
        if m is None or self._vision is None:
            raise RuntimeError(f"argus.vision not importable: {self._import_error}")
        fn = getattr(self._vision, name, None)
        if not callable(fn):
            raise AttributeError(f"argus.vision.{name} not callable")
        try:
            return fn(*args, **kwargs)
        finally:
            self.mark_vision_use()

    def status(self) -> dict:
        # Probe import so the flag and error are populated for diagnostics
        self._try_import()
        return {
            "in_process": self._argus is not None,
            "vision_module": self._vision is not None,
            "session_pinned": self._session_pinned,
            "idle_timeout_s": self.idle_timeout_s,
            "seconds_since_vision_use": (round(time.monotonic() - self._last_vision_use, 1)
                                         if self._last_vision_use else None),
            "import_error": self._import_error,
            "argus_module": getattr(self._argus, "__file__", None),
            "exposed": (sorted([n for n in dir(self._argus)
                                if not n.startswith("_") and callable(getattr(self._argus, n, None))])
                        if self._argus else []),
        }


# Module-level singleton
DAEMON = ArgusDaemon()
