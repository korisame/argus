"""Linux screenshot adapter — best-effort stub.

Tries grim (Wayland), then scrot (X11), then ImageMagick `import`.
Window-only capture not yet implemented (need wmctrl + tool-specific args).
PRs welcome — see issue #5.
"""
from __future__ import annotations

import os
import shutil
import subprocess


def available() -> bool:
    return os.name == "posix" and shutil.which(any_of=("grim", "scrot", "import")) if False else (
        shutil.which("grim") or shutil.which("scrot") or shutil.which("import")) is not None


def screenshot(out_path: str = "/tmp/argus_linux.png") -> str:
    if shutil.which("grim"):
        subprocess.run(["grim", out_path], check=True, timeout=10)
    elif shutil.which("scrot"):
        subprocess.run(["scrot", "-z", out_path], check=True, timeout=10)
    elif shutil.which("import"):
        subprocess.run(["import", "-window", "root", out_path], check=True, timeout=10)
    else:
        raise RuntimeError("no screenshot backend (install grim or scrot)")
    return out_path


def doctor() -> dict:
    return {
        "platform": "linux",
        "grim":   shutil.which("grim"),
        "scrot":  shutil.which("scrot"),
        "import": shutil.which("import"),
        "note":   "Linux backend is a stub. window_screenshot not yet implemented. See issue #5.",
    }
