"""Apple Mail send/draft via AppleScript."""
from __future__ import annotations

from . import safety, intent


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def send(to: str, subject: str, body: str, *, cc: str | None = None,
         bcc: str | None = None, send_now: bool = False,
         confirmed: bool = False) -> dict:
    """Compose mail. send_now=True actually sends; otherwise leaves draft.

    Refuses send_now without confirmed=True (anti-misfire safety).
    """
    if send_now and not confirmed:
        return {"ok": False, "blocked": "send_now=true requires confirmed=true (safety)"}
    addrs = []
    addrs.append(f'make new to recipient with properties {{address:"{_esc(to)}"}}')
    if cc:  addrs.append(f'make new cc recipient with properties {{address:"{_esc(cc)}"}}')
    if bcc: addrs.append(f'make new bcc recipient with properties {{address:"{_esc(bcc)}"}}')
    script = (
        f'tell application "Mail"\n'
        f'  set newMsg to make new outgoing message with properties '
        f'{{subject:"{_esc(subject)}", content:"{_esc(body)}", visible:{"false" if send_now else "true"}}}\n'
        f'  tell newMsg\n    ' + "\n    ".join(addrs) + "\n  end tell\n"
        + (f'  send newMsg\n' if send_now else '')
        + 'end tell\n'
    )
    res = safety.safe_exec_apple_script(script, timeout=15)
    intent.log("argus.mail.send", target=to,
               outcome="ok" if res.get("ok") else "fail",
               observation={"sent": send_now, "subject": subject[:80]})
    return {"ok": res.get("ok", False), "to": to, "subject": subject,
            "send_now": send_now, "stderr": res.get("stderr")}
