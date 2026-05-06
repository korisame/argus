"""Operational safety: log rotation, escape-hatch sandboxing, audit trail."""
from __future__ import annotations

import gzip
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from . import intent as _intent

LOG_MAX_BYTES = int(os.environ.get("ARGUS_LOG_MAX_BYTES", str(50 * 1024 * 1024)))   # 50 MB
LOG_KEEP_ROTATIONS = int(os.environ.get("ARGUS_LOG_KEEP", "5"))


# ─── log rotation ────────────────────────────────────────────────
def rotate_logs() -> dict:
    """If intent.jsonl > LOG_MAX_BYTES, rotate it. Returns summary."""
    p = _intent.LOG_PATH
    if not p.exists():
        return {"rotated": False, "reason": "no log file"}
    try:
        size = p.stat().st_size
    except Exception:
        return {"rotated": False, "reason": "stat failed"}
    if size <= LOG_MAX_BYTES:
        return {"rotated": False, "size": size, "max": LOG_MAX_BYTES}
    ts = time.strftime("%Y%m%d-%H%M%S")
    rotated = p.with_suffix(f".jsonl.{ts}.gz")
    try:
        with open(p, "rb") as src, gzip.open(rotated, "wb") as dst:
            shutil.copyfileobj(src, dst)
        p.write_text("", encoding="utf-8")  # truncate
    except Exception as e:
        return {"rotated": False, "error": str(e)}
    # prune old rotations
    olds = sorted(p.parent.glob("intent.jsonl.*.gz"))
    pruned = []
    while len(olds) > LOG_KEEP_ROTATIONS:
        old = olds.pop(0)
        try: old.unlink(); pruned.append(str(old))
        except Exception: pass
    return {"rotated": True, "size": size, "compressed_to": str(rotated),
            "pruned": pruned}


# ─── escape-hatch sandboxing ─────────────────────────────────────
DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\s+/",
    r"\bsudo\s+rm",
    r"\bdd\s+if=.*of=/dev",
    r":\(\)\s*\{.*:\|\:&.*\}",     # fork bomb
    r">\s*/dev/sd[a-z]",
    r"mkfs\.[a-z]+",
    r"\bdiskutil\s+(eraseDisk|secureErase)",
    r"with\s+administrator\s+privileges",  # AppleScript admin escalation
    r"do\s+shell\s+script.*with\s+admin",
]

DANGEROUS_RE = re.compile("|".join(DANGEROUS_PATTERNS), re.IGNORECASE | re.DOTALL)


def is_dangerous(code: str) -> Optional[str]:
    """Return matched pattern (string) or None."""
    if not code:
        return None
    m = DANGEROUS_RE.search(code)
    return m.group(0) if m else None


def safe_exec_apple_script(code: str, *, timeout: float = 30.0,
                            allow_dangerous: bool = False) -> dict:
    """Run AppleScript with denylist + audit log."""
    danger = is_dangerous(code)
    _intent.log("argus.exec_apple_script.audit",
                outcome="audit",
                observation={"code_preview": code[:200],
                              "code_len": len(code),
                              "dangerous": danger})
    if danger and not allow_dangerous:
        return {"ok": False, "blocked_by_safety": danger,
                "hint": "Pass allow_dangerous=true to override (logged in audit)."}
    try:
        r = subprocess.run(["osascript", "-e", code], capture_output=True,
                           text=True, timeout=timeout)
        return {"ok": r.returncode == 0,
                "stdout": (r.stdout or "").strip()[:5000],
                "stderr": (r.stderr or "").strip()[:2000]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def safe_run_python(code: str, *, timeout: float = 60.0,
                     allow_dangerous: bool = False, ns: Optional[dict] = None) -> dict:
    """Exec arbitrary Python with denylist + audit."""
    danger = is_dangerous(code)
    _intent.log("argus.run.audit", outcome="audit",
                observation={"code_preview": code[:200],
                              "code_len": len(code),
                              "dangerous": danger})
    if danger and not allow_dangerous:
        return {"ok": False, "blocked_by_safety": danger,
                "hint": "Pass allow_dangerous=true to override (logged in audit)."}
    from io import StringIO
    import sys, threading
    buf = StringIO()
    err: list = []
    done = threading.Event()
    namespace = ns or {}

    def runner():
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            exec(compile(code, "<argus_run>", "exec"), namespace, namespace)
        except Exception as e:
            err.append(repr(e))
        finally:
            sys.stdout = old_stdout
            done.set()

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    if not done.wait(timeout=timeout):
        return {"ok": False, "error": f"timeout after {timeout}s",
                "partial_stdout": buf.getvalue()[:5000]}
    return {"ok": not err, "stdout": buf.getvalue()[:10000],
            "error": err[0] if err else None}


# ─── vision batch coalescing ─────────────────────────────────────
import threading as _th
_BATCH_LOCK = _th.Lock()
_BATCH_BUFFER: dict[str, dict] = {}    # screenshot_path → {targets:[], event, results}
_BATCH_WINDOW_S = float(os.environ.get("ARGUS_VISION_BATCH_S", "0.4"))


def _flush_batch(screenshot_path: str, find_fn) -> None:
    """Worker that runs after the batch window, calling find_fn(targets) once."""
    time.sleep(_BATCH_WINDOW_S)
    with _BATCH_LOCK:
        entry = _BATCH_BUFFER.pop(screenshot_path, None)
    if not entry:
        return
    results = {}
    for tgt in entry["targets"]:
        try:
            results[tgt] = find_fn(tgt, screenshot_path)
        except Exception as e:
            results[tgt] = {"error": str(e)}
    entry["results"].update(results)
    entry["event"].set()


def vision_find_batched(target: str, screenshot_path: str, find_fn) -> Optional[dict]:
    """Coalesce concurrent finds on the same screenshot into a single batch."""
    with _BATCH_LOCK:
        entry = _BATCH_BUFFER.get(screenshot_path)
        if not entry:
            entry = {"targets": [], "event": _th.Event(), "results": {}}
            _BATCH_BUFFER[screenshot_path] = entry
            _th.Thread(target=_flush_batch,
                       args=(screenshot_path, find_fn), daemon=True).start()
        entry["targets"].append(target)
    entry["event"].wait(timeout=_BATCH_WINDOW_S * 4)
    return entry["results"].get(target)
