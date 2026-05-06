"""Search a substring across all visible windows.

Captures each visible window via core.screen + runs Apple Vision OCR,
returns matches with bbox + window metadata.
"""
from __future__ import annotations

import re
from typing import Optional

from . import screen as _screen
from adapters import ocr as _ocr


def search(query: str, *, case_sensitive: bool = False,
           max_windows: int = 12, max_matches: int = 50) -> dict:
    if not _screen.available() or not _ocr.available():
        return {"ok": False, "error": "screen / OCR unavailable"}
    wins = _screen.list_windows()[:max_windows]
    pat = re.compile(re.escape(query), 0 if case_sensitive else re.IGNORECASE)
    hits = []
    for w in wins:
        path = f"/tmp/argus_text_search_{w['wid']}.png"
        try:
            _screen.capture(w["wid"], out_path=path)
        except Exception:
            continue
        boxes = _ocr.all_text(path, fast=True)
        for b in boxes:
            if pat.search(b["text"]):
                hits.append({
                    "wid": w["wid"], "owner": w["owner"], "title": w["title"],
                    "text": b["text"],
                    "x": b["x"] + w["bounds"]["x"],
                    "y": b["y"] + w["bounds"]["y"],
                    "bbox_in_window": [b["x"], b["y"], b["w"], b["h"]],
                    "confidence": b["confidence"],
                })
                if len(hits) >= max_matches:
                    break
        if len(hits) >= max_matches:
            break
    return {"ok": True, "query": query, "hits": hits, "windows_searched": min(len(wins), max_windows)}
