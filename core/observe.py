"""argus_observe — high-level monitoring DSL.

Watch for an event in an app/window:
  - text_appears(query):    poll OCR, fire when query appears
  - state_changes:          screenshot diff exceeds threshold
  - app_changes:            frontmost app changes
  - http_endpoint(url):     poll HTTP endpoint, fire on status change

Each watch runs in a background thread. Notifies via macOS notification +
intent.log entry. Stops after `max_fires` events or `timeout_s` elapsed.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from . import intent, screen, notify, router, diff_screens, http_client
from adapters import ocr as _ocr

_WATCHES: dict[str, dict] = {}
_LOCK = threading.RLock()


def _runner(name: str, kind: str, params: dict, max_fires: int,
            timeout_s: float, interval_s: float):
    state = _WATCHES.get(name)
    if not state:
        return
    started = time.time()
    fires = 0
    last_shot = None
    last_app = None
    last_status = None
    while not state["stop_event"].is_set() and (time.time() - started < timeout_s):
        try:
            event = None
            if kind == "text_appears":
                cap = screen.capture_frontmost(out_path=f"/tmp/argus_obs_{name}.png")
                if cap.get("ok") and _ocr.available():
                    boxes = _ocr.all_text(cap["path"], fast=True)
                    text = "\n".join(b["text"] for b in boxes)
                    if params.get("query", "").lower() in text.lower():
                        event = {"kind": kind, "match": params["query"],
                                 "screenshot": cap["path"]}
            elif kind == "state_changes":
                cap = screen.capture_frontmost(out_path=f"/tmp/argus_obs_{name}.png")
                if cap.get("ok"):
                    if last_shot:
                        d = diff_screens.compare(last_shot, cap["path"])
                        if not d.get("identical") and d.get("overall_mean_delta", 0) > params.get("threshold", 5):
                            event = {"kind": kind, "delta": d.get("overall_mean_delta")}
                    last_shot = cap["path"]
            elif kind == "app_changes":
                cur = router.detect().get("app", {}).get("bundle_id")
                if last_app and cur != last_app:
                    event = {"kind": kind, "from": last_app, "to": cur}
                last_app = cur
            elif kind == "http_endpoint":
                r = http_client.request("GET", params.get("url"), timeout=5)
                cur = r.get("status")
                if last_status is not None and cur != last_status:
                    event = {"kind": kind, "url": params.get("url"),
                             "from": last_status, "to": cur}
                last_status = cur
            if event:
                fires += 1
                intent.log("argus.observe", target=name, outcome="event",
                           observation=event)
                notify.notify(f"argus_observe: {name}",
                              str(event)[:200], sound="Tink")
                if fires >= max_fires:
                    break
        except Exception as e:
            intent.log("argus.observe", target=name, outcome="error",
                       observation={"error": str(e)})
        state["stop_event"].wait(interval_s)


def start(name: str, *, kind: str, params: dict | None = None,
          max_fires: int = 5, timeout_s: float = 3600.0,
          interval_s: float = 2.0) -> dict:
    if kind not in ("text_appears", "state_changes", "app_changes", "http_endpoint"):
        return {"ok": False, "error": f"unknown kind: {kind}"}
    with _LOCK:
        if name in _WATCHES and _WATCHES[name]["thread"].is_alive():
            return {"ok": False, "error": f"watch {name!r} already running"}
        stop_event = threading.Event()
        t = threading.Thread(target=_runner,
                              args=(name, kind, params or {}, max_fires, timeout_s, interval_s),
                              daemon=True, name=f"argus-observe-{name}")
        _WATCHES[name] = {"thread": t, "stop_event": stop_event,
                            "kind": kind, "params": params or {},
                            "started": time.time()}
        t.start()
    return {"ok": True, "name": name, "kind": kind,
            "max_fires": max_fires, "timeout_s": timeout_s}


def stop(name: str) -> dict:
    with _LOCK:
        w = _WATCHES.get(name)
        if not w:
            return {"ok": True, "noop": True}
        w["stop_event"].set()
        _WATCHES.pop(name, None)
    return {"ok": True, "stopped": name}


def list_watches() -> dict:
    with _LOCK:
        return {"watches": [
            {"name": n, "kind": w["kind"],
             "alive": w["thread"].is_alive(),
             "started": w["started"]}
            for n, w in _WATCHES.items()
        ]}
