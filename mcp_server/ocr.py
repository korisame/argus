"""Apple Vision OCR (VNRecognizeTextRequest).

Native, free, fast (<150ms typical). Use for exact-text targets before
defaulting to Moondream's natural-language grounding.
"""
from __future__ import annotations

import re
from typing import Optional

try:
    import Quartz
    import objc
    from Vision import (
        VNRecognizeTextRequest,
        VNImageRequestHandler,
        VNRequestTextRecognitionLevelAccurate,
        VNRequestTextRecognitionLevelFast,
    )
    from Foundation import NSURL
    HAVE_VISION = True
except Exception as _e:  # pragma: no cover
    HAVE_VISION = False
    _VISION_ERR = repr(_e)


def available() -> bool:
    return HAVE_VISION


def _ocr_image_path(path: str, fast: bool = False, langs=("en-US", "it-IT")) -> list[dict]:
    """Return [{text, x, y, w, h, confidence}] for `path`. Coords are pixel coords
    in the image's coordinate system (top-left origin)."""
    if not HAVE_VISION:
        return []
    url = NSURL.fileURLWithPath_(path)
    handler = VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    req = VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(
        VNRequestTextRecognitionLevelFast if fast else VNRequestTextRecognitionLevelAccurate
    )
    req.setUsesLanguageCorrection_(True)
    try:
        req.setRecognitionLanguages_(list(langs))
    except Exception:
        pass

    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        return []

    # Need image dims to convert normalized → pixel
    img_src = Quartz.CGImageSourceCreateWithURL(url, None)
    img = Quartz.CGImageSourceCreateImageAtIndex(img_src, 0, None)
    W = Quartz.CGImageGetWidth(img)
    H = Quartz.CGImageGetHeight(img)

    out = []
    for obs in (req.results() or []):
        cand = obs.topCandidates_(1)
        if not cand:
            continue
        text = str(cand[0].string())
        # bbox: normalized, bottom-left origin (Vision convention)
        bb = obs.boundingBox()
        x = float(bb.origin.x) * W
        # Flip Y to top-left origin
        y = (1.0 - float(bb.origin.y) - float(bb.size.height)) * H
        w = float(bb.size.width) * W
        h = float(bb.size.height) * H
        out.append({
            "text": text,
            "x": x, "y": y, "w": w, "h": h,
            "confidence": float(cand[0].confidence()),
        })
    return out


def find(query: str, screenshot_path: str, fuzzy: bool = True) -> Optional[dict]:
    """Find best OCR match for `query` in `screenshot_path`.

    Returns {x, y, bbox, text, confidence, source: 'ocr'} or None.
    Coords are pixel coords (image-space; caller must convert to screen
    coords if image was scaled — but typically screenshot is at 1:1).
    """
    if not HAVE_VISION:
        return None
    boxes = _ocr_image_path(screenshot_path)
    if not boxes:
        return None

    q = query.strip().lower()
    q_tokens = set(re.findall(r"\w+", q))
    best = None
    best_score = 0.0
    for b in boxes:
        tl = b["text"].lower()
        if tl == q:
            score = 1.0 * b["confidence"]
        elif q in tl or tl in q:
            score = (0.85 - min(0.3, abs(len(tl) - len(q)) / max(len(q), 1))) * b["confidence"]
        elif fuzzy and q_tokens:
            t_tokens = set(re.findall(r"\w+", tl))
            if not t_tokens:
                continue
            overlap = len(q_tokens & t_tokens) / len(q_tokens | t_tokens)
            score = 0.7 * overlap * b["confidence"]
        else:
            continue
        if score > best_score:
            best_score = score
            best = {
                "x": b["x"] + b["w"] / 2,
                "y": b["y"] + b["h"] / 2,
                "bbox": [b["x"], b["y"], b["w"], b["h"]],
                "text": b["text"],
                "confidence": round(score, 3),
                "source": "ocr",
            }
    return best


def all_text(screenshot_path: str, fast: bool = False) -> list[dict]:
    return _ocr_image_path(screenshot_path, fast=fast)


def doctor() -> dict:
    return {
        "vision_available": HAVE_VISION,
        "error": _VISION_ERR if not HAVE_VISION else None,
    }
