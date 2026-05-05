"""Surface detection.

Three surfaces matter:
  - "browser"    Chrome / Chromium with debug port we can attach (CDP)
  - "webview"    Electron / WebKit-shell apps (WhatsApp, Spotify, VS Code, ...)
                 They have a Chrome runtime under the hood but argus-prime
                 currently treats them as native (AX still works, CDP doesn't).
  - "native"    Cocoa / AppKit apps (Finder, Mail, Preview, Excel, ...)
"""
from __future__ import annotations

from typing import Optional

from adapters import ax, cdp


# Bundle ids that are Chrome itself (we route through CDP)
_BROWSER_BUNDLES = {
    "com.google.Chrome", "com.google.Chrome.beta", "com.google.Chrome.canary",
    "org.chromium.Chromium",
    "company.thebrowser.Browser",          # Arc
}

# Bundle ids of Electron / webview shells (still native for argus-prime today)
_WEBVIEW_BUNDLES = {
    "com.tinyspeck.slackmacgap",            # Slack
    "com.spotify.client",                   # Spotify
    "com.microsoft.VSCode",                 # VS Code
    "com.todesktop.230313mzl4w4u92",        # Cursor
    "com.openai.chat",                      # ChatGPT desktop
    "com.anthropic.claudefordesktop",       # Claude desktop
    "com.automattic.beeper.desktop",        # Beeper
    "net.whatsapp.WhatsApp",                # WhatsApp
    "com.linear",                           # Linear
}


def detect() -> dict:
    """Return {surface, app, scope, ...} where scope is the cache key prefix."""
    front = ax.frontmost_app() or {}
    bundle = (front.get("bundle_id") or "").lower()
    name = front.get("name") or ""

    if any(bundle == b.lower() for b in _BROWSER_BUNDLES):
        host = None
        try:
            host = cdp.host()
        except Exception:
            host = None
        scope = f"web:{host}" if host else f"web:{name}"
        return {"surface": "browser", "app": front, "host": host,
                "scope": scope}

    if bundle in {b.lower() for b in _WEBVIEW_BUNDLES}:
        return {"surface": "webview", "app": front, "scope": f"native:{bundle}"}

    return {"surface": "native", "app": front, "scope": f"native:{bundle}"}


def doctor() -> dict:
    return {"current": detect(),
            "browser_bundles": sorted(_BROWSER_BUNDLES),
            "webview_bundles": sorted(_WEBVIEW_BUNDLES)}
