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

from core import cascade, intent, router, vision, verify, session, repl
from adapters import ax, ocr, cdp, cgevent

PROTO_VERSION = "2024-11-05"
SERVER_NAME = "argus"
SERVER_VERSION = "0.3.0"


# ─── tool catalog ─────────────────────────────────────────────────────
TOOLS = [
    {"name": "argus_doctor",
     "description": "Diagnostics: AX, OCR, CDP/browser-harness, vision singleton, surface router. First call.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},

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
     "description": "Run arbitrary AppleScript. Escape hatch.",
     "inputSchema": {"type": "object", "properties": {
         "code": {"type": "string"}
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
]


# ─── helpers ──────────────────────────────────────────────────────
def _text(v):
    return [{"type": "text",
             "text": v if isinstance(v, str) else json.dumps(v, default=str, indent=2)}]


def _take_screenshot() -> str:
    return cgevent.screenshot("/tmp/argus_prime_shot.png")


# ─── tool handlers ────────────────────────────────────────────────
def tool_argus_doctor(_):
    info = {
        "argus_version": SERVER_VERSION,
        "surface_router": router.doctor(),
        "ax": ax.doctor(),
        "ocr": ocr.doctor(),
        "cdp": cdp.doctor(),
        "vision": vision.VISION.status(),
        "cgevent": cgevent.doctor(),
        "data_dir": str(intent.DATA_DIR),
    }
    return _text(info)


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
    return _text(out)


def tool_argus_type(args):
    text = args["text"]
    force = bool(args.get("force_secure", False))
    if not force and ax.available() and ax.is_secure_field_focused():
        return _text({"typed": False,
                      "blocked": "AXSecureTextField focused. Pass force_secure=true to override."})
    res = cgevent.type_text(text)
    intent.log("argus.type", outcome="ok",
               observation={"chars": len(text)})
    return _text({"typed": True, "chars": len(text), "result": res})


def tool_argus_key(args):
    res = cgevent.key(args["name"], modifiers=args.get("modifiers"))
    intent.log("argus.key", target=args["name"], outcome="ok")
    return _text({"pressed": args["name"], "modifiers": args.get("modifiers"),
                  "result": res})


def tool_argus_scroll(args):
    coords = None
    if "x" in args and "y" in args:
        coords = (float(args["x"]), float(args["y"]))
    res = cgevent.scroll(args["direction"],
                         amount=int(args.get("amount", 5)),
                         coords=coords)
    intent.log("argus.scroll", target=args["direction"], outcome="ok")
    return _text({"scrolled": args["direction"], "result": res})


def tool_argus_open_app(args):
    res = cgevent.open_app(args["name"])
    intent.log("argus.open_app", target=args["name"], outcome="ok")
    return _text(res)


def tool_argus_quit_app(args):
    res = cgevent.quit_app(args["name"])
    intent.log("argus.quit_app", target=args["name"], outcome="ok")
    return _text(res)


def tool_argus_exec_apple_script(args):
    res = cgevent.exec_apple_script(args["code"])
    intent.log("argus.exec_apple_script", outcome="ok" if res.get("ok") else "fail",
               observation={"stdout_len": len(res.get("stdout", ""))})
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


def tool_argus_session_begin(_):
    return _text(vision.VISION.pin())


def tool_argus_session_end(args):
    return _text(vision.VISION.unpin(unload=bool(args.get("unload", True))))


def tool_argus_vision_unload(_):
    vision.VISION._unload_now()
    return _text({"unloaded": True})


HANDLERS = {t["name"]: globals()[f"tool_{t['name']}"] for t in TOOLS}


# ─── JSON-RPC plumbing ────────────────────────────────────────────
def _send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _ok(rid, result): _send({"jsonrpc": "2.0", "id": rid, "result": result})
def _err(rid, code, msg): _send({"jsonrpc": "2.0", "id": rid,
                                 "error": {"code": code, "message": msg}})


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


if __name__ == "__main__":
    main()
