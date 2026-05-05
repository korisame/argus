"""argus_setup wizard — orchestrates a clean install.

Each step returns {ok, name, detail, action_required?, fix_cmd?}. The MCP
tool surfaces a list of these so the agent can prompt the user for the
items that need human attention (e.g. Moondream API key, TCC permissions).
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Optional


def _step_python() -> dict:
    py = shutil.which("python3") or sys.executable
    v = sys.version_info
    return {"ok": (v.major, v.minor) >= (3, 10),
            "name": "python", "detail": f"{py} {v.major}.{v.minor}.{v.micro}",
            "fix_cmd": "brew install python@3.12" if (v.major, v.minor) < (3, 10) else None}


def _step_uv() -> dict:
    p = shutil.which("uv")
    return {"ok": p is not None, "name": "uv",
            "detail": p or "missing",
            "fix_cmd": "brew install uv" if not p else None}


def _step_argus_cli() -> dict:
    p = shutil.which("argus")
    return {"ok": p is not None, "name": "argus_cli", "detail": p or "missing",
            "fix_cmd": "uv tool install argus-skill" if not p else None}


def _step_pyobjc() -> dict:
    """Check the python that runs the MCP server has pyobjc."""
    try:
        __import__("ApplicationServices")
        __import__("Vision")
        __import__("Quartz")
        return {"ok": True, "name": "pyobjc", "detail": "Vision + AX + Quartz importable"}
    except Exception as e:
        py = sys.executable
        return {"ok": False, "name": "pyobjc",
                "detail": f"missing in {py}: {e}",
                "fix_cmd": f'uv pip install --python "{py}" '
                            f'pyobjc-framework-Vision pyobjc-framework-ApplicationServices '
                            f'pyobjc-framework-Quartz'}


def _step_websocket() -> dict:
    try:
        __import__("websocket")
        return {"ok": True, "name": "websocket-client", "detail": "importable"}
    except Exception as e:
        py = sys.executable
        return {"ok": False, "name": "websocket-client",
                "detail": f"missing: {e}",
                "fix_cmd": f'uv pip install --python "{py}" websocket-client'}


def _step_browser_harness() -> dict:
    p = shutil.which("browser-harness")
    return {"ok": p is not None, "name": "browser-harness",
            "detail": p or "optional — only needed for legacy CDP fallback",
            "fix_cmd": "uv tool install -e ~/Developer/browser-harness-pro" if not p else None}


def _step_automation_chrome() -> dict:
    """Check that the dedicated automation Chrome is up."""
    try:
        with socket.create_connection(("127.0.0.1", 9333), timeout=1):
            return {"ok": True, "name": "automation_chrome",
                    "detail": "127.0.0.1:9333 listening"}
    except Exception:
        return {"ok": False, "name": "automation_chrome",
                "detail": "127.0.0.1:9333 not listening",
                "fix_cmd": "browser-harness --boot-chrome && browser-harness --install-agent"}


def _step_moondream_key() -> dict:
    if os.environ.get("MOONDREAM_API_KEY"):
        return {"ok": True, "name": "moondream_key",
                "detail": "MOONDREAM_API_KEY set in env"}
    env_file = Path(os.path.expanduser("~/.argus/.env"))
    if env_file.exists() and "MOONDREAM_API_KEY" in env_file.read_text(errors="ignore"):
        return {"ok": True, "name": "moondream_key",
                "detail": f"present in {env_file}"}
    return {"ok": False, "name": "moondream_key",
            "detail": "Get a key at https://moondream.ai/c/cloud, then "
                      "echo 'MOONDREAM_API_KEY=mk_...' >> ~/.argus/.env",
            "action_required": "user_input",
            "fix_cmd": "mkdir -p ~/.argus && nano ~/.argus/.env"}


def _step_policy_file() -> dict:
    p = Path(os.path.expanduser("~/.argus/policy.yaml"))
    if p.exists():
        return {"ok": True, "name": "policy_file", "detail": str(p)}
    return {"ok": False, "name": "policy_file",
            "detail": "missing — call argus_policy action='write_default'",
            "fix_cmd": "argus_policy action='write_default'"}


def _step_tcc_screen_recording() -> dict:
    """Best-effort: try a screencapture, see if it produced a non-empty file."""
    try:
        out = "/tmp/argus_setup_tcc.png"
        r = subprocess.run(["screencapture", "-x", out],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1024:
            return {"ok": True, "name": "tcc_screen_recording",
                    "detail": "screencapture works"}
        return {"ok": False, "name": "tcc_screen_recording",
                "detail": "screencapture produced empty file — Screen Recording denied",
                "fix_cmd": "open 'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture'"}
    except Exception as e:
        return {"ok": False, "name": "tcc_screen_recording",
                "detail": f"screencapture failed: {e}",
                "fix_cmd": "open 'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture'"}


def run() -> dict:
    """Run all checks. Returns {ok, steps:[...], next_actions:[...]}."""
    steps = [
        _step_python(),
        _step_uv(),
        _step_argus_cli(),
        _step_pyobjc(),
        _step_websocket(),
        _step_browser_harness(),
        _step_automation_chrome(),
        _step_moondream_key(),
        _step_policy_file(),
        _step_tcc_screen_recording(),
    ]
    failing = [s for s in steps if not s["ok"]]
    next_actions = [
        {"step": s["name"], "fix_cmd": s.get("fix_cmd"),
         "action_required": s.get("action_required", "shell")}
        for s in failing
    ]
    return {
        "ok": all(s["ok"] for s in steps),
        "steps": steps,
        "passing": [s["name"] for s in steps if s["ok"]],
        "failing": [s["name"] for s in failing],
        "next_actions": next_actions,
    }
