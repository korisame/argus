"""Unified text diff (difflib)."""
from __future__ import annotations

import difflib
from typing import Optional


def diff_strings(a: str, b: str, *, context: int = 3,
                 a_label: str = "before", b_label: str = "after") -> dict:
    a_lines = a.splitlines(keepends=True)
    b_lines = b.splitlines(keepends=True)
    diff = list(difflib.unified_diff(a_lines, b_lines,
                                       fromfile=a_label, tofile=b_label,
                                       n=context))
    if not diff:
        return {"ok": True, "identical": True, "diff": ""}
    return {"ok": True, "identical": False, "diff": "".join(diff),
            "lines_added": sum(1 for l in diff if l.startswith("+") and not l.startswith("+++")),
            "lines_removed": sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))}


def diff_files(a_path: str, b_path: str, *, context: int = 3) -> dict:
    try:
        a = open(a_path, encoding="utf-8").read()
        b = open(b_path, encoding="utf-8").read()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return diff_strings(a, b, context=context, a_label=a_path, b_label=b_path)


def similarity(a: str, b: str) -> dict:
    """Quick similarity ratio 0..1."""
    return {"ratio": difflib.SequenceMatcher(None, a, b).ratio(),
            "len_a": len(a), "len_b": len(b)}
