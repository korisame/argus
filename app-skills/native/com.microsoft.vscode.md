---
bundle_id: com.microsoft.VSCode
name: Visual Studio Code
---

# VS Code

## Surface
Electron. AX is partial; keyboard-shortcut-driven workflow is mandatory.

## Core shortcuts
- **Command palette:** `Cmd+Shift+P` (or `F1`) — does almost everything
- **Quick open file:** `Cmd+P`
- **Quick open symbol:** `Cmd+T` or `@` inside Cmd+P
- **Go to symbol in file:** `Cmd+Shift+O`
- **Go to line:** `Ctrl+G` or `:` in Cmd+P
- **Toggle terminal:** `` Ctrl+` ``
- **New terminal:** `` Cmd+Shift+` ``
- **Toggle sidebar:** `Cmd+B`
- **Find in file:** `Cmd+F`. **Find in project:** `Cmd+Shift+F`.
- **Save:** `Cmd+S`. **Save all:** `Cmd+Option+S`.
- **Toggle word wrap:** `Option+Z`
- **Multi-cursor:** `Cmd+Option+↑/↓` or `Cmd+Click`
- **Comment line:** `Cmd+/`
- **Format file:** `Shift+Option+F`
- **Switch tab:** `Cmd+Option+→/←` (or `Cmd+1/2/3...`)
- **Close tab:** `Cmd+W`
- **Reopen closed tab:** `Cmd+Shift+T`

## Patterns
- Open file by name: `Cmd+P` → type partial → Return.
- Run a command: `Cmd+Shift+P` → type → Return. Most agent ops should use this.
- Insert at cursor (when terminal not focused): `argus_paste` is much faster than typing.

## API alternative
For programmatic file edits, prefer `argus_files` (read+write+edit) over UI driving.
For repo operations, prefer `argus_repl start cmd="bash"` and `git ...`.

## Don't
- Don't try to open Cursor/VS Code's AI chat via UI — those are extension-driven and brittle. Use the extension's own slash command if available.
