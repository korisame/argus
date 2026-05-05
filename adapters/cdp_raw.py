"""Raw Chrome DevTools Protocol — no browser-harness dependency.

Stdlib + websockets only. Connects to the dedicated automation Chrome
(default 127.0.0.1:9333). Persistent ws connection to the active tab,
re-attaches if Chrome rotates.

Replaces adapters/cdp.py for v0.5+. The old cdp.py stays as fallback
when the websockets package isn't available.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from typing import Any, Optional
from urllib.request import urlopen
from urllib.parse import urlparse

try:
    import websocket  # websocket-client (sync). pip install websocket-client
    HAVE_WS = True
    _ERR = None
except Exception as _e:
    HAVE_WS = False
    _ERR = repr(_e)


CDP_URL = os.environ.get("BU_CDP_URL", "http://127.0.0.1:9333")


def available() -> bool:
    return HAVE_WS


# ─── connection management ───────────────────────────────────────
class _CDPClient:
    """Single persistent connection to Chrome's active page."""
    def __init__(self):
        self._lock = threading.RLock()
        self._ws: Optional[Any] = None
        self._target_id: Optional[str] = None
        self._session_id: Optional[str] = None
        self._msg_id = 0

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def _http_targets(self) -> list[dict]:
        url = CDP_URL.rstrip("/") + "/json"
        with urlopen(url, timeout=4) as r:
            return json.loads(r.read().decode("utf-8"))

    def _pick_active_target(self) -> Optional[dict]:
        """Pick the topmost normal page (not extensions/devtools/etc)."""
        try:
            targets = self._http_targets()
        except Exception:
            return None
        pages = [t for t in targets
                 if t.get("type") == "page" and not t.get("url", "").startswith("devtools://")]
        if not pages:
            return None
        # Prefer one without about:blank
        for t in pages:
            if t.get("url") and t["url"] != "about:blank":
                return t
        return pages[0]

    def _ensure(self) -> bool:
        with self._lock:
            if self._ws and self._ws.connected:
                return True
            t = self._pick_active_target()
            if not t:
                return False
            ws_url = t.get("webSocketDebuggerUrl")
            if not ws_url:
                return False
            self._ws = websocket.create_connection(ws_url, timeout=8)
            self._target_id = t.get("id")
            return True

    def _call(self, method: str, params: dict | None = None,
              timeout: float = 10.0) -> dict:
        if not self._ensure():
            return {"error": "no CDP connection"}
        rid = self._next_id()
        payload = {"id": rid, "method": method, "params": params or {}}
        with self._lock:
            self._ws.send(json.dumps(payload))
            self._ws.settimeout(timeout)
            while True:
                raw = self._ws.recv()
                msg = json.loads(raw)
                if msg.get("id") == rid:
                    if "error" in msg:
                        return {"error": msg["error"]}
                    return msg.get("result", {})
                # ignore events / out-of-order

    def close(self):
        with self._lock:
            if self._ws:
                try: self._ws.close()
                except Exception: pass
            self._ws = None


_CLIENT = _CDPClient()


# ─── public API (matches adapters/cdp.py shape) ──────────────────
def page_info() -> dict:
    if not HAVE_WS:
        return {"ok": False, "error": f"websocket-client not installed: {_ERR}"}
    targets = _CLIENT._http_targets() if hasattr(_CLIENT, "_http_targets") else []
    t = _CLIENT._pick_active_target() if targets else None
    if not t:
        return {"ok": False, "error": "no active CDP target"}
    return {"ok": True, "url": t.get("url"), "title": t.get("title"),
            "id": t.get("id"), "type": t.get("type"),
            "host": urlparse(t.get("url") or "").hostname}


def host() -> Optional[str]:
    info = page_info()
    return info.get("host") if isinstance(info, dict) else None


def navigate(url: str) -> dict:
    return _CLIENT._call("Page.navigate", {"url": url}, timeout=15)


def evaluate(expression: str, return_by_value: bool = True) -> Any:
    res = _CLIENT._call("Runtime.evaluate", {
        "expression": expression,
        "returnByValue": return_by_value,
        "awaitPromise": True,
    })
    if "error" in res:
        return res
    r = res.get("result", {})
    return r.get("value") if "value" in r else r


