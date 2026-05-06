---
host: claude.ai
---

# claude.ai

## Surface
Browser. SPA — routes change without full page reload, so DOM diff verify works better than URL diff.

## Auth
Persists in cookies + localStorage. `argus_session save name=claude` after login.

## Selectors / shortcuts
- **New chat:** `Cmd+Shift+O` (or click "New chat" in sidebar)
- **Toggle sidebar:** `Cmd+S`
- **Send message:** `Return` (Shift+Return for new line)
- **Search chats:** `Cmd+K`
- **Settings:** click avatar bottom-left → Settings

## Patterns
- Send a message: focus compose (probably already focused) → `argus_paste` (long text) → `Return`.
- Read latest assistant response: scroll to bottom + `argus_extract({"reply": "the most recent assistant message"})`.

## Don't
- Don't drive deletion of conversations via UI — there's no API recovery if you misfire.
- Don't try to extract an entire long thread via vision — use `argus_dom_query "[data-testid=user-message]"` for structured extraction.
