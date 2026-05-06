---
bundle_id: com.tinyspeck.slackmacgap
name: Slack
---

# Slack (desktop, Electron)

## Surface
Webview / Electron. AX works for most static elements but compose box is a contenteditable.

## Auth
Slack login persists in the Electron app — no session jar needed. Multi-workspace via Cmd+1/2/3...

## Core shortcuts
- **Quick switcher** (jump to channel/DM/person): `Cmd+K`
- **All unreads:** `Cmd+Shift+A`
- **Threads:** `Cmd+Shift+T`
- **Mentions & reactions:** `Cmd+Shift+M`
- **Drafts & sent:** `Cmd+Shift+D`
- **Channel browser:** `Cmd+Shift+L`
- **DM list:** `Cmd+Shift+K`
- **Workspaces:** `Cmd+1` ... `Cmd+9`
- **Workspace switcher:** `Cmd+Option+]` / `[`
- **Mark as read:** `Esc`
- **Mark all read in channel:** `Shift+Esc`
- **Edit last message:** `↑`
- **Bold/italic/code:** `Cmd+B` / `Cmd+I` / `Cmd+Shift+C`
- **Send message:** `Return`. **New line:** `Shift+Return`.
- **Slash command palette:** type `/` in compose

## Patterns
- Send a message to channel #foo: `Cmd+K` → type `foo` → Return → type message → Return.
- Add reaction to last message: hover (or `↑` to focus + `R`) → emoji picker.
- Schedule message: type message + Cmd+Shift+Return → time picker.

## Don't
- Don't drive Cmd+Shift+S to "save" (Slack interprets as set status).
- Don't use vision to find emoji picker — keyboard is faster.
- Don't paste images bigger than 10MB without checking workspace upload limits.
