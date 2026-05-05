---
bundle_id: com.apple.mail
name: Mail
---

# Mail (Apple)

## Surface
Native. AppleScript is far more reliable than UI clicking for compose/send.

## Compose + send (preferred)
```applescript
tell application "Mail"
    set newMsg to make new outgoing message with properties ¬
        {subject:"Hello", content:"Body text", visible:false}
    tell newMsg
        make new to recipient with properties {address:"someone@example.com"}
    end tell
    send newMsg
end tell
```

## Read selected message
```applescript
tell application "Mail"
    set m to item 1 of (get selection)
    return (subject of m) & "\n---\n" & (content of m)
end tell
```

## UI fallbacks (when AppleScript not enough)
- New mail: Cmd+N
- Reply: Cmd+R, Reply all: Cmd+Shift+R, Forward: Cmd+Shift+F
- Send: Cmd+Shift+D
- Mark as read/unread: Cmd+Shift+U

## Don't
- Don't paste 2FA codes into Mail compose via `argus_type`.
- Avoid clicking the send button via vision when Cmd+Shift+D works in 1 step.
