# Workflow templates

Declarative JSON workflows for `argus_workflow`. Loaded by name via the
`argus_workflow_template` tool.

## Format

```json
{
  "name":        "human readable name",
  "scope":       "web:<host> | native:<bundle.id>",
  "description": "what it does",
  "vars":        {"key": "default value"},     // {{key}} interpolated in args
  "steps":       [{"do": "click|type|paste|key|send_keys|scroll|open_app|wait_for|ask|extract", "args": {...}}],
  "on_error":    "abort | continue"
}
```

Branching: `{"if": {"ask": "predicate?"}, "expect": "yes", "then": [...], "else": [...]}`.

## Pre-shipped

| File | Scope | What |
|---|---|---|
| `post_to_notion.json` | web:www.notion.so | Open Notion, new page, type title + body, save |
| `gmail_compose.json` | web:mail.google.com | Compose new email — to/subject/body |
| `github_search_repo.json` | web:github.com | Search a repo via global `/` shortcut |
| `linear_new_issue.json` | web:linear.app | Create new issue via `c` shortcut |

## Adding new ones

1. Save as `app-skills/workflows/<name>.json`.
2. Loadable immediately via `argus_workflow_template name="..."`.
3. Open a PR with the template — keep `vars` generic, prefer `paste` for long
   text, prefer keyboard shortcuts over visual clicks where possible.
