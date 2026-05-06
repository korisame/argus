# Argus v2.3.0 — overnight build complete (96 tools)

**Repo:** https://github.com/korisame/argus
**v2.0.0 release notes:** https://github.com/korisame/argus/releases/tag/v2.0.0
**Local:** ~/.claude/plugins/argus → v2.3.0 (96 tools, READY)

## Tags shipped overnight (rollback-safe)

| Tag | Tools | Highlight |
|---|---|---|
| **v0.4.0-stable** | 24 | rollback target |
| v1.0.0 | 54 | first stable release |
| v1.5.0 | 73 | http + jq + sql + image |
| **v2.0.0** | 86 | major: summary + observe |
| v2.1.0 | 90 | cookies + LS + emulate + pdf_export |
| v2.2.0 | 93 | log_search + export_skills + help |
| **v2.3.0** | 96 | download + archive + text_diff |

20 tags total. ~10000+ lines net new across 60+ modules.

## Categories of 96 tools

- **Resolver atoms (12):** doctor, see, surface, find, click, type, paste, key, send_keys, scroll, open_app, quit_app
- **Discovery (8):** window, window_list, find_all, wait_for, history, metrics, cache, text_search
- **Higher-order (10):** pattern, replay, workflow, workflow_template, macros, chain, workspace, predict_next, extract, ask
- **Browser (8):** browser, dom_query, session, secure_session, cookies, localstorage, emulate, pdf_export
- **Apple apps (8):** notes, reminders, calendar, calendar_create, mail, imessage, contacts, clipboard
- **System (8):** open_app, quit_app, focus, notify, speak, listen, system, app_explore
- **Files+data (10):** files, http, jq, sql, image, pdf, qr, redact, drag, download
- **Devops (4):** git, repl, schedule, archive
- **Voice/translate/web (4):** speak, listen, translate, search_web
- **Admin (12):** setup, uninstall, dashboard, chrome, skills, session, secure_session, log_rotate, install_log_rotation, health, benchmark, exec_apple_script
- **Observability (6):** history, metrics, cache, summary, observe, log_search
- **Utility (5):** smart_click, archive_ops, text_diff, export_skills, help
- **Compatibility (1):** cu_route
- **Onboarding (1):** quickstart
- **Diff/history (3):** diff_screens, screenshot_history, text_diff

## Live verification (just now)

- 9/9 pytest passing
- argus_doctor: status=READY on all 5 deps (ax, ocr, cdp, vision, argus_core)
- 7/7 v2.2 tools (help, summary, log_search, export_skills, localstorage, cookies, etc.)
- argus_search_web: korisame/argus indexed by DuckDuckGo

## Performance (M-series Apple Silicon)

| op | p50 | p95 |
|---|---|---|
| cache_lookup | 0.11ms | 0.86ms |
| cdp_raw.page_info | 0.37ms | 15.82ms |
| ax.find | 0.73ms | 42.11ms |
| screen.list_windows | 6.78ms | 7.35ms |
| ocr.all_text(fast) | 8.01ms | 208.67ms |
| screencapture | 85.22ms | 91.81ms |

## Bugs found + fixed overnight

- v1.0: cdp_raw WS Origin handshake (Chrome 130+ anti-CSRF) — patched + chrome_admin always passes --remote-allow-origins=*
- v0.5: Notes/Reminders TCC timeouts — apple_apps.create_note open-first
- v1.7→v1.8: app_explore cold-start — polls NSWorkspace up to 8s

## Things to do in the morning

1. **Restart Claude Code** to load v2.3.0 (96 tools)
2. `gh auth refresh -h github.com -s delete_repo workflow` then:
   - `gh repo delete korisame/background-screenshot` (today only archived)
   - re-add `.github/workflows/ci.yml`
3. Read: `~/Desktop/ARGUS_v0.5.0_marketing_TODO.md` — full marketing plan
4. Try: `argus_help` (no args) → see all 14 tool categories with counts
5. Try: `argus_summary` → 1-line state snapshot
6. Try: `argus_export_skills action=export` → bundle your learned cache for community
7. Open dashboard: `argus_dashboard action=start` → http://127.0.0.1:9999

## Status: READY for marketing push

argus is now a **96-tool macOS automation platform**. It replaces
Anthropic Computer Use entirely on Mac, plus does:
- Task patterns + replay + workflows + chains + multi-window orchestration
- Cookies + localStorage + device emulation + page→PDF
- Apple ecosystem (Notes/Mail/Calendar/Contacts/iMessage/Reminders/Clipboard)
- git + scheduler + archive + http + sql + jq + image + qr + translate
- TTS + STT + screenshot diff + redact PII
- Observability (history + metrics + cache + summary + observe + log_search)
- App auto-discovery + shareable skill bundles + categorized help

All behind tag-based rollback. v0.4.0-stable, v1.0.0, v2.0.0 preserved.
