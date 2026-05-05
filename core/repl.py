"""Persistent process / REPL pattern.

The only feature worth keeping from desktop-commander: long-running shell
processes (Python, Node, psql, lldb, ssh, ...) that retain state between
calls. Each handle is identified by an integer pid plus a sticky `name`.

API (intent-shaped, not Posix):
  start(cmd, [name], [cwd], [env]) → {pid, name}
  send(pid|name, data, [enter])    → {bytes_sent}
  read(pid|name, [timeout_s])      → {stdout, stderr, alive, returncode?}
  kill(pid|name, [signal=15])      → {killed}
  list()                            → [{pid, name, cmd, alive, ...}]
"""
from __future__ import annotations

import os
import shlex
import signal as _signal
import subprocess
import threading
import time
from typing import Optional, Union

_LOCK = threading.RLock()
_PROCS: dict[int, dict] = {}      # pid → {name, cmd, popen, started, last_read}
_NAMES: dict[str, int] = {}       # name → pid


def _select(handle: Union[int, str]) -> Optional[dict]:
    with _LOCK:
        if isinstance(handle, int):
            return _PROCS.get(handle)
        if isinstance(handle, str):
            pid = _NAMES.get(handle)
            return _PROCS.get(pid) if pid else None
    return None


def start(cmd: str, name: Optional[str] = None,
          cwd: Optional[str] = None, env: Optional[dict] = None) -> dict:
    """Spawn a long-running process. Returns {pid, name}."""
    args = shlex.split(cmd)
    full_env = {**os.environ}
    if env:
        full_env.update(env)
    p = subprocess.Popen(args, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         cwd=cwd, env=full_env,
                         text=True, bufsize=1)
    name = name or args[0]
    with _LOCK:
        _PROCS[p.pid] = {"name": name, "cmd": cmd, "popen": p,
                         "started": time.time(), "last_read": 0.0,
                         "stdout_buf": [], "stderr_buf": []}
        _NAMES[name] = p.pid
    # background drain
    threading.Thread(target=_drain, args=(p.pid,), daemon=True).start()
    return {"pid": p.pid, "name": name}


def _drain(pid: int):
    proc = _select(pid)
    if not proc:
        return
    p: subprocess.Popen = proc["popen"]
    while p.poll() is None:
        line = p.stdout.readline() if p.stdout else ""
        if line:
            with _LOCK:
                proc["stdout_buf"].append(line)
        else:
            time.sleep(0.05)


def send(handle: Union[int, str], data: str, enter: bool = True) -> dict:
    proc = _select(handle)
    if not proc:
        return {"ok": False, "error": "no such process"}
    p: subprocess.Popen = proc["popen"]
    if not p.stdin:
        return {"ok": False, "error": "no stdin"}
    payload = data + ("\n" if enter and not data.endswith("\n") else "")
    try:
        p.stdin.write(payload)
        p.stdin.flush()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "bytes_sent": len(payload)}


def read(handle: Union[int, str], timeout_s: float = 1.0) -> dict:
    proc = _select(handle)
    if not proc:
        return {"ok": False, "error": "no such process"}
    p: subprocess.Popen = proc["popen"]
    deadline = time.monotonic() + timeout_s
    out_chunks = []
    while time.monotonic() < deadline:
        with _LOCK:
            if proc["stdout_buf"]:
                out_chunks.extend(proc["stdout_buf"])
                proc["stdout_buf"] = []
        if out_chunks:
            break
        time.sleep(0.05)
    err = ""
    try:
        if p.stderr and not p.stderr.closed:
            # non-blocking-ish: drain available
            import select
            r, _, _ = select.select([p.stderr], [], [], 0)
            if r:
                err = p.stderr.read(8192) or ""
    except Exception:
        pass
    rc = p.poll()
    return {"ok": True, "stdout": "".join(out_chunks), "stderr": err,
            "alive": rc is None, "returncode": rc}


def kill(handle: Union[int, str], sig: int = _signal.SIGTERM) -> dict:
    proc = _select(handle)
    if not proc:
        return {"ok": False, "error": "no such process"}
    p: subprocess.Popen = proc["popen"]
    try:
        p.send_signal(sig)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    try:
        p.wait(timeout=2)
    except Exception:
        try: p.kill()
        except Exception: pass
    with _LOCK:
        nm = proc["name"]
        _PROCS.pop(p.pid, None)
        if _NAMES.get(nm) == p.pid:
            _NAMES.pop(nm, None)
    return {"ok": True, "killed": p.pid}


def list_procs() -> list[dict]:
    out = []
    with _LOCK:
        for pid, proc in _PROCS.items():
            p: subprocess.Popen = proc["popen"]
            out.append({"pid": pid, "name": proc["name"],
                        "cmd": proc["cmd"], "alive": p.poll() is None,
                        "started": proc["started"]})
    return out
