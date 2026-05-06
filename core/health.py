"""Continuous health monitor — background ticker.

Every N seconds, runs a lightweight doctor and logs DEGRADED/BROKEN
transitions to intent.jsonl. Useful for unattended workflows.

Start: argus_health action='start' [interval_s=60]
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from . import intent
from . import router as _router
from adapters import ax, ocr, cdp, cdp_raw, cgevent

_STATE: dict = {"thread": None, "stop_event": None, "interval_s": 60.0,
                "last_status": None, "last_check": None,
                "transitions": []}


def _check() -> dict:
    deps = {
        "ax": bool(ax.available()),
        "ocr": bool(ocr.available()),
        "cdp": bool(cdp.available()) or bool(cdp_raw.available()),
        "argus_core": bool(cgevent.doctor().get("argus_core_importable")),
    }
    n_ok = sum(deps.values())
    if n_ok == len(deps):
        status = "READY"
    elif deps["argus_core"] and (deps["ax"] or deps["ocr"]):
        status = "DEGRADED"
    else:
        status = "BROKEN"
    return {"status": status, "deps": deps,
            "surface": _router.detect().get("surface")}


def _runner(stop: threading.Event, interval_s: float):
    while not stop.is_set():
        try:
            cur = _check()
            ts = time.time()
            _STATE["last_status"] = cur
            _STATE["last_check"] = ts
            prev = (_STATE["transitions"][-1]["status"]
                    if _STATE["transitions"] else None)
            if cur["status"] != prev:
                _STATE["transitions"].append({"ts": ts, "status": cur["status"],
                                                "deps": cur["deps"]})
                _STATE["transitions"] = _STATE["transitions"][-50:]
                intent.log("argus.health", outcome=cur["status"].lower(),
                           observation=cur)
        except Exception as e:
            intent.log("argus.health", outcome="error",
                       observation={"error": str(e)})
        stop.wait(interval_s)


def start(interval_s: float = 60.0) -> dict:
    if _STATE["thread"] and _STATE["thread"].is_alive():
        return {"ok": True, "already_running": True,
                "interval_s": _STATE["interval_s"]}
    stop = threading.Event()
    t = threading.Thread(target=_runner, args=(stop, interval_s),
                          daemon=True, name="argus-health")
    t.start()
    _STATE["thread"] = t
    _STATE["stop_event"] = stop
    _STATE["interval_s"] = interval_s
    return {"ok": True, "started": True, "interval_s": interval_s}


def stop() -> dict:
    s = _STATE["stop_event"]
    if not s:
        return {"ok": True, "running": False}
    s.set()
    _STATE["thread"] = None
    _STATE["stop_event"] = None
    return {"ok": True, "stopped": True}


def status() -> dict:
    running = _STATE["thread"] is not None and _STATE["thread"].is_alive()
    return {"running": running, "interval_s": _STATE["interval_s"],
            "last_status": _STATE["last_status"],
            "last_check_ts": _STATE["last_check"],
            "transitions": _STATE["transitions"][-10:]}
