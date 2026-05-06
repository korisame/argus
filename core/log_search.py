"""Search intent.jsonl with regex/text query, optional time window."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Optional

from . import intent


def search(query: str, *, regex: bool = False,
           since_hours: Optional[float] = None,
           limit: int = 50,
           field: Optional[str] = None) -> dict:
    """Search the intent log. `field` ∈ {target, intent, scope, source, observation}.
    If field is None, search across all string fields."""
    if not intent.LOG_PATH.exists():
        return {"ok": True, "count": 0, "matches": []}
    pat = re.compile(query, re.IGNORECASE) if regex else None
    cutoff = (time.time() - since_hours * 3600) if since_hours else None
    matches: list[dict] = []
    with open(intent.LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if cutoff and row.get("ts", 0) < cutoff:
                continue
            haystack: str
            if field:
                v = row.get(field)
                haystack = json.dumps(v) if isinstance(v, (dict, list)) else str(v or "")
            else:
                haystack = json.dumps(row)
            hit = (pat.search(haystack) if regex else
                   query.lower() in haystack.lower())
            if hit:
                matches.append(row)
                if len(matches) >= limit:
                    break
    return {"ok": True, "query": query, "count": len(matches),
            "matches": matches}
