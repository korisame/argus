"""macOS mouse + keyboard via CGEvent — self-contained.

Falls back to argus core when available (richer keysyms), otherwise uses
Quartz CGEvent directly + osascript `keystroke` for unknown keys.

Critical: this module MUST work even when argus core isn't importable —
Cowork bundles the plugin under its own python which doesn't see ~/Developer/argus.
"""
from __future__ import annotations

import subprocess
import time
from typing import Optional

# Optional argus core
try:
    import argus  # type: ignore
    HAVE_ARGUS = True
except Exception:
    HAVE_ARGUS = False

# Quartz CGEvent — primary backend
try:
    import Quartz
    HAVE_QUARTZ = True
    _QERR = None
except Exception as _e:
    HAVE_QUARTZ = False
    _QERR = repr(_e)


# US-layout keycodes
KEYCODES: dict[str, int] = {
    "a":0,"s":1,"d":2,"f":3,"h":4,"g":5,"z":6,"x":7,"c":8,"v":9,
    "b":11,"q":12,"w":13,"e":14,"r":15,"y":16,"t":17,
    "1":18,"2":19,"3":20,"4":21,"6":22,"5":23,"=":24,"9":25,"7":26,
    "-":27,"8":28,"0":29,"]":30,"o":31,"u":32,"[":33,"i":34,"p":35,
    "Return":36,"Enter":36,"l":37,"j":38,"'":39,"k":40,";":41,"\\":42,
    ",":43,"/":44,"n":45,"m":46,".":47,"Tab":48,"Space":49," ":49,
    "`":50,"Backspace":51,"Delete":51,"Escape":53,"Esc":53,
    "F5":96,"F6":97,"F7":98,"F3":99,"F8":100,"F9":101,"F11":103,"F10":109,
    "F12":111,"F2":120,"F1":122,"F4":118,
    "Help":114,"Home":115,"PageUp":116,"End":119,"PageDown":121,
    "Left":123,"ArrowLeft":123,"Right":124,"ArrowRight":124,
    "Down":125,"ArrowDown":125,"Up":126,"ArrowUp":126,
    "+":24,
}

MOD_MASK = {
    "cmd":     1 << 20,
    "command": 1 << 20,
    "shift":   1 << 17,
    "ctrl":    1 << 18,
    "control": 1 << 18,
    "alt":     1 << 19,
    "opt":     1 << 19,
    "option":  1 << 19,
    "fn":      1 << 23,
}


def _parse_modifiers(mods: Optional[str]) -> int:
    if not mods:
        return 0
    flags = 0
    for tok in mods.replace("-", "+").split("+"):
        tok = tok.strip().lower()
        if tok in MOD_MASK:
            flags |= MOD_MASK[tok]
    return flags


def _post_mouse(event_type, x: float, y: float, button=None):
    if button is None:
        button = Quartz.kCGMouseButtonLeft
    ev = Quartz.CGEventCreateMouseEvent(None, event_type,
                                          Quartz.CGPointMake(x, y), button)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


# ─── Public API ────────────────────────────────────────────────
def screenshot(path: str = "/tmp/argus_prime_shot.png") -> str:
    if HAVE_ARGUS:
        try:
            return argus.see(path)
        except Exception:
            pass
    subprocess.run(["screencapture", "-x", path], check=True, timeout=10)
    return path


def click(x: float, y: float, double: bool = False) -> dict:
    if HAVE_ARGUS:
        try:
            r = argus.click("", vision=False, coords=(int(x), int(y)),
                              double=double)
            return {"ok": True, "via": "argus_core", **(r or {})}
        except Exception:
            pass
    if not HAVE_QUARTZ:
        return {"ok": False,
                "error": f"Quartz unavailable: {_QERR}",
                "hint": "uv pip install pyobjc-framework-Quartz into "
                        "the python that runs this MCP server"}
    n = 2 if double else 1
    for _ in range(n):
        _post_mouse(Quartz.kCGEventLeftMouseDown, x, y)
        time.sleep(0.02)
        _post_mouse(Quartz.kCGEventLeftMouseUp, x, y)
    return {"ok": True, "via": "quartz_cgevent",
            "x": x, "y": y, "double": double}


