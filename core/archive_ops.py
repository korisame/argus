"""Archive utilities: zip, tar.gz, gzip."""
from __future__ import annotations

import gzip
import os
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Optional


def zip_create(paths: list[str], out_path: str) -> dict:
    try:
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            for p in paths:
                src = Path(os.path.expanduser(p))
                if not src.exists():
                    continue
                if src.is_dir():
                    for f in src.rglob("*"):
                        if f.is_file():
                            z.write(f, arcname=str(f.relative_to(src.parent)))
                else:
                    z.write(src, arcname=src.name)
        return {"ok": True, "out_path": out_path,
                "size": os.path.getsize(out_path)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def zip_extract(zip_path: str, *, out_dir: Optional[str] = None) -> dict:
    out_dir = out_dir or os.path.splitext(zip_path)[0]
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(out_dir)
            members = z.namelist()
        return {"ok": True, "out_dir": out_dir, "members": len(members)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def tar_create(paths: list[str], out_path: str, *, gzip_compress: bool = True) -> dict:
    mode = "w:gz" if gzip_compress else "w"
    try:
        with tarfile.open(out_path, mode) as t:
            for p in paths:
                src = Path(os.path.expanduser(p))
                if src.exists():
                    t.add(src, arcname=src.name)
        return {"ok": True, "out_path": out_path,
                "size": os.path.getsize(out_path),
                "compressed": gzip_compress}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def tar_extract(tar_path: str, *, out_dir: Optional[str] = None) -> dict:
    out_dir = out_dir or os.path.splitext(tar_path)[0]
    try:
        with tarfile.open(tar_path, "r:*") as t:
            t.extractall(out_dir)
            members = t.getnames()
        return {"ok": True, "out_dir": out_dir, "members": len(members)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def gzip_compress(in_path: str, *, out_path: Optional[str] = None) -> dict:
    out_path = out_path or in_path + ".gz"
    try:
        with open(in_path, "rb") as f_in, gzip.open(out_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        return {"ok": True, "out_path": out_path,
                "in_size": os.path.getsize(in_path),
                "out_size": os.path.getsize(out_path)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def gzip_decompress(in_path: str, *, out_path: Optional[str] = None) -> dict:
    out_path = out_path or in_path.removesuffix(".gz")
    try:
        with gzip.open(in_path, "rb") as f_in, open(out_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        return {"ok": True, "out_path": out_path,
                "in_size": os.path.getsize(in_path),
                "out_size": os.path.getsize(out_path)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
