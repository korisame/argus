"""PDF text extraction.

Two paths:
  1. Native text via PyPDF2 / pypdfium2 (text-based PDFs)
  2. Apple Vision OCR per page (scanned PDFs) — slow but no cloud
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from adapters import ocr as _ocr


def _try_pypdf(path: str) -> Optional[str]:
    try:
        from pypdf import PdfReader
        r = PdfReader(path)
        out = []
        for i, page in enumerate(r.pages):
            try:
                out.append(f"--- page {i+1} ---")
                out.append(page.extract_text() or "")
            except Exception:
                pass
        return "\n".join(out) if out else None
    except Exception:
        return None


def _pdf_to_images(path: str, *, dpi: int = 150) -> list[str]:
    """Convert PDF pages to PNGs via sips (built-in macOS) or pdftoppm."""
    out = []
    if shutil.which("sips"):
        # sips can't do per-page directly; use ImageMagick if available
        pass
    if shutil.which("pdftoppm"):
        with tempfile.TemporaryDirectory(prefix="argus_pdf_") as td:
            base = os.path.join(td, "page")
            subprocess.run(["pdftoppm", "-r", str(dpi), "-png", path, base],
                           capture_output=True, timeout=120)
            for p in sorted(Path(td).glob("page-*.png")):
                # Move to /tmp with stable name
                dst = f"/tmp/argus_pdf_{p.stem}.png"
                shutil.copy(p, dst)
                out.append(dst)
    return out


def extract_text(path: str, *, force_ocr: bool = False,
                 max_pages: int = 50) -> dict:
    """Extract text from PDF. Tries native first, OCR if force_ocr or empty."""
    if not os.path.isfile(path):
        return {"ok": False, "error": "file not found"}
    text = None
    method = None
    if not force_ocr:
        text = _try_pypdf(path)
        if text and text.strip():
            method = "pypdf"
    if not text or force_ocr:
        if not _ocr.available():
            return {"ok": False, "error": "Apple Vision OCR unavailable + native text empty",
                    "tried_native": True}
        images = _pdf_to_images(path)[:max_pages]
        if not images:
            return {"ok": False,
                    "error": "no images produced (install pdftoppm: brew install poppler)"}
        chunks = []
        for i, img in enumerate(images):
            boxes = _ocr.all_text(img, fast=False)
            chunks.append(f"--- page {i+1} ---")
            chunks.append("\n".join(b["text"] for b in boxes))
        text = "\n".join(chunks)
        method = "apple_vision_ocr"
    return {"ok": True, "method": method, "chars": len(text or ""),
            "text": (text or "")[:50000]}


def page_count(path: str) -> dict:
    try:
        from pypdf import PdfReader
        return {"ok": True, "pages": len(PdfReader(path).pages)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
