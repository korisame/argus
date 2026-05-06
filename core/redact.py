"""Privacy filter — blur PII (emails, credit cards, SSNs, phone numbers) in screenshots.

Strategy:
  1. OCR the image
  2. Match regex patterns on each detected box
  3. Composite a blurred / blacked-out rectangle over each match
"""
from __future__ import annotations

import re
from typing import Optional

from adapters import ocr as _ocr

PATTERNS = {
    "email":       re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "ssn_us":      re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b"),
    "phone":       re.compile(r"\+?\d{1,3}[\s.\-]?\(?\d{1,4}\)?[\s.\-]?\d{1,4}[\s.\-]?\d{1,9}"),
    "iban":        re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
    "api_key":     re.compile(r"(?:sk-|pk_|mk_|gho_|ghp_|github_pat_)[A-Za-z0-9_]{16,}"),
}


def redact(input_path: str, *, out_path: Optional[str] = None,
           kinds: Optional[list[str]] = None,
           method: str = "blur",   # "blur" or "blackout"
           blur_radius: int = 12) -> dict:
    if not _ocr.available():
        return {"ok": False, "error": "OCR unavailable"}
    out_path = out_path or input_path.rsplit(".", 1)[0] + ".redacted.png"
    kinds = kinds or list(PATTERNS.keys())
    boxes = _ocr.all_text(input_path, fast=False)
    redactions = []
    for b in boxes:
        for kind in kinds:
            pat = PATTERNS.get(kind)
            if not pat: continue
            if pat.search(b["text"]):
                redactions.append({**b, "kind": kind})
                break

    if not redactions:
        return {"ok": True, "out_path": input_path,
                "redactions": 0, "noop": True}

    try:
        from PIL import Image, ImageFilter, ImageDraw
        img = Image.open(input_path).convert("RGB")
        if method == "blur":
            for r in redactions:
                x, y, w, h = int(r["x"]), int(r["y"]), int(r["w"]), int(r["h"])
                region = img.crop((x, y, x + w, y + h))
                region = region.filter(ImageFilter.GaussianBlur(radius=blur_radius))
                img.paste(region, (x, y))
        else:
            draw = ImageDraw.Draw(img)
            for r in redactions:
                x, y, w, h = int(r["x"]), int(r["y"]), int(r["w"]), int(r["h"])
                draw.rectangle([x, y, x + w, y + h], fill=(0, 0, 0))
        img.save(out_path)
        return {"ok": True, "out_path": out_path,
                "redactions": len(redactions),
                "by_kind": {k: sum(1 for r in redactions if r["kind"] == k)
                             for k in kinds}}
    except Exception as e:
        return {"ok": False, "error": str(e)}
