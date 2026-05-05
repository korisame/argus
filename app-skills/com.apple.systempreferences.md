---
bundle_id: com.apple.systempreferences
name: System Settings
---

# System Settings (macOS 13+)

## Surface
Native. Notoriously hard to script — the Settings app rewrote its UI, breaking most older AppleScript automations.

## Best strategies

### Open a specific pane directly via URL
Avoid the search box — pass an `x-apple.systempreferences:` URL:

```applescript
do shell script "open 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'"
```

Common pane IDs:
- `com.apple.preference.security?Privacy_Accessibility`
- `com.apple.preference.security?Privacy_ScreenCapture`
- `com.apple.preference.security?Privacy_Camera`
- `com.apple.preference.security?Privacy_Microphone`
- `com.apple.preference.network`
- `com.apple.preference.displays`
- `com.apple.preference.keyboard`
- `com.apple.preference.sound`

### Search inside Settings
1. `argus_open_app "System Settings"`
2. Cmd+F, type the query, Return.
3. Click the highlighted result with `argus_click`.

## Permission prompts during automation
If argus needs Accessibility / Screen Recording and the prompt fires:
1. `do shell script "open 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'"`
2. STOP and ask the user — toggling permissions for the host app
   (Claude / Terminal) can't be done by argus itself reliably and
   requires admin password.

## Don't
- Don't try to toggle a checkbox in Settings via vision when the result is permission-gated. Always escalate to the user.
