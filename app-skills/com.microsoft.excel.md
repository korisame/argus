---
bundle_id: com.microsoft.Excel
name: Microsoft Excel
---

# Microsoft Excel (macOS)

## Surface
Native. Has rich AppleScript dictionary — use it, vision is overkill.

## Open / activate workbook
```applescript
tell application "Microsoft Excel"
    activate
    open "/Users/shaun/Documents/budget.xlsx"
end tell
```

## Read / write a cell
```applescript
tell application "Microsoft Excel"
    set v to value of range "B2" of active sheet
end tell

tell application "Microsoft Excel"
    set value of range "B2" of active sheet to 42
end tell
```

## Read a range as a list of rows
```applescript
tell application "Microsoft Excel"
    set vals to value of range "A1:C10" of active sheet
end tell
-- vals is a list of lists
```

## Set a formula
```applescript
tell application "Microsoft Excel"
    set formula of range "D2" of active sheet to "=SUM(A2:C2)"
end tell
```

## Switch sheet
```applescript
tell application "Microsoft Excel" to activate object worksheet "Q3" of active workbook
```

## Save
```applescript
tell application "Microsoft Excel" to save active workbook
```

## When to use the xlsx skill instead
For non-interactive editing (especially batch / large files), prefer the
`anthropic-skills:xlsx` skill — it uses openpyxl directly and doesn't
require Excel to be running.

## Don't
- Don't `argus_click` cell coordinates — Excel zoom level invalidates them.
- Don't paste large amounts of data via `argus_type` — use AppleScript `set value of range`.
