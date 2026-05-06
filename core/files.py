"""Filesystem ops with policy guards.

Safer than raw bash: blocks writes/deletes under /System, /Library system dirs,
and /usr without explicit allow_unsafe=true. Read ops are unrestricted but
limited to 10MB per file by default.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Optional

# Path prefixes considered dangerous for write/delete
PROTECTED_PREFIXES = (
    "/System", "/usr/bin", "/usr/sbin", "/usr/lib", "/Library/Apple",
    "/private/var/db", "/Volumes/Recovery",
)


def _is_protected(path: str) -> Optional[str]:
    p = os.path.abspath(os.path.expanduser(path))
    for pre in PROTECTED_PREFIXES:
        if p.startswith(pre + "/") or p == pre:
            return pre
    return None


def read(path: str, *, max_bytes: int = 10 * 1024 * 1024) -> dict:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return {"ok": False, "error": "file not found"}
    if not p.is_file():
        return {"ok": False, "error": "not a file"}
    size = p.stat().st_size
    if size > max_bytes:
        return {"ok": False, "error": f"file too large ({size} > {max_bytes})",
                "size": size, "hint": "pass max_bytes to override"}
    try:
        text = p.read_text(encoding="utf-8")
        return {"ok": True, "text": text, "size": size, "lines": text.count("\n") + 1}
    except UnicodeDecodeError:
        # binary
        data = p.read_bytes()
        return {"ok": True, "binary": True, "size": size,
                "sha256": hashlib.sha256(data).hexdigest()}


def write(path: str, content: str, *, allow_unsafe: bool = False,
          create_dirs: bool = True) -> dict:
    danger = _is_protected(path)
    if danger and not allow_unsafe:
        return {"ok": False, "blocked_by_policy": danger,
                "hint": "Pass allow_unsafe=true (audit-logged) to write here."}
    p = Path(os.path.expanduser(path))
    if create_dirs:
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(p), "bytes_written": len(content.encode("utf-8"))}


def delete(path: str, *, allow_unsafe: bool = False, recursive: bool = False) -> dict:
    danger = _is_protected(path)
    if danger and not allow_unsafe:
        return {"ok": False, "blocked_by_policy": danger}
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return {"ok": True, "noop": True}
    try:
        if p.is_dir():
            if recursive:
                shutil.rmtree(p)
            else:
                p.rmdir()
        else:
            p.unlink()
        return {"ok": True, "deleted": str(p)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def move(src: str, dst: str, *, allow_unsafe: bool = False) -> dict:
    for x in (src, dst):
        d = _is_protected(x)
        if d and not allow_unsafe:
            return {"ok": False, "blocked_by_policy": d}
    sp = Path(os.path.expanduser(src))
    dp = Path(os.path.expanduser(dst))
    if not sp.exists():
        return {"ok": False, "error": "source not found"}
    dp.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(sp), str(dp))
    return {"ok": True, "src": str(sp), "dst": str(dp)}


def copy(src: str, dst: str, *, allow_unsafe: bool = False) -> dict:
    danger = _is_protected(dst)
    if danger and not allow_unsafe:
        return {"ok": False, "blocked_by_policy": danger}
    sp = Path(os.path.expanduser(src))
    dp = Path(os.path.expanduser(dst))
    if not sp.exists():
        return {"ok": False, "error": "source not found"}
    dp.parent.mkdir(parents=True, exist_ok=True)
    if sp.is_dir():
        shutil.copytree(str(sp), str(dp), dirs_exist_ok=True)
    else:
        shutil.copy2(str(sp), str(dp))
    return {"ok": True, "src": str(sp), "dst": str(dp)}


def list_dir(path: str, *, max_entries: int = 200) -> dict:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return {"ok": False, "error": "directory not found"}
    if not p.is_dir():
        return {"ok": False, "error": "not a directory"}
    items = []
    for i, entry in enumerate(sorted(p.iterdir())):
        if i >= max_entries:
            break
        try:
            st = entry.stat()
            items.append({
                "name": entry.name,
                "kind": "dir" if entry.is_dir() else "file" if entry.is_file() else "other",
                "size": st.st_size if entry.is_file() else None,
                "mtime": st.st_mtime,
            })
        except Exception:
            pass
    return {"ok": True, "path": str(p), "count": len(items), "items": items}


def exists(path: str) -> dict:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return {"exists": False}
    st = p.stat()
    return {"exists": True, "kind": "dir" if p.is_dir() else "file" if p.is_file() else "other",
            "size": st.st_size, "mtime": st.st_mtime}
