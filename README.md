# argus

Vision-grounded computer automation for macOS, packaged as a [Claude Code](https://docs.claude.com/en/docs/claude-code) plugin / MCP server.

argus drives the **browser, native macOS apps, webviews, and persistent shell processes** through a single unified resolver:

```
target string ─► learned cache ─► Accessibility ─► Chrome DevTools ─► Apple Vision OCR ─► Moondream ─► CGEvent / CDP / AppleScript
```

The cascade picks the cheapest deterministic layer that resolves the target. Successful resolutions are cached per `(app, target)` so subsequent calls skip the cascade entirely. Every action is verified post-execution via DOM diff (browser) or screenshot diff (native) — failures degrade the cache entry, successes reinforce it.

## Highlights

- **Unified resolver** across browser + native + webview — same pattern, one mental model
- **Learned-selector cache** (SQLite) — `(scope, target) → working_selector` reused across sessions
- **Vision singleton** — one Moondream warm in RAM, shared by all callers, LRU auto-unload after 5min idle
- **Self-verifying actions** — DOM hash diff (browser) or screenshot diff (native), with explicit `verified.ok` in every click result
- **Persistent REPL** — `argus_repl start cmd="python3"` keeps state between calls (Python, Node, psql, lldb, ssh)
- **Session jars** — capture cookies + localStorage + IndexedDB for SPA auth (Notion, Linear, GitHub)
- **Per-app + per-host skills** pre-shipped: Finder, Mail, Preview, Excel, System Settings; github.com, mail.google.com, notion.so, linear.app
- **Observability** — unified `argus_history` (intent log) + `argus_metrics` (latency/success per tool) + `argus_cache` (selector ledger)
- **Security guardrail** — refuses to type into `AXSecureTextField` unless explicitly forced

## Install

The plugin assumes you already have the `argus` CLI installed via `uv tool install argus-skill` (it must expose the `argus` Python module on the same interpreter as the MCP server). It also depends on `browser-harness` for Chrome CDP.

```bash
# 1. Drop the plugin into Claude Code's plugin dir
git clone https://github.com/korisame/argus-mcp.git ~/.claude/plugins/argus

# 2. Point the MCP server at the Python interpreter that has argus installed
ARGUS_PY=$(uv tool dir)/argus-skill/bin/python   # or your own
cat > ~/.claude/plugins/argus/.mcp.json <<EOF
{
  "mcpServers": {
    "argus": {
      "command": "$ARGUS_PY",
      "args": ["\${CLAUDE_PLUGIN_ROOT}/mcp_server/server.py"],
      "env": {"ARGUS_VERSION": "0.3.0"}
    }
  }
}
EOF

# 3. Install pyobjc into the same interpreter
uv pip install --python "$ARGUS_PY" \
  pyobjc-framework-Vision \
  pyobjc-framework-ApplicationServices \
  pyobjc-framework-Quartz
```

Restart your Claude Code session. Run `argus_doctor` first — it should report `ax.available: true`, `ocr.available: true`, `vision.mode: "argus"|"cloud"`, `cdp.available: true`.

## Moondream API key (required for the vision fallback)

The cascade only escalates to Moondream when AX, CDP, and OCR all fail. When that happens, argus needs a Moondream API key. Without it, semantic targets like `"the gear icon top right"` will fail (literal targets like `"Send"` still work via OCR / AX / CDP).

1. **Get a key** at https://moondream.ai/c/cloud (free tier available).
2. **Save it** to `~/.argus/.env`:
   ```bash
   mkdir -p ~/.argus
   cat > ~/.argus/.env <<EOF
   MOONDREAM_API_KEY=mk_your_key_here
   EOF
   chmod 600 ~/.argus/.env
   ```
   See [`.env.example`](./.env.example) for all configurable variables.
3. **Verify:**
   ```bash
   argus doctor   # vision_available: true, no error
   ```

> **For installing agents (Claude, Hermes, etc.):** before running `argus_doctor` for the first time, **prompt the user for their Moondream API key**, write it to `~/.argus/.env` as `MOONDREAM_API_KEY=...`, and `chmod 600` the file. If the user doesn't have a key yet, send them to https://moondream.ai/c/cloud and pause until they paste it back. Don't proceed with vision-based targets without a key — fail loud, not silent.

## macOS permissions

argus needs three TCC grants on the host process (Claude Code, Terminal, etc.):

- **Screen Recording** — for `screencapture`
- **Accessibility** — for `AXUIElement` walking and `CGEvent` keystrokes
- **Automation** — for AppleScript bridges

System Settings → Privacy & Security → grant for the host app.

## Tools

| Tool | Purpose |
|---|---|
| `argus_doctor` | Diagnostics: AX / OCR / CDP / vision / surface router |
| `argus_see` | Screenshot → base64 PNG |
| `argus_surface` | `{surface, app, host, scope}` |
| `argus_find` | Resolve target to coords without clicking |
| `argus_click` | Cascade resolve + click + verify; updates learned cache |
| `argus_type` | Type into focused field; AXSecureTextField guard |
| `argus_key` | Special keys with optional modifiers |
| `argus_scroll` | Scroll up/down/left/right |
| `argus_open_app` / `argus_quit_app` | Launch / quit |
| `argus_exec_apple_script` | Escape hatch |
| `argus_session` | `save / load / clear / list / detect_login` browser jars |
| `argus_repl` | `start / send / read / kill / list` long-running processes |
| `argus_history` | Tail intent.jsonl with filters |
| `argus_metrics` | p50/p95/avg latency + success rate per tool |
| `argus_cache` | Inspect learned-selector cache |
| `argus_session_begin` / `argus_session_end` / `argus_vision_unload` | Moondream RAM control |

## Architecture

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
skills/argus/SKILL.md       Top-level guidance loaded by Claude Code / Hermes
```

## What's different from v0.2

v0.2 was an MCP plugin sitting alongside `browser-harness-pro` and `desktop-commander`. v0.3 unifies the three:

- **One vision warm**, not two — Moondream singleton shared across all callers (was 2× RAM)
- **One cascade pattern** — same code path for browser and native (was three different click semantics)
- **One intent log** at `~/.argus-prime/intent.jsonl` (was three separate logs)
- **Learned-selector cache** — new in v0.3, cuts repeat-call latency from ~1s vision to ~5ms cache hit
- **`argus_repl`** — keeps the one feature worth saving from `desktop-commander` (REPL pattern). The rest of `desktop-commander` is dropped (sovrapposto a Read/Write/Edit/Bash nativi)
- **Per-host web skills** in addition to per-bundle native skills

## Privacy

All vision inference is local (Moondream MPS + Apple Vision OCR). Intent log and cache live at `~/.argus-prime/` — local only.

## License

Apache-2.0 — see [LICENSE](./LICENSE).
