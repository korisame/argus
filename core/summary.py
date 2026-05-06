"""argus_summary — one-line snapshot of where you are + what's recent.

Combines: surface, last 3 ok intents, top-N most-used tools, vision mode,
cache size. Returns text + structured.
"""
from __future__ import annotations

from . import intent, router, vision


def summary() -> dict:
    surf = router.detect()
    recent = intent.history(limit=5, outcome="ok")
    metrics = intent.metrics()
    cache = intent.cache_view(limit=999)
    vmode = vision.VISION.status().get("mode")

    top_tools = sorted(metrics.items(), key=lambda kv: -kv[1].get("calls", 0))[:3]
    top_str = ", ".join(f"{t}({m['calls']})" for t, m in top_tools)

    line = (
        f"surface={surf.get('surface')} "
        f"app={surf.get('app',{}).get('name')} "
        f"vision={vmode} "
        f"cache={len(cache)} "
        f"top={top_str or '∅'}"
    )
    return {
        "line": line,
        "surface": surf,
        "vision_mode": vmode,
        "cache_entries": len(cache),
        "top_tools": [{"name": t, "calls": m.get("calls"),
                        "p50_ms": m.get("p50_ms")} for t, m in top_tools],
        "recent_ok": [{"intent": r.get("intent"), "target": r.get("target"),
                        "ms": r.get("ms")} for r in recent],
    }
