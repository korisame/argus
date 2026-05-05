"""App-skills registry — pull community skills from a GitHub repo.

Default: https://github.com/korisame/argus-skills (raw content via raw.githubusercontent.com).
Override with ARGUS_SKILLS_REGISTRY=<owner>/<repo>.

Layout in the registry repo (mirror of argus's app-skills/):
  app-skills/native/<bundle.id>.md
  app-skills/web/<host>.md
  index.json                   # optional manifest with metadata
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

DEFAULT_REPO = os.environ.get("ARGUS_SKILLS_REGISTRY", "korisame/argus-skills")
DEFAULT_BRANCH = os.environ.get("ARGUS_SKILLS_BRANCH", "main")
LOCAL_SKILLS_ROOT = Path(__file__).resolve().parent.parent / "app-skills"


def _raw_url(path: str, repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"


def _fetch(url: str, timeout: float = 8.0) -> Optional[bytes]:
    try:
        req = Request(url, headers={"User-Agent": "argus/registry"})
        with urlopen(req, timeout=timeout) as r:
            return r.read()
    except (HTTPError, URLError, Exception):
        return None


def index() -> dict:
    """Fetch index.json from the registry. Falls back to a directory listing
    via the GitHub API if missing."""
    body = _fetch(_raw_url("index.json"))
    if body:
        try:
            return {"source": "index.json", **json.loads(body.decode("utf-8"))}
        except Exception:
            pass
    # Fallback: GitHub Contents API to list app-skills/
    api = f"https://api.github.com/repos/{DEFAULT_REPO}/contents/app-skills?ref={DEFAULT_BRANCH}"
    body = _fetch(api)
    if not body:
        return {"error": f"registry unreachable: {DEFAULT_REPO}@{DEFAULT_BRANCH}",
                "tried": [_raw_url("index.json"), api]}
    try:
        items = json.loads(body.decode("utf-8"))
    except Exception:
        return {"error": "invalid response from GitHub API"}
    return {"source": "github_api", "repo": DEFAULT_REPO, "branch": DEFAULT_BRANCH,
            "directories": [it["name"] for it in items if it.get("type") == "dir"]}


def install(name: str, kind: str = "auto") -> dict:
    """Install a single skill file. `name`:
       - "github.com" or "www.notion.so"      → web/
       - "com.apple.finder" or "com.foo.bar"  → native/
       - "web/github.com" or "native/com.foo" → explicit
       `kind`: "auto" | "native" | "web"
    """
    name = name.strip()
    if "/" in name:
        kind, _, name = name.partition("/")
    if kind == "auto":
        kind = "native" if name.startswith("com.") or name.startswith("net.") \
                       or name.startswith("org.") else "web"
    if kind not in ("native", "web"):
        return {"ok": False, "error": f"invalid kind: {kind}"}

    rel = f"app-skills/{kind}/{name}.md"
    body = _fetch(_raw_url(rel))
    if body is None:
        return {"ok": False, "error": f"not found: {rel} in {DEFAULT_REPO}"}

    LOCAL_SKILLS_ROOT.mkdir(parents=True, exist_ok=True)
    (LOCAL_SKILLS_ROOT / kind).mkdir(parents=True, exist_ok=True)
    out = LOCAL_SKILLS_ROOT / kind / f"{name}.md"
    out.write_bytes(body)
    return {"ok": True, "installed": str(out), "size": len(body),
            "from": _raw_url(rel)}


def list_local() -> dict:
    out = {"native": [], "web": []}
    for kind in ("native", "web"):
        d = LOCAL_SKILLS_ROOT / kind
        if d.is_dir():
            out[kind] = sorted(p.stem for p in d.glob("*.md")
                               if not p.name.startswith("README"))
    return out
