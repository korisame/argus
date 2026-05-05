"""macOS Accessibility (AXUIElement) walker.

Deterministic element lookup for native apps. Returns center pixel coords
when a matching element is found, else None — caller falls back to OCR / vision.

Requires Accessibility permission for the host app (System Settings →
Privacy & Security → Accessibility → Claude / Terminal / etc.).
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

try:
    # pyobjc — ships with macOS Python, but not always
    from ApplicationServices import (
        AXUIElementCreateApplication,
        AXUIElementCopyAttributeValue,
        AXUIElementCopyAttributeNames,
        kAXChildrenAttribute,
        kAXTitleAttribute,
        kAXDescriptionAttribute,
        kAXValueAttribute,
        kAXHelpAttribute,
        kAXRoleAttribute,
        kAXSubroleAttribute,
        kAXPositionAttribute,
        kAXSizeAttribute,
        kAXEnabledAttribute,
        kAXFocusedAttribute,
    )
    from AppKit import NSWorkspace
    HAVE_AX = True
except Exception as _e:  # pragma: no cover
    HAVE_AX = False
    _AX_ERR = repr(_e)


TEXT_ATTRS = ("AXTitle", "AXDescription", "AXHelp", "AXValue", "AXPlaceholderValue")
MAX_NODES = 4000          # safety cap per traversal
MAX_DEPTH = 40


def available() -> bool:
    return HAVE_AX


def _attr(elem, name):
    try:
        err, val = AXUIElementCopyAttributeValue(elem, name, None)
        return val if err == 0 else None
    except Exception:
        return None


def _frontmost_pid() -> Optional[int]:
    if not HAVE_AX:
        return None
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return int(app.processIdentifier()) if app else None


def _ax_app(pid: int):
    return AXUIElementCreateApplication(pid)


def _bbox_center(elem):
    pos = _attr(elem, kAXPositionAttribute)
    size = _attr(elem, kAXSizeAttribute)
    if not pos or not size:
        return None
    # AXValue wraps CGPoint/CGSize; pyobjc unwraps them as tuples
    try:
        x, y = pos.x, pos.y
        w, h = size.width, size.height
    except AttributeError:
        # Older pyobjc: AXValueGetValue helpers
        return None
    return {"x": float(x + w / 2), "y": float(y + h / 2),
            "bbox": [float(x), float(y), float(w), float(h)]}


def _texts_of(elem) -> list[str]:
    out = []
    for a in TEXT_ATTRS:
        v = _attr(elem, a)
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out


def _walk(elem, depth=0, budget=None):
    if budget is None:
        budget = [MAX_NODES]
    if budget[0] <= 0 or depth > MAX_DEPTH:
        return
    budget[0] -= 1
    yield elem, depth
    children = _attr(elem, kAXChildrenAttribute) or []
    for c in children:
        yield from _walk(c, depth + 1, budget)


def find(query: str, pid: int | None = None, fuzzy: bool = True) -> Optional[dict]:
    """Find the best AX match for `query` in the frontmost (or given) app.

    Returns {x, y, bbox, role, text, confidence, source: 'ax'} or None.
    Strategy: collect all elements with non-empty text, score by:
      - exact case-insensitive equality        → 1.0
      - substring case-insensitive             → 0.8
      - fuzzy token overlap                    → 0..0.7
    Returns the highest-scoring element (with center coords).
    """
    if not HAVE_AX:
        return None
    pid = pid or _frontmost_pid()
    if not pid:
        return None
    root = _ax_app(pid)

    q = query.strip().lower()
    q_tokens = set(re.findall(r"\w+", q))
    best = None
    best_score = 0.0
    for elem, _depth in _walk(root):
        texts = _texts_of(elem)
        if not texts:
            continue
        for t in texts:
            tl = t.lower()
            if tl == q:
                score = 1.0
            elif q in tl or tl in q:
                score = 0.8 - min(0.3, abs(len(tl) - len(q)) / max(len(q), 1))
            elif fuzzy and q_tokens:
                t_tokens = set(re.findall(r"\w+", tl))
                if not t_tokens:
                    continue
                overlap = len(q_tokens & t_tokens) / len(q_tokens | t_tokens)
                score = 0.7 * overlap
            else:
                continue
            if score > best_score:
                ctr = _bbox_center(elem)
                if ctr is None:
                    continue
                role = _attr(elem, kAXRoleAttribute) or ""
                best_score = score
                best = {**ctr, "role": str(role), "text": t,
                        "confidence": round(score, 3), "source": "ax"}
                if score >= 1.0:
                    return best
    return best


def is_secure_field_focused(pid: int | None = None) -> bool:
    """True if the focused element is an AXSecureTextField (password). For guardrails."""
    if not HAVE_AX:
        return False
    pid = pid or _frontmost_pid()
    if not pid:
        return False
    root = _ax_app(pid)
    # Walk to find focused element
    for elem, _ in _walk(root):
        focused = _attr(elem, kAXFocusedAttribute)
        if focused:
            sub = _attr(elem, kAXSubroleAttribute) or ""
            role = _attr(elem, kAXRoleAttribute) or ""
            return "Secure" in str(sub) or "Secure" in str(role)
    return False


def doctor() -> dict:
    return {
        "ax_available": HAVE_AX,
        "error": _AX_ERR if not HAVE_AX else None,
        "frontmost_pid": _frontmost_pid() if HAVE_AX else None,
    }
