# app-skills

Per-context knowledge files. Argus loads the matching one when an app/host
becomes the current scope.

## Layout

```
app-skills/
├── native/<bundle.id>.md       e.g. com.apple.finder.md
└── web/<host>.md                e.g. github.com.md
```

`<bundle.id>` matches what `argus_surface` returns under `app.bundle_id` for
native apps. `<host>` matches `host` for browser scope (`web:<host>`).

## When to add a new file

When you discover a non-obvious pattern for an app/site:
- a keyboard shortcut that beats UI clicks
- an icon that Moondream consistently misidentifies
- a stable AppleScript / API path that replaces UI driving
- an auth/session quirk worth documenting

## Format

```
---
bundle_id: com.foo.bar      # native only
host: foo.com               # web only
---

# Foo

## Surface
...

## Common operations / Selectors
...

## Don't
...
```

## Pre-shipped

**Native:** Finder, Mail, Preview/Anteprima, Excel, System Settings.
**Web:** github.com, mail.google.com, www.notion.so, linear.app.
