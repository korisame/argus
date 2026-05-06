# argus

> **Vision-grounded macOS automation as a Claude Code MCP plugin.**
> One unified resolver — Accessibility → Apple Vision OCR → Chrome DevTools → Moondream — drives the **browser, native macOS apps, webview Electron apps, and persistent shell processes** through 49 atomic tools. Replaces Anthropic Computer Use on macOS.

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![macOS](https://img.shields.io/badge/macOS-13+-black?logo=apple)]()
[![MCP](https://img.shields.io/badge/MCP-server-purple)]()

> *Demo GIF goes here — argus_click "the gear icon top right" with bbox overlay + verified.ok=true* (run `argus_benchmark` to see the numbers below on your hardware.)

---

## Why argus, not Computer Use / browser-harness?

| | **Anthropic Computer Use** | **browser-harness-pro** | **argus** |
|---|---|---|---|
| Surface | screenshot + pixel click | Chrome only (CDP) | Chrome + native + webview |
| Targeting | pixel coordinates | CSS / ARIA / text + Moondream | **AX → OCR → CDP → Moondream cascade** |
| Self-verify | no | DOM diff | **DOM diff (browser) + screenshot diff (native)** |
| Learned cache | no | per-page only | **`(scope, target) → selector` SQLite, cross-session** |
| Task patterns | no | no | **record / replay deterministic sequences** |
| Persistent REPL | no | no | **Python / Node / psql / lldb / ssh** |
| Session jars | n/a | cookies | **cookies + localStorage + IndexedDB**, AES-256-GCM at rest |
| Policy guardrails | no | no | **denylist apps + destructive-verb confirm + AXSecureTextField hard-block** |
| Web dashboard | no | no | **http://127.0.0.1:9999** |
| Claude tokens | many (visual call back-and-forth) | none | **none** |

Computer Use is cross-platform but primitive. argus is macOS-only but a **strict superset** when you're on Mac.

---

## Install

```bash
# 1. argus core CLI (uv-managed)
uv tool install argus-skill   # or: uv tool install -e ~/Developer/argus

# 2. plugin
git clone https://github.com/korisame/argus.git ~/.claude/plugins/argus

# 3. point MCP server at the python that has argus
ARGUS_PY=$(uv tool dir)/argus-skill/bin/python
cat > ~/.claude/plugins/argus/.mcp.json <<EOF
{
  "mcpServers": {
    "argus": {
      "command": "$ARGUS_PY",
      "args": ["\${CLAUDE_PLUGIN_ROOT}/mcp_server/server.py"],
      "env": {
        "ARGUS_VERSION": "0.9.0",
        "BU_CDP_URL": "http://127.0.0.1:9333",
        "ARGUS_ASYNC": "1"
      }
    }
  }
}
EOF

# 4. python deps in that interpreter
uv pip install --python "$ARGUS_PY" \
  pyobjc-framework-Vision pyobjc-framework-ApplicationServices \
  pyobjc-framework-Quartz websocket-client cryptography pyyaml

# 5. dedicated automation Chrome (no consent prompt)
browser-harness --boot-chrome
browser-harness --install-agent   # auto-start at login
```

Restart Claude Code, then run `argus_doctor`. Should report `status: READY`.

For agents installing argus on behalf of a user: **call `argus_setup` first** — it returns a step-by-step checklist with `fix_cmd` for everything missing.

## Moondream API key (required for vision fallback)

Vision fires only when AX, OCR, and CDP-DOM all fail to resolve a target. When that happens you need a Moondream key:

```bash
# Get a free key at https://moondream.ai/c/cloud
mkdir -p ~/.argus
echo "MOONDREAM_API_KEY=mk_your_key_here" >> ~/.argus/.env
chmod 600 ~/.argus/.env
```

argus reads `~/.argus/.env` automatically at server startup.

## Five-second usage

```
argus_doctor                                    # health check
argus_surface                                   # where am I?
argus_click "Send"                              # vision-grounded click
argus_extract {"price": "total amount"}         # scrape any page into JSON
argus_ask "Is the build green?"                 # Moondream Q&A
argus_repl start cmd="python3" name="repl"      # persistent REPL
argus_repl send handle="repl" data="2+2"
argus_repl read handle="repl"                   # → "4"
argus_pattern record_begin name="login" scope="web:foo" intent_label="sign in"
   ... do the login by hand ...
argus_pattern record_end name="login"
argus_replay scope="web:foo" intent_label="sign in"   # next time, deterministic
argus_workflow_template name="post_to_notion" vars='{"title":"…","body":"…"}'
argus_dashboard action=start                    # open http://127.0.0.1:9999
```

## Tool catalog (49)

<details>
<summary>Click to expand</summary>

**Atoms (12):** `argus_doctor`, `argus_see`, `argus_surface`, `argus_find`, `argus_click`, `argus_type`, `argus_paste`, `argus_key`, `argus_send_keys`, `argus_scroll`, `argus_open_app`, `argus_quit_app`

**Discovery & state:** `argus_window`, `argus_window_list`, `argus_find_all`, `argus_wait_for`, `argus_history`, `argus_metrics`, `argus_cache`

**Higher-order:** `argus_pattern`, `argus_replay`, `argus_workflow`, `argus_workflow_template`, `argus_macros`, `argus_extract`, `argus_ask`, `argus_dom_query`

**Admin & infrastructure:** `argus_setup`, `argus_uninstall`, `argus_dashboard`, `argus_chrome`, `argus_skills`, `argus_session`, `argus_secure_session`, `argus_repl`, `argus_log_rotate`, `argus_install_log_rotation`, `argus_health`, `argus_benchmark`, `argus_diff_screens`

**Safety & escape hatches:** `argus_policy`, `argus_exec_apple_script` (sandboxed), `argus_session_begin/end`, `argus_vision_unload`

**Apple-specific:** `argus_notes`, `argus_reminders`

**Compatibility:** `argus_cu_route` — Anthropic Computer Use shim (intercepts CU-style calls and routes them to argus equivalents)

</details>

## Architecture

```
mcp_server/server.py        JSON-RPC dispatch (asyncio by default)
core/
├── router.py               surface detection (browser / webview / native)
├── cascade.py              cache → AX || OCR || CDP → vision (parallelized)
├── verify.py               DOM diff (browser) | screenshot diff (native)
├── vision.py               Moondream singleton (process-wide)
├── intent.py               jsonl + SQLite learned-selector cache + metrics
├── patterns.py             task-pattern memory: (scope, intent) → sequence
├── replay.py               execute saved patterns step-by-step
├── workflow.py             declarative JSON workflows + branching
├── extract.py              schema-driven structured extraction
├── benchmark.py            perf suite
├── health.py               continuous DEGRADED/BROKEN monitor
├── policy.py               ~/.argus/policy.yaml guardrails
├── safety.py               escape-hatch denylist + log rotation + vision batch
├── secure_session.py       Keychain-encrypted session jars
├── session.py              browser session jars (cookies/localStorage/IDB)
├── repl.py                 persistent shell processes
├── apple_apps.py           Notes + Reminders helper (open-first pattern)
├── macros.py               built-in micro-workflows
├── prewarm.py              vision pre-warm on argus_open_app
├── dashboard.py            local web UI (http://127.0.0.1:9999)
├── wizard.py               argus_setup onboarding checklist
├── uninstall.py            clean removal across integration points
├── chrome_admin.py         dedicated automation Chrome lifecycle
├── registry.py             pull app-skills from korisame/argus-skills
├── diff_screens.py         screenshot diff for state monitoring
└── asyncio_runtime.py      concurrent dispatch via thread pool
adapters/
├── ax.py                   AXUIElement walker (pyobjc)
├── ocr.py                  VNRecognizeTextRequest wrapper
├── cdp.py                  Chrome DevTools (browser-harness wrapper, fallback)
├── cdp_raw.py              Chrome DevTools direct (websocket-client, primary)
├── cgevent.py              mouse / key / screenshot
├── linux_screen.py         Linux stub: grim / scrot / import
└── linux_input.py          Linux stub: xdotool / wtype / ydotool
app-skills/
├── native/<bundle.id>.md   per-app patterns (Finder, Mail, Preview, Excel, …)
├── web/<host>.md           per-domain patterns (github.com, gmail.com, …)
└── workflows/<name>.json   pre-shipped declarative templates
skills/argus/SKILL.md       loaded by Claude Code / Hermes via symlink
```

## macOS permissions

argus needs three TCC grants on the host process (Claude Code / Terminal / Hermes):

- **Screen Recording** — for `screencapture`
- **Accessibility** — for AXUIElement + CGEvent
- **Automation** — for AppleScript bridges (Notes / Reminders / Excel)

`argus_setup` checks all three and surfaces missing ones with the exact System Settings URL.

## Privacy

All vision inference is local (Moondream MPS + Apple Vision OCR). The intent log lives at `~/.argus-prime/intent.jsonl` and the cache at `~/.argus-prime/cache.db` — both local-only. Encrypted session jars use a per-jar key in the macOS Keychain.

## Versions

| Tag | Highlights |
|---|---|
| `v0.4.0-stable` | First production-ready (24 tools, autotune, learned cache) — **rollback target** |
| `v0.5.0` | Universal surface, Computer Use shim, async dispatch, task patterns, policy, dashboard, registry, headless Chrome |
| `v0.6.0` | `argus_extract`, `argus_ask` (Moondream Q&A), Keychain-encrypted sessions, escape-hatch sandboxing, vision batching |
| `v0.7.0` | `argus_replay`, declarative `argus_workflow`, AX‖OCR cascade parallelism, browser DOM fast-path |
| `v0.8.0` | Macros, workflow templates, Notes/Reminders helper, screen-diff, Linux backend stubs |
| `v0.9.0` | Benchmark, health monitor, DOM query, scheduled log rotation |

## Contributing

5 issues are open with `help wanted`:
- Add app-skills for: Slack desktop, VS Code, Cursor, figma.com, claude.ai, chatgpt.com
- Linux backend completion (AT-SPI + Wayland)

App-skills are markdown — no code required, just patterns you've discovered for an app/site you use.

## License

Apache-2.0 — see [LICENSE](./LICENSE).
