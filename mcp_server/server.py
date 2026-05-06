"""argus MCP server — unified (v0.3).

10 atomic tools:
  argus_doctor   argus_see       argus_surface   argus_find
  argus_click    argus_type      argus_key        argus_scroll
  argus_session  argus_repl      argus_history    argus_metrics
  argus_open_app argus_quit_app  argus_exec_apple_script
  argus_session_begin  argus_session_end  argus_vision_unload

(yes that's actually 17 — 10 are the conceptual atoms, the rest are setup/teardown
helpers and OS-level escape hatches we kept for parity with v0.2.)
"""
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import time
import traceback

# Make sibling packages importable when launched as `python3 server.py`
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)


def _load_dotenv() -> dict:
    """Load ~/.argus/.env (and ~/Developer/argus/.env as fallback) into os.environ.
    Quick win C — server picks up MOONDREAM_API_KEY without shell export."""
    loaded = []
    for path in (os.path.expanduser("~/.argus/.env"),
                 os.path.expanduser("~/Developer/argus/.env")):
        if not os.path.isfile(path):
            continue
        try:
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
                    loaded.append(k)
        except Exception:
            pass
    return {"loaded_from": [p for p in (os.path.expanduser("~/.argus/.env"),
                                         os.path.expanduser("~/Developer/argus/.env"))
                             if os.path.isfile(p)],
            "vars_set": loaded}


_DOTENV_INFO = _load_dotenv()

from core import (cascade, intent, router, vision, verify, session, repl,
                  autotune, screen, patterns, policy, prewarm, dashboard,
                  wizard, uninstall as _uninstall, chrome_admin, registry,
                  asyncio_runtime, extract, safety, secure_session,
                  replay as _replay, workflow as _workflow,
                  apple_apps, diff_screens, macros,
                  benchmark, health, chain as _chain,
                  workspace as _workspace, predict as _predict)
from adapters import ax, ocr, cdp, cdp_raw, cgevent

PROTO_VERSION = "2024-11-05"
SERVER_NAME = "argus"
SERVER_VERSION = "0.10.0"

WORKFLOWS_DIR = os.path.join(ROOT, "app-skills", "workflows")