def click(x: float, y: float, double: bool = False) -> dict:
    """Synthetic mouse click at viewport (x,y)."""
    n = 2 if double else 1
    a = _CLIENT._call("Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": x, "y": y, "button": "left",
        "clickCount": n, "buttons": 1,
    })
    b = _CLIENT._call("Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": x, "y": y, "button": "left",
        "clickCount": n,
    })
    return {"ok": "error" not in a and "error" not in b, "press": a, "release": b}


def type_text(text: str) -> dict:
    """Type literal text via Input.insertText (handles unicode)."""
    return _CLIENT._call("Input.insertText", {"text": text})


def press_key(key_name: str, modifiers: int = 0) -> dict:
    """Press a single key. modifiers bitmap: 1=Alt 2=Ctrl 4=Meta 8=Shift."""
    a = _CLIENT._call("Input.dispatchKeyEvent", {
        "type": "rawKeyDown", "key": key_name, "modifiers": modifiers,
    })
    b = _CLIENT._call("Input.dispatchKeyEvent", {
        "type": "keyUp", "key": key_name, "modifiers": modifiers,
    })
    return {"ok": "error" not in a and "error" not in b}


def screenshot(path: str = "/tmp/argus_cdp_raw.png") -> str:
    res = _CLIENT._call("Page.captureScreenshot", {"format": "png",
                                                     "captureBeyondViewport": False},
                        timeout=15)
    data = res.get("data")
    if not data:
        return path
    with open(path, "wb") as f:
        f.write(base64.b64decode(data))
    return path


def state_snapshot() -> dict:
    """For verify_change: hash url + body innerHTML + scroll position."""
    js = """
    (function(){
      const body = document.body ? document.body.innerHTML : '';
      // cheap 32-bit hash
      let h = 5381;
      for (let i = 0; i < body.length; i++) h = ((h << 5) + h + body.charCodeAt(i)) | 0;
      return {url: location.href, dom_hash: h, sx: window.scrollX, sy: window.scrollY,
              len: body.length};
    })()
    """
    return evaluate(js) or {}


def find(target: str) -> Optional[dict]:
    """DOM-based find: pick the smallest visible element whose text matches.

    Returns {x, y, bbox, text, confidence, source: 'cdp_raw', selector}.
    """
    js = """
    (function(target) {
      const t = target.toLowerCase();
      const els = Array.from(document.querySelectorAll('button, a, [role=button], input, [role=link], [role=menuitem], [aria-label]'));
      let best = null, bestScore = 0;
      for (const el of els) {
        const r = el.getBoundingClientRect();
        if (r.width < 4 || r.height < 4) continue;
        if (r.bottom < 0 || r.right < 0 || r.top > innerHeight || r.left > innerWidth) continue;
        const labels = [
          (el.innerText || '').trim(),
          (el.getAttribute('aria-label') || '').trim(),
          (el.getAttribute('placeholder') || '').trim(),
          (el.getAttribute('title') || '').trim(),
          (el.value || '').trim(),
        ].filter(Boolean);
        for (const lbl of labels) {
          const ll = lbl.toLowerCase();
          let score = 0;
          if (ll === t) score = 1.0;
          else if (ll.includes(t) || t.includes(ll)) score = 0.85 - Math.min(0.3, Math.abs(ll.length - t.length) / Math.max(t.length, 1));
          if (score > bestScore) {
            bestScore = score;
            // prefer smaller bbox (more specific)
            const area = r.width * r.height;
            best = {
              x: r.left + r.width / 2,
              y: r.top + r.height / 2,
              bbox: [r.left, r.top, r.width, r.height],
              text: lbl,
              confidence: Math.round(score * 100) / 100,
              area: area,
              tag: el.tagName.toLowerCase(),
              role: el.getAttribute('role') || '',
            };
          }
        }
      }
      return best;
    })(%s)
    """ % json.dumps(target)
    res = evaluate(js)
    if not isinstance(res, dict) or "x" not in res:
        return None
    res["source"] = "cdp_raw"
    res["selector"] = f"DOM[text={res.get('text')!r}]"
    return res


def doctor() -> dict:
    if not HAVE_WS:
        return {"available": False, "error": _ERR,
                "hint": "pip install websocket-client into the argus python"}
    try:
        targets = _CLIENT._http_targets()
        return {"available": True, "url": CDP_URL,
                "targets": len(targets),
                "active": _CLIENT._pick_active_target() or {}}
    except Exception as e:
        return {"available": False, "error": str(e),
                "hint": "Chrome not running on " + CDP_URL}
