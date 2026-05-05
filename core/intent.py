"""Unified intent log + learned-selector cache.

Single source of truth for all argus-prime activity. Replaces:
  ~/.argus/intent.jsonl     (argus core)
  bh internal log           (browser-harness)
  no log at all             (desktop-commander)

Two stores:
  - intent.jsonl   append-only events (target, surface, source, outcome, ms)
  - cache.db       SQLite of (scope, target_norm) → working_selector + stats
                   updated on every success / invalidated on verified failure

Cache lookup key: (scope, target). Scope is:
  - "native:<bundle_id>"     for AX / OCR / vision on a native app
  - "web:<host>"             for CDP DOM / vision on a browser tab
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import threading
from collections import deque, defaultdict
from pathlib import Path
from typing import Optional

DATA_DIR = Path(os.environ.get("ARGUS_PRIME_HOME") or os.path.expanduser("~/.argus-prime"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = DATA_DIR / "intent.jsonl"
CACHE_PATH = DATA_DIR / "cache.db"

_CACHE_LOCK = threading.RLock()
_LOG_LOCK = threading.RLock()


def _normalise(target: str) -> str:
    return re.sub(r"\s+", " ", target.strip().lower())


# ─── intent log ──────────────────────────────────────────────────────────
def log(intent: str, *, scope: str = "", target: str = "",
        source: Optional[str] = None, outcome: str = "ok",
        ms: float = 0.0, confidence: Optional[float] = None,
        observation: Optional[dict] = None, **extra) -> None:
    """Append one event."""
    row = {
        "ts": time.time(),
        "intent": intent,
        "scope": scope,
        "target": target,
        "source": source,
        "outcome": outcome,
        "ms": round(ms, 1),
        "confidence": confidence,
        "observation": observation,
    }
    if extra:
        row.update(extra)
    with _LOG_LOCK:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")


def history(limit: int = 50, intent: Optional[str] = None,
            scope: Optional[str] = None, outcome: Optional[str] = None) -> list[dict]:
    """Tail intent.jsonl with optional filters (most recent first)."""
    if not LOG_PATH.exists():
        return []
    try:
        size = LOG_PATH.stat().st_size
        chunk = min(size, max(8192, limit * 600))
        with open(LOG_PATH, "rb") as f:
            f.seek(-chunk, os.SEEK_END if size > chunk else os.SEEK_SET)
            data = f.read().decode("utf-8", errors="ignore")
    except Exception:
        data = LOG_PATH.read_text(errors="ignore")
    out = []
    for line in reversed(data.splitlines()):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if intent and row.get("intent") != intent: continue
        if scope and row.get("scope") != scope: continue
        if outcome and row.get("outcome") != outcome: continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


# ─── learned selector cache ─────────────────────────────────────────────
def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(CACHE_PATH, timeout=5)
    c.execute("""
        CREATE TABLE IF NOT EXISTS selectors (
            scope TEXT NOT NULL,
            target_norm TEXT NOT NULL,
            source TEXT NOT NULL,
            selector TEXT NOT NULL,
            confidence REAL,
            successes INTEGER DEFAULT 0,
            failures INTEGER DEFAULT 0,
            last_success REAL,
            last_failure REAL,
            PRIMARY KEY (scope, target_norm)
        )
    """)
    c.commit()
    return c


def cache_lookup(scope: str, target: str) -> Optional[dict]:
    """Return cached selector or None. Skips entries with bad failure/success ratio."""
    if not scope or not target:
        return None
    with _CACHE_LOCK:
        c = _conn()
        try:
            row = c.execute(
                "SELECT source, selector, confidence, successes, failures, last_success "
                "FROM selectors WHERE scope=? AND target_norm=?",
                (scope, _normalise(target)),
            ).fetchone()
        finally:
            c.close()
    if not row:
        return None
    source, selector, confidence, succ, fail, last_succ = row
    if succ + fail >= 3 and succ / max(succ + fail, 1) < 0.4:
        return None  # poisoned entry, force re-cascade
    return {"source": source, "selector": selector, "confidence": confidence,
            "successes": succ, "failures": fail, "last_success": last_succ,
            "from_cache": True}


def cache_record_success(scope: str, target: str, *, source: str,
                          selector: str, confidence: float = 1.0) -> None:
    if not scope or not target:
        return
    norm = _normalise(target)
    now = time.time()
    with _CACHE_LOCK:
        c = _conn()
        try:
            c.execute("""
                INSERT INTO selectors (scope, target_norm, source, selector, confidence,
                                        successes, failures, last_success)
                VALUES (?, ?, ?, ?, ?, 1, 0, ?)
                ON CONFLICT(scope, target_norm) DO UPDATE SET
                    source=excluded.source,
                    selector=excluded.selector,
                    confidence = (selectors.confidence * selectors.successes + excluded.confidence) /
                                 (selectors.successes + 1),
                    successes = selectors.successes + 1,
                    last_success = excluded.last_success
            """, (scope, norm, source, selector, float(confidence), now))
            c.commit()
        finally:
            c.close()


def cache_record_failure(scope: str, target: str) -> None:
    if not scope or not target:
        return
    with _CACHE_LOCK:
        c = _conn()
        try:
            c.execute("""
                UPDATE selectors
                SET failures = failures + 1, last_failure = ?
                WHERE scope = ? AND target_norm = ?
            """, (time.time(), scope, _normalise(target)))
            c.commit()
        finally:
            c.close()


def cache_view(scope: Optional[str] = None, limit: int = 100) -> list[dict]:
    with _CACHE_LOCK:
        c = _conn()
        try:
            if scope:
                rows = c.execute(
                    "SELECT scope, target_norm, source, selector, confidence, "
                    "successes, failures, last_success FROM selectors "
                    "WHERE scope=? ORDER BY last_success DESC LIMIT ?",
                    (scope, limit)).fetchall()
            else:
                rows = c.execute(
                    "SELECT scope, target_norm, source, selector, confidence, "
                    "successes, failures, last_success FROM selectors "
                    "ORDER BY last_success DESC LIMIT ?",
                    (limit,)).fetchall()
        finally:
            c.close()
    keys = ["scope", "target_norm", "source", "selector", "confidence",
            "successes", "failures", "last_success"]
    return [dict(zip(keys, r)) for r in rows]


# ─── in-process metrics (per process lifetime) ──────────────────────────
_METRICS_LOCK = threading.Lock()
_LATENCIES: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
_COUNTS: dict[str, dict] = defaultdict(lambda: {"ok": 0, "err": 0})


def metrics_record(tool: str, ok: bool, ms: float) -> None:
    with _METRICS_LOCK:
        _LATENCIES[tool].append(ms)
        _COUNTS[tool]["ok" if ok else "err"] += 1


def metrics(reset: bool = False) -> dict:
    with _METRICS_LOCK:
        out = {}
        for tool, lats in _LATENCIES.items():
            if not lats: continue
            arr = sorted(lats)
            n = len(arr)
            c = _COUNTS[tool]
            tot = c["ok"] + c["err"]
            out[tool] = {
                "calls": tot, "ok": c["ok"], "err": c["err"],
                "success_rate": round(c["ok"] / tot, 3) if tot else None,
                "p50_ms": round(arr[n // 2], 1),
                "p95_ms": round(arr[min(n - 1, int(n * 0.95))], 1),
                "avg_ms": round(sum(arr) / n, 1),
            }
        if reset:
            _LATENCIES.clear()
            _COUNTS.clear()
        return out
