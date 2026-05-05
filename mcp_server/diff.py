"""Screenshot diff for self-verifying actions.

Cheap perceptual diff: dHash + per-region pixel delta around a bbox.
If the action region didn't change, the action probably didn't land.
"""
from __future__ import annotations

from typing import Optional


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
        return x.bit_count()  # Python 3.10+
    except AttributeError:
        return bin(x).count("1")


def diff_global(path_before: str, path_after: str) -> dict:
    """Whole-screen perceptual diff. Returns {distance, changed, hash_before, hash_after}."""
    from PIL import Image
    a = Image.open(path_before)
    b = Image.open(path_after)
    ha = _dhash(a)
    hb = _dhash(b)
    d = _hamming(ha, hb)
    return {"distance": d, "changed": d > 4, "hash_before": ha, "hash_after": hb}


def diff_region(path_before: str, path_after: str, bbox: list, pad: int = 30) -> dict:
    """Pixel-mean delta inside a region (with padding). High delta => something visibly happened.

    bbox: [x, y, w, h] in image pixel coords.
    Returns {mean_delta, changed_pixels, total_pixels, changed_ratio}.
    """
    from PIL import Image, ImageChops
    a = Image.open(path_before).convert("RGB")
    b = Image.open(path_after).convert("RGB")
    if a.size != b.size:
        b = b.resize(a.size)
    x, y, w, h = bbox
    x = max(0, int(x) - pad)
    y = max(0, int(y) - pad)
    x2 = min(a.size[0], int(x + w + 2 * pad))
    y2 = min(a.size[1], int(y + h + 2 * pad))
    box = (x, y, x2, y2)
    ca = a.crop(box)
    cb = b.crop(box)
    delta = ImageChops.difference(ca, cb)
    pixels = list(delta.getdata())
    total = len(pixels)
    if total == 0:
        return {"mean_delta": 0.0, "changed_pixels": 0, "total_pixels": 0, "changed_ratio": 0.0}
    sums = [sum(p) for p in pixels]
    mean = sum(sums) / (total * 3)
    changed = sum(1 for s in sums if s > 30)
    return {
        "mean_delta": round(mean, 2),
        "changed_pixels": changed,
        "total_pixels": total,
        "changed_ratio": round(changed / total, 4),
    }


def verify(path_before: str, path_after: str, bbox: Optional[list] = None) -> dict:
    """Combined verifier.
    Returns:
      {
        ok: bool,        # action probably had visible effect
        reason: str,     # human description
        global_distance: int,
        region_changed_ratio: float | None,
      }
    """
    g = diff_global(path_before, path_after)
    region = diff_region(path_before, path_after, bbox) if bbox else None

    if region is not None:
        if region["changed_ratio"] >= 0.02:
            return {"ok": True, "reason": f"region delta {region['changed_ratio']:.2%}",
                    "global_distance": g["distance"], "region_changed_ratio": region["changed_ratio"]}
        if g["distance"] > 8:
            return {"ok": True, "reason": f"global hash delta {g['distance']} (region quiet)",
                    "global_distance": g["distance"], "region_changed_ratio": region["changed_ratio"]}
        return {"ok": False,
                "reason": f"region quiet ({region['changed_ratio']:.2%}) and global hash delta {g['distance']}",
                "global_distance": g["distance"], "region_changed_ratio": region["changed_ratio"]}
    # No bbox — fall back to global only
    if g["distance"] > 4:
        return {"ok": True, "reason": f"global hash delta {g['distance']}",
                "global_distance": g["distance"], "region_changed_ratio": None}
    return {"ok": False, "reason": f"global hash delta {g['distance']} (no change detected)",
            "global_distance": g["distance"], "region_changed_ratio": None}
