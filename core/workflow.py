"""Declarative workflow runner — JSON higher than patterns.

Workflow shape:
{
  "name": "post_to_notion",
  "scope": "web:www.notion.so",
  "vars": {"title": "Hello", "body": "World"},
  "steps": [
    {"do": "open_app", "args": {"name": "Google Chrome"}},
    {"do": "wait_for", "args": {"target": "Notion", "timeout_s": 10}},
    {"do": "send_keys", "args": {"combo": "cmd+p"}},
    {"do": "type",      "args": {"text": "{{title}}"}},
    {"do": "key",       "args": {"name": "Return"}},
    {"do": "send_keys", "args": {"combo": "cmd+enter"}},
    {"if": {"ask": "Is the page saved?"}, "expect": "yes",
     "then": [{"do": "log", "args": {"msg": "saved ok"}}],
     "else": [{"do": "fail", "args": {"reason": "save did not happen"}}]},
  ],
  "on_error": "abort"
}

Supports:
  - {{var}} interpolation in args
  - if/then/else branches with ask predicate
  - on_error: abort | continue
  - log step (no-op except records)
  - fail step (raises)
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

from . import intent, vision, screen


_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def _interpolate(value: Any, vars_: dict) -> Any:
    if isinstance(value, str):
        return _VAR_RE.sub(lambda m: str(vars_.get(m.group(1), m.group(0))), value)
    if isinstance(value, list):
        return [_interpolate(v, vars_) for v in value]
    if isinstance(value, dict):
        return {k: _interpolate(v, vars_) for k, v in value.items()}
    return value


def _step_ask_yes(predicate: dict, vars_: dict) -> bool:
    q = _interpolate(predicate.get("ask", ""), vars_)
    if not q:
        return False
    cap = screen.capture_frontmost(out_path="/tmp/argus_workflow_ask.png")
    if not cap.get("ok"):
        return False
    ans = (vision.VISION.ask(cap["path"], q) or "").lower()
    return ans.startswith("yes") or ans.startswith("y")


def _exec_step(step: dict, *, handlers: dict[str, Callable[[dict], Any]],
               vars_: dict, executed: list) -> dict:
    if "if" in step:
        cond = step["if"]
        expect = step.get("expect", "yes")
        ok = _step_ask_yes(cond, vars_)
        branch = step.get("then" if (ok and expect == "yes") else "else", [])
        executed.append({"branch": "then" if ok else "else",
                          "cond": cond, "expect": expect, "matched": ok})
        for sub in (branch or []):
            r = _exec_step(sub, handlers=handlers, vars_=vars_, executed=executed)
            if not r.get("ok"):
                return r
        return {"ok": True}

    op = step.get("do") or step.get("op")
    args_in = _interpolate(step.get("args") or {}, vars_)

    if op == "log":
        executed.append({"op": "log", "args": args_in})
        return {"ok": True}
    if op == "fail":
        return {"ok": False, "error": args_in.get("reason", "explicit fail")}
    if op == "set":
        for k, v in args_in.items():
            vars_[k] = v
        executed.append({"op": "set", "args": args_in})
        return {"ok": True}

    op_to_tool = {
        "click":     "argus_click",
        "type":      "argus_type",
        "paste":     "argus_paste",
        "key":       "argus_key",
        "send_keys": "argus_send_keys",
        "scroll":    "argus_scroll",
        "open_app":  "argus_open_app",
        "wait_for":  "argus_wait_for",
        "ask":       "argus_ask",
        "extract":   "argus_extract",
    }
    tool = op_to_tool.get(op)
    if not tool:
        return {"ok": False, "error": f"unknown op {op!r}"}
    fn = handlers.get(tool)
    if not fn:
        return {"ok": False, "error": f"handler missing for {tool}"}
    try:
        res = fn(args_in)
        executed.append({"op": op, "args": args_in,
                          "result": str(res)[:200]})
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def run(workflow: dict, *, handlers: dict[str, Callable[[dict], Any]],
        extra_vars: dict | None = None, dry_run: bool = False) -> dict:
    name = workflow.get("name") or "<anonymous>"
    scope = workflow.get("scope", "")
    vars_ = dict(workflow.get("vars") or {})
    if extra_vars:
        vars_.update(extra_vars)
    on_err = workflow.get("on_error", "abort")
    executed: list = []
    started = time.time()

    if dry_run:
        return {"ok": True, "dry_run": True, "name": name,
                "expanded_steps": [_interpolate(s, vars_)
                                    for s in workflow.get("steps", [])],
                "vars": vars_}

    for i, step in enumerate(workflow.get("steps") or []):
        r = _exec_step(step, handlers=handlers, vars_=vars_, executed=executed)
        if not r.get("ok"):
            intent.log("argus.workflow", scope=scope, target=name,
                       outcome="fail",
                       observation={"step_index": i, "error": r.get("error")})
            if on_err == "abort":
                return {"ok": False, "name": name, "scope": scope,
                        "failed_at_step": i, "error": r.get("error"),
                        "executed": executed,
                        "elapsed_s": round(time.time() - started, 2)}
    intent.log("argus.workflow", scope=scope, target=name, outcome="ok",
               observation={"steps": len(executed),
                             "elapsed_s": round(time.time() - started, 2)})
    return {"ok": True, "name": name, "scope": scope,
            "steps_executed": len(executed),
            "elapsed_s": round(time.time() - started, 2),
            "executed": executed, "vars": vars_}
