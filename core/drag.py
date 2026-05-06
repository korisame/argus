"""Drag-and-drop primitive via CGEvent.

CGEvent path: mouse-down at start → series of move events → mouse-up at end.
Optional duration (seconds) for human-like timing.
"""
from __future__ import annotations

import time
from typing import Optional

try:
    import Quartz
    HAVE_QUARTZ = True
except Exception as _e:
    HAVE_QUARTZ = False
    _ERR = repr(_e)


def drag(x1: float, y1: float, x2: float, y2: float, *,
         duration: float = 0.4, steps: int = 20,
         button: str = "left") -> dict:
    if not HAVE_QUARTZ:
        return {"ok": False, "error": _ERR or "Quartz unavailable"}
    btn_map = {
        "left":   (Quartz.kCGEventLeftMouseDown,  Quartz.kCGEventLeftMouseDragged,  Quartz.kCGEventLeftMouseUp,  Quartz.kCGMouseButtonLeft),
        "right":  (Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseDragged, Quartz.kCGEventRightMouseUp, Quartz.kCGMouseButtonRight),
    }
    if button not in btn_map:
        return {"ok": False, "error": f"unknown button: {button}"}
    down, dragged, up, b = btn_map[button]

    def _post(event_type, x, y):
        ev = Quartz.CGEventCreateMouseEvent(None, event_type,
                                              Quartz.CGPointMake(x, y), b)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)

    _post(down, x1, y1)
    if steps < 1: steps = 1
    dt = duration / steps
    for i in range(1, steps + 1):
        t = i / steps
        x = x1 + (x2 - x1) * t
        y = y1 + (y2 - y1) * t
        _post(dragged, x, y)
        time.sleep(dt)
    _post(up, x2, y2)
    return {"ok": True, "from": [x1, y1], "to": [x2, y2],
            "duration": duration, "steps": steps, "button": button}