# ─── tool catalog ─────────────────────────────────────────────────────
TOOLS = [
    {"name": "argus_doctor",
     "description": "Diagnostics. Returns {status: READY|DEGRADED|BROKEN, summary, deps, surface, dotenv}. Pass full=true for the verbose blob (ax/ocr/cdp/vision/cgevent details).",
     "inputSchema": {"type": "object", "properties": {
         "full": {"type": "boolean", "default": False}
     }, "additionalProperties": False}},

    {"name": "argus_see",
     "description": "Screenshot of the current screen → base64 PNG.",
     "inputSchema": {"type": "object", "properties": {
         "max_dim": {"type": "integer", "default": 1600}
     }, "additionalProperties": False}},

    {"name": "argus_surface",
     "description": "Where am I? Returns {surface: 'browser'|'webview'|'native', app: {bundle_id,name,pid}, host?}",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},

    {"name": "argus_find",
     "description": "Resolve target to coords WITHOUT clicking. Returns {x,y,bbox?,source,confidence,scope,attempts,ms}. Cascade: cache → AX → CDP-DOM → OCR → vision.",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string"}
     }, "required": ["target"], "additionalProperties": False}},

    {"name": "argus_click",
     "description": "Cascade resolve + click + verify. Returns {clicked, x, y, source, confidence, verified:{ok,reason}, attempts, ms}. Updates the learned-selector cache on success.",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string"},
         "double": {"type": "boolean", "default": False},
         "verify": {"type": "boolean", "default": True},
         "min_confidence": {"type": "number", "default": 0.55}
     }, "required": ["target"], "additionalProperties": False}},

    {"name": "argus_type",
     "description": "Type into focused field. Refuses on AXSecureTextField unless force_secure=true.",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string"},
         "force_secure": {"type": "boolean", "default": False}
     }, "required": ["text"], "additionalProperties": False}},

    {"name": "argus_paste",
     "description": "Paste text into focused field via clipboard (much faster than typing for long text; handles Unicode/IME natively). Refuses on AXSecureTextField unless force_secure=true. Restores prior clipboard contents.",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string"},
         "force_secure": {"type": "boolean", "default": False},
         "restore_clipboard": {"type": "boolean", "default": True}
     }, "required": ["text"], "additionalProperties": False}},

    {"name": "argus_wait_for",
     "description": "Poll until target appears (or condition met) within timeout. Returns the resolved hit, or {timed_out: true}. Use to eliminate sleep() guesswork.",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string", "description": "target string for cascade resolver"},
         "timeout_s": {"type": "number", "default": 10.0},
         "poll_s": {"type": "number", "default": 0.4},
         "min_confidence": {"type": "number", "default": 0.55}
     }, "required": ["target"], "additionalProperties": False}},

    {"name": "argus_find_all",
     "description": "Return ALL matches for target (not just the best). Useful for duplicates, e.g. 'pick the second Sign In button'. Each hit has {x, y, bbox, source, confidence, text?}.",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string"},
         "min_confidence": {"type": "number", "default": 0.4},
         "limit": {"type": "integer", "default": 20}
     }, "required": ["target"], "additionalProperties": False}},

    {"name": "argus_send_keys",
     "description": "Composite keyboard shortcut as single string, e.g. 'cmd+shift+t' or 'ctrl+alt+delete'. Maps the last token to the key, the rest to modifiers.",
     "inputSchema": {"type": "object", "properties": {
         "combo": {"type": "string"}
     }, "required": ["combo"], "additionalProperties": False}},

    {"name": "argus_key",
     "description": "Special key (Return, Tab, Escape, ArrowUp/Down/Left/Right, Backspace) with optional modifiers ('cmd'|'shift+cmd'|'ctrl'|'alt').",
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string"},
         "modifiers": {"type": "string"}
     }, "required": ["name"], "additionalProperties": False}},

    {"name": "argus_scroll",
     "description": "Scroll up/down/left/right at cursor (or at coords if provided).",
     "inputSchema": {"type": "object", "properties": {
         "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
         "amount": {"type": "integer", "default": 5},
         "x": {"type": "number"}, "y": {"type": "number"}
     }, "required": ["direction"], "additionalProperties": False}},

    {"name": "argus_open_app",
     "description": "Launch / focus a macOS app by name.",
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string"}
     }, "required": ["name"], "additionalProperties": False}},

    {"name": "argus_quit_app",
     "description": "Quit a macOS app gracefully.",
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string"}
     }, "required": ["name"], "additionalProperties": False}},

    {"name": "argus_exec_apple_script",
     "description": "Run arbitrary AppleScript. Escape hatch — sandboxed via safety.is_dangerous(). Refuses on rm -rf / fork bombs / disk-erase / admin escalation. Pass allow_dangerous=true (audit-logged) to override.",
     "inputSchema": {"type": "object", "properties": {
         "code": {"type": "string"},
         "allow_dangerous": {"type": "boolean", "default": False}
     }, "required": ["code"], "additionalProperties": False}},

    {"name": "argus_session",
     "description": "Browser session jar (cookies + storage). action ∈ {save, load, clear, list, detect_login}.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["save", "load", "clear", "list", "detect_login"]},
         "name": {"type": "string", "default": "default"}
     }, "required": ["action"], "additionalProperties": False}},

    {"name": "argus_repl",
     "description": "Persistent REPL / long-running process. action ∈ {start, send, read, kill, list}. Use for python3, node, psql, lldb, ssh...",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["start", "send", "read", "kill", "list"]},
         "cmd": {"type": "string"},
         "name": {"type": "string"},
         "handle": {"type": "string", "description": "pid (as string) or name"},
         "data": {"type": "string"},
         "enter": {"type": "boolean", "default": True},
         "timeout_s": {"type": "number", "default": 1.0},
         "cwd": {"type": "string"}
     }, "required": ["action"], "additionalProperties": False}},

    {"name": "argus_history",
     "description": "Recent intent log entries (most recent first). Filter by intent / scope / outcome.",
     "inputSchema": {"type": "object", "properties": {
         "limit": {"type": "integer", "default": 50},
         "intent": {"type": "string"},
         "scope": {"type": "string"},
         "outcome": {"type": "string", "enum": ["ok", "fail"]}
     }, "additionalProperties": False}},

    {"name": "argus_metrics",
     "description": "Per-tool latency (p50/p95/avg) and success rate for this server process. Optional reset.",
     "inputSchema": {"type": "object", "properties": {
         "reset": {"type": "boolean", "default": False}
     }, "additionalProperties": False}},

    {"name": "argus_cache",
     "description": "Inspect the learned-selector cache. action ∈ {view}. Filter by scope (e.g. 'web:github.com' or 'native:com.apple.finder').",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["view"], "default": "view"},
         "scope": {"type": "string"},
         "limit": {"type": "integer", "default": 100}
     }, "additionalProperties": False}},

    {"name": "argus_autotune",
     "description": "Read intent.jsonl + learned cache. Promote well-proven selectors (>=20 successes, >=90% rate) into app-skills/<scope>.md, and surface top recurring failures. action ∈ {report, promote, full}. dry_run available for promote/full.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["report", "promote", "full"], "default": "full"},
         "dry_run": {"type": "boolean", "default": False}
     }, "additionalProperties": False}},

    {"name": "argus_session_begin",
     "description": "Pin the Moondream model in RAM for a burst of vision calls (no auto-unload).",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},

    {"name": "argus_session_end",
     "description": "Unpin Moondream. Frees RAM immediately by default.",
     "inputSchema": {"type": "object", "properties": {
         "unload": {"type": "boolean", "default": True}
     }, "additionalProperties": False}},

    {"name": "argus_vision_unload",
     "description": "Free the Moondream model RAM right now.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},

    # ─── v0.5 additions ───────────────────────────────────────────
    {"name": "argus_window",
     "description": "Capture a specific app window — foreground or background. Returns base64 PNG. Match by app name, bundle_id, or window title. Doesn't bring the app to front.",
     "inputSchema": {"type": "object", "properties": {
         "app": {"type": "string", "description": "partial case-insensitive owner name"},
         "bundle_id": {"type": "string"},
         "title": {"type": "string", "description": "substring of window title"},
         "index": {"type": "integer", "default": 0},
         "max_dim": {"type": "integer", "default": 1600},
         "frontmost": {"type": "boolean", "default": False,
                        "description": "If true, capture frontmost app's main window."}
     }, "additionalProperties": False}},

    {"name": "argus_window_list",
     "description": "List all visible windows with metadata (wid, app, title, bounds, layer).",
     "inputSchema": {"type": "object", "properties": {
         "app": {"type": "string", "description": "filter by app name"}
     }, "additionalProperties": False}},

    {"name": "argus_pattern",
     "description": "Task-pattern memory. action ∈ {record_begin, record_step, record_end, lookup, list, delete}. record_begin(name, scope, intent_label) starts a recording; subsequent argus_click/type/etc append; record_end commits. lookup(scope, intent_label) returns the saved sequence for replay.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["record_begin", "record_step", "record_end",
                                                 "lookup", "list", "delete"]},
         "name": {"type": "string"},
         "scope": {"type": "string"},
         "intent_label": {"type": "string"},
         "op": {"type": "string"},
         "args": {"type": "object", "additionalProperties": True},
         "ok": {"type": "boolean", "default": True},
         "save": {"type": "boolean", "default": True},
         "limit": {"type": "integer", "default": 100}
     }, "required": ["action"], "additionalProperties": False}},

    {"name": "argus_policy",
     "description": "Inspect / write the policy file (~/.argus/policy.yaml). action ∈ {doctor, write_default, reload, check_app, check_destructive}.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["doctor", "write_default",
                                                 "reload", "check_app", "check_destructive"]},
         "scope": {"type": "string"},
         "target": {"type": "string"}
     }, "required": ["action"], "additionalProperties": False}},

    {"name": "argus_setup",
     "description": "Onboarding wizard — checks Python, uv, argus CLI, pyobjc, websocket-client, browser-harness, automation Chrome, Moondream key, policy file, Screen Recording TCC. Returns step results + suggested fix commands.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},

    {"name": "argus_uninstall",
     "description": "Clean removal across all integration points. action ∈ {plan, execute}. plan dry-runs, execute removes ~/.claude/plugins/argus, ~/.codex/skills/argus, ~/.openclaw/skills/argus, ~/.argus-prime, ~/.argus, launchd agent, BU_CDP_URL from zshrc. force_full also removes ~/Developer/argus.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["plan", "execute"], "default": "plan"},
         "force_full": {"type": "boolean", "default": False},
         "kill_chrome": {"type": "boolean", "default": True}
     }, "additionalProperties": False}},

    {"name": "argus_dashboard",
     "description": "Local web dashboard on http://127.0.0.1:9999 — cache view, intent log, metrics, patterns, autotune. action ∈ {start, stop, status}.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["start", "stop", "status"], "default": "start"},
         "port": {"type": "integer", "default": 9999}
     }, "additionalProperties": False}},

    {"name": "argus_chrome",
     "description": "Manage the dedicated automation Chrome (port 9333). action ∈ {status, boot, kill, install_agent}. boot supports headless=true.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["status", "boot", "kill", "install_agent"]},
         "headless": {"type": "boolean", "default": False}
     }, "required": ["action"], "additionalProperties": False}},

    {"name": "argus_skills",
     "description": "Pull app-skills from the community registry (default: korisame/argus-skills). action ∈ {index, install, list_local}. install accepts 'github.com', 'com.apple.finder', 'web/foo.com', or 'native/com.foo'.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["index", "install", "list_local"]},
         "name": {"type": "string"},
         "kind": {"type": "string", "enum": ["auto", "native", "web"], "default": "auto"}
     }, "required": ["action"], "additionalProperties": False}},

    {"name": "argus_chain",
     "description": "Composable tool pipeline. steps=[{tool, args, [as]}]. Output of each step bound to {{prev}} or {{step_N}}/{{as}} for subsequent steps. Use to fuse multi-step ops into one MCP call.",
     "inputSchema": {"type": "object", "properties": {
         "steps": {"type": "array", "items": {"type": "object",
             "properties": {"tool": {"type": "string"},
                              "args": {"type": "object"},
                              "as": {"type": "string"}},
             "required": ["tool"]}},
         "on_error": {"type": "string", "enum": ["abort", "continue"], "default": "abort"}
     }, "required": ["steps"], "additionalProperties": False}},

    {"name": "argus_workspace",
     "description": "Multi-window orchestration. tasks=[{app, tool, args}]. Brings each app to front, runs tool, captures result. Optionally returns to a final app at the end.",
     "inputSchema": {"type": "object", "properties": {
         "tasks": {"type": "array", "items": {"type": "object",
             "properties": {"app": {"type": "string"},
                              "tool": {"type": "string"},
                              "args": {"type": "object"}}}},
         "return_to": {"type": "string"}
     }, "required": ["tasks"], "additionalProperties": False}},

    {"name": "argus_workspace_capture_all",
     "description": "Capture screenshots of ALL visible windows (foreground + background) at once. Returns list of {wid, owner, title, path}. Capped at 20 to avoid disk spam.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},

    {"name": "argus_predict_next",
     "description": "Suggest the next likely action for the current scope based on saved patterns + recent intent history. Returns ranked suggestions with replay hints.",
     "inputSchema": {"type": "object", "properties": {
         "scope": {"type": "string"},
         "top_n": {"type": "integer", "default": 5}
     }, "additionalProperties": False}},

    {"name": "argus_benchmark",
     "description": "Run a perf suite (router, AX, OCR, CDP, vision, screencapture, cache). Returns p50/p95/avg/stdev per op.",
     "inputSchema": {"type": "object", "properties": {
         "iterations": {"type": "integer", "default": 10}
     }, "additionalProperties": False}},

    {"name": "argus_health",
     "description": "Continuous health monitor. action ∈ {start, stop, status}. Logs DEGRADED/BROKEN transitions to intent.jsonl.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["start", "stop", "status"], "default": "status"},
         "interval_s": {"type": "number", "default": 60}
     }, "additionalProperties": False}},

    {"name": "argus_dom_query",
     "description": "Direct CDP DOM query (browser only). Returns matched elements with text, bbox, attrs. For agents that prefer DOM over vision.",
     "inputSchema": {"type": "object", "properties": {
         "selector": {"type": "string"},
         "max_results": {"type": "integer", "default": 50},
         "attrs": {"type": "array", "items": {"type": "string"}}
     }, "required": ["selector"], "additionalProperties": False}},

    {"name": "argus_install_log_rotation",
     "description": "Install launchd agent that runs argus_log_rotate nightly. Optional hour (24h, default 3 = 3am).",
     "inputSchema": {"type": "object", "properties": {
         "hour": {"type": "integer", "default": 3, "minimum": 0, "maximum": 23}
     }, "additionalProperties": False}},

    {"name": "argus_macros",
     "description": "Built-in micro-workflows. action ∈ {list, run}. run macro_name='save'|'undo'|'new_tab'|'spotlight'|... Pre-baked common UI gestures.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["list", "run"]},
         "macro_name": {"type": "string"}
     }, "required": ["action"], "additionalProperties": False}},

    {"name": "argus_workflow_template",
     "description": "Load a pre-shipped workflow template by name (e.g. 'post_to_notion', 'gmail_compose'), optionally override vars, and run it.",
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string"},
         "vars": {"type": "object"},
         "dry_run": {"type": "boolean", "default": False},
         "list": {"type": "boolean", "default": False}
     }, "additionalProperties": False}},

    {"name": "argus_diff_screens",
     "description": "Compare two screenshots. Returns regions of change + perceptual delta. For state monitoring.",
     "inputSchema": {"type": "object", "properties": {
         "path_a": {"type": "string"},
         "path_b": {"type": "string"},
         "threshold": {"type": "integer", "default": 30}
     }, "required": ["path_a", "path_b"], "additionalProperties": False}},

    {"name": "argus_notes",
     "description": "Create a note in Apple Notes (with open-first pattern to avoid TCC timeout).",
     "inputSchema": {"type": "object", "properties": {
         "title": {"type": "string"},
         "body": {"type": "string"},
         "folder": {"type": "string", "default": "Notes"},
         "account": {"type": "string"}
     }, "required": ["title", "body"], "additionalProperties": False}},

    {"name": "argus_reminders",
     "description": "Create a reminder in Apple Reminders.",
     "inputSchema": {"type": "object", "properties": {
         "title": {"type": "string"},
         "notes": {"type": "string"},
         "list_name": {"type": "string"},
         "due_date": {"type": "string", "description": "AppleScript date string, e.g. 'tomorrow at 9:00am'"}
     }, "required": ["title"], "additionalProperties": False}},

    {"name": "argus_replay",
     "description": "Replay a saved task pattern step-by-step. Provide (scope, intent_label) — the saved sequence executes via the same argus tools that recorded it. Use after argus_pattern record_end. dry_run=true to preview.",
     "inputSchema": {"type": "object", "properties": {
         "scope": {"type": "string"},
         "intent_label": {"type": "string"},
         "dry_run": {"type": "boolean", "default": False},
         "step_delay_s": {"type": "number", "default": 0.25}
     }, "required": ["scope", "intent_label"], "additionalProperties": False}},

    {"name": "argus_workflow",
     "description": "Run a declarative JSON workflow (steps + branching + variables). Higher-level than patterns. Supports {{var}} interpolation, if/then/else with vision predicate, on_error abort/continue. Pass dry_run=true to expand without executing.",
     "inputSchema": {"type": "object", "properties": {
         "workflow": {"type": "object",
                       "description": "{name, scope, vars, steps:[{do, args}|{if,then,else}], on_error}"},
         "extra_vars": {"type": "object"},
         "dry_run": {"type": "boolean", "default": False}
     }, "required": ["workflow"], "additionalProperties": False}},

    {"name": "argus_extract",
     "description": "Extract structured data from a screenshot. Pass {schema: {field_name: 'natural language description'}}. Returns {field: value, _meta:{...}}. OCR-first then Moondream Q&A. Use for scraping any site/app without an API.",
     "inputSchema": {"type": "object", "properties": {
         "schema": {"type": "object", "additionalProperties": {"type": "string"},
                     "description": "field_name → description"},
         "window_app": {"type": "string", "description": "capture this app's window instead of frontmost"}
     }, "required": ["schema"], "additionalProperties": False}},

    {"name": "argus_ask",
     "description": "Visual question-answering on the current screen (or window). Returns {answer, screenshot}. Use for 'is the build green?', 'what's the error in this dialog?', 'how many unread emails?'.",
     "inputSchema": {"type": "object", "properties": {
         "question": {"type": "string"},
         "window_app": {"type": "string"}
     }, "required": ["question"], "additionalProperties": False}},

    {"name": "argus_secure_session",
     "description": "Encrypted session jars (cookies+localStorage+IDB). action ∈ {encrypt, decrypt, list}. Encryption key per-jar in macOS Keychain. AES-256-GCM (or openssl fallback).",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["encrypt", "decrypt", "list"]},
         "name": {"type": "string", "default": "default"}
     }, "required": ["action"], "additionalProperties": False}},

    {"name": "argus_log_rotate",
     "description": "Rotate intent.jsonl if > 50MB (gzip + keep last 5). Run nightly via cron, or on-demand.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},

    {"name": "argus_cu_route",
     "description": "Computer Use shim. Translates Anthropic Computer-Use-style {action, coordinate, text, ...} payloads into native argus tools. Lets agents that 'know how to' use Computer Use drive argus instead. action examples: 'screenshot', 'left_click', 'type', 'key', 'scroll', 'mouse_move'.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string"},
         "coordinate": {"type": "array", "items": {"type": "number"},
                          "minItems": 2, "maxItems": 2},
         "text": {"type": "string"},
         "duration": {"type": "number"}
     }, "required": ["action"], "additionalProperties": True}},
]


