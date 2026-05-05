"""Unified resolver — same code path for browser and native.

Order:
  0. literal "x,y"                       (instant)
  1. learned-cache hit                   (~5ms SQLite)
  2. AX (native + webview)               (~50ms)
  3. CDP DOM (browser)                   (~80ms)
  4. Apple Vision OCR                    (~150ms)
  5. Moondream visual grounding          (~1-3s)

Every successful resolution updates the learned cache so subsequent calls
on the same (scope, target) skip straight to the winning layer.
"""
from __future__ import annotations

import re
import time
from typing import Optional, Callable

from . import intent, vision
from . import router as _router
from adapters import ax, ocr, cdp


COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[,\sx]\s*(-?\d+(?:\.\d+)?)\s*$")


def parse_coords(target: str) -> Optional[tuple[float, float]]:
    m = COORD_RE.match(target)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def _try_cache(scope: str, target: str) -> Optional[dict]:
    hit = intent.cache_lookup(scope, target)
    if not hit:
        return None
    src = hit["source"]
    sel = hit["selector"]

    # Re-validate the cached selector against the live UI
    if src == "ax":
        live = ax.find_by_selector(sel)
        if live:
            live["from_cache"] = True
            return live
    elif src == "ocr":
        # Selector format: OCR[text='...']
        m = re.match(r"OCR\[text=(.+)\]$", sel)
        if m:
            text = m.group(1).strip().strip("'\"")
            shot = "/tmp/argus_prime_shot.png"
            try:
                from adapters import cgevent
                cgevent.screenshot(shot)
                live = ocr.find(text, shot)
                if live:
                    live["from_cache"] = True
                    return live
            except Exception:
                pass
    elif src == "cdp":
        # CDP selector cache lookup is currently a no-op (browser-harness
        # already has its own page_cache). Treat as miss.
        return None
    return None


def resolve(target: str,
            screenshot_path: Optional[str] = None,
            screenshot_callable: Optional[Callable[[], str]] = None,
            min_confidence: float = 0.55,
            allow_vision: bool = True,
            allow_ocr: bool = True,
            allow_ax: bool = True,
            allow_cdp: bool = True,
            allow_cache: bool = True) -> dict:
    """Resolve `target` to coords + metadata.

    Returns a dict with:
      x, y, bbox?, source ('coords'|'cache'|'ax'|'cdp'|'ocr'|'vision'|None),
      confidence, selector?, scope, attempts (ordered), ms, error?
    """
    t0 = time.monotonic()
    attempts: list[str] = []

    # 0) literal coords
    co = parse_coords(target)
    if co:
        return {"x": co[0], "y": co[1], "source": "coords",
                "confidence": 1.0, "scope": "", "attempts": ["coords"],
                "ms": round((time.monotonic() - t0) * 1000, 1)}

    surface = _router.detect()
    scope = surface.get("scope") or ""

    # 1) learned cache
    if allow_cache and scope:
        attempts.append("cache")
        hit = _try_cache(scope, target)
        if hit:
            hit["scope"] = scope
            hit["attempts"] = attempts
            hit["ms"] = round((time.monotonic() - t0) * 1000, 1)
            return hit

    # ensure we have a screenshot for OCR / vision later
    def _shot() -> Optional[str]:
        nonlocal screenshot_path
        if screenshot_path:
            return screenshot_path
        if screenshot_callable:
            try:
                screenshot_path = screenshot_callable()
                return screenshot_path
            except Exception:
                return None
        return None

    is_browser = surface.get("surface") == "browser"

    # 2) AX (native + webview only — Chrome doesn't expose Cocoa text via AX)
    if allow_ax and ax.available() and not is_browser:
        attempts.append("ax")
        hit = ax.find(target)
        if hit and hit["confidence"] >= min_confidence:
            hit["scope"] = scope
            hit["attempts"] = attempts
            hit["ms"] = round((time.monotonic() - t0) * 1000, 1)
            return hit

    # 3) CDP DOM (browser only)
    if allow_cdp and is_browser and cdp.available():
        attempts.append("cdp")
        hit = cdp.find(target)
        if hit and hit.get("confidence", 0) >= min_confidence:
            hit["scope"] = scope
            hit["attempts"] = attempts
            hit["ms"] = round((time.monotonic() - t0) * 1000, 1)
            return hit

    # 4) OCR
    if allow_ocr and ocr.available():
        sp = _shot()
        if sp:
            attempts.append("ocr")
            hit = ocr.find(target, sp)
            if hit and hit["confidence"] >= min_confidence:
                hit["scope"] = scope
                hit["attempts"] = attempts
                hit["ms"] = round((time.monotonic() - t0) * 1000, 1)
                return hit

    # 5) Vision
    if allow_vision:
        sp = _shot()
        attempts.append("vision")
        hit = vision.VISION.find(target, sp)
        if hit:
            hit["scope"] = scope
            hit["attempts"] = attempts
            hit["selector"] = hit.get("selector") or f"VISION[target={target!r}]"
            hit["ms"] = round((time.monotonic() - t0) * 1000, 1)
            return hit

    return {"source": None, "scope": scope,
            "error": f"target not found: {target!r}",
            "attempts": attempts,
            "ms": round((time.monotonic() - t0) * 1000, 1)}


def record_outcome(resolved: dict, *, target: str, ok: bool) -> None:
    """Update the learned cache after the action's verify step."""
    scope = resolved.get("scope")
    src = resolved.get("source")
    sel = resolved.get("selector")
    if not scope or not src or not sel:
        return
    if ok:
        intent.cache_record_success(scope, target,
                                    source=src, selector=sel,
                                    confidence=resolved.get("confidence") or 0.5)
    else:
        intent.cache_record_failure(scope, target)
