"""Resolution cascade for click/find targets:
   1. raw 'x,y' string → coords
   2. AX (deterministic, ~50ms)             — native apps only
   3. Apple Vision OCR (free, ~150ms)       — text targets
   4. Moondream visual grounding (~1-3s)    — semantic descriptions

Returns a uniform dict: {x, y, bbox, source, confidence, text?}
"""
from __future__ import annotations

import re
from typing import Optional

try:
    from . import ax, ocr
except ImportError:
    import ax, ocr  # type: ignore


COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[,\sx]\s*(-?\d+(?:\.\d+)?)\s*$")

# A target is "semantic" (skip OCR, jump to vision) if it looks like a description
# rather than literal visible text. Heuristic: contains positional/visual words.
_SEMANTIC_HINTS = {
    "icon", "icona", "button", "pulsante", "menu", "gear", "ingranaggio",
    "top", "bottom", "left", "right", "corner", "alto", "basso", "destra", "sinistra",
    "the ", "il ", "la ", "lo ", "near", "vicino", "below", "above", "sopra", "sotto",
}


def _is_semantic(target: str) -> bool:
    t = target.lower()
    return any(h in t for h in _SEMANTIC_HINTS)


def parse_coords(target: str) -> Optional[tuple[float, float]]:
    m = COORD_RE.match(target)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def resolve(target: str,
            screenshot_path: Optional[str] = None,
            vision_callable=None,
            min_confidence: float = 0.55,
            allow_vision: bool = True,
            allow_ocr: bool = True,
            allow_ax: bool = True) -> dict:
    """Resolve `target` to coords.

    Returns dict with keys:
      x, y, bbox?, source ('coords'|'ax'|'ocr'|'vision'|None),
      confidence, text?, attempts: [..ordered list of layers tried..]
    If unresolvable: {source: None, error: str, attempts: [...]}
    """
    attempts = []

    # 1) raw coords
    co = parse_coords(target)
    if co:
        return {"x": co[0], "y": co[1], "source": "coords",
                "confidence": 1.0, "attempts": ["coords"]}

    # 2) AX
    if allow_ax and ax.available():
        attempts.append("ax")
        hit = ax.find(target)
        if hit and hit["confidence"] >= min_confidence:
            hit["attempts"] = attempts
            return hit

    semantic = _is_semantic(target)

    # 3) OCR (skip if target is clearly semantic, no exact text to find)
    if allow_ocr and screenshot_path and ocr.available() and not semantic:
        attempts.append("ocr")
        hit = ocr.find(target, screenshot_path)
        if hit and hit["confidence"] >= min_confidence:
            hit["attempts"] = attempts
            return hit

    # 4) Vision (Moondream) — caller-injected to avoid hard import here
    if allow_vision and vision_callable is not None:
        attempts.append("vision")
        try:
            v = vision_callable(target, screenshot_path)
        except Exception as e:
            return {"source": None, "error": f"vision failed: {e}", "attempts": attempts}
        if v and "x" in v and "y" in v:
            v.setdefault("source", "vision")
            v.setdefault("confidence", 0.5)
            v["attempts"] = attempts
            return v

    return {"source": None, "error": f"target not found: {target!r}", "attempts": attempts}