# ─── helpers ──────────────────────────────────────────────────────
def _text(v):
    return [{"type": "text",
             "text": v if isinstance(v, str) else json.dumps(v, default=str, indent=2)}]


def _take_screenshot() -> str:
    return cgevent.screenshot("/tmp/argus_prime_shot.png")


# ─── tool handlers ────────────────────────────────────────────────
def tool_argus_doctor(args):
    full = bool(args.get("full", False))
    ax_d = ax.doctor()
    ocr_d = ocr.doctor()
    cdp_d = cdp.doctor()
    vis = vision.VISION.status()
    cge = cgevent.doctor()
    surf = router.doctor()

    # ─── compute summary ───
    deps = {
        "ax": bool(ax_d.get("available")),
        "ocr": bool(ocr_d.get("available")),
        "cdp": bool(cdp_d.get("available")),
        "vision": vis.get("mode") in ("argus", "cloud"),
        "argus_core": bool(cge.get("argus_core_importable")),
    }
    n_ok = sum(deps.values())
    n_tot = len(deps)
    if n_ok == n_tot:
        status = "READY"
    elif deps["argus_core"] and (deps["ax"] or deps["ocr"]):
        status = "DEGRADED"
    else:
        status = "BROKEN"
    missing = [k for k, v in deps.items() if not v]
    summary = f"{status} — argus v{SERVER_VERSION}, surface={surf['current'].get('surface', '?')}"
    if missing:
        summary += f", missing: {', '.join(missing)}"

    base = {
        "status": status,
        "summary": summary,
        "argus_version": SERVER_VERSION,
        "deps": deps,
        "surface": surf["current"],
        "dotenv": _DOTENV_INFO,
    }
    if not full:
        return _text(base)

    base.update({
        "ax_full": ax_d, "ocr_full": ocr_d, "cdp_full": cdp_d,
        "vision_full": vis, "cgevent_full": cge,
        "router_full": surf, "data_dir": str(intent.DATA_DIR),
    })
    return _text(base)


