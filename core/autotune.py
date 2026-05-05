"""Autotune: read intent.jsonl + cache, propose updates to app-skills/.

Two outputs:
  1. promotions   — well-proven cache entries (>=20 successes, >=90% success rate)
                    appended to the matching app-skills/<scope>.md file
  2. failure_report — top recurring failures grouped by scope, surfaced for the
                      agent / user to investigate (often hint at a missing
                      app-skill pattern)

Designed to be run:
  - on demand via the argus_autotune MCP tool
  - or as a launchd job nightly (`argus_autotune --run`)

Idempotent: each app-skills file gets one auto-block delimited by markers,
overwritten in place. Manual additions outside the block are preserved.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Optional

from . import intent

MIN_SUCCESS_FOR_PROMOTION = 20
MIN_SUCCESS_RATIO = 0.90
TOP_N_FAILURES = 25

AUTO_BLOCK_HEADER = "<!-- argus-autotune:start -->"
AUTO_BLOCK_FOOTER = "<!-- argus-autotune:end -->"


# ─── failure analysis ────────────────────────────────────────────
def failure_report(window_lines: int = 1000) -> dict:
    """Group recent failures by (scope, target). Returns top recurring."""
    rows = intent.history(limit=window_lines, outcome="fail")
    by_pair: dict[tuple[str, str], int] = defaultdict(int)
    by_scope: dict[str, int] = defaultdict(int)
    for r in rows:
        scope = r.get("scope") or "unknown"
        target = r.get("target") or ""
        if target:
            by_pair[(scope, target)] += 1
        by_scope[scope] += 1
    ranked_pairs = sorted(by_pair.items(), key=lambda kv: -kv[1])[:TOP_N_FAILURES]
    return {
        "window_lines": window_lines,
        "total_failures": len(rows),
        "by_scope": dict(sorted(by_scope.items(), key=lambda kv: -kv[1])),
        "top_pairs": [{"scope": s, "target": t, "count": c}
                       for (s, t), c in ranked_pairs],
    }


# ─── promotions ──────────────────────────────────────────────────
def _eligible_entries() -> list[dict]:
    """Cache rows that have earned promotion."""
    out = []
    with sqlite3.connect(intent.CACHE_PATH, timeout=5) as c:
        rows = c.execute(
            "SELECT scope, target_norm, source, selector, confidence, "
            "successes, failures, last_success "
            "FROM selectors "
            "WHERE successes >= ? "
            "  AND CAST(successes AS REAL) / (successes + failures) >= ? "
            "ORDER BY successes DESC",
            (MIN_SUCCESS_FOR_PROMOTION, MIN_SUCCESS_RATIO),
        ).fetchall()
    keys = ["scope", "target_norm", "source", "selector", "confidence",
            "successes", "failures", "last_success"]
    return [dict(zip(keys, r)) for r in rows]


def _scope_to_skill_path(scope: str, skills_root: Path) -> Optional[Path]:
    """native:com.apple.finder → app-skills/native/com.apple.finder.md
       web:github.com         → app-skills/web/github.com.md
    """
    if scope.startswith("native:"):
        bundle = scope[len("native:"):].lower()
        if not bundle:
            return None
        return skills_root / "native" / f"{bundle}.md"
    if scope.startswith("web:"):
        host = scope[len("web:"):].lower()
        if not host:
            return None
        return skills_root / "web" / f"{host}.md"
    return None


def _render_block(promotions: list[dict]) -> str:
    """Render the auto-block: a Markdown table of high-confidence selectors."""
    if not promotions:
        return ""
    lines = [
        AUTO_BLOCK_HEADER,
        "## Argus learned selectors (autotuned)",
        "",
        "These were learned from your usage. Argus will skip the cascade and replay them when matching targets are clicked.",
        "",
        "| Target | Source | Selector | Successes | Confidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    for p in promotions:
        sel = (p["selector"] or "").replace("|", "\\|")
        lines.append(f"| `{p['target_norm']}` | {p['source']} | `{sel}` | "
                     f"{p['successes']} | {p['confidence']:.2f} |")
    lines.append(AUTO_BLOCK_FOOTER)
    return "\n".join(lines)


def _splice_block(file_text: str, block: str) -> str:
    """Replace existing auto-block (if present) or append at end."""
    pat = re.compile(re.escape(AUTO_BLOCK_HEADER) + r".*?" + re.escape(AUTO_BLOCK_FOOTER),
                     flags=re.DOTALL)
    if pat.search(file_text):
        return pat.sub(block, file_text)
    sep = "\n\n" if file_text and not file_text.endswith("\n\n") else ""
    return file_text + sep + block + "\n"


def promote(skills_root: Optional[Path] = None, dry_run: bool = False) -> dict:
    """Read cache, write promotions into app-skills/. Returns summary."""
    skills_root = skills_root or _default_skills_root()
    skills_root.mkdir(parents=True, exist_ok=True)
    (skills_root / "native").mkdir(parents=True, exist_ok=True)
    (skills_root / "web").mkdir(parents=True, exist_ok=True)

    entries = _eligible_entries()
    by_scope: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_scope[e["scope"]].append(e)

    written: list[dict] = []
    skipped: list[dict] = []
    for scope, items in by_scope.items():
        path = _scope_to_skill_path(scope, skills_root)
        if path is None:
            skipped.append({"scope": scope, "reason": "unsupported scope shape"})
            continue
        block = _render_block(items)
        existing = path.read_text(encoding="utf-8") if path.exists() else (
            f"---\n{'host' if scope.startswith('web:') else 'bundle_id'}: "
            f"{scope.split(':', 1)[1]}\n---\n\n# {scope.split(':', 1)[1]}\n\n"
        )
        new = _splice_block(existing, block)
        if dry_run:
            written.append({"scope": scope, "path": str(path),
                            "promotions": len(items), "would_write": True})
        else:
            path.write_text(new, encoding="utf-8")
            written.append({"scope": scope, "path": str(path),
                            "promotions": len(items)})
    return {
        "written": written,
        "skipped": skipped,
        "total_eligible_entries": len(entries),
        "scopes_touched": len(by_scope),
        "dry_run": dry_run,
    }


def _default_skills_root() -> Path:
    """app-skills/ next to this file's package."""
    here = Path(__file__).resolve().parent.parent
    return here / "app-skills"


def run_full(dry_run: bool = False) -> dict:
    """Full autotune pass: failure report + promotions."""
    return {
        "promotions": promote(dry_run=dry_run),
        "failures": failure_report(),
    }
