# Argus v2.0.0 — overnight build complete

**Repo:** https://github.com/korisame/argus
**Release:** https://github.com/korisame/argus/releases/tag/v2.0.0
**Local:** ~/.claude/plugins/argus → v2.0.0 (86 tools, READY)

## Versions shipped (rollback-safe tags)

| Tag | Tools | What |
|---|---|---|
| v0.4.0-stable | 24 | first production-ready, ROLLBACK TARGET |
| v1.0.0 | 54 | first stable release |
| v1.5.0 | 73 | http + jq + sql + image |
| v1.8.0 | 80 | drag + system + app_explore fix |
| **v2.0.0** | 86 | observe + summary, MAJOR RELEASE |

Total: 17 tags shipped overnight.

## Tools by category (86 total)

- Resolver (12), Discovery (8), Higher-order (10), Browser (3),
  Apple apps (8), System (8), Files+data (8), Voice/translate/web (4),
  Admin (12), Safety (4), Devops (3), Compatibility (1),
  Onboarding (1), Diff/history (3), Observability (2)

## Final live verification

- 9/9 pytest passing
- argus_doctor: status=READY on all 5 deps
- argus_summary: live, returns 1-line snapshot
- argus_observe: 4 event kinds (text_appears, state_changes, app_changes, http_endpoint)
- All earlier tools verified (cu_route, chain, workspace, predict, etc.)

## Performance (M-series)

| op | p50 |
|---|---|
| cache_lookup | 0.11ms |
| cdp_raw.page_info | 0.37ms |
| ax.find | 0.73ms |
| screen.list_windows | 6.78ms |
| ocr.all_text(fast) | 8ms |
| screencapture | 85ms |

## Bugs fixed overnight

- v1.0: cdp_raw WS Origin handshake (Chrome 130+ anti-CSRF)
- v0.5: Notes/Reminders TCC timeout (open-first pattern)
- v1.7→v1.8: app_explore cold-start (poll up to 8s)

## Things to do in the morning

1. **Restart Claude Code** to load v2.0.0 (86 tools)
2. `gh auth refresh -h github.com -s delete_repo workflow` then:
   - `gh repo delete korisame/background-screenshot` (today only archived)
   - re-add `.github/workflows/ci.yml`
3. Read: `~/Desktop/ARGUS_v0.5.0_marketing_TODO.md` (full marketing plan)
4. Open dashboard: `argus_dashboard action=start` → http://127.0.0.1:9999

## Lines of code

~8000+ net new across 50+ new modules. Behind tag-based rollback.

## Status: READY for marketing push.

Continuing iteration if credits allow.
