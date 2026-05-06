"""Multi-window orchestration.

Today: focus + act + read across N apps/windows/tabs sequentially.
The 'parallel' bit is mostly: avoid losing context (frontmost app changes
are tracked) and screenshot in the background where possible.

Each task is {target_app, action, args}. Argus brings the app to front,
runs the action, captures result, returns control. Final result is
{tasks: [...], final_surface: {...}}.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from . import router as _router
from . import screen as _screen
from adapters import cgevent


def run_tasks(tasks: list[dict], *,
              handlers: dict[str, Callable[[dict], Any]],
              return_to: str | None = None) -> dict:
    """Each task: {app: 'Safari', tool: 'argus_click', args: {...}}.

    Sequence:
      1. Capture starting surface
      2. For each task: focus app → run tool → record result
      3. Optionally focus `return_to` app at the end
    """
    start = _router.detect()
    out: list = []

    for i, task in enumerate(tasks):
        app = task.get("app")
        tool = task.get("tool")
        args = task.get("args") or {}

        if app:
            try:
                cgevent.open_app(app)
                time.sleep(0.6)
            except Exception:
                pass

        if not tool:
            out.append({"task": i, "app": app, "skipped": True,
                        "reason": "no tool specified (focus only)"})
            continue
        fn = handlers.get(tool)
        if not fn:
            out.append({"task": i, "app": app, "tool": tool, "ok": False,
                         "error": f"unknown tool {tool!r}"})
            continue
        try:
            res = fn(args)
            out.append({"task": i, "app": app, "tool": tool, "ok": True,
                         "result_preview": str(res)[:200],
                         "surface_after": _router.detect()})
        except Exception as e:
            out.append({"task": i, "app": app, "tool": tool, "ok": False,
                         "error": str(e)})

    if return_to:
        try:
            cgevent.open_app(return_to)
            time.sleep(0.4)
        except Exception:
            pass

    return {"start_surface": start, "tasks": out,
            "final_surface": _router.detect()}


def background_capture_all() -> dict:
    """Capture screenshots of all visible windows (frontmost AND background)."""
    if not _screen.available():
        return {"ok": False, "error": "screen module unavailable"}
    wins = _screen.list_windows()
    captured: list = []
    for w in wins[:20]:  # cap to avoid spamming the disk
        path = f"/tmp/argus_workspace_{w['wid']}.png"
        try:
            _screen.capture(w["wid"], out_path=path)
            captured.append({"wid": w["wid"], "owner": w["owner"],
                              "title": w["title"], "path": path})
        except Exception as e:
            captured.append({"wid": w["wid"], "error": str(e)})
    return {"ok": True, "captured": len(captured), "windows": captured}
