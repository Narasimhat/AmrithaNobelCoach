#!/usr/bin/env python3
"""
Load data/sqlite_export.json into Snowflake tables.

Required environment variables:
  SNOWFLAKE_ACCOUNT
  SNOWFLAKE_USER
  SNOWFLAKE_PASSWORD
  SNOWFLAKE_WAREHOUSE
  SNOWFLAKE_DATABASE
  SNOWFLAKE_SCHEMA

Usage:
  python3 scripts/load_to_snowflake.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable

import snowflake.connector

ROOT = Path(__file__).resolve().parents[1]
EXPORT_PATH = ROOT / "data" / "sqlite_export.json"

TABLE_SPECS = {
    "profiles": """
        id INTEGER,
        name STRING,
        age INTEGER,
        interests STRING,
        dream STRING
    """,
    "projects": """
        id INTEGER,
        child_id INTEGER,
        name STRING,
        goal STRING,
        tags STRING,
        system_prompt STRING,
        created_ts STRING,
        archived INTEGER
    """,
    "threads": """
        id INTEGER,
        project_id INTEGER,
        title STRING,
        created_ts STRING,
        archived INTEGER
    """,
    "messages": """
        id INTEGER,
        thread_id INTEGER,
        role STRING,
        content STRING,
        created_ts STRING,
        model STRING,
        tokens_in INTEGER,
        tokens_out INTEGER
    """,
    "points_log": """
        ts STRING,
        delta INTEGER,
        reason STRING
    """,
    "missions_log": """
        ts STRING,
        date STRING,
        category STRING,
        mission STRING
    """,
    "user_missions": """
        id INTEGER,
        created_ts STRING,
        title STRING,
        details STRING,
        tag STRING,
        status STRING DEFAULT 'todo'
    """,
    "diary": """
        day STRING,
        big_question STRING,
        tried STRING,
        found STRING,
        ai_wrong STRING,
        next_step STRING,
        gratitude STRING,
        kindness STRING,
        planet STRING
    """,
    "content_feed": """
        title STRING,
        summary STRING,
        body STRING,
        tags STRING,
        cta STRING,
        zoom_link STRING,
        resource_link STRING,
        posted_at STRING
    """,
}

TABLE_COLUMNS = {
    "profiles": ["id", "name", "age", "interests", "dream"],
    "projects": ["id", "child_id", "name", "goal", "tags", "system_prompt", "created_ts", "archived"],
    "threads": ["id", "project_id", "title", "created_ts", "archived"],
    "messages": ["id", "thread_id", "role", "content", "created_ts", "model", "tokens_in", "tokens_out"],
    "points_log": ["ts", "delta", "reason"],
    "missions_log": ["ts", "date", "category", "mission"],
    "user_missions": ["id", "created_ts", "title", "details", "tag", "status"],
    "diary": ["day", "big_question", "tried", "found", "ai_wrong", "next_step", "gratitude", "kindness", "planet"],
    "content_feed": ["title", "summary", "body", "tags", "cta", "zoom_link", "resource_link", "posted_at"],
}


def get_conn():
    missing = [key for key in [
        "SNOWFLAKE_ACCOUNT",
        "SNOWFLAKE_USER",
        "SNOWFLAKE_PASSWORD",
        "SNOWFLAKE_WAREHOUSE",
        "SNOWFLAKE_DATABASE",
        "SNOWFLAKE_SCHEMA",
    ] if not os.getenv(key)]
    if missing:
        raise SystemExit(f"Missing environment variables: {', '.join(missing)}")

    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema=os.getenv("SNOWFLAKE_SCHEMA"),
    )


def ensure_table(cursor, table: str, spec: str) -> None:
    cursor.execute(f"CREATE OR REPLACE TABLE {table} ({spec})")


def insert_rows(cursor, table: str, rows: Iterable[Dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        return
    columns = TABLE_COLUMNS.get(table) or list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    payload = []
    for row in rows:
        values = []
        for col in columns:
            value = row.get(col)
            if isinstance(value, (list, dict)):
                value = json.dumps(value)
            values.append(value)
        payload.append(values)
    cursor.executemany(insert_sql, payload)


def main() -> None:
    if not EXPORT_PATH.exists():
        raise SystemExit(f"{EXPORT_PATH} not found. Run scripts/export_sqlite.py first.")
    payload = json.loads(EXPORT_PATH.read_text())

    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(f"USE DATABASE {os.getenv('SNOWFLAKE_DATABASE')}")
        cursor.execute(f"USE SCHEMA {os.getenv('SNOWFLAKE_SCHEMA')}")
        for table, spec in TABLE_SPECS.items():
            data = payload.get(table, [])
            ensure_table(cursor, table, spec)
            insert_rows(cursor, table, data)
            print(f"Loaded {len(data)} rows into {table}")
        conn.commit()
    print("Snowflake load complete.")


if __name__ == "__main__":
    main()
