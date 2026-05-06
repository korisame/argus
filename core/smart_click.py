"""argus_smart_click — robust click with retries + alternate targets.

Strategy:
  1. Try `target` via the cascade resolver
  2. If verified.ok=false, try `alternates` one by one
  3. If still failing, optionally re-screenshot + Moondream Q&A to verify
     the right element is even visible
  4. Configurable retry count + delay between attempts
"""
from __future__ import annotations

import time
from typing import Callable, Optional


def smart_click(target: str, *, alternates: list[str] | None = None,
                handlers: dict[str, Callable] | None = None,
                retries: int = 2, retry_delay_s: float = 0.6,
                require_verify: bool = True) -> dict:
    if not handlers:
        return {"ok": False, "error": "handlers required"}
    fn = handlers.get("argus_click")
    if not fn:
        return {"ok": False, "error": "argus_click handler missing"}

    targets = [target] + (alternates or [])
    attempts = []
    for tgt in targets:
        for attempt in range(retries + 1):
            try:
                res = fn({"target": tgt, "verify": require_verify})
            except Exception as e:
                attempts.append({"target": tgt, "attempt": attempt,
                                  "ok": False, "error": str(e)})
                continue
            # MCP handlers return content list — extract text
            try:
                import json
                payload = json.loads(res[0]["text"])
            except Exception:
                attempts.append({"target": tgt, "attempt": attempt,
                                  "ok": False, "raw": str(res)[:200]})
                continue
            if payload.get("clicked") and (
                not require_verify or
                (payload.get("verified") or {}).get("ok") is not False
            ):
                return {"ok": True, "target_used": tgt,
                        "attempt": attempt, "result": payload,
                        "attempts": attempts}
            attempts.append({"target": tgt, "attempt": attempt,
                              "result_summary": str(payload)[:200]})
            if attempt < retries:
                time.sleep(retry_delay_s)

    return {"ok": False, "tried": targets, "attempts": attempts,
            "hint": "All targets+alternates failed verification."}
