"""Built-in micro-workflows: the small UI gestures every agent needs.

Macros are name → list of (op, args) — same shape as patterns. Loaded by
argus_macros tool. They differ from app-skills (which are docs, not code)
and from patterns (which are user-recorded, not pre-baked).
"""
from __future__ import annotations

MACROS = {
    "dismiss_modal": [
        {"op": "key", "args": {"name": "Escape"}},
    ],
    "save": [
        {"op": "key", "args": {"name": "s", "modifiers": "cmd"}},
    ],
    "save_as": [
        {"op": "key", "args": {"name": "s", "modifiers": "shift+cmd"}},
    ],
    "undo": [
        {"op": "key", "args": {"name": "z", "modifiers": "cmd"}},
    ],
    "redo": [
        {"op": "key", "args": {"name": "z", "modifiers": "shift+cmd"}},
    ],
    "select_all": [
        {"op": "key", "args": {"name": "a", "modifiers": "cmd"}},
    ],
    "copy": [
        {"op": "key", "args": {"name": "c", "modifiers": "cmd"}},
    ],
    "paste": [
        {"op": "key", "args": {"name": "v", "modifiers": "cmd"}},
    ],
    "cut": [
        {"op": "key", "args": {"name": "x", "modifiers": "cmd"}},
    ],
    "find": [
        {"op": "key", "args": {"name": "f", "modifiers": "cmd"}},
    ],
    "find_next": [
        {"op": "key", "args": {"name": "g", "modifiers": "cmd"}},
    ],
    "new_tab": [
        {"op": "key", "args": {"name": "t", "modifiers": "cmd"}},
    ],
    "close_tab": [
        {"op": "key", "args": {"name": "w", "modifiers": "cmd"}},
    ],
    "reopen_closed_tab": [
        {"op": "key", "args": {"name": "t", "modifiers": "shift+cmd"}},
    ],
    "next_tab": [
        {"op": "key", "args": {"name": "Tab", "modifiers": "ctrl"}},
    ],
    "prev_tab": [
        {"op": "key", "args": {"name": "Tab", "modifiers": "shift+ctrl"}},
    ],
    "app_switcher_next": [
        {"op": "key", "args": {"name": "Tab", "modifiers": "cmd"}},
    ],
    "app_quit": [
        {"op": "key", "args": {"name": "q", "modifiers": "cmd"}},
    ],
    "app_hide": [
        {"op": "key", "args": {"name": "h", "modifiers": "cmd"}},
    ],
    "minimize_window": [
        {"op": "key", "args": {"name": "m", "modifiers": "cmd"}},
    ],
    "fullscreen_toggle": [
        {"op": "key", "args": {"name": "f", "modifiers": "ctrl+cmd"}},
    ],
    "spotlight": [
        {"op": "key", "args": {"name": "Space", "modifiers": "cmd"}},
    ],
    "screenshot_area": [
        {"op": "key", "args": {"name": "4", "modifiers": "shift+cmd"}},
    ],
    "screenshot_window": [
        {"op": "key", "args": {"name": "5", "modifiers": "shift+cmd"}},
    ],
    "submit_form": [   # most web forms accept Enter on a focused submit button
        {"op": "key", "args": {"name": "Return"}},
    ],
    # ── Window / desktop management ──
    "mission_control": [
        {"op": "key", "args": {"name": "Up", "modifiers": "ctrl"}},
    ],
    "exposé_app_windows": [
        {"op": "key", "args": {"name": "Down", "modifiers": "ctrl"}},
    ],
    "show_desktop": [
        {"op": "key", "args": {"name": "F11"}},
    ],
    "next_desktop": [
        {"op": "key", "args": {"name": "Right", "modifiers": "ctrl"}},
    ],
    "prev_desktop": [
        {"op": "key", "args": {"name": "Left", "modifiers": "ctrl"}},
    ],
    "zoom_in": [
        {"op": "key", "args": {"name": "Plus", "modifiers": "cmd"}},
    ],
    "zoom_out": [
        {"op": "key", "args": {"name": "Minus", "modifiers": "cmd"}},
    ],
    # ── Finder ──
    "finder_new_folder": [
        {"op": "key", "args": {"name": "n", "modifiers": "shift+cmd"}},
    ],
    "finder_open_selected": [
        {"op": "key", "args": {"name": "o", "modifiers": "cmd"}},
    ],
    "finder_quick_look": [
        {"op": "key", "args": {"name": "Space"}},
    ],
    "finder_get_info": [
        {"op": "key", "args": {"name": "i", "modifiers": "cmd"}},
    ],
    # ── Print / share ──
    "print_dialog": [
        {"op": "key", "args": {"name": "p", "modifiers": "cmd"}},
    ],
    "preferences": [
        {"op": "key", "args": {"name": "comma", "modifiers": "cmd"}},
    ],
}


def list_macros() -> dict:
    return {name: {"steps": len(steps), "ops": [s.get("op") for s in steps]}
            for name, steps in MACROS.items()}


def get(name: str) -> list[dict] | None:
    return MACROS.get(name)


def run(name: str, *, handlers) -> dict:
    """Execute a macro by name. Returns {ok, name, executed}."""
    steps = MACROS.get(name)
    if not steps:
        return {"ok": False, "error": f"unknown macro {name!r}",
                "available": sorted(MACROS.keys())}
    out = []
    op_to_tool = {
        "click":     "argus_click",
        "type":      "argus_type",
        "paste":     "argus_paste",
        "key":       "argus_key",
        "send_keys": "argus_send_keys",
        "scroll":    "argus_scroll",
    }
    for i, step in enumerate(steps):
        tool = op_to_tool.get(step.get("op"))
        if not tool:
            return {"ok": False, "name": name, "failed_at": i,
                    "error": f"unknown op {step.get('op')!r}"}
        fn = handlers.get(tool)
        if not fn:
            return {"ok": False, "name": name, "failed_at": i,
                    "error": f"missing handler {tool}"}
        try:
            r = fn(step.get("args") or {})
            out.append({"step": i, "op": step["op"]})
        except Exception as e:
            return {"ok": False, "name": name, "failed_at": i, "error": str(e)}
    return {"ok": True, "name": name, "executed": out}
