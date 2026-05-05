"""Annotated screenshot overlay — draw bbox + crosshair so the caller can
visually verify what was clicked when confidence is low.
"""
from __future__ import annotations

import base64
import io
import tempfile


def annotate(screenshot_path: str, x: float, y: float, bbox: list | None = None,
             label: str | None = None, max_dim: int = 1400) -> dict:
    """Returns {b64, mime, width, height} for a PNG with bbox + crosshair drawn."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.open(screenshot_path).convert("RGB")
    W0, H0 = img.size
    draw = ImageDraw.Draw(img, "RGBA")

    # bbox
    if bbox:
        bx, by, bw, bh = bbox
        draw.rectangle([bx, by, bx + bw, by + bh], outline=(255, 64, 64, 255), width=4)
        draw.rectangle([bx, by, bx + bw, by + bh], fill=(255, 64, 64, 60))

    # crosshair
    r = 24
    draw.ellipse([x - r, y - r, x + r, y + r], outline=(255, 255, 0, 255), width=4)
    draw.line([x - r * 1.5, y, x + r * 1.5, y], fill=(255, 255, 0, 255), width=3)
    draw.line([x, y - r * 1.5, x, y + r * 1.5], fill=(255, 255, 0, 255), width=3)

    if label:
        ty = max(8, y - r - 28)
        try:
            font = ImageFont.load_default()
            draw.text((x + 6, ty), label, fill=(255, 255, 255, 255), font=font,
                      stroke_width=2, stroke_fill=(0, 0, 0, 255))
        except Exception:
            draw.text((x + 6, ty), label, fill=(255, 255, 255, 255))

    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim))

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return {
        "b64": base64.b64encode(buf.getvalue()).decode(),
        "mime": "image/png",
        "width": img.size[0],
        "height": img.size[1],
        "original_size": [W0, H0],
    }
