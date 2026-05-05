# app-skills

Per-app knowledge files. Loaded by argus when an app becomes frontmost
(matching by `bundle_id` in front-matter, falling back to filename).

Add a new file when you discover a non-obvious pattern for an app —
keyboard shortcut, AppleScript that beats vision, an icon that
Moondream consistently misidentifies, etc.

Format:
```
---
bundle_id: com.foo.bar
name: Foo
---

# Foo

## Surface
...

## Common operations
...

## Quirks / Don't
...
```
