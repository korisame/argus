"""macOS native notifications + sound."""
from __future__ import annotations

import subprocess


def notify(title: str, message: str = "", *, subtitle: str = "",
           sound: str | None = None) -> dict:
    safe = lambda s: s.replace('"', '\\"')
    parts = [f'display notification "{safe(message)}" with title "{safe(title)}"']
    if subtitle:
        parts.append(f'subtitle "{safe(subtitle)}"')
    if sound:
        parts.append(f'sound name "{safe(sound)}"')
    script = " ".join(parts)
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=5)
        return {"ok": r.returncode == 0,
                "title": title, "message": message,
                "stderr": r.stderr.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def beep(times: int = 1) -> dict:
    try:
        subprocess.run(["osascript", "-e", f"beep {times}"],
                       capture_output=True, timeout=3)
        return {"ok": True, "times": times}
    except Exception as e:
        return {"ok": False, "error": str(e)}
