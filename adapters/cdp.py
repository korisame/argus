"""Chrome DevTools Protocol — Step 1 wrapper over the `browser-harness` CLI.

Step 2 (later): port the helpers.py code in-process to drop the subprocess
overhead. For now this is a clean adapter: it gives the cascade resolver
the shape it needs (DOM-based selectors, CDP eval) without the cascade
having to know what `browser-harness` is.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Optional


def _bh_path() -> Optional[str]:
    return shutil.which("browser-harness")


def available() -> bool:
    return _bh_path() is not None


def _run(code: str, timeout: float = 30.0) -> dict:
    """Run a Python snippet inside browser-harness CLI, parse the JSON result.

    The snippet should `print(json.dumps(...))` its return value. We capture
    stdout, take the LAST valid JSON line.
    """
    cli = _bh_path()
    if not cli:
        return {"ok": False, "error": "browser-harness CLI not on PATH"}
    r = subprocess.run([cli, "-c", code], capture_output=True,
                       text=True, timeout=timeout)
    if r.returncode != 0:
        return {"ok": False, "error": (r.stderr or r.stdout)[-500:]}
    out = (r.stdout or "").strip()
    # Try last line as JSON
    for line in reversed(out.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return {"ok": True, "result": json.loads(line)}
        except Exception:
            return {"ok": True, "raw": line}
    return {"ok": True, "raw": out}


def page_info() -> dict:
    """{url, title, host, ...} for the current Chrome tab, or {ok: False}."""
    res = _run("import json; print(json.dumps(page_info()))", timeout=10)
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
    """smart_click() in dry-run mode: returns coords without clicking.

    browser-harness's smart_click cascade: CSS → ARIA → text. We compose a
    snippet that calls it with `dry_run=True` if supported, else use
    find_visual_target as fallback.
    """
    code = (
        "import json\n"
        f"target = {target!r}\n"
        "try:\n"
        "    res = find_visual_target(text=target)\n"
        "except Exception as e:\n"
        "    res = {'error': str(e)}\n"
        "print(json.dumps(res))\n"
    )
    res = _run(code, timeout=15)
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
    code = f"import json; print(json.dumps(click_at_xy({int(x)}, {int(y)}, clicks={n})))"
    return _run(code, timeout=15)


def smart_click(target: str) -> dict:
    code = (
        "import json\n"
        f"print(json.dumps(smart_click({target!r})))\n"
    )
    return _run(code, timeout=20)


def type_text(text: str) -> dict:
    code = f"import json; print(json.dumps(type_text({text!r})))"
    return _run(code, timeout=15)


def press_key(key_name: str, modifiers: int = 0) -> dict:
    code = f"import json; print(json.dumps(press_key({key_name!r}, modifiers={modifiers})))"
    return _run(code, timeout=10)


def screenshot(path: str = "/tmp/argus_prime_cdp.png") -> str:
    code = f"import json; print(json.dumps(capture_screenshot({path!r})))"
    _run(code, timeout=15)
    return path


def state_snapshot() -> dict:
    """DOM hash + url for verify_change()."""
    code = "import json; print(json.dumps(state_snapshot()))"
    res = _run(code, timeout=10)
    return res.get("result") if res.get("ok") and "result" in res else {}


def doctor() -> dict:
    cli = _bh_path()
    if not cli:
        return {"available": False, "error": "browser-harness CLI not found on PATH"}
    info = page_info()
    return {"available": True, "cli": cli, "page": info}
