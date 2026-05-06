"""Linux mouse + keyboard via xdotool / wtype (Wayland).

Minimal stub. Wayland support requires wtype + wlr-randr; X11 has full xdotool.
"""
from __future__ import annotations

import shutil
import subprocess


def available() -> bool:
    return any(shutil.which(c) for c in ("xdotool", "wtype", "ydotool"))


def click(x: float, y: float, double: bool = False) -> dict:
    if shutil.which("xdotool"):
        cmd = ["xdotool", "mousemove", str(int(x)), str(int(y)),
               "click", "1"]
        if double:
            cmd += ["click", "1"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return {"ok": r.returncode == 0, "via": "xdotool"}
    if shutil.which("ydotool"):
        # ydotool needs daemon
        subprocess.run(["ydotool", "mousemove", str(int(x)), str(int(y))],
                       capture_output=True, timeout=5)
        r = subprocess.run(["ydotool", "click", "0xC0" if not double else "0xC0", "0xC0"],
                           capture_output=True, text=True, timeout=10)
        return {"ok": r.returncode == 0, "via": "ydotool"}
    return {"ok": False, "error": "no input backend (install xdotool or ydotool)"}


def type_text(text: str) -> dict:
    if shutil.which("xdotool"):
        r = subprocess.run(["xdotool", "type", "--", text],
                           capture_output=True, text=True, timeout=15)
        return {"ok": r.returncode == 0, "via": "xdotool"}
    if shutil.which("wtype"):
        r = subprocess.run(["wtype", text], capture_output=True, text=True, timeout=15)
        return {"ok": r.returncode == 0, "via": "wtype"}
    return {"ok": False, "error": "no input backend"}


def key(name: str, modifiers: str = "") -> dict:
    combo = f"{modifiers}+{name}".strip("+") if modifiers else name
    if shutil.which("xdotool"):
        r = subprocess.run(["xdotool", "key", "--", combo],
                           capture_output=True, text=True, timeout=5)
        return {"ok": r.returncode == 0, "via": "xdotool"}
    return {"ok": False, "error": "xdotool required for key events on Linux"}


def doctor() -> dict:
    return {"platform": "linux",
            "xdotool": shutil.which("xdotool"),
            "wtype":   shutil.which("wtype"),
            "ydotool": shutil.which("ydotool"),
            "note":    "Linux input backend is a stub. PRs welcome (issue #5)."}