def tool_argus_see(args):
    max_dim = int(args.get("max_dim", 1600))
    path = _take_screenshot()
    from PIL import Image
    img = Image.open(path)
    if max_dim and max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim))
        path2 = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
        img.save(path2)
        path = path2
    with open(path, "rb") as f:
        b = f.read()
    return [{"type": "image", "data": base64.b64encode(b).decode(), "mimeType": "image/png"}]


def tool_argus_surface(_):
    return _text(router.detect())


def tool_argus_find(args):
    target = args["target"]
    res = cascade.resolve(target, screenshot_callable=_take_screenshot)
    intent.log("argus.find", scope=res.get("scope", ""), target=target,
               source=res.get("source"), outcome="ok" if res.get("source") else "fail",
               ms=res.get("ms", 0), confidence=res.get("confidence"))
    return _text(res)


def tool_argus_click(args):
    target = args["target"]
    double = bool(args.get("double", False))
    do_verify = bool(args.get("verify", True))
    min_conf = float(args.get("min_confidence", 0.55))

    # ── policy gate ──
    surf = router.detect()
    scope = surf.get("scope") or ""
    allowed, reason = policy.app_allowed(scope)
    if not allowed:
        intent.log("argus.click", scope=scope, target=target, outcome="blocked",
                   error=reason)
        return _text({"clicked": False, "blocked_by_policy": reason})
    destructive = policy.is_destructive(target)
    if destructive and not args.get("confirm_destructive"):
        intent.log("argus.click", scope=scope, target=target, outcome="needs_confirm",
                   observation={"matched_verb": destructive})
        return _text({"clicked": False,
                      "needs_confirm": f"target matches destructive verb {destructive!r}. "
                                        f"Re-call with confirm_destructive=true to proceed.",
                      "matched_verb": destructive})

    res = cascade.resolve(target, screenshot_callable=_take_screenshot,
                          min_confidence=min_conf)
    if res.get("source") is None:
        intent.log("argus.click", scope=res.get("scope", ""), target=target,
                   outcome="fail", ms=res.get("ms", 0), error=res.get("error"))
        return _text({"clicked": False, **res})

    out = {
        "clicked": True,
        "x": res["x"], "y": res["y"],
        "bbox": res.get("bbox"),
        "source": res.get("source"),
        "confidence": res.get("confidence"),
        "scope": res.get("scope"),
        "attempts": res.get("attempts", []),
        "ms_resolve": res.get("ms"),
    }

    if do_verify:
        with verify.Verifier(bbox=res.get("bbox"),
                             surface_hint=router.detect().get("surface")) as v:
            cgevent.click(res["x"], res["y"], double=double)
        out["verified"] = v.result
        ok = bool(v.result and v.result.get("ok"))
    else:
        cgevent.click(res["x"], res["y"], double=double)
        ok = True

    cascade.record_outcome(res, target=target, ok=ok)
    intent.log("argus.click", scope=res.get("scope", ""), target=target,
               source=res.get("source"), outcome="ok" if ok else "fail",
               ms=res.get("ms", 0), confidence=res.get("confidence"),
               observation={"verified": out.get("verified")})
    if ok:
        patterns.record_step("click", {"target": target, "double": double})
    return _text(out)


