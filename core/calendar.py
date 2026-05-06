"""Read events from Apple Calendar via AppleScript.

Reads, doesn't write. Calendar AppleScript is slow (~3-5s for upcoming
queries) so cap result counts.
"""
from __future__ import annotations

import json
from typing import Optional

from . import safety


def upcoming(hours: int = 24, max_events: int = 20) -> dict:
    """Return events in the next `hours` hours across all calendars."""
    script = f'''
    set startDate to current date
    set endDate to startDate + {hours} * hours
    set evList to {{}}
    tell application "Calendar"
        repeat with c in (every calendar)
            try
                set evs to (every event of c whose start date is greater than or equal to startDate and start date is less than endDate)
                repeat with e in evs
                    set evRecord to "{{\\"calendar\\":" & quoted form of (name of c as text) & ", \\"summary\\":" & quoted form of (summary of e as text) & ", \\"start\\":" & quoted form of (start date of e as text) & ", \\"end\\":" & quoted form of (end date of e as text) & "}}"
                    set end of evList to evRecord
                end repeat
            end try
        end repeat
    end tell
    return evList as string
    '''
    res = safety.safe_exec_apple_script(script, timeout=20, allow_dangerous=False)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error") or res.get("stderr")}
    raw = (res.get("stdout") or "").strip()
    # Parse the comma-separated AppleScript records into JSON-y dicts
    events = []
    if raw:
        # Each record is "{key:val, ...}" — split heuristically
        chunks = []
        depth = 0
        cur = ""
        for ch in raw:
            cur += ch
            if ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    chunks.append(cur.strip().lstrip(","))
                    cur = ""
        for c in chunks:
            try:
                events.append(json.loads(c))
            except Exception:
                continue
    return {"ok": True, "hours": hours, "count": len(events),
            "events": events[:max_events]}
