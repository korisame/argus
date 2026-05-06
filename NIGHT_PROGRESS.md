# Argus — final overnight state (latest: v1.9.0)

**Repo:** https://github.com/korisame/argus
**Local:** ~/.claude/plugins/argus → v1.9.0
**Status:** READY on all 5 deps

## Tags shipped overnight (rollback-safe)

| Tag | Tools | What |
|---|---|---|
| v0.4.0-stable | 24 | rollback target |
| v1.0.0 | 54 | first stable release |
| v1.5.0 | 73 | http + jq + sql + image |
| v1.7.0 | 78 | app_explore + redact + focus |
| v1.8.0 | 80 | drag + system controls |
| **v1.9.0** | 84 | contacts + qr + translate + screenshot history |

## Tools by category (84 total)

- **Resolver (12):** doctor, see, surface, find, click, type, paste, key, send_keys, scroll, open_app, quit_app
- **Discovery & state (8):** window, window_list, find_all, wait_for, history, metrics, cache, text_search
- **Higher-order (10):** pattern, replay, workflow, workflow_template, macros, chain, workspace, predict_next, extract, ask
- **Browser (3):** dom_query, browser, smart_click
- **Apple apps (8):** notes, reminders, calendar(read), calendar_create, mail, imessage, contacts, clipboard
- **System (8):** notify, speak, listen, focus, drag, system, lock_screen via system, app_explore
- **Files+data (8):** files, http, jq, sql, image, pdf, qr, redact
- **Voice/translate/web (3):** speak, listen, translate, search_web
- **Admin (12):** setup, uninstall, dashboard, chrome, skills, session, secure_session, repl, log_rotate, install_log_rotation, health, benchmark
- **Safety (4):** policy, exec_apple_script (sandboxed), session_begin/end, vision_unload
- **Devops (3):** git, schedule, archive
- **Compatibility (1):** cu_route
- **Onboarding (1):** quickstart
- **Diff/history (3):** diff_screens, screenshot_history

## Live verification

- 9/9 pytest passing
- argus_doctor: READY v1.9.0
- All 5 deps green: ax, ocr, cdp, vision, argus_core

## Performance (M-series)

cache_lookup 0.11ms · cdp_raw.page_info 0.37ms · ax.find 0.73ms ·
screen.list_windows 6.78ms · ocr.all_text(fast) 8ms · screencapture 85ms

## Bugs fixed overnight

- Chrome 130+ WS Origin handshake → patched cdp_raw + chrome_admin
- Notes/Reminders TCC timeout → apple_apps.create_note open-first
- app_explore cold-start → polls NSWorkspace up to 8s

## Things needing your touch in the morning

1. **Restart Claude Code app** to pick up v1.9.0 (84 tools)
2. **gh auth refresh -h github.com -s delete_repo workflow** then:
   - gh repo delete korisame/background-screenshot
   - re-add .github/workflows/ci.yml
3. **Read: ~/Desktop/ARGUS_v0.5.0_marketing_TODO.md** — full marketing plan
4. (Optional) argus_dashboard action=start → http://127.0.0.1:9999

## Lines of code added

~7000+ lines net new across 40+ new modules. All behind tag-based rollback.

Continuing iteration on v2.0 path now.