def tool_argus_type(args):
    text = args["text"]
    force = bool(args.get("force_secure", False))
    pol = policy.load()
    surf = router.detect()
    scope = surf.get("scope") or ""
    type_ok, reason = policy.type_allowed(scope)
    if not type_ok:
        intent.log("argus.type", scope=scope, outcome="blocked", error=reason)
        return _text({"typed": False, "blocked_by_policy": reason})
    if not force and pol.get("block_secure_field", True) and ax.available() \
            and ax.is_secure_field_focused():
        return _text({"typed": False,
                      "blocked": "AXSecureTextField focused. Pass force_secure=true to override."})
    res = cgevent.type_text(text)
    intent.log("argus.type", outcome="ok", scope=scope,
               observation={"chars": len(text)})
    patterns.record_step("type", {"text": text})
    return _text({"typed": True, "chars": len(text), "result": res})


def tool_argus_key(args):
    res = cgevent.key(args["name"], modifiers=args.get("modifiers"))
    intent.log("argus.key", target=args["name"], outcome="ok")
    patterns.record_step("key", {"name": args["name"], "modifiers": args.get("modifiers")})
    return _text({"pressed": args["name"], "modifiers": args.get("modifiers"),
                  "result": res})


def tool_argus_paste(args):
    """Quick win A: clipboard-based paste."""
    text = args["text"]
    force = bool(args.get("force_secure", False))
    restore = bool(args.get("restore_clipboard", True))
    if not force and ax.available() and ax.is_secure_field_focused():
        return _text({"pasted": False,
                      "blocked": "AXSecureTextField focused. Pass force_secure=true to override."})
    import subprocess as _sp
    prior = None
    if restore:
        try:
            r = _sp.run(["pbpaste"], capture_output=True, text=True, timeout=2)
            prior = r.stdout
        except Exception:
            prior = None
    try:
        _sp.run(["pbcopy"], input=text, text=True, check=True, timeout=5)
    except Exception as e:
        return _text({"pasted": False, "error": f"pbcopy failed: {e}"})
    # Cmd+V
    cgevent.key("v", modifiers="cmd")
    if restore and prior is not None:
        try:
            import time as _t
            _t.sleep(0.2)
            _sp.run(["pbcopy"], input=prior, text=True, check=False, timeout=5)
        except Exception:
            pass
    intent.log("argus.paste", outcome="ok", observation={"chars": len(text)})
    patterns.record_step("paste", {"text": text[:200] + ("..." if len(text) > 200 else "")})
    return _text({"pasted": True, "chars": len(text), "restored_clipboard": restore})


def tool_argus_wait_for(args):
    """Quick win B: poll cascade until target resolves."""
    import time as _t
    target = args["target"]
    timeout_s = float(args.get("timeout_s", 10.0))
    poll_s = float(args.get("poll_s", 0.4))
    min_conf = float(args.get("min_confidence", 0.55))
    deadline = _t.monotonic() + timeout_s
    attempts = 0
    last_err = None
    while _t.monotonic() < deadline:
        attempts += 1
        res = cascade.resolve(target, screenshot_callable=_take_screenshot,
                              min_confidence=min_conf)
        if res.get("source"):
            res["wait_attempts"] = attempts
            res["wait_elapsed_s"] = round(timeout_s - max(0, deadline - _t.monotonic()), 2)
            intent.log("argus.wait_for", target=target, outcome="ok",
                       source=res.get("source"), ms=res.get("ms", 0))
            return _text(res)
        last_err = res.get("error")
        _t.sleep(poll_s)
    intent.log("argus.wait_for", target=target, outcome="fail",
               observation={"attempts": attempts, "last_error": last_err})
    return _text({"timed_out": True, "target": target, "attempts": attempts,
                  "timeout_s": timeout_s, "last_error": last_err})


