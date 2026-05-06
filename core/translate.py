"""Text translation using macOS Translate.framework via shortcuts CLI.

Pure-Python alternative not available without a network LLM. The cleanest
local path is the macOS `shortcuts` CLI invoking a user-created
'Translate' shortcut, OR Apple's `say` doesn't translate but on-device
Translate framework requires Cocoa code.

Fallback: print a hint to install a Shortcut.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from typing import Optional

SHORTCUT_NAME = "argus-translate"


def translate(text: str, *, target_lang: str = "en") -> dict:
    """If the user has a Shortcut named 'argus-translate' that takes text and
    returns translated text, run it via `shortcuts run`. Otherwise return a
    hint."""
    if not shutil.which("shortcuts"):
        return {"ok": False, "error": "macOS shortcuts CLI not found",
                "hint": "needs macOS 12+"}
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                           delete=False, encoding="utf-8") as f:
            f.write(text)
            in_path = f.name
        out_path = tempfile.NamedTemporaryFile(suffix=".txt", delete=False).name
        r = subprocess.run(
            ["shortcuts", "run", SHORTCUT_NAME, "-i", in_path, "-o", out_path],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return {"ok": False, "error": (r.stderr or "").strip()[:500],
                    "hint": f"Create a Shortcut named '{SHORTCUT_NAME}' that takes text and returns translated text (Translate Text action). Then re-run."}
        try:
            translated = open(out_path, encoding="utf-8").read()
        except Exception:
            translated = ""
        return {"ok": True, "translated": translated.strip()[:5000],
                "via": "shortcuts CLI"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
