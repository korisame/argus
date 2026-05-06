"""argus_schedule — install launchd jobs that invoke argus tools on a calendar.

Each scheduled job is a launchd plist + a Python wrapper script. Jobs live
under ~/.argus-prime/scheduled/<name>/.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(os.path.expanduser("~/.argus-prime/scheduled"))
ROOT.mkdir(parents=True, exist_ok=True)

LAUNCHD_AGENTS = Path(os.path.expanduser("~/Library/LaunchAgents"))


def _label(name: str) -> str:
    return f"ai.argus.scheduled.{name}"


def install(name: str, *, tool: str, args: dict, hour: int = 9, minute: int = 0,
            weekday: int | None = None) -> dict:
    """Install a launchd job that runs argus_<tool>(args) at HH:MM.

    weekday: 0=Sunday..6=Saturday. None = every day.
    """
    job_dir = ROOT / name
    job_dir.mkdir(parents=True, exist_ok=True)
    args_path = job_dir / "args.json"
    args_path.write_text(json.dumps({"tool": tool, "args": args}))

    py = shutil.which("python3") or "/usr/bin/python3"
    server_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "mcp_server", "server.py")

    runner = job_dir / "run.py"
    runner.write_text(f"""#!/usr/bin/env python3
import json, subprocess, sys
spec = json.loads(open(r'{args_path}').read())
inp = '\\n'.join([
    '{{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{{}}}}',
    json.dumps({{"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {{"name": "argus_" + spec["tool"], "arguments": spec["args"]}}}}),
])
r = subprocess.run([sys.executable, r'{server_path}'], input=inp,
                   capture_output=True, text=True, env={{"ARGUS_ASYNC": "0"}}, timeout=180)
print(r.stdout)
""")

    plist_path = LAUNCHD_AGENTS / f"{_label(name)}.plist"
    cal_lines = [f"<key>Hour</key><integer>{hour}</integer>",
                 f"<key>Minute</key><integer>{minute}</integer>"]
    if weekday is not None:
        cal_lines.append(f"<key>Weekday</key><integer>{weekday}</integer>")
    plist = f"""<?xml version='1.0' encoding='UTF-8'?>
<!DOCTYPE plist PUBLIC '-//Apple//DTD PLIST 1.0//EN' 'http://www.apple.com/DTDs/PropertyList-1.0.dtd'>
<plist version='1.0'><dict>
<key>Label</key><string>{_label(name)}</string>
<key>ProgramArguments</key><array>
<string>{py}</string>
<string>{runner}</string>
</array>
<key>StartCalendarInterval</key><dict>{''.join(cal_lines)}</dict>
<key>StandardOutPath</key><string>{job_dir / 'out.log'}</string>
<key>StandardErrorPath</key><string>{job_dir / 'err.log'}</string>
</dict></plist>
"""
    LAUNCHD_AGENTS.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist)
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True, timeout=5)
    r = subprocess.run(["launchctl", "load", "-w", str(plist_path)],
                       capture_output=True, text=True, timeout=5)
    return {"ok": r.returncode == 0, "name": name, "label": _label(name),
            "plist": str(plist_path), "runner": str(runner),
            "schedule": f"{hour:02d}:{minute:02d}" + (f" weekday={weekday}" if weekday is not None else ""),
            "stderr": (r.stderr or "").strip()}


def uninstall(name: str) -> dict:
    plist = LAUNCHD_AGENTS / f"{_label(name)}.plist"
    if plist.exists():
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True, timeout=5)
        plist.unlink()
    job_dir = ROOT / name
    if job_dir.exists():
        shutil.rmtree(job_dir)
    return {"ok": True, "removed": name}


def list_jobs() -> dict:
    if not ROOT.is_dir():
        return {"jobs": []}
    out = []
    for d in sorted(ROOT.iterdir()):
        if not d.is_dir(): continue
        ap = d / "args.json"
        spec = json.loads(ap.read_text()) if ap.exists() else {}
        plist = LAUNCHD_AGENTS / f"{_label(d.name)}.plist"
        out.append({"name": d.name, "tool": spec.get("tool"),
                    "args": spec.get("args"),
                    "plist_present": plist.exists(),
                    "out_log": str(d / "out.log"),
                    "err_log": str(d / "err.log")})
    return {"jobs": out}