def tool_argus_find_all(args):
    """Quick win E: return ALL matches above min_confidence."""
    target = args["target"]
    min_conf = float(args.get("min_confidence", 0.4))
    limit = int(args.get("limit", 20))

    out: list[dict] = []
    surface = router.detect()
    is_browser = surface.get("surface") == "browser"
    scope = surface.get("scope") or ""

    # AX: walker can return all matches above threshold
    if not is_browser and ax.available():
        # ax.find returns only the best; for find_all we re-walk and collect.
        # Cheap alternative: call OCR which already gives all boxes.
        pass

    shot = _take_screenshot()
    # OCR — naturally returns multiple boxes
    if ocr.available():
        all_boxes = ocr.all_text(shot)
        q = target.strip().lower()
        import re as _re
        q_tokens = set(_re.findall(r"\w+", q))
        for b in all_boxes:
            tl = b["text"].lower()
            if tl == q:
                score = b["confidence"]
            elif q in tl or tl in q:
                score = (0.85 - min(0.3, abs(len(tl) - len(q)) / max(len(q), 1))) * b["confidence"]
            elif q_tokens:
                t_tokens = set(_re.findall(r"\w+", tl))
                if not t_tokens: continue
                ov = len(q_tokens & t_tokens) / len(q_tokens | t_tokens)
                score = 0.7 * ov * b["confidence"]
            else:
                continue
            if score >= min_conf:
                out.append({
                    "x": b["x"] + b["w"] / 2,
                    "y": b["y"] + b["h"] / 2,
                    "bbox": [b["x"], b["y"], b["w"], b["h"]],
                    "text": b["text"],
                    "confidence": round(score, 3),
                    "source": "ocr",
                })

    out.sort(key=lambda h: -h["confidence"])
    return _text({"target": target, "scope": scope, "count": len(out),
                  "hits": out[:limit]})


def tool_argus_send_keys(args):
    """Quick win G: parse 'cmd+shift+t' → key='t', modifiers='cmd+shift'."""
    combo = args["combo"].strip()
    if not combo:
        return _text({"error": "empty combo"})
    parts = [p.strip() for p in combo.replace("-", "+").split("+") if p.strip()]
    if not parts:
        return _text({"error": "no key tokens"})
    key_name = parts[-1]
    mods = "+".join(parts[:-1]) if len(parts) > 1 else None
    res = cgevent.key(key_name, modifiers=mods)
    intent.log("argus.send_keys", target=combo, outcome="ok")
    patterns.record_step("send_keys", {"combo": combo})
    return _text({"pressed": key_name, "modifiers": mods, "combo": combo, "result": res})


def tool_argus_scroll(args):
    coords = None
    if "x" in args and "y" in args:
        coords = (float(args["x"]), float(args["y"]))
    res = cgevent.scroll(args["direction"],
                         amount=int(args.get("amount", 5)),
                         coords=coords)
    intent.log("argus.scroll", target=args["direction"], outcome="ok")
    patterns.record_step("scroll", {"direction": args["direction"],
                                     "amount": int(args.get("amount", 5))})
    return _text({"scrolled": args["direction"], "result": res})


def tool_argus_open_app(args):
    res = cgevent.open_app(args["name"])
    intent.log("argus.open_app", target=args["name"], outcome="ok")
    patterns.record_step("open_app", {"name": args["name"]})
    prewarm.kick(args["name"])  # background OCR prewarm
    return _text(res)


def tool_argus_quit_app(args):
    res = cgevent.quit_app(args["name"])
    intent.log("argus.quit_app", target=args["name"], outcome="ok")
    return _text(res)


def tool_argus_exec_apple_script(args):
    code = args["code"]
    allow = bool(args.get("allow_dangerous", False))
    res = safety.safe_exec_apple_script(code, allow_dangerous=allow)
    intent.log("argus.exec_apple_script",
               outcome="ok" if res.get("ok") else ("blocked" if res.get("blocked_by_safety") else "fail"),
               observation={"stdout_len": len(res.get("stdout", "")),
                             "blocked": res.get("blocked_by_safety")})
    return _text(res)


def tool_argus_session(args):
    action = args["action"]
    name = args.get("name", "default")
    if action == "save":   return _text(session.save(name))
    if action == "load":   return _text(session.load(name))
    if action == "clear":  return _text(session.clear(name))
    if action == "list":   return _text({"sessions": session.list_saved()})
    if action == "detect_login": return _text(session.detect_login_required())
    return _text({"error": f"unknown action: {action}"})


def tool_argus_repl(args):
    action = args["action"]
    if action == "start":
        if not args.get("cmd"):
            return _text({"error": "cmd required"})
        return _text(repl.start(args["cmd"], name=args.get("name"),
                                cwd=args.get("cwd")))
    if action == "list":
        return _text(repl.list_procs())
    handle = args.get("handle")
    if handle is None:
        return _text({"error": "handle required (pid as string or name)"})
    try:
        h = int(handle)
    except (TypeError, ValueError):
        h = handle
    if action == "send":
        if "data" not in args:
            return _text({"error": "data required"})
        return _text(repl.send(h, args["data"], enter=bool(args.get("enter", True))))
    if action == "read":
        return _text(repl.read(h, timeout_s=float(args.get("timeout_s", 1.0))))
    if action == "kill":
        return _text(repl.kill(h))
    return _text({"error": f"unknown action: {action}"})


def tool_argus_history(args):
    return _text(intent.history(limit=int(args.get("limit", 50)),
                                intent=args.get("intent"),
                                scope=args.get("scope"),
                                outcome=args.get("outcome")))


def tool_argus_metrics(args):
    return _text(intent.metrics(reset=bool(args.get("reset", False))))


def tool_argus_cache(args):
    return _text(intent.cache_view(scope=args.get("scope"),
                                   limit=int(args.get("limit", 100))))


def tool_argus_autotune(args):
    action = args.get("action", "full")
    dry = bool(args.get("dry_run", False))
    if action == "report":  return _text(autotune.failure_report())
    if action == "promote": return _text(autotune.promote(dry_run=dry))
    if action == "full":    return _text(autotune.run_full(dry_run=dry))
    return _text({"error": f"unknown action: {action}"})


def tool_argus_session_begin(_):
    return _text(vision.VISION.pin())


def tool_argus_session_end(args):
    return _text(vision.VISION.unpin(unload=bool(args.get("unload", True))))


def tool_argus_vision_unload(_):
    vision.VISION._unload_now()
    return _text({"unloaded": True})


# ─── v0.5 handlers ─────────────────────────────────────────────────
def tool_argus_window(args):
    if args.get("frontmost"):
        res = screen.capture_frontmost()
    else:
        res = screen.capture_window(
            app=args.get("app"), bundle_id=args.get("bundle_id"),
            title=args.get("title"), index=int(args.get("index", 0)),
        )
    if not res.get("ok"):
        return _text(res)
    path = res["path"]
    max_dim = int(args.get("max_dim", 1600))
    try:
        from PIL import Image
        img = Image.open(path)
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim))
            import tempfile as _tf
            path = _tf.NamedTemporaryFile(suffix=".png", delete=False).name
            img.save(path)
    except Exception:
        pass
    with open(path, "rb") as f:
        b = f.read()
    return [
        {"type": "image", "data": base64.b64encode(b).decode(), "mimeType": "image/png"},
        {"type": "text", "text": json.dumps({"window": res.get("window"), "path": path}, default=str)},
    ]


