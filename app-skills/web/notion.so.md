---
host: www.notion.so
---

# Notion (www.notion.so)

## Surface
Browser. Auth via JWT in localStorage (NOT just cookies) — `argus_session save` post-v0.3 captures localStorage too.

## Selectors / patterns
- Quick switcher: `Cmd+P` then type page name + Return. Faster and more reliable than navigating the sidebar.
- Slash commands inside any block: `/h1`, `/todo`, `/code`, `/database`, etc.
- Mention person/page: `@`.
- Block menu (drag handle): hover left of a block, click the `⋮⋮` icon. Vision-grounded if needed.

## Database queries via API (when possible)
For programmatic reads/writes of databases, prefer the Notion HTTP API (set `NOTION_TOKEN` env var) over driving the UI. Faster, deterministic, no rate-limit issues.

## Don't
- Don't bulk-edit pages via UI — use the API.
- Don't rely on URL-based navigation for sub-pages within a database; their URLs change when moved.
