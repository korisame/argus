"""Manage the dedicated automation Chrome (delegates to browser-harness CLI)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _bh() -> str:
    p = shutil.which("browser-harness")
    if not p:
        raise RuntimeError("browser-harness CLI not on PATH")
    return p


def _bh_env_file() -> Path:
    """browser-harness reads ~/.browser-harness-pro/.env via _load_env() for HEADLESS toggle."""
    return Path(os.path.expanduser("~/.browser-harness-pro/.env"))


def status() -> dict:
    try:
        r = subprocess.run([_bh(), "--doctor"], capture_output=True, text=True, timeout=8)
        return {"ok": r.returncode == 0,
                "stdout": (r.stdout or "").strip()[:1000],
                "stderr": (r.stderr or "").strip()[:500]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def boot(headless: bool = False, *, allow_all_origins: bool = True) -> dict:
    """Boot dedicated automation Chrome.

    Chrome 130+ requires --remote-allow-origins=* to accept WS connections
    from CDP clients (anti-CSRF). Pass allow_all_origins=False ONLY if you
    know what you're doing.
    """
    env_file = _bh_env_file()
    env_file.parent.mkdir(parents=True, exist_ok=True)
    cur = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    cur_lines = [l for l in cur.splitlines()
                 if not l.startswith("BH_AUTOMATION_HEADLESS=")
                 and not l.startswith("BH_AUTOMATION_FLAGS=")]
    cur_lines.append(f"BH_AUTOMATION_HEADLESS={'1' if headless else '0'}")
    if allow_all_origins:
        cur_lines.append("BH_AUTOMATION_FLAGS=--remote-allow-origins=*")
    env_file.write_text("\n".join(cur_lines) + "\n", encoding="utf-8")
    try:
        r = subprocess.run([_bh(), "--boot-chrome"], capture_output=True, text=True, timeout=20)
        return {"ok": r.returncode == 0, "headless": headless,
                "allow_all_origins": allow_all_origins,
                "stdout": (r.stdout or "").strip()[:500],
                "stderr": (r.stderr or "").strip()[:500]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def kill() -> dict:
    try:
        r = subprocess.run([_bh(), "--kill-chrome"], capture_output=True, text=True, timeout=10)
        return {"ok": r.returncode == 0, "stdout": (r.stdout or "").strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def install_agent() -> dict:
    try:
        r = subprocess.run([_bh(), "--install-agent"], capture_output=True, text=True, timeout=10)
        return {"ok": r.returncode == 0, "stdout": (r.stdout or "").strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}
