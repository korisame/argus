"""QR code generate / decode.

Generate: tries `segno` (pure Python), falls back to `qrencode` CLI.
Decode: Apple Vision VNDetectBarcodesRequest (no extra deps).
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Optional


def generate(text: str, *, out_path: str = "/tmp/argus_qr.png",
             scale: int = 8) -> dict:
    try:
        import segno
        segno.make(text).save(out_path, scale=scale)
        return {"ok": True, "out_path": out_path, "via": "segno"}
    except Exception:
        pass
    if shutil.which("qrencode"):
        try:
            subprocess.run(["qrencode", "-o", out_path, "-s", str(scale), text],
                           check=True, timeout=10)
            return {"ok": True, "out_path": out_path, "via": "qrencode"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "no QR backend (pip install segno or brew install qrencode)"}


def decode(image_path: str) -> dict:
    """Apple Vision barcode detection."""
    try:
        from Vision import VNDetectBarcodesRequest, VNImageRequestHandler
        from Foundation import NSURL
        url = NSURL.fileURLWithPath_(image_path)
        handler = VNImageRequestHandler.alloc().initWithURL_options_(url, None)
        req = VNDetectBarcodesRequest.alloc().init()
        ok, _ = handler.performRequests_error_([req], None)
        if not ok:
            return {"ok": False, "error": "Vision request failed"}
        out = []
        for obs in (req.results() or []):
            out.append({
                "payload": str(obs.payloadStringValue() or ""),
                "symbology": str(obs.symbology() or ""),
                "confidence": float(obs.confidence()),
            })
        return {"ok": True, "count": len(out), "barcodes": out}
    except Exception as e:
        return {"ok": False, "error": f"Vision barcode decode failed: {e}"}
