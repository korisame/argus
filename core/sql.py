"""SQLite client. Read-only by default; write requires allow_write=true."""
from __future__ import annotations

import sqlite3
from typing import Any


def execute(db_path: str, sql: str, *, params: tuple | list | None = None,
            allow_write: bool = False, max_rows: int = 500) -> dict:
    is_write = sql.strip().split(maxsplit=1)[0].upper() in (
        "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "REPLACE",
        "TRUNCATE", "PRAGMA",
    )
    if is_write and not allow_write:
        return {"ok": False, "blocked": "write SQL requires allow_write=true"}
    try:
        c = sqlite3.connect(db_path, timeout=5)
        try:
            cur = c.cursor()
            cur.execute(sql, params or ())
            if is_write:
                c.commit()
                return {"ok": True, "rows_affected": cur.rowcount, "write": True}
            cols = [d[0] for d in (cur.description or [])]
            rows = cur.fetchmany(max_rows)
            return {"ok": True, "columns": cols, "row_count": len(rows),
                    "rows": [dict(zip(cols, r)) for r in rows]}
        finally:
            c.close()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_tables(db_path: str) -> dict:
    return execute(db_path, "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")


def schema(db_path: str, table: str) -> dict:
    return execute(db_path, f"PRAGMA table_info({table})", allow_write=True)
