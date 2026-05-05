"""Chrome DevTools Protocol adapter — in-process when possible.

Tries to import browser-harness-pro's `helpers.py` directly. If that works,
calls go through the in-process daemon socket (~10-30ms per call). Falls
back to the `browser-harness` CLI subprocess (~200-400ms) when the import
isn't available.
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
from typing import Optional

# Common locations for the browser-harness-pro checkout
_BH_PATHS = (
    os.path.expanduser("~/Developer/browser-harness-pro"),
    os.path.expanduser("~/Developer/browser-harness"),
    os.environ.get("BH_HOME"),
)


_helpers = None
_import_error: Optional[str] = None


def _try_import_helpers():
    """Lazy: import browser_harness helpers.py once."""
    global _helpers, _import_error
    if _helpers is not None or _import_error is not None:
        return _helpers
    for p in _BH_PATHS:
        if not p or not os.path.isdir(p):
            continue
        if p not in sys.path:
            sys.path.insert(0, p)
        try:
            _helpers = importlib.import_module("helpers")
            return _helpers
        except Exception as e:
            _import_error = repr(e)
            continue
    if _import_error is None:
        _import_error = "browser-harness-pro checkout not found in BH_HOME or ~/Developer/"
    return None


def _bh_path() -> Optional[str]:
    return shutil.which("browser-harness")


def available() -> bool:
    return _try_import_helpers() is not None or _bh_path() is not None


# ─── in-process direct call ──────────────────────────────────────
def _direct(name: str, *args, **kwargs) -> dict:
    h = _try_import_helpers()
    if h is None:
        return {"ok": False, "error": f"helpers not importable: {_import_error}"}
    fn = getattr(h, name, None)
    if not callable(fn):
        return {"ok": False, "error": f"helpers.{name} not callable"}
    try:
        result = fn(*args, **kwargs)
        return {"ok": True, "result": result, "via": "in-process"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "via": "in-process"}


# ─── subprocess fallback ─────────────────────────────────────────
def _subprocess(code: str, timeout: float = 30.0) -> dict:
    cli = _bh_path()
    if not cli:
        return {"ok": False, "error": "browser-harness CLI not on PATH"}
    try:
        r = subprocess.run([cli, "-c", code], capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"browser-harness timed out after {timeout}s "
                                       "(Chrome not running or no debug port?)"}
    except Exception as e:
        return {"ok": False, "error": f"browser-harness invocation failed: {e}"}
    if r.returncode != 0:
        return {"ok": False, "error": (r.stderr or r.stdout)[-500:]}
    out = (r.stdout or "").strip()
    for line in reversed(out.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return {"ok": True, "result": json.loads(line), "via": "subprocess"}
        except Exception:
            return {"ok": True, "raw": line, "via": "subprocess"}
    return {"ok": True, "raw": out, "via": "subprocess"}


def _call(direct_name: str, subprocess_code: str, timeout: float = 30.0,
          *args, **kwargs) -> dict:
    """Try in-process first, fall back to subprocess. Same return shape."""
    res = _direct(direct_name, *args, **kwargs)
    if res.get("ok"):
        return res
    return _subprocess(subprocess_code, timeout=timeout)


# ─── public API (same shape as v0.3) ─────────────────────────────
def page_info() -> dict:
    res = _call("page_info", "import json; print(json.dumps(page_info()))",
                timeout=10)
    if res.get("ok") and "result" in res:
        return res["result"]
    return res


def host() -> Optional[str]:
    info = page_info()
    if not isinstance(info, dict):
        return None
    url = info.get("url")
    if not url:
        return None
    try:
        from urllib.parse import urlparse
        return urlparse(url).hostname
    except Exception:
        return None


def find(target: str) -> Optional[dict]:
    """Locate a clickable target via browser-harness's find_visual_target."""
    res = _call("find_visual_target",
                f"import json; print(json.dumps(find_visual_target(text={target!r})))",
                timeout=15, text=target)
    if not res.get("ok") or "result" not in res:
        return None
    r = res["result"]
    if not isinstance(r, dict) or "x" not in r:
        return None
    x, y = float(r["x"]), float(r["y"])
    bbox = r.get("bbox") or [x - 16, y - 16, 32, 32]
    return {"x": x, "y": y, "bbox": bbox,
            "text": r.get("text") or target,
            "confidence": float(r.get("confidence", 0.7)),
            "source": "cdp",
            "selector": r.get("selector") or f"DOM[text={target!r}]"}


def click(x: float, y: float, double: bool = False) -> dict:
    n = 2 if double else 1
    return _call("click_at_xy",
                 f"import json; print(json.dumps(click_at_xy({int(x)}, {int(y)}, clicks={n})))",
                 timeout=15, x=int(x), y=int(y), clicks=n)


def smart_click(target: str) -> dict:
    return _call("smart_click",
                 f"import json; print(json.dumps(smart_click({target!r})))",
                 timeout=20, target=target)


def type_text(text: str) -> dict:
    return _call("type_text",
                 f"import json; print(json.dumps(type_text({text!r})))",
                 timeout=15, text=text)


def press_key(key_name: str, modifiers: int = 0) -> dict:
    return _call("press_key",
                 f"import json; print(json.dumps(press_key({key_name!r}, modifiers={modifiers})))",
                 timeout=10, key=key_name, modifiers=modifiers)


def screenshot(path: str = "/tmp/argus_prime_cdp.png") -> str:
    _call("capture_screenshot",
          f"import json; print(json.dumps(capture_screenshot({path!r})))",
          timeout=15, path=path)
    return path


def state_snapshot() -> dict:
    res = _call("state_snapshot",
                "import json; print(json.dumps(state_snapshot()))",
                timeout=10)
    return res.get("result") if res.get("ok") and "result" in res else {}


def doctor() -> dict:
    cli = _bh_path()
    in_proc = _try_import_helpers() is not None
    return {
        "available": in_proc or bool(cli),
        "in_process": in_proc,
        "subprocess_fallback": bool(cli),
        "cli": cli,
        "import_error": _import_error,
        "bh_paths_checked": [p for p in _BH_PATHS if p],
        "note": "page_info() not probed; call argus_surface to check live Chrome connection",
    }
