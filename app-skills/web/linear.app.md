---
host: linear.app
---

# Linear (linear.app)

## Surface
Browser. Heavy keyboard-shortcut UI — almost everything has one.

## Auth
Persists via cookies + localStorage. `argus_session save name=linear` after first login.

## Shortcuts
- New issue anywhere: `c`
- Issue search/quick switcher: `Cmd+K`
- Assign: `a`. Status: `s`. Priority: `Cmd+Shift+P`. Labels: `l`. Due date: `d`.
- Cycle through views in current team: `g` then `1..9`
- Submit issue from new-issue modal: `Cmd+Return`

## API alternative
Most write operations have a clean GraphQL API (`LINEAR_API_KEY`). Use it for batch issue creation / bulk status changes. The UI is for reading and ad-hoc edits.

## Don't
- Don't drag issues across columns with vision — use the `s` shortcut to set status from the keyboard.
