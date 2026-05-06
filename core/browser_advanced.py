"""Advanced browser ops via cdp_raw: cookies, localStorage, emulation, PDF."""
from __future__ import annotations

import base64
from typing import Optional

from adapters import cdp_raw


# ─── Cookies ──────────────────────────────────────────────────────
def cookies_get(*, urls: Optional[list[str]] = None) -> dict:
    params = {"urls": urls} if urls else {}
    res = cdp_raw._CLIENT._call("Network.getCookies", params, timeout=10)
    return {"ok": "error" not in res, "result": res.get("result", res)}


def cookies_set(name: str, value: str, *, domain: str, path: str = "/",
                 secure: bool = False, http_only: bool = False,
                 expires: Optional[float] = None) -> dict:
    params = {"name": name, "value": value, "domain": domain,
              "path": path, "secure": secure, "httpOnly": http_only}
    if expires:
        params["expires"] = float(expires)
    res = cdp_raw._CLIENT._call("Network.setCookie", params, timeout=10)
    return {"ok": "error" not in res, "result": res.get("result", res)}


def cookies_clear(*, domain: Optional[str] = None) -> dict:
    if domain:
        # Network.deleteCookies accepts name + domain — need iter first
        existing = cookies_get().get("result", {}).get("cookies", [])
        n = 0
        for c in existing:
            if c.get("domain", "").lstrip(".") == domain.lstrip("."):
                cdp_raw._CLIENT._call("Network.deleteCookies",
                                        {"name": c["name"], "domain": c["domain"]},
                                        timeout=5)
                n += 1
        return {"ok": True, "deleted": n}
    res = cdp_raw._CLIENT._call("Network.clearBrowserCookies", {}, timeout=5)
    return {"ok": "error" not in res, "cleared_all": True}


# ─── localStorage ─────────────────────────────────────────────────
def localstorage_get(key: Optional[str] = None) -> dict:
    js = "JSON.stringify(Object.fromEntries(Object.entries(localStorage)))"
    text = cdp_raw.evaluate(js)
    try:
        import json
        data = json.loads(text) if isinstance(text, str) else text
    except Exception:
        data = {}
    if key:
        return {"ok": True, "key": key, "value": data.get(key)}
    return {"ok": True, "items": data, "count": len(data)}


def localstorage_set(key: str, value: str) -> dict:
    import json
    js = f"localStorage.setItem({json.dumps(key)}, {json.dumps(value)}); 'ok'"
    return {"ok": cdp_raw.evaluate(js) == "ok", "key": key}


def localstorage_clear() -> dict:
    cdp_raw.evaluate("localStorage.clear(); 'ok'")
    return {"ok": True}


# ─── Device emulation ─────────────────────────────────────────────
def emulate_device(*, width: int, height: int,
                   device_scale_factor: float = 2.0,
                   mobile: bool = True,
                   user_agent: Optional[str] = None) -> dict:
    p1 = cdp_raw._CLIENT._call("Emulation.setDeviceMetricsOverride", {
        "width": width, "height": height,
        "deviceScaleFactor": device_scale_factor, "mobile": mobile,
    })
    if user_agent:
        cdp_raw._CLIENT._call("Emulation.setUserAgentOverride",
                                {"userAgent": user_agent})
    return {"ok": "error" not in p1, "width": width, "height": height,
            "mobile": mobile}


def emulate_clear() -> dict:
    cdp_raw._CLIENT._call("Emulation.clearDeviceMetricsOverride", {})
    cdp_raw._CLIENT._call("Emulation.setUserAgentOverride", {"userAgent": ""})
    return {"ok": True}


# ─── PDF export ───────────────────────────────────────────────────
def print_to_pdf(*, out_path: str = "/tmp/argus_page.pdf",
                  landscape: bool = False, paper_format: Optional[str] = None,
                  scale: float = 1.0) -> dict:
    params = {"landscape": landscape, "scale": scale,
              "printBackground": True}
    res = cdp_raw._CLIENT._call("Page.printToPDF", params, timeout=30)
    data = res.get("data")
    if not data:
        return {"ok": False, "error": res.get("error", "no PDF data")}
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(data))
    import os
    return {"ok": True, "path": out_path,
            "size": os.path.getsize(out_path)}
