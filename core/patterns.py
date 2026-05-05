"""Task-pattern memory.

Higher-order than the selector cache: stores entire **sequences** of actions
keyed by `(scope, intent)`. When a recorded pattern exists for an intent,
argus can replay it step-by-step with verify, falling back to ad-hoc
cascade resolution only when a step diverges.

Storage: ~/.argus-prime/patterns.db (SQLite)
  patterns(scope, intent_norm, version, steps_json, successes, failures,
           last_success, last_failure)

Step shape:
  {"op": "click|type|paste|key|send_keys|wait_for|scroll|navigate",
   "args": {...},
   "expect_verify": "ok"|"any"}
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from typing import Optional

from . import intent as _intent

DB_PATH = _intent.DATA_DIR / "patterns.db"
_LOCK = threading.RLock()


def _normalise(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=5)
    c.execute("""
        CREATE TABLE IF NOT EXISTS patterns (
            scope TEXT NOT NULL,
            intent_norm TEXT NOT NULL,
            version INTEGER DEFAULT 1,
            steps_json TEXT NOT NULL,
            successes INTEGER DEFAULT 0,
            failures INTEGER DEFAULT 0,
            last_success REAL,
            last_failure REAL,
            PRIMARY KEY (scope, intent_norm)
        )
    """)
    c.commit()
    return c


# ─── recording ──────────────────────────────────────────────────
_RECORDING: dict[str, dict] = {}   # name → {scope, intent, steps:[], started}


def record_begin(name: str, scope: str, intent_label: str) -> dict:
    """Start a named recording. All argus actions while active will be
    appended to the buffer. Call record_end(name, ok) to commit/discard."""
    with _LOCK:
        if name in _RECORDING:
            return {"ok": False, "error": f"recording {name!r} already active"}
        _RECORDING[name] = {
            "scope": scope,
            "intent": intent_label,
            "steps": [],
            "started": time.time(),
        }
    return {"ok": True, "name": name, "scope": scope, "intent": intent_label}


def record_step(op: str, args: dict, *, expect_verify: str = "ok") -> int:
    """Append a step to ALL active recordings. Returns count of recordings updated."""
    n = 0
    with _LOCK:
        for rec in _RECORDING.values():
            rec["steps"].append({"op": op, "args": args,
                                 "expect_verify": expect_verify})
            n += 1
    return n


def record_end(name: str, *, ok: bool = True, save: bool = True) -> dict:
    """Stop a recording. If save and ok, persist to patterns.db."""
    with _LOCK:
        rec = _RECORDING.pop(name, None)
    if rec is None:
        return {"ok": False, "error": f"no active recording {name!r}"}
    duration = round(time.time() - rec["started"], 2)
    if not save or not ok:
        return {"ok": True, "saved": False, "steps": len(rec["steps"]),
                "duration_s": duration}
    return save_pattern(rec["scope"], rec["intent"], rec["steps"])


# ─── persistence ────────────────────────────────────────────────
def save_pattern(scope: str, intent_label: str, steps: list[dict]) -> dict:
    norm = _normalise(intent_label)
    sj = json.dumps(steps)
    with _LOCK:
        c = _conn()
        try:
            c.execute("""
                INSERT INTO patterns (scope, intent_norm, steps_json,
                                      successes, last_success)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(scope, intent_norm) DO UPDATE SET
                    steps_json = excluded.steps_json,
                    version    = patterns.version + 1,
                    successes  = patterns.successes + 1,
                    last_success = excluded.last_success
            """, (scope, norm, sj, time.time()))
            c.commit()
        finally:
            c.close()
    return {"ok": True, "saved": True, "scope": scope,
            "intent": intent_label, "steps": len(steps)}


def lookup(scope: str, intent_label: str) -> Optional[dict]:
    if not scope or not intent_label:
        return None
    norm = _normalise(intent_label)
    with _LOCK:
        c = _conn()
        try:
            row = c.execute(
                "SELECT version, steps_json, successes, failures, last_success "
                "FROM patterns WHERE scope=? AND intent_norm=?",
                (scope, norm),
            ).fetchone()
        finally:
            c.close()
    if not row:
        return None
    version, sj, succ, fail, last = row
    if succ + fail >= 3 and succ / max(succ + fail, 1) < 0.4:
        return None
    return {"scope": scope, "intent": intent_label, "version": version,
            "steps": json.loads(sj),
            "successes": succ, "failures": fail, "last_success": last}


def record_outcome(scope: str, intent_label: str, *, ok: bool) -> None:
    norm = _normalise(intent_label)
    with _LOCK:
        c = _conn()
        try:
            if ok:
                c.execute("UPDATE patterns SET successes=successes+1, "
                          "last_success=? WHERE scope=? AND intent_norm=?",
                          (time.time(), scope, norm))
            else:
                c.execute("UPDATE patterns SET failures=failures+1, "
                          "last_failure=? WHERE scope=? AND intent_norm=?",
                          (time.time(), scope, norm))
            c.commit()
        finally:
            c.close()


def list_patterns(scope: Optional[str] = None, limit: int = 100) -> list[dict]:
    with _LOCK:
        c = _conn()
        try:
            if scope:
                rows = c.execute(
                    "SELECT scope, intent_norm, version, steps_json, successes, failures, "
                    "last_success FROM patterns WHERE scope=? "
                    "ORDER BY last_success DESC LIMIT ?",
                    (scope, limit)).fetchall()
            else:
                rows = c.execute(
                    "SELECT scope, intent_norm, version, steps_json, successes, failures, "
                    "last_success FROM patterns "
                    "ORDER BY last_success DESC LIMIT ?", (limit,)).fetchall()
        finally:
            c.close()
    out = []
    for r in rows:
        steps = json.loads(r[3])
        out.append({"scope": r[0], "intent": r[1], "version": r[2],
                    "step_count": len(steps), "step_ops": [s.get("op") for s in steps],
                    "successes": r[4], "failures": r[5], "last_success": r[6]})
    return out


def delete_pattern(scope: str, intent_label: str) -> dict:
    norm = _normalise(intent_label)
    with _LOCK:
        c = _conn()
        try:
            c.execute("DELETE FROM patterns WHERE scope=? AND intent_norm=?",
                      (scope, norm))
            n = c.total_changes
            c.commit()
        finally:
            c.close()
    return {"ok": True, "deleted": n}
