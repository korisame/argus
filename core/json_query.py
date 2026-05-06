"""Tiny dotted-path JSON query — alternative to jq for simple ops.

Path syntax:
  foo.bar       → obj["foo"]["bar"]
  foo[0]        → obj["foo"][0]
  foo[*].bar    → list of obj["foo"][i]["bar"]
  foo[?key=v]   → list of items where item["key"] == v
"""
from __future__ import annotations

import json
import re
from typing import Any


_TOKEN = re.compile(
    r"\.([a-zA-Z_][a-zA-Z0-9_-]*)|"          # .key
    r"\[(\d+)\]|"                            # [int]
    r"\[\*\]|"                               # [*]
    r"\[\?([a-zA-Z_][a-zA-Z0-9_]*)=([^\]]+)\]"  # [?k=v]
)


def query(data: Any, path: str) -> Any:
    """Apply path to data. Returns matched value/list. Empty path returns data."""
    if not path:
        return data
    # Allow leading 'foo' (no dot)
    if path[0] not in ".[":
        path = "." + path
    cur = [data]
    for m in _TOKEN.finditer(path):
        key, idx, wildcard_or_filter = None, None, None
        if m.group(1):
            key = m.group(1)
        elif m.group(2):
            idx = int(m.group(2))
        elif m.group(3):
            # filter [?k=v]
            fk, fv = m.group(3), m.group(4).strip().strip("'\"")
            wildcard_or_filter = ("filter", fk, fv)
        elif m.group(0) == "[*]":
            wildcard_or_filter = ("wildcard",)
        nxt = []
        for x in cur:
            if key is not None and isinstance(x, dict):
                nxt.append(x.get(key))
            elif idx is not None and isinstance(x, list) and 0 <= idx < len(x):
                nxt.append(x[idx])
            elif wildcard_or_filter:
                if wildcard_or_filter[0] == "wildcard":
                    if isinstance(x, list):
                        nxt.extend(x)
                    elif isinstance(x, dict):
                        nxt.extend(x.values())
                elif wildcard_or_filter[0] == "filter" and isinstance(x, list):
                    fk, fv = wildcard_or_filter[1], wildcard_or_filter[2]
                    nxt.extend(it for it in x
                                if isinstance(it, dict) and str(it.get(fk)) == fv)
        cur = [v for v in nxt if v is not None] or [None]
    if len(cur) == 1:
        return cur[0]
    return cur


def query_str(json_text: str, path: str) -> dict:
    try:
        data = json.loads(json_text)
    except Exception as e:
        return {"ok": False, "error": f"invalid JSON: {e}"}
    return {"ok": True, "result": query(data, path)}
