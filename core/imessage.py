"""iMessage send via Messages.app AppleScript.

Apple deprecated some Messages AppleScript hooks; this uses the still-working
'send X to chat Y' pattern. Recipient must be an existing buddy or recent contact.
"""
from __future__ import annotations

from . import safety, intent


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def send(to: str, text: str, *, service: str = "iMessage",
         confirmed: bool = False) -> dict:
    """Send text to phone/email recipient. Refuses without confirmed=true."""
    if not confirmed:
        return {"ok": False, "blocked": "send requires confirmed=true (safety)"}
    script = (
        f'tell application "Messages"\n'
        f'  set targetService to 1st service whose service type = {service}\n'
        f'  set targetBuddy to buddy "{_esc(to)}" of targetService\n'
        f'  send "{_esc(text)}" to targetBuddy\n'
        f'end tell\n'
    )
    res = safety.safe_exec_apple_script(script, timeout=10)
    intent.log("argus.imessage.send", target=to,
               outcome="ok" if res.get("ok") else "fail",
               observation={"chars": len(text)})
    return {"ok": res.get("ok", False), "to": to, "service": service,
            "stderr": res.get("stderr")}
