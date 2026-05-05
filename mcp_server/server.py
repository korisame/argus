"""Argus MCP server v0.2.0.

Architecture:
  client ──► MCP (stdio JSON-RPC)
                │
                ▼
        ┌───────────────┐
        │  server.py    │   tool dispatch + history/metrics + diff verify
        └─┬─────────────┘
          │
          ├─ daemon.DAEMON  →  in-process `import argus` (warm Moondream)
          │       fallback: subprocess `argus <cmd>` (legacy path)
          │
          ├─ routing.resolve(target)  →  AX → OCR → Vision cascade
          │       ax.py (AXUIElement walker)
          │       ocr.py (Apple Vision VNRecognizeTextRequest)
          │
          ├─ overlay.py  →  annotated screenshot (low-confidence clicks)
          ├─ diff.py     →  pre/post screenshot verifier
          └─ history.py  →  ~/.argus/intent.jsonl reader + in-process metrics
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

# Make imports work when launched as `python3 server.py` (not `-m`)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from mcp_server import ax, ocr, routing, daemon, overlay, diff, history
except Exception:
    import ax, ocr, routing, daemon, overlay, diff, history  # type: ignore

PROTO_VERSION = "2024-11-05"
SERVER_NAME = "argus"
SERVER_VERSION = "0.2.0"


# ─────────────────────── Tool catalog ───────────────────────
TOOLS = [
    {"name": "argus_doctor",
     "description": "Diagnostics: argus version, AX availability, OCR availability, vision backend, daemon status, frontmost app. Call first if anything misbehaves.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},

    {"name": "argus_see",
     "description": "Take a fresh screenshot of the entire screen and return as base64 PNG. Use this to SEE before clicking.",
     "inputSchema": {"type": "object", "properties": {
         "max_dim": {"type": "integer", "default": 1600,
                     "description": "Downscale longest side to <= this many pixels."}
     }, "additionalProperties": False}},

    {"name": "argus_surface",
     "description": "Return frontmost app: bundle_id, name, surface ('browser'|'desktop'), URL/title if browser. Cheap.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},

    {"name": "argus_click",
     "description": "Click an element via cascade resolver (AX → OCR → vision). Returns {clicked:bool, x, y, bbox?, source, confidence, attempts, verified, annotated_b64?}. Pass coords='x,y' for raw pixel click. `verify=true` (default) takes a post-action screenshot diff and reports whether the click had visible effect.",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string", "description": "visible text / NL description, or 'x,y'"},
         "double": {"type": "boolean", "default": False},
         "verify": {"type": "boolean", "default": True},
         "min_confidence": {"type": "number", "default": 0.55},
         "annotate_below": {"type": "number", "default": 0.75,
                             "description": "Return annotated screenshot when confidence < this."}
     }, "required": ["target"], "additionalProperties": False}},

    {"name": "argus_find",
     "description": "Resolve target to coords WITHOUT clicking. Returns {x, y, bbox?, source, confidence, attempts, candidates?}. Useful for verification or to feed coords into another tool.",
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string"},
         "annotate": {"type": "boolean", "default": False}
     }, "required": ["target"], "additionalProperties": False}},

    {"name": "argus_type",
     "description": "Type text into focused field. Routes via CDP for browsers, AppleScript otherwise. Refuses if focus is on AXSecureTextField (password).",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string"},
         "force_secure": {"type": "boolean", "default": False,
                          "description": "Override password-field guard. Default false."}
     }, "required": ["text"], "additionalProperties": False}},

    {"name": "argus_key",
     "description": "Press a special key. Common: Return, Tab, Escape, ArrowUp/Down/Left/Right, Backspace. Modifiers: 'cmd' / 'shift+cmd' / 'ctrl' / 'alt'.",
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string"},
         "modifiers": {"type": "string"}
     }, "required": ["name"], "additionalProperties": False}},

    {"name": "argus_scroll",
     "description": "Scroll up/down/left/right at the cursor. Browser uses CDP, native uses CGEvent.",
     "inputSchema": {"type": "object", "properties": {
         "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
         "amount": {"type": "integer", "default": 5}
     }, "required": ["direction"], "additionalProperties": False}},

    {"name": "argus_open_app",
     "description": "Launch or focus a macOS app by name (e.g. 'Safari', 'Anteprima', 'System Settings').",
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string"}
     }, "required": ["name"], "additionalProperties": False}},

    {"name": "argus_quit_app",
     "description": "Quit a macOS app gracefully via AppleScript.",
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string"}
     }, "required": ["name"], "additionalProperties": False}},

    {"name": "argus_exec_apple_script",
     "description": "Run arbitrary AppleScript. Escape hatch for app-specific automation when CGEvent + vision aren't enough.",
     "inputSchema": {"type": "object", "properties": {
         "code": {"type": "string"}
     }, "required": ["code"], "additionalProperties": False}},

    {"name": "argus_run",
     "description": "Run arbitrary Python code with the argus module pre-imported. Use for multi-step macros.",
     "inputSchema": {"type": "object", "properties": {
         "code": {"type": "string"}
     }, "required": ["code"], "additionalProperties": False}},

    {"name": "argus_session_begin",
     "description": "Pin the Moondream model in RAM for a burst of vision calls (no auto-unload). Pair with argus_session_end.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},

    {"name": "argus_session_end",
     "description": "Unpin the Moondream model and free RAM immediately (default) or just unpin (unload=false).",
     "inputSchema": {"type": "object", "properties": {
         "unload": {"type": "boolean", "default": True}
     }, "additionalProperties": False}},

    {"name": "argus_vision_unload",
     "description": "Free RAM held by the Moondream model right now. Next vision call cold-reloads (~10-30s).",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},

    {"name": "argus_history",
     "description": "Read recent entries from ~/.argus/intent.jsonl (most recent first). Optional filter by tool name.",
     "inputSchema": {"type": "object", "properties": {
         "limit": {"type": "integer", "default": 50},
         "tool": {"type": "string"}
     }, "additionalProperties": False}},

    {"name": "argus_metrics",
     "description": "Per-tool latency (p50/p95/avg) and success/error counts for this server process.",
     "inputSchema": {"type": "object", "properties": {
         "reset": {"type": "boolean", "default": False}
     }, "additionalProperties": False}},
]


# ─────────────────────── argus CLI fallback ───────────────────────
def _argus_cli_path():
    return shutil.which("argus")


def _run_argus_cli(*args, timeout=60, input_text=None):
    cli = _argus_cli_path()
    if not cli:
        raise RuntimeError("argus CLI not on PATH and in-process import failed")
    r = subprocess.run([cli, *args], capture_output=True, text=True,
                       timeout=timeout, input=input_text, env={**os.environ})
    out = (r.stdout or "").rstrip()
    err = (r.stderr or "").rstrip()
    if r.returncode != 0:
        raise RuntimeError(f"argus {args[0]} exited {r.returncode}\nstdout:\n{out}\nstderr:\n{err}")
    return out


def _try_in_process(call, *args, **kwargs):
    """Run via daemon if importable, else None (caller falls back to CLI)."""
    if daemon.DAEMON.available():
        try:
            return daemon.DAEMON.call(call, *args, **kwargs)
        except Exception:
            return None
    return None


# ─────────────────────── helpers ───────────────────────
def _text(value):
    return [{"type": "text", "text": value if isinstance(value, str) else json.dumps(value, default=str, indent=2)}]


def _json_text(obj):
    return [{"type": "text", "text": json.dumps(obj, default=str, indent=2)}]


def _take_screenshot(max_dim=1600) -> str:
    """Capture a fresh screenshot, return file path."""
    # argus.see() returns a path string
    out = _try_in_process("see")
    if isinstance(out, str) and out:
        return out
    if isinstance(out, dict) and "screenshot" in out:
        return out["screenshot"]
    # CLI fallback
    raw = _run_argus_cli("see", timeout=15)
    try:
        return json.loads(raw)["screenshot"]
    except Exception:
        # CLI may print bare path
        return raw.strip()


def _surface_info() -> dict:
    """Use argus.page_info() — surface() only returns the type string."""
    out = _try_in_process("page_info")
    if isinstance(out, dict):
        return out
    raw = _run_argus_cli("surface", timeout=10)
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}


def _vision_callable(target: str, screenshot_path: str | None) -> dict | None:
    """Adapter: argus.vision.find or CLI `argus click --dry-run` to get coords."""
    # Prefer in-process
    if daemon.DAEMON.available():
        try:
            res = daemon.DAEMON.vision_call("find", target, screenshot_path)
            if res and "x" in res:
                return res
        except Exception:
            pass
    # CLI fallback: `argus find <target>` (assumes CLI exposes this; if not, click --dry-run)
    try:
        raw = _run_argus_cli("find", target, timeout=120)
        return json.loads(raw)
    except Exception:
        try:
            raw = _run_argus_cli("click", target, "--dry-run", timeout=120)
            return json.loads(raw)
        except Exception:
            return None


def _do_click(x: float, y: float, double: bool = False) -> None:
    """Perform the actual click at pixel coords (skip vision since we already have coords)."""
    if daemon.DAEMON.available():
        try:
            # argus.click(target, *, vision=True, coords=None, double=False)
            daemon.DAEMON.call("click", "", vision=False,
                               coords=(int(x), int(y)), double=double)
            return
        except Exception:
            pass
    extra = ["--double"] if double else []
    _run_argus_cli("click", f"{int(x)},{int(y)}", *extra, timeout=30)


# ─────────────────────── tool handlers ───────────────────────
def tool_argus_doctor(args):
    info = {
        "argus_plugin_version": SERVER_VERSION,
        "daemon": daemon.DAEMON.status(),
        "ax": ax.doctor(),
        "ocr": ocr.doctor(),
    }
    # Underlying argus core — `doctor` is a CLI-only command, not a module function,
    # so always shell out for it.
    try:
        info["argus_core"] = json.loads(_run_argus_cli("doctor", timeout=15))
    except Exception as e:
        info["argus_core_error"] = str(e)
    return _json_text(info)


def tool_argus_see(args):
    max_dim = int(args.get("max_dim", 1600))
    path = _take_screenshot(max_dim=max_dim)
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


def tool_argus_surface(args):
    return _json_text(_surface_info())


def tool_argus_find(args):
    target = args["target"]
    annotate = bool(args.get("annotate", False))
    shot = _take_screenshot()
    res = routing.resolve(target, screenshot_path=shot, vision_callable=_vision_callable)
    out = dict(res)
    if annotate and "x" in res:
        out["annotated"] = overlay.annotate(shot, res["x"], res["y"],
                                            res.get("bbox"),
                                            label=f"{res.get('source')} {res.get('confidence', 0):.2f}")
    return _json_text(out)


def tool_argus_click(args):
    target = args["target"]
    double = bool(args.get("double", False))
    verify = bool(args.get("verify", True))
    min_conf = float(args.get("min_confidence", 0.55))
    ann_below = float(args.get("annotate_below", 0.75))

    shot_before = _take_screenshot() if verify else None
    if not shot_before:
        shot_before = _take_screenshot()  # always need it for routing

    res = routing.resolve(target, screenshot_path=shot_before,
                          vision_callable=_vision_callable, min_confidence=min_conf)
    if res.get("source") is None:
        return _json_text({"clicked": False, **res})

    x, y = res["x"], res["y"]
    _do_click(x, y, double=double)

    out = {
        "clicked": True,
        "x": x, "y": y,
        "bbox": res.get("bbox"),
        "source": res.get("source"),
        "confidence": res.get("confidence"),
        "text": res.get("text"),
        "attempts": res.get("attempts", []),
    }

    # Annotate when low-confidence
    if (res.get("confidence") or 0) < ann_below:
        try:
            ann = overlay.annotate(shot_before, x, y, res.get("bbox"),
                                   label=f"{res.get('source')} {res.get('confidence', 0):.2f}")
            out["annotated_b64"] = ann["b64"]
            out["annotated_mime"] = ann["mime"]
        except Exception as e:
            out["annotate_error"] = str(e)

    # Verify
    if verify:
        time.sleep(0.35)
        try:
            shot_after = _take_screenshot()
            v = diff.verify(shot_before, shot_after, bbox=res.get("bbox"))
            out["verified"] = v
        except Exception as e:
            out["verify_error"] = str(e)

    return _json_text(out)


def tool_argus_type(args):
    text = args["text"]
    force = bool(args.get("force_secure", False))
    if not force and ax.available() and ax.is_secure_field_focused():
        return _json_text({
            "typed": False,
            "blocked": "AXSecureTextField focused — refusing to type. Pass force_secure=true if you really mean it.",
        })
    if daemon.DAEMON.available():
        try:
            daemon.DAEMON.call("type_text", text)
            return _json_text({"typed": True, "chars": len(text), "via": "in-process"})
        except Exception:
            pass
    out = _run_argus_cli("type", text, timeout=30)
    return _text(out)


def tool_argus_key(args):
    name = args["name"]
    mods = args.get("modifiers")
    if daemon.DAEMON.available():
        try:
            daemon.DAEMON.call("key", name, modifiers=mods)
            return _json_text({"pressed": name, "modifiers": mods, "via": "in-process"})
        except Exception:
            pass
    extra = ["--mod", mods] if mods else []
    return _text(_run_argus_cli("key", name, *extra, timeout=10))


def tool_argus_scroll(args):
    direction = args["direction"]
    amount = int(args.get("amount", 5))
    if daemon.DAEMON.available():
        try:
            daemon.DAEMON.call("scroll", direction, amount=amount)
            return _json_text({"scrolled": direction, "amount": amount, "via": "in-process"})
        except Exception:
            pass
    return _text(_run_argus_cli("scroll", direction, "--amount", str(amount), timeout=10))


def tool_argus_open_app(args):
    name = args["name"]
    if daemon.DAEMON.available():
        try:
            daemon.DAEMON.call("open_app", name)
            return _json_text({"opened": name, "via": "in-process"})
        except Exception:
            pass
    return _text(_run_argus_cli("open", name, timeout=15))


def tool_argus_quit_app(args):
    name = args["name"]
    # argus module doesn't expose quit_app — use AppleScript via the CLI's exec
    if daemon.DAEMON.available():
        try:
            script = f'tell application "{name}" to quit'
            daemon.DAEMON.call("exec_apple_script", script)
            return _json_text({"quit": name, "via": "in-process apple_script"})
        except Exception:
            pass
    try:
        return _text(_run_argus_cli("quit", name, timeout=10))
    except Exception:
        # CLI may not have a `quit` subcommand either — final fallback to bare osascript
        import subprocess as _sp
        _sp.run(["osascript", "-e", f'tell application "{name}" to quit'], check=False, timeout=10)
        return _json_text({"quit": name, "via": "osascript"})


def tool_argus_exec_apple_script(args):
    code = args["code"]
    if daemon.DAEMON.available():
        try:
            res = daemon.DAEMON.call("exec_apple_script", code)
            return _json_text({"ok": True, "result": res, "via": "in-process"})
        except Exception:
            pass
    return _text(_run_argus_cli("exec", code, timeout=60))


def tool_argus_run(args):
    code = args["code"]
    if daemon.DAEMON.available():
        try:
            # Execute in a namespace with argus pre-imported
            import argus as _argus  # noqa
            ns = {"argus": _argus}
            for n in ("see", "click", "type_text", "key", "scroll", "open_app",
                      "quit_app", "surface", "page_info"):
                if hasattr(_argus, n):
                    ns[n] = getattr(_argus, n)
            from io import StringIO
            buf = StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                exec(compile(code, "<argus_run>", "exec"), ns, ns)
            finally:
                sys.stdout = old
            return _text(buf.getvalue() or "(no stdout)")
        except Exception:
            pass
    return _text(_run_argus_cli("run", "-c", code, timeout=180))


def tool_argus_session_begin(args):
    return _json_text(daemon.DAEMON.session_begin())


def tool_argus_session_end(args):
    unload = bool(args.get("unload", True))
    return _json_text(daemon.DAEMON.session_end(unload=unload))


def tool_argus_vision_unload(args):
    if daemon.DAEMON.available():
        try:
            daemon.DAEMON.vision_call("vision_unload")
            return _json_text({"unloaded": True, "via": "in-process"})
        except Exception:
            pass
    code = "import argus.vision as v; import json; print(json.dumps(v.vision_unload()))"
    return _text(_run_argus_cli("run", "-c", code, timeout=20))


def tool_argus_history(args):
    return _json_text(history.history(limit=int(args.get("limit", 50)), tool=args.get("tool")))


def tool_argus_metrics(args):
    out = history.metrics()
    if args.get("reset"):
        history.reset_metrics()
    return _json_text(out)


HANDLERS = {t["name"]: globals()[f"tool_{t['name']}"] for t in TOOLS}


# ─────────────────────── JSON-RPC plumbing ───────────────────────
def _send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _ok(rid, result):
    _send({"jsonrpc": "2.0", "id": rid, "result": result})


def _err(rid, code, message):
    _send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})


def main():
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
                _ok(rid, {
                    "protocolVersion": PROTO_VERSION,
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "capabilities": {"tools": {}},
                })
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
                    history.record(name, True, (time.monotonic() - t0) * 1000)
                    _ok(rid, {"content": result, "isError": False})
                except Exception as e:
                    history.record(name, False, (time.monotonic() - t0) * 1000)
                    _ok(rid, {
                        "content": [{"type": "text",
                                     "text": f"error: {e}\n{traceback.format_exc()}"}],
                        "isError": True,
                    })
            elif method == "ping":
                _ok(rid, {})
            elif method.startswith("notifications/"):
                continue
            else:
                _err(rid, -32601, f"method not implemented: {method}")
        except Exception as e:
            _err(rid, -32603, f"internal: {e}")


if __name__ == "__main__":
    main()
