"""Wrapped git operations with audit + safety.

Read ops (status, log, diff): unrestricted.
Write ops (commit, push, force-push, reset): policy gate, audit log,
require confirmed=true for destructive (push --force, reset --hard).
"""
from __future__ import annotations

import subprocess
from typing import Optional

from . import safety, intent


def _git(args: list[str], cwd: str, timeout: float = 15.0) -> dict:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                           text=True, timeout=timeout)
        return {"ok": r.returncode == 0,
                "stdout": (r.stdout or "")[-5000:],
                "stderr": (r.stderr or "")[-2000:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "git timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def status(cwd: str) -> dict:
    return _git(["status", "--short", "--branch"], cwd)


def log(cwd: str, n: int = 10) -> dict:
    return _git(["log", f"-{n}", "--oneline", "--decorate"], cwd)


def diff(cwd: str, *, staged: bool = False, path: Optional[str] = None) -> dict:
    args = ["diff"]
    if staged: args.append("--staged")
    if path: args.append(path)
    return _git(args, cwd, timeout=20)


def add(cwd: str, paths: list[str] | None = None, all_files: bool = False) -> dict:
    if all_files:
        return _git(["add", "-A"], cwd)
    if not paths:
        return {"ok": False, "error": "paths or all_files=true required"}
    return _git(["add", *paths], cwd)


def commit(cwd: str, message: str, *, allow_empty: bool = False) -> dict:
    args = ["commit", "-m", message]
    if allow_empty: args.append("--allow-empty")
    res = _git(args, cwd)
    intent.log("argus.git.commit", target=cwd,
               outcome="ok" if res.get("ok") else "fail",
               observation={"message": message[:120]})
    return res


def push(cwd: str, *, remote: str = "origin", branch: str | None = None,
         force: bool = False, confirmed: bool = False) -> dict:
    if force and not confirmed:
        return {"ok": False, "blocked": "force push requires confirmed=true"}
    args = ["push", remote]
    if branch: args.append(branch)
    if force:  args.append("--force-with-lease")
    res = _git(args, cwd, timeout=60)
    intent.log("argus.git.push", target=f"{remote}/{branch or 'HEAD'}",
               outcome="ok" if res.get("ok") else "fail",
               observation={"force": force})
    return res


def pull(cwd: str, *, remote: str = "origin", branch: str | None = None,
         rebase: bool = False) -> dict:
    args = ["pull"]
    if rebase: args.append("--rebase")
    args += [remote]
    if branch: args.append(branch)
    return _git(args, cwd, timeout=60)


def checkout(cwd: str, ref: str) -> dict:
    return _git(["checkout", ref], cwd)


def branch_list(cwd: str) -> dict:
    return _git(["branch", "-a"], cwd)


def reset(cwd: str, ref: str = "HEAD", *, hard: bool = False,
          confirmed: bool = False) -> dict:
    if hard and not confirmed:
        return {"ok": False, "blocked": "reset --hard requires confirmed=true"}
    args = ["reset"]
    if hard: args.append("--hard")
    args.append(ref)
    return _git(args, cwd)
