"""argus_uninstall — clean removal across all integration points."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

REMOVAL_PATHS = [
    "~/.claude/plugins/argus",
    "~/.codex/skills/argus",
    "~/.openclaw/skills/argus",
    "~/.argus-prime",
    "~/.argus",
    "~/Library/LaunchAgents/com.browser-harness-pro.chrome.plist",
]

ZSHRC_MARKERS = [
    "argus / browser-harness — use dedicated automation Chrome",
    "export BU_CDP_URL=http://127.0.0.1:9333",
]


def plan() -> dict:
    """List what would be removed without removing anything."""
    paths_present = []
    paths_missing = []
    for p in REMOVAL_PATHS:
        rp = Path(os.path.expanduser(p))
        (paths_present if rp.exists() else paths_missing).append(str(rp))
    zshrc = Path(os.path.expanduser("~/.zshrc"))
    zshrc_lines = []
    if zshrc.exists():
        for i, line in enumerate(zshrc.read_text(errors="ignore").splitlines(), 1):
            for m in ZSHRC_MARKERS:
                if m in line:
                    zshrc_lines.append({"line": i, "text": line.rstrip()})
    return {
        "paths_to_remove": paths_present,
        "paths_already_gone": paths_missing,
        "zshrc_lines_to_remove": zshrc_lines,
        "warning": "Hermes skill (~/.hermes/skills/argus → ~/Developer/argus/SKILL.md) "
                   "and ~/Developer/argus core are NOT removed by default — they belong "
                   "to the underlying argus CLI. Use 'force_full' to also wipe those.",
    }


def execute(force_full: bool = False, kill_chrome: bool = True) -> dict:
    """Actually remove. Returns summary."""
    removed = []
    failed = []

    paths = list(REMOVAL_PATHS)
    if force_full:
        paths += ["~/Developer/argus", "~/Developer/argus-mcp",
                  "~/.hermes/skills/argus"]

    for p in paths:
        rp = Path(os.path.expanduser(p))
        if not rp.exists():
            continue
        try:
            if rp.is_dir():
                shutil.rmtree(rp)
            else:
                rp.unlink()
            removed.append(str(rp))
        except Exception as e:
            failed.append({"path": str(rp), "error": str(e)})

    # Strip zshrc lines
    zshrc = Path(os.path.expanduser("~/.zshrc"))
    zshrc_changes = 0
    if zshrc.exists():
        try:
            text = zshrc.read_text(encoding="utf-8")
            for m in ZSHRC_MARKERS:
                # remove the line and a possible preceding comment
                text = re.sub(r"^.*" + re.escape(m) + r".*\n", "", text, flags=re.MULTILINE)
                zshrc_changes += 1
            zshrc.write_text(text, encoding="utf-8")
        except Exception as e:
            failed.append({"path": str(zshrc), "error": str(e)})

    # launchctl
    launchctl_msgs = []
    try:
        r = subprocess.run(["launchctl", "remove", "com.browser-harness-pro.chrome"],
                           capture_output=True, text=True, timeout=5)
        launchctl_msgs.append(("remove", r.returncode, r.stderr.strip() or "ok"))
    except Exception as e:
        launchctl_msgs.append(("remove", -1, str(e)))

    # kill automation chrome
    if kill_chrome:
        try:
            subprocess.run(["pkill", "-f", "chrome.*remote-debugging-port=9333"],
                           capture_output=True, timeout=5)
        except Exception:
            pass

    return {
        "removed": removed,
        "failed": failed,
        "zshrc_lines_stripped": zshrc_changes,
        "launchctl": launchctl_msgs,
        "force_full": force_full,
    }
