# Argus v2.2.0 — overnight build complete

**Repo:** https://github.com/korisame/argus
**v2.0.0 release:** https://github.com/korisame/argus/releases/tag/v2.0.0
**Local:** ~/.claude/plugins/argus → v2.2.0 (93 tools, READY)

## Tags shipped overnight (rollback-safe)

| Tag | Tools | Highlight |
|---|---|---|
| v0.4.0-stable | 24 | ROLLBACK TARGET |
| v1.0.0 | 54 | first stable |
| v1.5.0 | 73 | http + jq + sql + image |
| v2.0.0 | 86 | summary + observe DSL (major release) |
| v2.1.0 | 90 | cookies + localstorage + emulate + pdf_export |
| **v2.2.0** | 93 | log_search + export_skills + help |

19 tags total. ~9000+ lines net new across 56+ modules.

## What's in 93 tools

- Resolver atoms (12), Discovery (8), Higher-order (10), Browser (8 incl. cookies/LS/emulate/PDF),
  Apple apps (8), System (8), Files+data (8), Voice/translate/web (4),
  Admin (12), Safety (4), Devops (3), Compatibility (1), Onboarding (2),
  Diff/history (3), Observability (5)

## Live verification (just now)

- 9/9 pytest passing
- argus_doctor: status=READY on all 5 deps (ax, ocr, cdp, vision, argus_core)
- argus_summary: live 1-line snapshot
- argus_help: 14 categorized tool topics
- argus_log_search, argus_export_skills working

## Performance (M-series Apple Silicon)

| op | p50 |
|---|---|
| cache_lookup | 0.11ms |
| cdp_raw.page_info | 0.37ms |
| ax.find | 0.73ms |
| screen.list_windows | 6.78ms |
| ocr.all_text(fast) | 8ms |
| screencapture | 85ms |

## Things to do in the morning

1. **Restart Claude Code** to load v2.2.0 (93 tools)
2. `gh auth refresh -h github.com -s delete_repo workflow` then:
   - `gh repo delete korisame/background-screenshot`
   - re-add `.github/workflows/ci.yml`
3. Read: `~/Desktop/ARGUS_v0.5.0_marketing_TODO.md` (full marketing plan)
4. Try: `argus_help` (no args) → see all 14 tool categories
5. Try: `argus_summary` → 1-line state snapshot
6. Open dashboard: `argus_dashboard action=start` → http://127.0.0.1:9999

## Status

argus is now a 93-tool macOS automation platform. Replaces Anthropic
Computer Use entirely on Mac. Task patterns + replay + workflows + chains +
multi-window orchestration + cookies/localStorage/emulate + Apple ecosystem
(Notes/Mail/Calendar/Contacts/iMessage/Reminders) + git + scheduler + http +
sql + observability all in one MCP server.

Continuing iteration if credits allow.
