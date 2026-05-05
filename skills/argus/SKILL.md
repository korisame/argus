---
name: argus
description: Vision-grounded computer automation with hybrid AX + OCR + Moondream routing. Use when the user wants to control browser, native macOS apps, or anything visible on the screen — open apps, click buttons, type text, scrape pages, run multi-app workflows. Tools span Chrome (CDP), Finder/Mail/Anteprima/System Settings/Excel/etc. (AX + CGEvent + AppleScript), with Apple Vision OCR for exact-text targets and Moondream visual grounding for natural-language targets like "the gear icon top right".
---

# argus v0.2

Vision-grounded automation across **browser + desktop + every macOS app**.
v0.2 adds a hybrid resolver (AX → OCR → Vision), in-process daemon, and
self-verifying actions.

## When to use

- "Apri X e fai Y" / "Open X and do Y" — anything that involves a UI step
- Clicking icons, buttons, links — including ones without text labels
- Filling forms, typing into fields, pressing keyboard shortcuts
- Multi-app workflows (e.g. extract data from a website → paste into Excel)
- Anything where computer-use's pure pixel-clicking would be brittle

## Mental model

Every click goes through a **cascade resolver** — fastest deterministic
layer first, vision only when needed:

```
target string
    │
    ▼
┌────────────┐ raw "x,y"          → coords (instant)
│  routing   │ deterministic AX   → ~50ms, native apps only
│  cascade   │ Apple Vision OCR   → ~150ms, exact text on screen
└────────────┘ Moondream vision   → ~1-3s, semantic descriptions
    │
    ▼
action engine: CDP for browsers, CGEvent / AppleScript otherwise
```

You don't pick the layer — `argus_click` and `argus_find` pick by target
shape and what's available. Result includes `source` so you can see what
actually grounded the click.

## Core operations

```
argus_doctor                       # versions, AX/OCR/vision availability, daemon status
argus_see                          # screenshot → base64 PNG
argus_surface                      # frontmost app + URL/title
argus_find    target               # resolve to coords WITHOUT clicking
argus_click   target               # cascade resolve + click + verify
argus_type    text                 # types into focused field (refuses on AXSecureTextField)
argus_key     name [modifiers]     # special keys
argus_scroll  direction [amount]
argus_open_app  / argus_quit_app
argus_exec_apple_script  code
argus_run     code                 # python with argus pre-imported
argus_session_begin / argus_session_end
argus_vision_unload
argus_history [limit] [tool]       # ~/.argus/intent.jsonl tail
argus_metrics [reset]              # per-tool latency + success rate
```

## Click semantics (important)

`argus_click` returns:
```json
{
  "clicked": true,
  "x": 1240, "y": 88,
  "bbox": [1224, 72, 32, 32],
  "source": "ax | ocr | vision | coords",
  "confidence": 0.92,
  "attempts": ["ax", "ocr"],
  "verified": {"ok": true, "reason": "region delta 5.4%", "global_distance": 11},
  "annotated_b64": "..."   // only if confidence < annotate_below (default 0.75)
}
```

- `verified.ok: false` means the click landed but **nothing visibly changed**
  — likely missed, or hit a no-op. Re-screenshot and try a different target.
- `annotated_b64` is your best friend on low-confidence clicks: shows the
  bbox + crosshair where argus actually clicked.
- Pass `verify: false` for fire-and-forget (e.g. opening a known menu).

## Decision flow

1. **`argus_surface`** if you don't know where you are.
2. **For browsers** (`surface == "browser"`): argus delegates clicks/typing
   to CDP via `browser-harness`. Use `browser-harness` directly for richer
   DOM operations.
3. **For native apps**: cascade resolver handles it. If a target keeps
   failing, try `argus_find` (no side effects) to see what argus sees.
4. **App-specific quirks**: check `app-skills/<bundle_id>.md` (or call
   `argus_doctor` then read the matching file). Pre-shipped: Finder, Mail,
   Anteprima, Excel, System Settings.

## Sessions and RAM

- Moondream loads lazily on first vision call (~10–30s cold).
- After 5 min idle, the daemon unloads automatically.
- For burst workloads call **`argus_session_begin`** at the start; pinning
  prevents auto-unload. Call **`argus_session_end`** when done to free RAM
  immediately.
- `argus_vision_unload` forces an immediate unload at any time.

## Observability

- `argus_history` reads `~/.argus/intent.jsonl` (the argus core writes
  every action there). Useful for debugging "what did I just do?"
- `argus_metrics` returns p50/p95/avg latency and success rate per tool
  for the current MCP server process. Reset with `reset:true`.

## Security guardrails

- `argus_type` refuses to type into an `AXSecureTextField` (password). Pass
  `force_secure: true` ONLY if the user explicitly asked you to.
- Don't paste 2FA codes via `argus_type`. Defer to the user.
- Don't bypass argus when you know vision will work — pixel-coord guessing
  from screenshots is exactly what argus replaces.

## Auth-walled tasks

Stop and ask the user if you hit a login wall, OS permission prompt
(Accessibility, Screen Recording), or anything Apple ID-related. Don't try
to bypass.

## Privacy

- All vision inference is local (Moondream + Apple Vision on Apple Silicon)
- Intent log lives at `~/.argus/intent.jsonl` — local only
- Moondream API key (if used) stays in `~/.argus/.env`

## Architecture pointer

The plugin's MCP server lives in `mcp_server/` and is split into:
- `server.py`        — JSON-RPC dispatch + verify loop
- `routing.py`       — AX → OCR → Vision cascade
- `ax.py`            — AXUIElement walker
- `ocr.py`           — VNRecognizeTextRequest wrapper
- `daemon.py`        — in-process argus + warm Moondream session
- `overlay.py`       — annotated screenshot generator
- `diff.py`          — pre/post screenshot verifier
- `history.py`       — intent log reader + in-process metrics
