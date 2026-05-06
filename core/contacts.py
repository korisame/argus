"""Read Apple Contacts via AppleScript. Read-only."""
from __future__ import annotations

import json
from typing import Optional

from . import safety


def search(query: str, *, max_results: int = 10) -> dict:
    """Find contacts whose name/email/phone contains `query`. Returns list of dicts."""
    safe = query.replace('"', '\\"')
    script = f'''
    set output to ""
    tell application "Contacts"
        set foundList to (every person whose name contains "{safe}" or value of any email contains "{safe}" or value of any phone contains "{safe}")
        repeat with p in foundList
            set firstName to first name of p as text
            set lastName to last name of p as text
            set theName to name of p as text
            set emailList to ""
            try
                set emailList to (value of every email of p as text)
            end try
            set phoneList to ""
            try
                set phoneList to (value of every phone of p as text)
            end try
            set output to output & theName & "|" & emailList & "|" & phoneList & ";;"
        end repeat
    end tell
    return output
    '''
    res = safety.safe_exec_apple_script(script, timeout=15)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error") or res.get("stderr")}
    raw = (res.get("stdout") or "").strip()
    contacts = []
    for entry in raw.split(";;"):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("|")
        if len(parts) >= 3:
            contacts.append({
                "name": parts[0].strip(),
                "emails": [e.strip() for e in parts[1].split(",") if e.strip()],
                "phones": [p.strip() for p in parts[2].split(",") if p.strip()],
            })
    return {"ok": True, "query": query, "count": len(contacts),
            "contacts": contacts[:max_results]}
