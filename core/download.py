"""HTTP download with redirect following + size cap + content-type detection."""
from __future__ import annotations

import os
from typing import Optional
from urllib.request import Request, urlopen
from urllib.parse import urlparse


def download(url: str, *, out_path: Optional[str] = None,
             max_bytes: int = 500 * 1024 * 1024,
             timeout: float = 60.0,
             headers: Optional[dict] = None) -> dict:
    """Download a URL to disk. Returns {ok, path, size, content_type}."""
    if not out_path:
        # Derive filename from URL
        path = urlparse(url).path
        name = os.path.basename(path) or "argus_download.bin"
        out_path = f"/tmp/{name}"
    try:
        h = dict(headers or {})
        h.setdefault("User-Agent", "argus-mcp/2.3")
        req = Request(url, headers=h)
        with urlopen(req, timeout=timeout) as r, open(out_path, "wb") as f:
            ct = r.headers.get("Content-Type", "")
            cl = int(r.headers.get("Content-Length", 0) or 0)
            if cl and cl > max_bytes:
                return {"ok": False, "error": f"content-length {cl} > max {max_bytes}"}
            written = 0
            while True:
                chunk = r.read(64 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    f.close()
                    os.unlink(out_path)
                    return {"ok": False, "error": f"exceeded max {max_bytes} mid-stream"}
                f.write(chunk)
        return {"ok": True, "path": out_path,
                "size": os.path.getsize(out_path),
                "content_type": ct,
                "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}
