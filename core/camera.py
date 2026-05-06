"""Webcam single-frame capture via imagesnap (brew install imagesnap)
or ffmpeg AVFoundation."""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional


def capture(out_path: str = "/tmp/argus_camera.jpg",
            *, warmup_s: float = 0.5,
            device: Optional[str] = None) -> dict:
    if shutil.which("imagesnap"):
        cmd = ["imagesnap", "-w", str(warmup_s)]
        if device: cmd += ["-d", device]
        cmd += [out_path]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and os.path.exists(out_path):
                return {"ok": True, "via": "imagesnap", "path": out_path,
                        "size": os.path.getsize(out_path)}
            return {"ok": False, "error": r.stderr.strip() or "imagesnap failed"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    if shutil.which("ffmpeg"):
        cmd = ["ffmpeg", "-y", "-f", "avfoundation",
               "-framerate", "30", "-i", device or "default",
               "-frames:v", "1", out_path]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and os.path.exists(out_path):
                return {"ok": True, "via": "ffmpeg", "path": out_path,
                        "size": os.path.getsize(out_path)}
            return {"ok": False, "error": (r.stderr or "")[-500:]}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "install imagesnap (brew install imagesnap) or ffmpeg"}


def list_devices() -> dict:
    if shutil.which("imagesnap"):
        try:
            r = subprocess.run(["imagesnap", "-l"], capture_output=True, text=True, timeout=5)
            devs = [l.strip("=> ").strip() for l in r.stdout.splitlines() if l.strip().startswith("=>")]
            return {"ok": True, "via": "imagesnap", "devices": devs}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "install imagesnap"}
