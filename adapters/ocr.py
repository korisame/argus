"""Apple Vision OCR (VNRecognizeTextRequest).

~150ms native OCR. Second layer of cascade. Used for exact-text targets
before escalating to Moondream.
"""
from __future__ import annotations

import re
from typing import Optional

try:
    import Quartz
    from Vision import (
        VNRecognizeTextRequest,
        VNImageRequestHandler,
        VNRequestTextRecognitionLevelAccurate,
        VNRequestTextRecognitionLevelFast,
    )
    from Foundation import NSURL
    HAVE_VISION = True
    _ERR = None
except Exception as _e:
    HAVE_VISION = False
    _ERR = repr(_e)


def available() -> bool:
    return HAVE_VISION


def all_text(screenshot_path: str, fast: bool = False,
             langs=("en-US", "it-IT")) -> list[dict]:
    """[{text, x, y, w, h, confidence}] in pixel coords (top-left origin)."""
    if not HAVE_VISION:
        return []
    url = NSURL.fileURLWithPath_(screenshot_path)
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

    ok, _ = handler.performRequests_error_([req], None)
    if not ok:
        return []

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
        bb = obs.boundingBox()
        x = float(bb.origin.x) * W
        y = (1.0 - float(bb.origin.y) - float(bb.size.height)) * H
        w = float(bb.size.width) * W
        h = float(bb.size.height) * H
        out.append({"text": text, "x": x, "y": y, "w": w, "h": h,
                    "confidence": float(cand[0].confidence())})
    return out


def find(target: str, screenshot_path: str) -> Optional[dict]:
    """Best OCR match. Returns {x, y, bbox, text, confidence, source: 'ocr'} or None."""
    if not HAVE_VISION:
        return None
    boxes = all_text(screenshot_path)
    if not boxes:
        return None

    q = target.strip().lower()
    q_tokens = set(re.findall(r"\w+", q))
    best = None
    best_score = 0.0
    for b in boxes:
        tl = b["text"].lower()
        if tl == q:
            score = b["confidence"]
        elif q in tl or tl in q:
            score = (0.85 - min(0.3, abs(len(tl) - len(q)) / max(len(q), 1))) * b["confidence"]
        elif q_tokens:
            t_tokens = set(re.findall(r"\w+", tl))
            if not t_tokens:
                continue
            ov = len(q_tokens & t_tokens) / len(q_tokens | t_tokens)
            score = 0.7 * ov * b["confidence"]
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
                "selector": f"OCR[text={b['text']!r}]",
            }
    return best


def doctor() -> dict:
    return {"available": HAVE_VISION, "error": _ERR}
