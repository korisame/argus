# argus-mcp

Vision-grounded computer automation for macOS, packaged as a [Claude Code](https://docs.claude.com/en/docs/claude-code) plugin / MCP server.

argus drives the **browser, native macOS apps, and anything visible on the screen** through a hybrid resolver:

```
target string ─► Accessibility (AX) ─► Apple Vision OCR ─► Moondream vision ─► CGEvent / CDP / AppleScript
```

You don't pick the layer — argus picks the cheapest deterministic one that resolves your target. Click results carry coordinates, bbox, confidence and an annotated screenshot when confidence is low; every action is followed by a screenshot diff so the agent can tell whether the click had visible effect.

## Highlights

- **In-process daemon** — no subprocess per call, Moondream stays warm with a 5-minute LRU idle timer
- **Hybrid AX → OCR → Vision cascade** — deterministic where possible, vision only when needed
- **Self-verifying actions** — pre/post screenshot diff, explicit `verified: {ok, reason}` in every click result
- **Annotated screenshots** for low-confidence clicks (bbox + crosshair overlay)
- **App-specific knowledge** — pre-shipped skills for Finder, Mail, Preview, Excel, System Settings
- **Observability** — `argus_history` (intent log) + `argus_metrics` (per-tool latency, success rate)
- **Security guardrail** — refuses to type into `AXSecureTextField` unless explicitly forced

## Install

The plugin assumes you already have the [`argus`](https://github.com/) CLI installed via `uv tool install argus-skill` (or equivalent — it must expose the `argus` Python module on the same interpreter as the MCP server).

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
      "env": {"ARGUS_PLUGIN_VERSION": "0.2.1"}
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

Restart your Claude Code session. Run `argus_doctor` first — it should report `in_process: true`, `ax_available: true`, and `vision_available: true`.

## macOS permissions

argus needs three TCC grants on the host process (Claude Code, Terminal, etc.):

- **Screen Recording** — for `screencapture`
- **Accessibility** — for `AXUIElement` walking and `CGEvent` keystrokes
- **Automation** — for AppleScript bridges

System Settings → Privacy & Security → grant for the host app.

## Tools

| Tool | What it does |
|---|---|
| `argus_doctor` | Diagnostics: AX/OCR/vision availability, daemon status, frontmost app |
| `argus_see` | Screenshot → base64 PNG |
| `argus_surface` | Frontmost app: bundle_id, name, surface, URL/title if browser |
| `argus_find` | Resolve target to coords without clicking |
| `argus_click` | Cascade resolve + click + verify; returns coords, bbox, source, confidence, annotated screenshot |
| `argus_type` | Type into focused field; refuses on `AXSecureTextField` |
| `argus_key` | Special keys (Return, Tab, ArrowUp, …) with optional modifiers |
| `argus_scroll` | Scroll up/down/left/right at cursor |
| `argus_open_app` / `argus_quit_app` | Launch / quit a macOS app |
| `argus_exec_apple_script` | Arbitrary AppleScript escape hatch |
| `argus_run` | Arbitrary Python with argus pre-imported |
| `argus_session_begin` / `argus_session_end` | Pin Moondream in RAM for a burst of vision calls |
| `argus_vision_unload` | Free Moondream RAM immediately |
| `argus_history` | Tail `~/.argus/intent.jsonl` |
| `argus_metrics` | p50/p95/avg latency + success rate per tool |

## Architecture

```
mcp_server/
├── server.py     JSON-RPC dispatch, verify loop, history hooks
├── routing.py    AX → OCR → Vision cascade resolver
├── ax.py         AXUIElement walker (pyobjc ApplicationServices)
├── ocr.py        VNRecognizeTextRequest wrapper (pyobjc Vision)
├── daemon.py     in-process argus + warm Moondream session
├── overlay.py    annotated screenshot generator (bbox + crosshair)
├── diff.py       pre/post screenshot verifier (dHash + region delta)
└── history.py    intent log reader + in-process metrics

skills/argus/SKILL.md         Top-level guidance loaded by Claude Code
app-skills/<bundle.id>.md     Per-app patterns (Finder, Mail, Preview, Excel, …)
```

## Privacy

All vision inference is local:
- **Moondream** runs on Apple Silicon GPU (MPS) via the underlying `argus` CLI
- **Apple Vision OCR** is the system framework — never leaves the device
- **AX walker** is pure macOS API, no network

The intent log lives at `~/.argus/intent.jsonl` and is local-only.

## License

Apache-2.0 — see [LICENSE](./LICENSE).
