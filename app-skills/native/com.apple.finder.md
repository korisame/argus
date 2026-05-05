---
bundle_id: com.apple.finder
name: Finder
---

# Finder

## Surface
Native macOS app. Use AX layer first; fall back to vision.

## Common operations

### Navigate to a path
Prefer AppleScript over clicking through sidebar:
```applescript
tell application "Finder"
    activate
    set target_folder to POSIX file "/Users/shaun/Documents/Reports" as alias
    open target_folder
end tell
```

### Switch view
- Cmd+1 (icon), Cmd+2 (list), Cmd+3 (column), Cmd+4 (gallery)
- Use `argus_key` with `modifiers="cmd"` and `name="1".."4"`

### Reveal file by name in current window
```applescript
tell application "Finder"
    activate
    set sel to (every item of (front window as Finder window) whose name is "report.pdf")
    select sel
end tell
```

### New folder
Cmd+Shift+N. Vision-grounded click on the rename text field is brittle; prefer:
```applescript
tell application "System Events" to keystroke "n" using {shift down, command down}
delay 0.4
tell application "System Events" to keystroke "MyFolder"
tell application "System Events" to key code 36
```

## Quirks
- Column view: clicking inside a column selects but doesn't open. Cmd+Down to open.
- Sidebar items resolve via AX text label (e.g. "Downloads", "iCloud Drive").
- Quick Look: select item, press Space. Use `argus_key name="space"`.

## Don't
- Don't try to drag-drop with vision; CGEvent drag is unreliable. Use Cmd+C / Cmd+V or AppleScript `move ... to ...`.
