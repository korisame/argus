"""Screenshot diff for state monitoring (different surface from verify.py).

verify.py is for action verify (single before/after). diff_screens is for
ad-hoc comparison: 'did anything change since I last looked?'.
Returns regions of change + perceptual delta.
"""
from __future__ import annotations

from typing import Optional


def compare(path_a: str, path_b: str, *, threshold: int = 30) -> dict:
    """Compare two screenshots. Returns {ok, identical, regions:[...], summary}."""
    try:
        from PIL import Image, ImageChops
    except Exception as e:
        return {"ok": False, "error": f"PIL missing: {e}"}
    try:
        a = Image.open(path_a).convert("RGB")
        b = Image.open(path_b).convert("RGB")
    except Exception as e:
        return {"ok": False, "error": f"open failed: {e}"}
    if a.size != b.size:
        b = b.resize(a.size)
    delta = ImageChops.difference(a, b)
    bbox = delta.getbbox()
    if not bbox:
        return {"ok": True, "identical": True, "regions": [], "summary": "no change"}

    # Fast region segmentation: split delta into 8x6 grid, mark cells with
    # mean delta > threshold
    W, H = delta.size
    cols, rows = 8, 6
    cw, rh = W // cols, H // rows
    regions = []
    for r in range(rows):
        for c in range(cols):
            x0, y0 = c * cw, r * rh
            x1, y1 = (c + 1) * cw, (r + 1) * rh
            cell = delta.crop((x0, y0, x1, y1))
            pixels = list(cell.getdata())
            if not pixels:
                continue
            mean = sum(sum(p) for p in pixels) / (len(pixels) * 3)
            if mean > threshold / 3:
                regions.append({"x": x0, "y": y0, "w": cw, "h": rh,
                                  "mean_delta": round(mean, 1)})
    pix = list(delta.getdata())
    overall = sum(sum(p) for p in pix) / (len(pix) * 3) if pix else 0.0
    return {"ok": True, "identical": False,
            "diff_bbox": list(bbox),
            "regions_changed": len(regions),
            "regions": regions[:20],
            "overall_mean_delta": round(overall, 2)}
