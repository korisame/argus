---
name: argus
description: Vision-grounded computer automation for macOS — one skill for browser, native apps, and webviews. Use when the user wants to control a UI: open apps, click buttons, type text, scrape pages, run multi-app or multi-tab workflows, drive long-running REPLs. Routes through a unified cascade — learned-selector cache → Accessibility (AX) → Chrome DevTools (DOM) → Apple Vision OCR → Moondream visual grounding — picking the cheapest deterministic layer that resolves the target. Every click is verified post-action via DOM diff or screenshot diff. Successful resolutions are cached per (app, target) so subsequent calls skip the full cascade.
---

# argus

One skill, three surfaces, one mental model.

## When to use

- "Apri X e fai Y" / "Open X and do Y" — anything involving a UI step
- Clicking icons, buttons, links — labeled or not
- Filling forms, keyboard shortcuts
- Multi-app or multi-tab workflows (web → native → file)
- Driving a persistent REPL (Python, Node, psql, lldb, ssh)
- Anything where pure pixel-clicking would be brittle

## Mental model

```
target string
    │
    ▼
┌─────────────┐  literal "x,y"          → coords (instant)
│  cascade    │  learned cache hit      → ~5ms
│  resolver   │  Accessibility (AX)     → ~50ms     (native + webview)
│             │  Chrome DevTools DOM    → ~80ms     (browser only)
│             │  Apple Vision OCR       → ~150ms    (any with text)
└─────────────┘  Moondream vision       → ~1-3s     (semantic targets)
    │
    ▼
action engine: CDP (browser) | CGEvent (native) | AppleScript (escape hatch)
    │
    ▼
verify (DOM diff | screenshot diff) → cache update
```

You don't pick the layer — `argus_click` and `argus_find` route by surface
and target shape. Result includes `source` and `attempts` so you see exactly
what grounded the click.

## Tools (17 total, 10 atomic)

**Atoms — these cover 90% of usage:**

| Tool | What |
|---|---|
| `argus_doctor` | AX / OCR / CDP / vision availability + surface router |
| `argus_see` | Screenshot → base64 PNG |
| `argus_surface` | Where am I? `{surface, app, host, scope}` |
| `argus_find` | Resolve target → coords (no side effects) |
| `argus_click` | Cascade resolve + click + verify, updates cache |
| `argus_type` | Type into focused field (refuses on AXSecureTextField) |
| `argus_key` | Special key + modifiers |
| `argus_scroll` | Up/down/left/right at cursor or coords |
| `argus_session` | `save / load / clear / list / detect_login` browser jars |
| `argus_repl` | `start / send / read / kill / list` long-running processes |

**Helpers:**

| Tool | What |
|---|---|
| `argus_open_app` / `argus_quit_app` | Launch / quit macOS app |
| `argus_exec_apple_script` | Escape hatch |
| `argus_history` | Tail intent.jsonl with filters |
| `argus_metrics` | Per-tool latency + success rate |
| `argus_cache` | Inspect learned-selector cache |
| `argus_session_begin` / `argus_session_end` / `argus_vision_unload` | Moondream RAM control |

## Click semantics

`argus_click` returns:

```json
{
  "clicked": true,
  "x": 1240, "y": 88,
  "bbox": [1224, 72, 32, 32],
  "source": "cache | ax | cdp | ocr | vision | coords",
  "confidence": 0.92,
  "scope": "native:com.apple.finder",
  "attempts": ["cache", "ax"],
  "verified": {"ok": true, "reason": "region delta 5.4%", "global_distance": 11},
  "ms_resolve": 56
}
```

- `verified.ok: false` → click landed but **nothing visibly changed**. The cache
  records the failure. Try a different target.
- `source: "cache"` → resolved in 5ms from a previously successful selector.
- `from_cache: true` (when `source` is e.g. `ax`) → cache validated against
  live UI before being used.

## Decision flow

1. **`argus_surface`** to know the scope — answers `{surface, app, host, scope}`.
2. **For browsers** (`surface == "browser"`): cascade includes CDP DOM. argus
   talks to Chrome through `browser-harness`.
3. **For native / webview**: cascade uses AX → OCR → vision.
4. **For app-specific patterns**: check `app-skills/native/<bundle.id>.md` or
   `app-skills/web/<host>.md`. Pre-shipped: Finder, Mail, Preview, Excel,
   System Settings; github.com, mail.google.com, www.notion.so, linear.app.
5. **For long-running shell sessions** (Python REPL, psql, lldb, ssh):
   `argus_repl start cmd="python3"` then send/read.

## Sessions and RAM

- **Vision singleton**: one Moondream instance, shared by everything.
- **Idle auto-unload** after 5 min.
- **Burst workload**: `argus_session_begin` pins, `argus_session_end` frees.
- `argus_vision_unload` drops it immediately.

## Browser session persistence

- `argus_session save name=<jar>` after manual login → captures cookies +
  localStorage + IndexedDB.
- `argus_session load name=<jar>` before driving → restores it.
- `argus_session detect_login` returns true if you're sitting on a login wall.

## Learned-selector cache

Every successful `argus_click` writes `(scope, target) → (source, selector,
confidence)` to `~/.argus-prime/cache.db`. The next call with the same target
skips the cascade and replays the cached selector. Failures degrade the
entry's success rate; entries with <40% success after 3+ tries are bypassed.

Inspect: `argus_cache` (optionally `scope="web:github.com"`).

## Security guardrails

- `argus_type` refuses to type into `AXSecureTextField` (passwords). Set
  `force_secure: true` only when the user has explicitly asked.
- Don't paste 2FA codes — defer to the user.
- Don't bypass argus when you know vision will work — pixel-coord guessing
  from screenshots is what argus replaces.

## Auth-walled tasks

Stop and ask the user if you hit a login wall, OS permission prompt
(Accessibility, Screen Recording, Automation), or anything Apple-ID-related.

## Privacy

All vision inference is local (Moondream MPS + Apple Vision OCR).
`~/.argus-prime/intent.jsonl` and `cache.db` are local-only.

## Architecture pointer

```
mcp_server/server.py        JSON-RPC + tool dispatch
core/
├── router.py               surface detection (browser / webview / native)
├── cascade.py              unified resolver: cache → AX → CDP → OCR → vision
├── verify.py               DOM diff (browser) | screenshot diff (native)
├── vision.py               Moondream singleton (process-wide)
├── intent.py               jsonl log + SQLite learned-selector cache + metrics
├── session.py              browser session jars
└── repl.py                 persistent processes
adapters/
├── ax.py, ocr.py           macOS native (pyobjc)
├── cdp.py                  Chrome DevTools wrapper (over browser-harness)
└── cgevent.py              mouse/key/screenshot
app-skills/
├── native/<bundle.id>.md
└── web/<host>.md
```
