"""High-level browser navigation via cdp_raw.

Wraps the few primitives most agents need: navigate, back, forward,
reload, new_tab. CDP-based, no UI clicking.
"""
from __future__ import annotations

from adapters import cdp_raw


def navigate(url: str) -> dict:
    return {"navigate": cdp_raw.navigate(url), "url": url}


def back() -> dict:
    js = "history.back()"
    return {"action": "back", "result": cdp_raw.evaluate(js)}


def forward() -> dict:
    js = "history.forward()"
    return {"action": "forward", "result": cdp_raw.evaluate(js)}


def reload(force: bool = False) -> dict:
    js = "location.reload(true)" if force else "location.reload()"
    return {"action": "reload", "force": force, "result": cdp_raw.evaluate(js)}


def new_tab(url: str = "about:blank") -> dict:
    """Create a new tab via CDP (Target.createTarget)."""
    res = cdp_raw._CLIENT._call("Target.createTarget", {"url": url})
    return {"action": "new_tab", "url": url, "result": res}


def close_tab(target_id: str | None = None) -> dict:
    """Close a tab by target id; defaults to active."""
    if target_id is None:
        active = cdp_raw._CLIENT._pick_active_target()
        if not active:
            return {"ok": False, "error": "no active tab"}
        target_id = active["id"]
    res = cdp_raw._CLIENT._call("Target.closeTarget", {"targetId": target_id})
    return {"action": "close_tab", "target_id": target_id, "result": res}


def list_tabs() -> dict:
    """Return all CDP targets (tabs + iframes + extensions)."""
    return {"targets": cdp_raw._CLIENT._http_targets()}
