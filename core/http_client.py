"""Generic HTTP client (stdlib).

For when an agent needs to call an arbitrary API. Returns body + status +
headers. Body is JSON-decoded if Content-Type is application/json.
"""
from __future__ import annotations

import gzip
import json
import urllib.request
import urllib.error
from typing import Any, Optional


def request(method: str, url: str, *, headers: dict | None = None,
            body: Any = None, json_body: Any = None,
            timeout: float = 30.0, max_size: int = 10 * 1024 * 1024) -> dict:
    headers = dict(headers or {})
    data: bytes | None = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    elif body is not None:
        data = body.encode("utf-8") if isinstance(body, str) else bytes(body)
    headers.setdefault("User-Agent", "argus-mcp/1.5")
    headers.setdefault("Accept-Encoding", "gzip")
    req = urllib.request.Request(url, data=data, method=method.upper(),
                                  headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(max_size)
            ct = r.headers.get("Content-Type", "")
            ce = r.headers.get("Content-Encoding", "")
            if ce.lower() == "gzip":
                try: raw = gzip.decompress(raw)
                except Exception: pass
            try:
                text = raw.decode("utf-8", errors="replace")
            except Exception:
                text = ""
            decoded: Any = None
            if "application/json" in ct.lower():
                try:
                    decoded = json.loads(text)
                except Exception:
                    decoded = None
            return {
                "ok": True, "status": r.status,
                "headers": dict(r.headers.items()),
                "body": text[:max_size // 2],
                "json": decoded,
                "bytes": len(raw),
            }
    except urllib.error.HTTPError as e:
        try: body_txt = e.read().decode("utf-8", errors="replace")[:5000]
        except Exception: body_txt = ""
        return {"ok": False, "status": e.code, "error": str(e),
                "body": body_txt}
    except Exception as e:
        return {"ok": False, "error": str(e)}
