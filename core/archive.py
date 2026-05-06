"""argus_archive — bundle a session into a tar.gz for sharing/debug."""
from __future__ import annotations

import os
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Optional

from . import intent


def bundle(*, include_screenshots: int = 50,
           out_path: Optional[str] = None) -> dict:
    """Create a tar.gz of intent.jsonl + cache.db + patterns.db + last N
    screenshots from /tmp."""
    if out_path is None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        out_path = f"/tmp/argus_archive_{ts}.tgz"
    home = intent.DATA_DIR
    items: list[tuple[Path, str]] = []
    for name in ("intent.jsonl", "cache.db", "patterns.db"):
        p = home / name
        if p.exists():
            items.append((p, name))
    # Last N screenshots from /tmp
    tmp = Path("/tmp")
    shots = sorted(
        [p for p in tmp.glob("argus_*.png") if p.is_file()],
        key=lambda p: -p.stat().st_mtime,
    )[:include_screenshots]
    for p in shots:
        items.append((p, f"screenshots/{p.name}"))
    # Plugin metadata if available
    try:
        cfg = Path("/Users/shaun/.claude/plugins/argus/.claude-plugin/plugin.json")
        if cfg.exists():
            items.append((cfg, "plugin.json"))
    except Exception:
        pass

    with tarfile.open(out_path, "w:gz") as tf:
        for src, arc in items:
            try:
                tf.add(src, arcname=arc)
            except Exception:
                pass
    size = os.path.getsize(out_path) if os.path.isfile(out_path) else 0
    return {"ok": True, "path": out_path, "size_bytes": size,
            "files_included": [arc for _, arc in items]}
