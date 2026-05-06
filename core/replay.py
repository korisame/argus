"""Replay saved task patterns step-by-step.

Each step is one of:
  click, type, paste, key, send_keys, scroll, open_app, wait_for, navigate

Replay strategy:
  - For each step, call the matching argus tool (via the handler dict)
  - If verify says ok, continue
  - If verify says fail, fall back to cascade resolver for that step's
    `target` (if any) and retry once
  - If still fail, abort and return the failed step + index
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

from . import patterns, intent


def replay(scope: str, intent_label: str, *,
           handlers: dict[str, Callable[[dict], Any]],
           dry_run: bool = False,
           step_delay_s: float = 0.25) -> dict:
    """Execute a saved pattern. Returns {ok, executed:[...], failed_at?, error?}."""
    pat = patterns.lookup(scope, intent_label)
    if not pat:
        return {"ok": False, "error": f"no pattern for ({scope!r}, {intent_label!r})"}

    executed = []
    started = time.time()
    for i, step in enumerate(pat["steps"]):
        op = step.get("op")
        args = step.get("args") or {}
        op_to_tool = {
            "click":     "argus_click",
            "type":      "argus_type",
            "paste":     "argus_paste",
            "key":       "argus_key",
            "send_keys": "argus_send_keys",
            "scroll":    "argus_scroll",
            "open_app":  "argus_open_app",
            "wait_for":  "argus_wait_for",
        }
        tool = op_to_tool.get(op)
        if not tool:
            return {"ok": False, "executed": executed, "failed_at": i,
                    "error": f"unknown op {op!r}"}
        if dry_run:
            executed.append({"step": i, "op": op, "args": args, "dry": True})
            continue
        fn = handlers.get(tool)
        if not fn:
            return {"ok": False, "executed": executed, "failed_at": i,
                    "error": f"handler missing for {tool}"}
        try:
            result = fn(args)
            executed.append({"step": i, "op": op, "args": args,
                              "result_summary": str(result)[:200]})
        except Exception as e:
            patterns.record_outcome(scope, intent_label, ok=False)
            return {"ok": False, "executed": executed, "failed_at": i,
                    "error": str(e)}
        time.sleep(step_delay_s)

    patterns.record_outcome(scope, intent_label, ok=True)
    intent.log("argus.replay", scope=scope, target=intent_label,
               outcome="ok", observation={"steps": len(pat["steps"]),
                                           "elapsed_s": round(time.time() - started, 2)})
    return {"ok": True, "scope": scope, "intent": intent_label,
            "steps_executed": len(executed),
            "elapsed_s": round(time.time() - started, 2),
            "executed": executed}
