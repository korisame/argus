"""Cross-surface action verifier.

Three modes, picked by surface:
  - browser  → DOM hash via cdp.state_snapshot() (URL + body hash)
  - native   → screenshot diff (dHash + region delta around bbox)
  - file ops → file hash before/after
"""
from __future__ import annotations

from typing import Optional

from . import router as _router
from adapters import cdp


# ─── screenshot diff ─────────────────────────────────────────────
def _dhash(img, size=16) -> int:
    g = img.convert("L").resize((size + 1, size))
    bits = 0
    for y in range(size):
        for x in range(size):
            left = g.getpixel((x, y))
            right = g.getpixel((x + 1, y))
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def _hamming(a: int, b: int) -> int:
    x = a ^ b
    try:
        return x.bit_count()
    except AttributeError:
        return bin(x).count("1")


def screenshot_diff(path_before: str, path_after: str,
                    bbox: Optional[list] = None, pad: int = 30) -> dict:
    from PIL import Image, ImageChops
    a = Image.open(path_before).convert("RGB")
    b = Image.open(path_after).convert("RGB")
    if a.size != b.size:
        b = b.resize(a.size)
    g = _hamming(_dhash(a), _dhash(b))
    if not bbox:
        return {"global_distance": g, "region_changed_ratio": None,
                "ok": g > 4, "reason": f"global hash delta {g}"}
    x, y, w, h = bbox
    x0 = max(0, int(x) - pad)
    y0 = max(0, int(y) - pad)
    x1 = min(a.size[0], int(x + w + 2 * pad))
    y1 = min(a.size[1], int(y + h + 2 * pad))
    ca = a.crop((x0, y0, x1, y1))
    cb = b.crop((x0, y0, x1, y1))
    delta = ImageChops.difference(ca, cb)
    pixels = list(delta.getdata())
    total = len(pixels)
    if total == 0:
        return {"global_distance": g, "region_changed_ratio": 0.0,
                "ok": g > 4, "reason": f"empty region; global delta {g}"}
    sums = [sum(p) for p in pixels]
    changed = sum(1 for s in sums if s > 30)
    ratio = changed / total
    if ratio >= 0.02:
        return {"global_distance": g, "region_changed_ratio": ratio, "ok": True,
                "reason": f"region delta {ratio:.2%}"}
    if g > 8:
        return {"global_distance": g, "region_changed_ratio": ratio, "ok": True,
                "reason": f"global delta {g} (region quiet)"}
    return {"global_distance": g, "region_changed_ratio": ratio, "ok": False,
            "reason": f"region quiet ({ratio:.2%}) + global delta {g}"}


# ─── DOM diff ────────────────────────────────────────────────────
def dom_diff(snapshot_before: dict, snapshot_after: dict) -> dict:
    if not snapshot_before or not snapshot_after:
        return {"ok": False, "reason": "missing snapshot"}
    url_before = snapshot_before.get("url")
    url_after = snapshot_after.get("url")
    hash_before = snapshot_before.get("dom_hash") or snapshot_before.get("body_hash")
    hash_after = snapshot_after.get("dom_hash") or snapshot_after.get("body_hash")
    if url_before != url_after:
        return {"ok": True, "reason": f"url changed: {url_before} → {url_after}"}
    if hash_before != hash_after:
        return {"ok": True, "reason": "DOM hash changed"}
    return {"ok": False, "reason": "url + DOM hash unchanged"}


# ─── unified entry ───────────────────────────────────────────────
class Verifier:
    """Use as a context manager:
        with Verifier(bbox=hit['bbox']) as v:
            do_action()
        v.result  → {ok, reason, ...}
    """
    def __init__(self, bbox: Optional[list] = None,
                 surface_hint: Optional[str] = None):
        self.bbox = bbox
        self.surface = surface_hint or _router.detect().get("surface")
        self.before_path = None
        self.after_path = None
        self.before_dom = None
        self.after_dom = None
        self.result: Optional[dict] = None

    def __enter__(self):
        if self.surface == "browser":
            try:
                self.before_dom = cdp.state_snapshot()
            except Exception:
                self.before_dom = None
        else:
            from adapters import cgevent
            self.before_path = cgevent.screenshot("/tmp/argus_prime_before.png")
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc:
            self.result = {"ok": False, "reason": f"action raised: {exc}"}
            return False
        # short settle
        import time
        time.sleep(0.35)
        if self.surface == "browser":
            try:
                self.after_dom = cdp.state_snapshot()
                self.result = dom_diff(self.before_dom or {}, self.after_dom or {})
            except Exception as e:
                self.result = {"ok": False, "reason": f"snapshot failed: {e}"}
        else:
            from adapters import cgevent
            self.after_path = cgevent.screenshot("/tmp/argus_prime_after.png")
            self.result = screenshot_diff(self.before_path, self.after_path,
                                          bbox=self.bbox)
        return False
