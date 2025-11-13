#!/usr/bin/env python3
"""
Dump the local SQLite progress database plus Knowledge Hub feed into JSON.

Usage:
    python scripts/export_sqlite.py

Outputs:
    data/sqlite_export.json
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "app.db"
EXPORT_PATH = ROOT / "data" / "sqlite_export.json"
FEED_PATH = ROOT / "data" / "content_feed.json"

# Skip FTS + internal SQLite tables
EXCLUDE_TABLES = {
    "sqlite_sequence",
    "messages_fts",
    "messages_fts_config",
    "messages_fts_content",
    "messages_fts_data",
    "messages_fts_docsize",
    "messages_fts_idx",
}


def fetch_tables(conn: sqlite3.Connection) -> Dict[str, List[Dict[str, Any]]]:
    tables = {}
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    for (table_name,) in cursor.fetchall():
        if table_name in EXCLUDE_TABLES:
            continue
        rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
        tables[table_name] = [dict(row) for row in rows]
    return tables


def load_feed() -> List[Dict[str, Any]]:
    if not FEED_PATH.exists():
        return []
    try:
        return json.loads(FEED_PATH.read_text())
    except json.JSONDecodeError:
        return []


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"SQLite database not found at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        payload = fetch_tables(conn)
    finally:
        conn.close()

    payload["content_feed"] = load_feed()
    payload["exported_at"] = datetime.now(tz=timezone.utc).isoformat()

    EXPORT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {EXPORT_PATH}")


if __name__ == "__main__":
    main()
