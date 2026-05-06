"""Structured data extraction from screenshots.

Combines OCR (cheap, exact text) + Moondream Q&A (semantic) + heuristics
to fill a user-provided JSON schema. Use case: scrape any site/app without
an API.

Usage (via argus_extract MCP tool):
    argus_extract(schema={
        "price": "the total price as a number",
        "date":  "the order date in YYYY-MM-DD",
        "items": "list of line-item descriptions",
    })

Strategy per field:
    1. If the schema description matches a literal-text pattern (price,
       date, email, phone), try OCR-only extraction first.
    2. Otherwise (or if OCR can't produce a confident answer), ask
       Moondream cloud Q&A.
    3. Fall back to None and surface the field as 'missing' so the caller
       can decide.
"""
from __future__ import annotations

import os
import re
from typing import Any, Optional

from . import vision as _vision
from . import screen as _screen
from adapters import ocr as _ocr


_PRICE_RE = re.compile(r"(?:€|\$|£|USD|EUR|GBP)\s?(\d+[.,]\d{2})|(\d+[.,]\d{2})\s?(?:€|\$|£|USD|EUR|GBP)|(\d+[.,]\d{2})")
_DATE_RE = re.compile(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b|\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"\+?\d{1,3}[\s.-]?\(?\d{1,4}\)?[\s.-]?\d{1,4}[\s.-]?\d{1,9}")
_URL_RE = re.compile(r"https?://[^\s)]+")


def _all_text(screenshot_path: str) -> str:
    if not _ocr.available():
        return ""
    boxes = _ocr.all_text(screenshot_path, fast=True)
    return "\n".join(b["text"] for b in boxes)


def _ocr_match(field_name: str, description: str, text: str) -> Optional[Any]:
    """Try to extract `field_name` from OCR text using regex hints."""
    desc = (description or "").lower()
    fld = field_name.lower()
    if any(k in desc + fld for k in ("price", "total", "amount", "cost", "prezzo", "totale")):
        m = _PRICE_RE.search(text)
        if m:
            for g in m.groups():
                if g:
                    return float(g.replace(",", "."))
    if any(k in desc + fld for k in ("date", "data", "when")):
        m = _DATE_RE.search(text)
        if m:
            return m.group(0)
    if any(k in desc + fld for k in ("email", "e-mail", "mail")):
        m = _EMAIL_RE.search(text)
        if m: return m.group(0)
    if any(k in desc + fld for k in ("phone", "tel", "telefono", "mobile")):
        m = _PHONE_RE.search(text)
        if m: return m.group(0)
    if any(k in desc + fld for k in ("url", "link", "website")):
        m = _URL_RE.search(text)
        if m: return m.group(0)
    return None


def _vision_query(screenshot_path: str, question: str) -> Optional[str]:
    """Use Moondream Q&A to answer `question` about the screenshot."""
    mode = _vision.VISION._ensure()
    if mode == "cloud":
        try:
            from PIL import Image
            img = Image.open(screenshot_path)
            res = _vision.VISION._cloud.query(img, question)
            return (res or {}).get("answer")
        except Exception:
            return None
    if mode == "argus":
        try:
            v = _vision.VISION._argus_v
            fn = getattr(v, "query", None) or getattr(v, "ask", None)
            if callable(fn):
                return fn(screenshot_path, question)
        except Exception:
            return None
    return None


def extract(schema: dict, screenshot_path: Optional[str] = None,
            window_app: Optional[str] = None) -> dict:
    """Extract fields described in `schema` from the current screen / a window.

    schema: {field_name: description} — description is a natural-language
            hint for what to extract.
    Returns: {field_name: value | None, _meta: {ocr_used, vision_used, missing}}
    """
    # 1. Get a screenshot
    if not screenshot_path:
        if window_app:
            cap = _screen.capture_window(app=window_app,
                                          out_path="/tmp/argus_extract.png")
            if not cap.get("ok"):
                return {"error": cap.get("error"), "schema": schema}
            screenshot_path = cap["path"]
        else:
            cap = _screen.capture_frontmost(out_path="/tmp/argus_extract.png")
            if not cap.get("ok"):
                return {"error": cap.get("error"), "schema": schema}
            screenshot_path = cap["path"]

    # 2. OCR all text once (cheap)
    ocr_text = _all_text(screenshot_path) if _ocr.available() else ""

    out: dict = {}
    meta = {"screenshot": screenshot_path,
            "ocr_chars": len(ocr_text), "vision_calls": 0,
            "missing": []}

    for field, desc in schema.items():
        # OCR-first
        v = _ocr_match(field, str(desc), ocr_text)
        if v is not None:
            out[field] = v
            continue
        # Vision Q&A fallback
        question = f"What is the {field}? {desc}"
        ans = _vision_query(screenshot_path, question)
        meta["vision_calls"] += 1
        if ans:
            out[field] = ans
        else:
            out[field] = None
            meta["missing"].append(field)

    out["_meta"] = meta
    return out
