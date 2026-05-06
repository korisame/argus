"""Image utility — PIL-based resize/crop/format/compose."""
from __future__ import annotations

from typing import Optional


def info(path: str) -> dict:
    try:
        from PIL import Image
        img = Image.open(path)
        return {"ok": True, "path": path, "size": list(img.size),
                "mode": img.mode, "format": img.format}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def resize(path: str, *, max_dim: int = 1600, out_path: Optional[str] = None,
           keep_aspect: bool = True) -> dict:
    out_path = out_path or path.rsplit(".", 1)[0] + f".{max_dim}.png"
    try:
        from PIL import Image
        img = Image.open(path)
        if keep_aspect:
            img.thumbnail((max_dim, max_dim))
        else:
            img = img.resize((max_dim, max_dim))
        img.save(out_path)
        return {"ok": True, "out_path": out_path, "size": list(img.size)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def crop(path: str, *, bbox: list, out_path: Optional[str] = None) -> dict:
    """bbox: [x, y, w, h]."""
    out_path = out_path or path.rsplit(".", 1)[0] + ".cropped.png"
    try:
        from PIL import Image
        img = Image.open(path)
        x, y, w, h = bbox
        img2 = img.crop((int(x), int(y), int(x + w), int(y + h)))
        img2.save(out_path)
        return {"ok": True, "out_path": out_path, "size": list(img2.size)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def convert(path: str, *, out_path: str, format: str = "PNG",
            quality: int = 85) -> dict:
    try:
        from PIL import Image
        img = Image.open(path)
        if format.upper() in ("JPEG", "JPG"):
            img = img.convert("RGB")
        img.save(out_path, format=format, quality=quality)
        return {"ok": True, "out_path": out_path, "format": format}
    except Exception as e:
        return {"ok": False, "error": str(e)}
