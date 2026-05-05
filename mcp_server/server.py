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

from core import cascade, intent, router, vision, verify, session, repl, autotune
from adapters import ax, ocr, cdp, cgevent

PROTO_VERSION = "2024-11-05"
SERVER_NAME = "argus"
SERVER_VERSION = "0.4.0"


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
    return _text({"pressed": key_name, "modifiers": mods, "combo": combo, "result": res})


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
