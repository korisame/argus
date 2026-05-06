"""Export learned-cache + patterns as a shareable .json bundle.

Use case: contribute your most-proven selectors back to the community
registry. Strips per-machine/per-user state, keeps only (scope, target,
source, selector, confidence_avg).
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

from . import intent


def export(*, min_successes: int = 5, scopes: Optional[list[str]] = None,
           out_path: Optional[str] = None) -> dict:
    """Bundle high-confidence cache entries + patterns into one JSON file."""
    out_path = out_path or f"/tmp/argus_skills_export_{int(time.time())}.json"
    bundle: dict = {
        "exported_at": time.time(),
        "argus_version": os.environ.get("ARGUS_VERSION", "?"),
        "selectors": [],
        "patterns": [],
    }

    # Selectors
    if intent.CACHE_PATH.exists():
        c = sqlite3.connect(intent.CACHE_PATH, timeout=5)
        try:
            q = ("SELECT scope, target_norm, source, selector, confidence, "
                 "successes, failures FROM selectors WHERE successes >= ?")
            args: list = [min_successes]
            if scopes:
                placeholders = ",".join("?" * len(scopes))
                q += f" AND scope IN ({placeholders})"
                args.extend(scopes)
            rows = c.execute(q, args).fetchall()
        finally:
            c.close()
        for r in rows:
            bundle["selectors"].append({
                "scope": r[0], "target": r[1], "source": r[2],
                "selector": r[3], "confidence": r[4],
                "successes": r[5], "failures": r[6],
            })

    # Patterns
    pat_path = intent.DATA_DIR / "patterns.db"
    if pat_path.exists():
        c = sqlite3.connect(pat_path, timeout=5)
        try:
            q = ("SELECT scope, intent_norm, version, steps_json, successes, failures "
                 "FROM patterns WHERE successes >= ?")
            args = [min_successes]
            if scopes:
                placeholders = ",".join("?" * len(scopes))
                q += f" AND scope IN ({placeholders})"
                args.extend(scopes)
            rows = c.execute(q, args).fetchall()
        finally:
            c.close()
        for r in rows:
            try:
                steps = json.loads(r[3])
            except Exception:
                steps = []
            bundle["patterns"].append({
                "scope": r[0], "intent": r[1], "version": r[2],
                "steps": steps, "successes": r[4], "failures": r[5],
            })

    Path(out_path).write_text(json.dumps(bundle, indent=2))
    return {"ok": True, "path": out_path,
            "selector_count": len(bundle["selectors"]),
            "pattern_count": len(bundle["patterns"]),
            "size": os.path.getsize(out_path)}


def import_bundle(path: str, *, dry_run: bool = False) -> dict:
    """Apply selectors + patterns from a bundle into local DBs."""
    try:
        bundle = json.loads(Path(path).read_text())
    except Exception as e:
        return {"ok": False, "error": str(e)}
    sel_imported, pat_imported = 0, 0

    if not dry_run:
        for s in bundle.get("selectors", []):
            try:
                intent.cache_record_success(s["scope"], s["target"],
                                              source=s["source"],
                                              selector=s["selector"],
                                              confidence=float(s.get("confidence", 0.5)))
                sel_imported += 1
            except Exception:
                pass
        # Patterns: directly write via patterns module
        try:
            from . import patterns
            for p in bundle.get("patterns", []):
                patterns.save_pattern(p["scope"], p["intent"], p.get("steps", []))
                pat_imported += 1
        except Exception:
            pass

    return {"ok": True, "dry_run": dry_run,
            "selectors_in_bundle": len(bundle.get("selectors", [])),
            "patterns_in_bundle": len(bundle.get("patterns", [])),
            "selectors_imported": sel_imported,
            "patterns_imported": pat_imported}
