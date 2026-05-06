"""argus_benchmark — measured perf report.

Runs a fixed suite of operations N times each, measures wall-clock time,
returns p50/p95/avg + variance. No side effects on the live UI: every op
is read-only or against test fixtures.
"""
from __future__ import annotations

import statistics
import tempfile
import time
from typing import Callable

from . import vision as _vision
from . import screen as _screen
from . import router as _router
from . import intent as _intent
from adapters import ax as _ax
from adapters import ocr as _ocr
from adapters import cdp_raw as _cdp_raw


def _time(fn: Callable[[], object]) -> float:
    t0 = time.monotonic()
    try:
        fn()
    except Exception:
        pass
    return (time.monotonic() - t0) * 1000


def _stats(samples: list[float]) -> dict:
    if not samples:
        return {"n": 0}
    samples_sorted = sorted(samples)
    n = len(samples_sorted)
    return {
        "n": n,
        "p50_ms": round(samples_sorted[n // 2], 2),
        "p95_ms": round(samples_sorted[min(n - 1, int(n * 0.95))], 2),
        "avg_ms": round(sum(samples) / n, 2),
        "min_ms": round(min(samples), 2),
        "max_ms": round(max(samples), 2),
        "stdev_ms": round(statistics.stdev(samples) if n > 1 else 0.0, 2),
    }


def run(iterations: int = 10) -> dict:
    """Returns {ops: {op_name: stats}, env: {...}}."""
    out: dict = {"iterations": iterations, "ops": {}, "env": {}}

    # Baseline screenshot for OCR/vision reuse
    try:
        cap = _screen.capture_frontmost(out_path="/tmp/argus_bench_shot.png")
        bench_shot = cap.get("path") if cap.get("ok") else None
    except Exception:
        bench_shot = None

    # 1. surface detection (~1ms)
    out["ops"]["router.detect"] = _stats([_time(_router.detect) for _ in range(iterations)])

    # 2. screen.list_windows (~5-15ms, depends on # windows)
    if _screen.available():
        out["ops"]["screen.list_windows"] = _stats(
            [_time(_screen.list_windows) for _ in range(iterations)])

    # 3. AX walker — find a benign target
    if _ax.available():
        out["ops"]["ax.find('File')"] = _stats(
            [_time(lambda: _ax.find("File")) for _ in range(iterations)])

    # 4. OCR full screen
    if _ocr.available() and bench_shot:
        out["ops"]["ocr.all_text(fast)"] = _stats(
            [_time(lambda: _ocr.all_text(bench_shot, fast=True)) for _ in range(iterations)])

    # 5. CDP raw page_info
    if _cdp_raw.available():
        out["ops"]["cdp_raw.page_info"] = _stats(
            [_time(_cdp_raw.page_info) for _ in range(iterations)])

    # 6. cache lookup (no hit, baseline)
    out["ops"]["intent.cache_lookup(miss)"] = _stats(
        [_time(lambda: _intent.cache_lookup("native:bench", "nonexistent"))
         for _ in range(iterations)])

    # 7. screenshot (full screen)
    out["ops"]["screencapture"] = _stats(
        [_time(lambda: _screen.capture_frontmost(out_path="/tmp/argus_bench_iter.png"))
         for _ in range(min(iterations, 5))])  # capped to 5 (slow op)

    # 8. vision singleton status (cheap)
    out["ops"]["vision.status"] = _stats(
        [_time(_vision.VISION.status) for _ in range(iterations)])

    out["env"] = {
        "ax": _ax.available(), "ocr": _ocr.available(),
        "cdp_raw": _cdp_raw.available(), "screen": _screen.available(),
        "vision_mode": _vision.VISION.status().get("mode"),
        "surface": _router.detect().get("surface"),
    }
    return out
