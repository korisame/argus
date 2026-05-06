"""argus_chain — composable tool pipeline.

Pass an ordered list of {tool, args} steps. Output of each step is available
to subsequent steps via {{prev}} or {{step_N}} interpolation in args.

Example:
  argus_chain steps=[
    {"tool": "argus_window", "args": {"app": "Safari"}, "as": "shot"},
    {"tool": "argus_extract", "args": {"schema": {"price": "total"}}}
  ]

Stops at first failure unless on_error=continue.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

_REF_RE = re.compile(r"\{\{(\w+)\}\}")


def _resolve(value: Any, ctx: dict) -> Any:
    if isinstance(value, str):
        def sub(m):
            key = m.group(1)
            v = ctx.get(key)
            return json.dumps(v) if isinstance(v, (dict, list)) else str(v) if v is not None else m.group(0)
        return _REF_RE.sub(sub, value)
    if isinstance(value, list):
        return [_resolve(x, ctx) for x in value]
    if isinstance(value, dict):
        return {k: _resolve(v, ctx) for k, v in value.items()}
    return value


def run(steps: list[dict], *, handlers: dict[str, Callable[[dict], Any]],
        on_error: str = "abort") -> dict:
    ctx: dict = {}
    executed: list = []
    for i, step in enumerate(steps):
        tool = step.get("tool")
        args = _resolve(step.get("args") or {}, ctx)
        as_key = step.get("as", f"step_{i}")
        if not tool:
            return {"ok": False, "executed": executed,
                    "failed_at": i, "error": "missing 'tool'"}
        fn = handlers.get(tool)
        if not fn:
            return {"ok": False, "executed": executed,
                    "failed_at": i, "error": f"unknown tool: {tool}"}
        try:
            result = fn(args)
            # Tool handlers return MCP content list; extract text or image
            extracted = _extract_text(result)
            ctx[as_key] = extracted
            ctx["prev"] = extracted
            executed.append({"step": i, "tool": tool, "as": as_key,
                              "ok": True, "preview": str(extracted)[:200]})
        except Exception as e:
            executed.append({"step": i, "tool": tool, "ok": False,
                              "error": str(e)})
            if on_error == "abort":
                return {"ok": False, "executed": executed,
                        "failed_at": i, "error": str(e), "ctx": _trunc(ctx)}
    return {"ok": True, "executed": executed, "ctx": _trunc(ctx)}


def _extract_text(mcp_result: Any) -> Any:
    """MCP handlers return a list of content blocks; parse the text into JSON if possible."""
    if not isinstance(mcp_result, list) or not mcp_result:
        return mcp_result
    first = mcp_result[0]
    if not isinstance(first, dict):
        return first
    if first.get("type") == "text":
        text = first.get("text", "")
        try:
            return json.loads(text)
        except Exception:
            return text
    return first


def _trunc(d: dict) -> dict:
    return {k: (str(v)[:300] if isinstance(v, str) else v) for k, v in d.items()}
