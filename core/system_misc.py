"""Misc system info: open URL, battery, volume, network."""
from __future__ import annotations

import re
import subprocess
from typing import Optional


def url_open(url: str, *, app: Optional[str] = None) -> dict:
    """Open URL in default browser (or specific app)."""
    cmd = ["open"]
    if app: cmd += ["-a", app]
    cmd.append(url)
    try:
        subprocess.run(cmd, check=False, timeout=5)
        return {"ok": True, "url": url, "app": app or "default"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def battery() -> dict:
    """Read battery state via pmset."""
    try:
        r = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=3)
        out = r.stdout
        # Match e.g. "85%; charging; 1:23 remaining"
        m = re.search(r"(\d+)%;\s*([\w\s]+?)(?:;|\n)", out)
        if not m:
            return {"ok": False, "error": "could not parse pmset", "raw": out[:300]}
        percent = int(m.group(1))
        state = m.group(2).strip()
        rem_match = re.search(r"(\d+:\d+)\s*remaining", out)
        remaining = rem_match.group(1) if rem_match else None
        return {"ok": True, "percent": percent, "state": state,
                "remaining": remaining,
                "charging": "charging" in state.lower() or "charged" in state.lower()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def volume_get() -> dict:
    try:
        r = subprocess.run(["osascript", "-e",
                            "set vol to (output volume of (get volume settings))"],
                           capture_output=True, text=True, timeout=3)
        muted_r = subprocess.run(["osascript", "-e",
                                    "output muted of (get volume settings)"],
                                   capture_output=True, text=True, timeout=3)
        return {"ok": True,
                "volume_pct": int(r.stdout.strip()),
                "muted": muted_r.stdout.strip() == "true"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def volume_set(pct: int, *, mute: Optional[bool] = None) -> dict:
    pct = max(0, min(100, int(pct)))
    try:
        subprocess.run(["osascript", "-e",
                        f"set volume output volume {pct}"],
                       capture_output=True, timeout=3)
        if mute is not None:
            subprocess.run(["osascript", "-e",
                            f"set volume {'with' if not mute else 'without'} output muted"],
                           capture_output=True, timeout=3)
        return {"ok": True, "volume_pct": pct, "muted": bool(mute)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def network_info() -> dict:
    """SSID, IP, internet up?"""
    out: dict = {}
    try:
        r = subprocess.run(["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"],
                           capture_output=True, text=True, timeout=3)
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("SSID:"):
                out["ssid"] = line.split(":", 1)[1].strip()
            elif line.startswith("RSSI:"):
                out["rssi_dbm"] = int(line.split(":", 1)[1].strip())
    except Exception:
        pass
    try:
        r = subprocess.run(["ipconfig", "getifaddr", "en0"],
                           capture_output=True, text=True, timeout=3)
        out["ip_en0"] = r.stdout.strip()
    except Exception:
        pass
    return {"ok": True, **out}
