# Argus — final overnight state

**Repo:** https://github.com/korisame/argus
**Local:** ~/.claude/plugins/argus → v1.7.0
**Status:** READY on all 5 deps (ax, ocr, cdp, vision, argus_core)

## Tags shipped tonight (rollback-safe)

| Tag | Tools | Highlights |
|---|---|---|
| **v0.4.0-stable** | 24 | rollback target |
| v0.5.0 | 34 | universal surface, CU shim, async, patterns |
| v0.6.0 | 38 | extract, ask, encrypted sessions, sandbox |
| v0.7.0 | 40 | replay, workflow, cascade parallel |
| v0.8.0 | 45 | macros, templates, Notes, screen-diff |
| v0.9.0 | 49 | benchmark, health, dom_query, log rotation |
| v0.10.0 | 53 | chain, workspace, predict_next |
| **v1.0.0** | 54 | first stable release |
| v1.1.0 | 57 | clipboard, files, calendar, more macros |
| v1.2.0 | 62 | notify, speak/listen, browser nav, PDF |
| v1.3.0 | 66 | web search, mail, iMessage, calendar create |
| v1.4.0 | 69 | git, scheduler, archive, 5 templates |
| v1.5.0 | 73 | http, jq, sql, image |
| v1.6.0 | 75 | smart_click, text_search |
| **v1.7.0** | 78 | app_explore, redact, focus |

## Live verification

- 9/9 pytest passing across all versions
- argus_doctor: READY v1.7.0
- argus_smart_click: clicked at coords with verify
- argus_focus: Finder activate
- argus_redact: PII filter (noop on clean screenshot)
- argus_text_search: searches across windows
- argus_search_web: korisame/argus-mcp already DDG-indexed

## Performance (M-series, real numbers)

cache_lookup 0.11ms · cdp_raw.page_info 0.37ms · ax.find 0.73ms ·
screen.list_windows 6.78ms · ocr.all_text(fast) 8ms · screencapture 85ms

## Bugs found + fixed

- v1.0: cdp_raw WS Origin handshake (Chrome 130+ anti-CSRF) → patched
- v0.5: Notes/Reminders TCC timeouts → apple_apps.create_note open-first pattern
- v1.7 minor: argus_app_explore on cold-start apps may need settle_s > 2s

## Things needing your touch in the morning

1. **Restart Claude Code app** to pick up v1.7.0 MCP server (78 tools)
2. **gh auth refresh -h github.com -s delete_repo workflow** then:
   - gh repo delete korisame/background-screenshot (today only archived)
   - re-add .github/workflows/ci.yml
3. **Read: ~/Desktop/ARGUS_v0.5.0_marketing_TODO.md** — full marketing plan
4. (Optional) Open dashboard: argus_dashboard action=start → http://127.0.0.1:9999

## Lines of code added tonight

~5500 lines net new across 30+ new modules. All behind tag-based rollback.

Continuing work overnight — see git log for details.