def tool_argus_window_list(args):
    wins = screen.list_windows()
    if args.get("app"):
        n = args["app"].lower()
        wins = [w for w in wins if n in (w["owner"] or "").lower()]
    return _text({"count": len(wins), "windows": wins})


def tool_argus_pattern(args):
    action = args["action"]
    if action == "record_begin":
        return _text(patterns.record_begin(args["name"], args["scope"], args["intent_label"]))
    if action == "record_step":
        n = patterns.record_step(args["op"], args.get("args") or {},
                                  expect_verify=args.get("expect_verify", "ok"))
        return _text({"ok": True, "active_recordings_updated": n})
    if action == "record_end":
        return _text(patterns.record_end(args["name"], ok=bool(args.get("ok", True)),
                                          save=bool(args.get("save", True))))
    if action == "lookup":
        hit = patterns.lookup(args["scope"], args["intent_label"])
        return _text(hit or {"hit": False})
    if action == "list":
        return _text({"patterns": patterns.list_patterns(scope=args.get("scope"),
                                                          limit=int(args.get("limit", 100)))})
    if action == "delete":
        return _text(patterns.delete_pattern(args["scope"], args["intent_label"]))
    return _text({"error": f"unknown action: {action}"})


def tool_argus_policy(args):
    action = args["action"]
    if action == "doctor":           return _text(policy.doctor())
    if action == "write_default":    return _text(policy.write_default_policy())
    if action == "reload":           return _text({"loaded": list(policy.load(force=True).keys())})
    if action == "check_app":        return _text({"scope": args.get("scope"),
                                                     "result": policy.app_allowed(args.get("scope", ""))})
    if action == "check_destructive":
        v = policy.is_destructive(args.get("target", ""))
        return _text({"target": args.get("target"), "destructive": bool(v),
                       "matched_verb": v})
    return _text({"error": f"unknown action: {action}"})


def tool_argus_setup(_):
    return _text(wizard.run())


def tool_argus_uninstall(args):
    action = args.get("action", "plan")
    if action == "plan":
        return _text(_uninstall.plan())
    if action == "execute":
        return _text(_uninstall.execute(force_full=bool(args.get("force_full", False)),
                                         kill_chrome=bool(args.get("kill_chrome", True))))
    return _text({"error": f"unknown action: {action}"})


def tool_argus_dashboard(args):
    action = args.get("action", "start")
    if action == "start":   return _text(dashboard.start(port=int(args.get("port", 9999))))
    if action == "stop":    return _text(dashboard.stop())
    if action == "status":  return _text(dashboard.status())
    return _text({"error": f"unknown action: {action}"})


def tool_argus_chrome(args):
    action = args["action"]
    if action == "status":         return _text(chrome_admin.status())
    if action == "boot":           return _text(chrome_admin.boot(headless=bool(args.get("headless", False))))
    if action == "kill":           return _text(chrome_admin.kill())
    if action == "install_agent":  return _text(chrome_admin.install_agent())
    return _text({"error": f"unknown action: {action}"})


def tool_argus_skills(args):
    action = args["action"]
    if action == "index":      return _text(registry.index())
    if action == "list_local": return _text(registry.list_local())
    if action == "install":
        if not args.get("name"):
            return _text({"error": "name required"})
        return _text(registry.install(args["name"], kind=args.get("kind", "auto")))
    return _text({"error": f"unknown action: {action}"})


def tool_argus_chain(args):
    return _text(_chain.run(args["steps"], handlers=HANDLERS,
                              on_error=args.get("on_error", "abort")))


def tool_argus_workspace(args):
    return _text(_workspace.run_tasks(args["tasks"], handlers=HANDLERS,
                                        return_to=args.get("return_to")))


def tool_argus_workspace_capture_all(_):
    return _text(_workspace.background_capture_all())


def tool_argus_predict_next(args):
    return _text(_predict.predict(scope=args.get("scope"),
                                    top_n=int(args.get("top_n", 5))))


def tool_argus_benchmark(args):
    return _text(benchmark.run(iterations=int(args.get("iterations", 10))))


def tool_argus_health(args):
    action = args.get("action", "status")
    if action == "start":  return _text(health.start(float(args.get("interval_s", 60))))
    if action == "stop":   return _text(health.stop())
    if action == "status": return _text(health.status())
    return _text({"error": f"unknown action: {action}"})


def tool_argus_dom_query(args):
    return _text({"selector": args["selector"],
                  "results": cdp_raw.query_selector_all(args["selector"],
                                                          attrs=args.get("attrs"),
                                                          max_results=int(args.get("max_results", 50)))})


def tool_argus_install_log_rotation(args):
    return _text(safety.install_log_rotation_agent(hour=int(args.get("hour", 3))))


def tool_argus_macros(args):
    action = args["action"]
    if action == "list":
        return _text(macros.list_macros())
    if action == "run":
        if not args.get("macro_name"):
            return _text({"error": "macro_name required"})
        return _text(macros.run(args["macro_name"], handlers=HANDLERS))
    return _text({"error": f"unknown action: {action}"})


def tool_argus_workflow_template(args):
    if args.get("list"):
        if not os.path.isdir(WORKFLOWS_DIR):
            return _text({"templates": []})
        names = sorted(os.path.splitext(f)[0]
                        for f in os.listdir(WORKFLOWS_DIR)
                        if f.endswith(".json"))
        return _text({"templates": names})
    name = args.get("name")
    if not name:
        return _text({"error": "name required (or pass list=true)"})
    path = os.path.join(WORKFLOWS_DIR, f"{name}.json")
    if not os.path.isfile(path):
        return _text({"error": f"template not found: {path}"})
    with open(path, encoding="utf-8") as f:
        wf = json.load(f)
    return _text(_workflow.run(wf, handlers=HANDLERS,
                                 extra_vars=args.get("vars"),
                                 dry_run=bool(args.get("dry_run", False))))


def tool_argus_diff_screens(args):
    return _text(diff_screens.compare(args["path_a"], args["path_b"],
                                       threshold=int(args.get("threshold", 30))))


def tool_argus_notes(args):
    return _text(apple_apps.create_note(args["title"], args["body"],
                                          folder=args.get("folder", "Notes"),
                                          account=args.get("account")))


