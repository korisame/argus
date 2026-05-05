"""Policy engine — guardrails on what argus can do.

Loads ~/.argus/policy.yaml at startup. Three checks per action:
  1. app_blocklist        — refuse to act on these apps/hosts entirely
  2. destructive_verbs    — require_confirm before clicking targets matching these
  3. type_blocklist       — refuse to type into these apps (e.g. 1Password)

If PyYAML is missing, falls back to a stdlib mini-parser (handles the
flat-list policy file we ship).

Default policy is permissive but flags the obvious dangers (1Password,
keychain, "delete account", "send money", "wire transfer", ...).
"""
from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from typing import Optional

POLICY_PATH = Path(os.path.expanduser("~/.argus/policy.yaml"))
_LOCK = threading.RLock()
_CACHED: Optional[dict] = None
_CACHED_MTIME: float = 0.0


_DEFAULT_POLICY = {
    "app_blocklist": [
        "com.agilebits.onepassword*",
        "com.lastpass.LastPass",
        "com.apple.keychainaccess",
    ],
    "type_blocklist": [
        "com.agilebits.onepassword*",
        "com.lastpass.LastPass",
    ],
    "destructive_verbs": [
        # English
        "delete account", "delete forever", "permanently delete",
        "send money", "wire transfer", "confirm payment", "place order",
        "buy now", "subscribe", "pay now", "transfer funds",
        "drop database", "drop table", "force push",
        # Italian
        "elimina account", "elimina definitivamente", "conferma pagamento",
        "invia denaro", "bonifico", "acquista ora", "abbonati",
    ],
    "require_confirm": True,        # gate destructive verbs (else just log)
    "block_secure_field": True,     # hard-block typing in AXSecureTextField
    "audit_log": True,              # append every blocked / confirmed action to intent log
}


def _load_yaml(text: str) -> dict:
    """Real PyYAML if installed, else stdlib mini-parser for flat-list files."""
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or {}
    except Exception:
        pass
    out: dict = {}
    cur_key: Optional[str] = None
    for line in text.splitlines():
        s = line.rstrip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("- "):
            if cur_key is None:
                continue
            val = s[2:].strip().strip('"').strip("'")
            out.setdefault(cur_key, []).append(val)
        elif ":" in s and not s.startswith(" "):
            k, _, v = s.partition(":")
            k = k.strip()
            v = v.strip()
            cur_key = k
            if v == "":
                out[k] = []
            elif v.lower() in ("true", "false"):
                out[k] = v.lower() == "true"
            else:
                out[k] = v.strip('"').strip("'")
    return out


def load(force: bool = False) -> dict:
    global _CACHED, _CACHED_MTIME
    with _LOCK:
        if not POLICY_PATH.exists():
            if _CACHED is None:
                _CACHED = dict(_DEFAULT_POLICY)
            return _CACHED
        try:
            mtime = POLICY_PATH.stat().st_mtime
        except Exception:
            mtime = 0.0
        if force or _CACHED is None or mtime > _CACHED_MTIME:
            try:
                txt = POLICY_PATH.read_text(encoding="utf-8")
                merged = dict(_DEFAULT_POLICY)
                merged.update(_load_yaml(txt))
                _CACHED = merged
                _CACHED_MTIME = mtime
            except Exception:
                _CACHED = dict(_DEFAULT_POLICY)
        return _CACHED


def _glob_match(pattern: str, value: str) -> bool:
    """Tiny glob: only `*` wildcard."""
    if not pattern or not value:
        return False
    pat = re.escape(pattern.lower()).replace(r"\*", ".*")
    return bool(re.fullmatch(pat, value.lower()))


def app_allowed(scope: str) -> tuple[bool, Optional[str]]:
    """Returns (allowed, reason_if_blocked)."""
    pol = load()
    bundle = ""
    if scope.startswith("native:"):
        bundle = scope[len("native:"):]
    elif scope.startswith("web:"):
        bundle = scope[len("web:"):]
    for pat in pol.get("app_blocklist") or []:
        if _glob_match(pat, bundle):
            return False, f"app '{bundle}' blocked by policy pattern {pat!r}"
    return True, None


def type_allowed(scope: str) -> tuple[bool, Optional[str]]:
    pol = load()
    bundle = scope[len("native:"):] if scope.startswith("native:") else \
             scope[len("web:"):] if scope.startswith("web:") else ""
    for pat in pol.get("type_blocklist") or []:
        if _glob_match(pat, bundle):
            return False, f"typing into '{bundle}' blocked by policy pattern {pat!r}"
    return True, None


def is_destructive(target: str) -> Optional[str]:
    """Returns the matched verb, or None."""
    pol = load()
    if not target:
        return None
    t = target.lower()
    for v in pol.get("destructive_verbs") or []:
        if v.lower() in t:
            return v
    return None


def doctor() -> dict:
    pol = load()
    return {
        "policy_file": str(POLICY_PATH),
        "exists": POLICY_PATH.exists(),
        "block_secure_field": pol.get("block_secure_field"),
        "require_confirm": pol.get("require_confirm"),
        "app_blocklist_n": len(pol.get("app_blocklist") or []),
        "type_blocklist_n": len(pol.get("type_blocklist") or []),
        "destructive_verbs_n": len(pol.get("destructive_verbs") or []),
    }


def write_default_policy() -> dict:
    """Idempotent: write the default policy file if it doesn't exist."""
    if POLICY_PATH.exists():
        return {"ok": True, "wrote": False, "path": str(POLICY_PATH)}
    POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# argus policy — guardrails. Reload is automatic on file change.",
        "",
        "block_secure_field: true",
        "require_confirm: true",
        "audit_log: true",
        "",
        "app_blocklist:",
    ]
    for v in _DEFAULT_POLICY["app_blocklist"]:
        lines.append(f'  - "{v}"')
    lines += ["", "type_blocklist:"]
    for v in _DEFAULT_POLICY["type_blocklist"]:
        lines.append(f'  - "{v}"')
    lines += ["", "destructive_verbs:"]
    for v in _DEFAULT_POLICY["destructive_verbs"]:
        lines.append(f'  - "{v}"')
    POLICY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(POLICY_PATH, 0o600)
    except Exception:
        pass
    return {"ok": True, "wrote": True, "path": str(POLICY_PATH)}
