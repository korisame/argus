"""Predict the next likely action for the current scope.

Uses two signals:
  1. patterns matching the current scope — list their first-step
  2. recent intent history (last 20 events) for this scope — most-frequent op

Returns a ranked list. Cheap heuristic, not ML.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from . import patterns as _patterns
from . import intent as _intent
from . import router as _router


def predict(scope: Optional[str] = None, top_n: int = 5) -> dict:
    if not scope:
        scope = _router.detect().get("scope") or ""
    suggestions = []

    # 1. Patterns whose intent matches this scope
    pats = _patterns.list_patterns(scope=scope, limit=20)
    for p in pats:
        first_op = (p["step_ops"][0] if p["step_ops"] else None)
        score = (p.get("successes") or 0) / max((p.get("successes") or 0) + (p.get("failures") or 0), 1)
        suggestions.append({
            "kind": "pattern",
            "intent": p["intent"], "first_op": first_op,
            "version": p["version"], "score": round(score, 3),
            "successes": p["successes"], "failures": p["failures"],
            "hint": f"argus_replay scope={scope!r} intent_label={p['intent']!r}",
        })

    # 2. Recent ops on this scope
    recent = _intent.history(limit=200, scope=scope, outcome="ok")
    op_freq = Counter()
    target_freq = Counter()
    for r in recent:
        intent_str = (r.get("intent") or "")
        if intent_str.startswith("argus."):
            op_freq[intent_str[len("argus."):]] += 1
        if r.get("target"):
            target_freq[r["target"]] += 1
    for op, c in op_freq.most_common(top_n):
        suggestions.append({"kind": "recent_op", "op": op, "count": c})
    for tgt, c in target_freq.most_common(top_n):
        suggestions.append({"kind": "recent_target", "target": tgt, "count": c})

    # Sort: patterns first (higher info), then recent ops
    suggestions.sort(key=lambda s: (s["kind"] != "pattern",
                                      -(s.get("score", 0) or s.get("count", 0))))
    return {"scope": scope, "suggestions": suggestions[:top_n]}
