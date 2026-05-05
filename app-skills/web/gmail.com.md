---
host: mail.google.com
---

# Gmail (mail.google.com)

## Surface
Browser. Heavy SPA — DOM hashes change frequently, so verify_change with `expect="url"` works better than DOM hash for navigation.

## Auth
- Persist Google session: `argus_session save name=google` after login. localStorage carries Gmail's auth state on top of cookies.
- Hits a 2FA prompt? Stop and ask the user.

## Selectors / patterns
- Compose: keyboard `c` is the canonical shortcut. `argus_key name="c"` faster than clicking the Compose button.
- Reply: `r`. Reply-all: `a`. Forward: `f`.
- Send: `Cmd+Return` inside an open compose.
- Search: `/` focuses the search bar.
- Archive selected: `e`. Mark unread: `Shift+u`.

## Don't
- Don't use vision to find the Compose button when `c` works.
- Don't paste sensitive content into compose without confirming the recipient — Gmail autocompletes the `To:` field aggressively.
