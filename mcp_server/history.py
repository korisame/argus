"""Read ~/.argus/intent.jsonl and the in-process metrics ring buffer.

intent.jsonl format (one JSON object per line) is owned by the argus CLI;
this module is read-only over it. We add a separate in-process counter
for the MCP server's own ops (latency, success/fail per tool).
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from threading import Lock

LOG_PATH = Path(os.path.expanduser("~/.argus/intent.jsonl"))

_metrics_lock = Lock()
_latencies: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
_counts: dict[str, dict] = defaultdict(lambda: {"ok": 0, "err": 0})


def record(tool: str, ok: bool, ms: float) -> None:
    with _metrics_lock:
        _latencies[tool].append(ms)
        _counts[tool]["ok" if ok else "err"] += 1


def metrics() -> dict:
    with _metrics_lock:
        out = {}
        for tool, lats in _latencies.items():
            if not lats:
                continue
            arr = sorted(lats)
            n = len(arr)
            p50 = arr[n // 2]
            p95 = arr[min(n - 1, int(n * 0.95))]
            c = _counts[tool]
            total = c["ok"] + c["err"]
            out[tool] = {
                "calls": total,
                "ok": c["ok"],
                "err": c["err"],
                "success_rate": round(c["ok"] / total, 3) if total else None,
                "p50_ms": round(p50, 1),
                "p95_ms": round(p95, 1),
                "avg_ms": round(sum(arr) / len(arr), 1),
            }
        return out


def history(limit: int = 50, tool: str | None = None) -> list[dict]:
    """Tail intent.jsonl (last N), optionally filter by tool/op name."""
    if not LOG_PATH.exists():
        return []
    # Read the tail without loading the whole file
    try:
        size = LOG_PATH.stat().st_size
        chunk = min(size, max(8192, limit * 512))
        with open(LOG_PATH, "rb") as f:
            f.seek(-chunk, os.SEEK_END if size > chunk else os.SEEK_SET)
            data = f.read().decode("utf-8", errors="ignore")
    except Exception:
        data = LOG_PATH.read_text(errors="ignore")
    lines = [l for l in data.splitlines() if l.strip()]
    out = []
    for l in reversed(lines):
        try:
            row = json.loads(l)
        except Exception:
            continue
        if tool and row.get("tool") != tool and row.get("op") != tool:
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return list(reversed(out))


def reset_metrics() -> None:
    with _metrics_lock:
        _latencies.clear()
        _counts.clear()