def tool_argus_reminders(args):
    return _text(apple_apps.create_reminder(args["title"],
                                              notes=args.get("notes", ""),
                                              list_name=args.get("list_name"),
                                              due_date=args.get("due_date")))


def tool_argus_replay(args):
    return _text(_replay.replay(args["scope"], args["intent_label"],
                                  handlers=HANDLERS,
                                  dry_run=bool(args.get("dry_run", False)),
                                  step_delay_s=float(args.get("step_delay_s", 0.25))))


def tool_argus_workflow(args):
    return _text(_workflow.run(args["workflow"],
                                 handlers=HANDLERS,
                                 extra_vars=args.get("extra_vars"),
                                 dry_run=bool(args.get("dry_run", False))))


def tool_argus_extract(args):
    return _text(extract.extract(args["schema"], window_app=args.get("window_app")))


def tool_argus_ask(args):
    q = args["question"]
    win = args.get("window_app")
    if win:
        cap = screen.capture_window(app=win, out_path="/tmp/argus_ask.png")
    else:
        cap = screen.capture_frontmost(out_path="/tmp/argus_ask.png")
    if not cap.get("ok"):
        return _text({"ok": False, "error": cap.get("error")})
    ans = vision.VISION.ask(cap["path"], q)
    intent.log("argus.ask", target=q, outcome="ok" if ans else "fail",
               source="vision", observation={"answer_chars": len(ans or "")})
    return _text({"answer": ans, "question": q, "screenshot": cap["path"],
                  "window": cap.get("window")})


def tool_argus_secure_session(args):
    action = args["action"]
    name = args.get("name", "default")
    if action == "encrypt": return _text(secure_session.encrypt_jar(name))
    if action == "decrypt": return _text(secure_session.decrypt_jar(name))
    if action == "list":    return _text(secure_session.list_jars())
    return _text({"error": f"unknown action: {action}"})


def tool_argus_log_rotate(_):
    return _text(safety.rotate_logs())


def tool_argus_cu_route(args):
    """Computer Use shim. Translates CU-style payloads to native argus calls."""
    action = (args.get("action") or "").lower().replace("-", "_")
    coord = args.get("coordinate")
    text = args.get("text")

    # Map Anthropic's Computer Use action names → argus
    if action in ("screenshot", "screen_shot"):
        return tool_argus_see({"max_dim": 1600})
    if action in ("left_click", "click", "mouse_click"):
        if coord and len(coord) == 2:
            return tool_argus_click({"target": f"{int(coord[0])},{int(coord[1])}"})
        if text:  # text = visual target description
            return tool_argus_click({"target": text})
        return _text({"error": "left_click needs coordinate or text"})
    if action == "double_click":
        if coord and len(coord) == 2:
            return tool_argus_click({"target": f"{int(coord[0])},{int(coord[1])}", "double": True})
        if text:
            return tool_argus_click({"target": text, "double": True})
        return _text({"error": "double_click needs coordinate or text"})
    if action in ("right_click", "middle_click"):
        return _text({"error": f"{action} not yet supported by argus shim"})
    if action == "mouse_move":
        return _text({"ok": True, "noop": True,
                       "note": "argus doesn't track cursor; targets are resolved per-click"})
    if action in ("type", "type_text"):
        if not text:
            return _text({"error": "type needs text"})
        # use paste route for performance on long strings
        return tool_argus_paste({"text": text}) if len(text) > 80 \
               else tool_argus_type({"text": text})
    if action in ("key", "key_press"):
        if not text:
            return _text({"error": "key needs text"})
        return tool_argus_send_keys({"combo": text})
    if action == "scroll":
        direction = "down"
        if coord and len(coord) == 2:
            dy = coord[1]
            direction = "up" if dy < 0 else "down"
        return tool_argus_scroll({"direction": direction,
                                   "amount": int(args.get("duration", 5))})
    if action in ("cursor_position", "wait"):
        return _text({"ok": True, "noop": True, "action": action})
    return _text({"error": f"unsupported CU action: {action}",
                  "supported": ["screenshot", "left_click", "double_click",
                                 "type", "key", "scroll", "mouse_move",
                                 "wait", "cursor_position"]})


HANDLERS = {t["name"]: globals()[f"tool_{t['name']}"] for t in TOOLS}


# ─── JSON-RPC plumbing ────────────────────────────────────────────
def _send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _ok(rid, result): _send({"jsonrpc": "2.0", "id": rid, "result": result})
def _err(rid, code, msg): _send({"jsonrpc": "2.0", "id": rid,
                                 "error": {"code": code, "message": msg}})


def _main_sync():
    """Legacy synchronous dispatch loop (kept for tests + emergency fallback)."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            _err(None, -32700, f"parse: {e}")
            continue
        method = req.get("method")
        rid = req.get("id")
        params = req.get("params") or {}
        try:
            if method == "initialize":
                _ok(rid, {"protocolVersion": PROTO_VERSION,
                          "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                          "capabilities": {"tools": {}}})
            elif method == "notifications/initialized":
                continue
            elif method == "tools/list":
                _ok(rid, {"tools": TOOLS})
            elif method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments") or {}
                fn = HANDLERS.get(name)
                if not fn:
                    _err(rid, -32601, f"unknown tool: {name}")
                    continue
                t0 = time.monotonic()
                try:
                    result = fn(arguments)
                    intent.metrics_record(name, True, (time.monotonic() - t0) * 1000)
                    _ok(rid, {"content": result, "isError": False})
                except Exception as e:
                    intent.metrics_record(name, False, (time.monotonic() - t0) * 1000)
                    _ok(rid, {"content": [{"type": "text",
                                           "text": f"error: {e}\n{traceback.format_exc()}"}],
                              "isError": True})
            elif method == "ping":
                _ok(rid, {})
            elif method.startswith("notifications/"):
                continue
            else:
                _err(rid, -32601, f"method not implemented: {method}")
        except Exception as e:
            _err(rid, -32603, f"internal: {e}")


def main():
    # asyncio dispatch by default; ARGUS_ASYNC=0 forces the legacy sync loop.
    use_async = os.environ.get("ARGUS_ASYNC", "1") != "0"
    if use_async:
        try:
            asyncio_runtime.run(HANDLERS, TOOLS,
                                proto=PROTO_VERSION, name=SERVER_NAME, version=SERVER_VERSION,
                                metrics_record=intent.metrics_record)
            return
        except Exception:
            # Fall back to sync if asyncio fails to start (rare)
            pass
    _main_sync()


if __name__ == "__main__":
    main()
