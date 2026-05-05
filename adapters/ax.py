"""macOS Accessibility (AXUIElement) walker.

Deterministic ~50ms element lookup for native apps. First layer of the cascade.
Returns center pixel coords + bbox + role + matched text.
"""
from __future__ import annotations

import re
from typing import Optional

try:
    from ApplicationServices import (
        AXUIElementCreateApplication,
        AXUIElementCopyAttributeValue,
        kAXChildrenAttribute,
        kAXTitleAttribute,
        kAXDescriptionAttribute,
        kAXValueAttribute,
        kAXHelpAttribute,
        kAXRoleAttribute,
        kAXSubroleAttribute,
        kAXPositionAttribute,
        kAXSizeAttribute,
        kAXFocusedAttribute,
    )
    from AppKit import NSWorkspace
    HAVE_AX = True
    _AX_ERR = None
except Exception as _e:  # pragma: no cover
    HAVE_AX = False
    _AX_ERR = repr(_e)


TEXT_ATTRS = ("AXTitle", "AXDescription", "AXHelp", "AXValue", "AXPlaceholderValue")
MAX_NODES = 4000
MAX_DEPTH = 40


def available() -> bool:
    return HAVE_AX


def _attr(elem, name):
    try:
        err, val = AXUIElementCopyAttributeValue(elem, name, None)
        return val if err == 0 else None
    except Exception:
        return None


def frontmost_app() -> Optional[dict]:
    if not HAVE_AX:
        return None
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if not app:
        return None
    return {"pid": int(app.processIdentifier()),
            "bundle_id": str(app.bundleIdentifier() or ""),
            "name": str(app.localizedName() or "")}


def _ax_app(pid: int):
    return AXUIElementCreateApplication(pid)


def _bbox_center(elem):
    pos = _attr(elem, kAXPositionAttribute)
    size = _attr(elem, kAXSizeAttribute)
    if not pos or not size:
        return None
    try:
        x, y = pos.x, pos.y
        w, h = size.width, size.height
    except AttributeError:
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
    yield elem
    children = _attr(elem, kAXChildrenAttribute) or []
    for c in children:
        yield from _walk(c, depth + 1, budget)


def find(target: str, pid: int | None = None) -> Optional[dict]:
    """Best AX match for `target`. Score: exact 1.0, substring 0.8, fuzzy 0..0.7."""
    if not HAVE_AX:
        return None
    front = frontmost_app() if pid is None else {"pid": pid}
    if not front or not front.get("pid"):
        return None
    root = _ax_app(front["pid"])

    q = target.strip().lower()
    q_tokens = set(re.findall(r"\w+", q))
    best = None
    best_score = 0.0

    for elem in _walk(root):
        for t in _texts_of(elem):
            tl = t.lower()
            if tl == q:
                score = 1.0
            elif q in tl or tl in q:
                score = 0.8 - min(0.3, abs(len(tl) - len(q)) / max(len(q), 1))
            elif q_tokens:
                t_tokens = set(re.findall(r"\w+", tl))
                if not t_tokens:
                    continue
                ov = len(q_tokens & t_tokens) / len(q_tokens | t_tokens)
                score = 0.7 * ov
            else:
                continue
            if score > best_score:
                ctr = _bbox_center(elem)
                if ctr is None:
                    continue
                role = _attr(elem, kAXRoleAttribute) or ""
                best_score = score
                # selector key (storable in cache):
                # role + matched-text — re-resolvable on next AX walk
                selector = f"AX[role={role};text={t!r}]"
                best = {**ctr, "role": str(role), "text": t,
                        "confidence": round(score, 3),
                        "source": "ax", "selector": selector}
                if score >= 1.0:
                    return best
    return best


def find_by_selector(selector: str, pid: int | None = None) -> Optional[dict]:
    """Replay a cached AX selector. Returns same shape as find() or None."""
    m = re.match(r"AX\[role=(.*?);text=(.+)\]$", selector)
    if not m:
        return None
    target_text = m.group(2).strip().strip("'\"")
    return find(target_text, pid=pid)


def is_secure_field_focused(pid: int | None = None) -> bool:
    if not HAVE_AX:
        return False
    front = frontmost_app() if pid is None else {"pid": pid}
    if not front or not front.get("pid"):
        return False
    root = _ax_app(front["pid"])
    for elem in _walk(root):
        if _attr(elem, kAXFocusedAttribute):
            sub = str(_attr(elem, kAXSubroleAttribute) or "")
            role = str(_attr(elem, kAXRoleAttribute) or "")
            return "Secure" in sub or "Secure" in role
    return False


def doctor() -> dict:
    return {"available": HAVE_AX, "error": _AX_ERR,
            "frontmost": frontmost_app() if HAVE_AX else None}