def type_text(text: str) -> dict:
    if HAVE_ARGUS:
        try:
            argus.type_text(text)
            return {"ok": True, "via": "argus_core", "chars": len(text)}
        except Exception:
            pass
    safe = text.replace("\\", "\\\\").replace('"', '\\"')
    try:
        subprocess.run(
            ["osascript", "-e",
             f'tell application "System Events" to keystroke "{safe}"'],
            check=False, timeout=15,
        )
        return {"ok": True, "via": "osascript_keystroke", "chars": len(text)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def key(name: str, modifiers: Optional[str] = None) -> dict:
    if HAVE_ARGUS:
        try:
            argus.key(name, modifiers=modifiers)
            return {"ok": True, "via": "argus_core",
                    "name": name, "modifiers": modifiers}
        except Exception:
            pass
    if HAVE_QUARTZ:
        code = KEYCODES.get(name) or KEYCODES.get(name.lower())
        if code is not None:
            flags = _parse_modifiers(modifiers)
            down = Quartz.CGEventCreateKeyboardEvent(None, code, True)
            up = Quartz.CGEventCreateKeyboardEvent(None, code, False)
            if flags:
                Quartz.CGEventSetFlags(down, flags)
                Quartz.CGEventSetFlags(up, flags)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
            time.sleep(0.02)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
            return {"ok": True, "via": "quartz_cgevent",
                    "name": name, "modifiers": modifiers}
    # osascript fallback
    safe = name.replace('"', '\\"')
    mod_clause = ""
    if modifiers:
        parts = []
        for m in modifiers.replace("-", "+").split("+"):
            m = m.strip().lower()
            if m in ("cmd", "command"): parts.append("command down")
            elif m == "shift": parts.append("shift down")
            elif m in ("ctrl", "control"): parts.append("control down")
            elif m in ("opt", "option", "alt"): parts.append("option down")
        if parts:
            mod_clause = " using {" + ", ".join(parts) + "}"
    try:
        subprocess.run(
            ["osascript", "-e",
             f'tell application "System Events" to keystroke "{safe}"{mod_clause}'],
            check=False, timeout=10,
        )
        return {"ok": True, "via": "osascript_keystroke",
                "name": name, "modifiers": modifiers}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def scroll(direction: str, amount: int = 5,
           coords: Optional[tuple] = None) -> dict:
    if HAVE_ARGUS:
        try:
            argus.scroll(direction, amount=amount, coords=coords)
            return {"ok": True, "via": "argus_core",
                    "direction": direction, "amount": amount}
        except Exception:
            pass
    if not HAVE_QUARTZ:
        return {"ok": False, "error": "Quartz unavailable"}
    dy = -3 if direction == "down" else 3 if direction == "up" else 0
    dx = -3 if direction == "right" else 3 if direction == "left" else 0
    for _ in range(max(1, amount)):
        ev = Quartz.CGEventCreateScrollWheelEvent(
            None, Quartz.kCGScrollEventUnitPixel, 2,
            int(dy * 10), int(dx * 10),
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        time.sleep(0.04)
    return {"ok": True, "via": "quartz_cgevent",
            "direction": direction, "amount": amount}


def open_app(name: str) -> dict:
    if HAVE_ARGUS:
        try:
            argus.open_app(name)
            return {"ok": True, "via": "argus_core", "opened": name}
        except Exception:
            pass
    subprocess.run(["open", "-a", name], check=False, timeout=10)
    return {"ok": True, "via": "open_cmd", "opened": name}


def quit_app(name: str) -> dict:
    script = f'tell application "{name}" to quit'
    if HAVE_ARGUS:
        try:
            argus.exec_apple_script(script)
            return {"ok": True, "via": "argus_core", "quit": name}
        except Exception:
            pass
    subprocess.run(["osascript", "-e", script], check=False, timeout=10)
    return {"ok": True, "via": "osascript", "quit": name}


def exec_apple_script(code: str) -> dict:
    if HAVE_ARGUS:
        try:
            return argus.exec_apple_script(code)
        except Exception:
            pass
    r = subprocess.run(["osascript", "-e", code], capture_output=True,
                       text=True, timeout=30)
    return {"ok": r.returncode == 0,
            "stdout": (r.stdout or "").strip(),
            "stderr": (r.stderr or "").strip()}


def doctor() -> dict:
    return {
        "argus_core_importable": HAVE_ARGUS,
        "argus_module": getattr(argus, "__file__", None) if HAVE_ARGUS else None,
        "quartz_available": HAVE_QUARTZ,
        "quartz_error": _QERR,
        "click_via": ("argus_core" if HAVE_ARGUS else
                       "quartz_cgevent" if HAVE_QUARTZ else
                       "BROKEN"),
    }
