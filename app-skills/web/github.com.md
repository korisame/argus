---
host: github.com
---

# github.com

## Surface
Browser (CDP via browser-harness).

## Auth
- Login wall on private repos / actions: `argus_session detect_login` returns true.
- Persist a logged-in session: `argus_session save name=github` after manual login. Restore with `argus_session load name=github` before driving.

## Selectors / patterns
- "Sign in" → `[data-testid=login-button]` (resolved by AX-equivalent text, cached after first hit)
- Repo search: keyboard `/` focuses the search bar — prefer `argus_key name="/"` then `argus_type "owner/repo"`
- Issue list filters: `is:open is:issue label:bug` in the search bar is faster than UI clicks
- Comment box: contenteditable, paste with Cmd+V (`argus_key Return modifiers="cmd"`-like is a no-op there; use the Markdown toolbar buttons)

## Don't
- Don't try to click GitHub avatars in headers — they trigger menus that overlap each other; use the URL pattern `https://github.com/<user>` instead.
- Don't drive 2FA flows. Defer to user.
