"""Initialize core Snowflake tables for The Silent Room (reverted app version).

Usage:
    python scripts/init_snowflake_schema.py

Snowflake credentials are read from environment variables:
    SNOWFLAKE_ACCOUNT
    SNOWFLAKE_USER
    SNOWFLAKE_PASSWORD
    SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_DATABASE
    SNOWFLAKE_SCHEMA
    SNOWFLAKE_ROLE      (optional)
"""

import os
import sys
import snowflake.connector


REQUIRED_VARS = (
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_PASSWORD",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_SCHEMA",
)


def get_params() -> dict:
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        sys.exit(f"Missing Snowflake environment variables: {', '.join(missing)}")
    params = {v: os.getenv(v) for v in REQUIRED_VARS}
    role = os.getenv("SNOWFLAKE_ROLE")
    if role:
        params["role"] = role
    return params


def main() -> None:
    params = get_params()
    conn = snowflake.connector.connect(
        account=params["SNOWFLAKE_ACCOUNT"],
        user=params["SNOWFLAKE_USER"],
        password=params["SNOWFLAKE_PASSWORD"],
        warehouse=params["SNOWFLAKE_WAREHOUSE"],
        database=params["SNOWFLAKE_DATABASE"],
        schema=params["SNOWFLAKE_SCHEMA"],
        role=params.get("role"),
    )
    cur = conn.cursor()
    try:
        statements = [
            """CREATE TABLE IF NOT EXISTS app_open (day DATE PRIMARY KEY)""",
            """CREATE TABLE IF NOT EXISTS points_log (ts TIMESTAMP_NTZ, delta INTEGER, reason STRING)""",
            """CREATE TABLE IF NOT EXISTS missions_log (ts TIMESTAMP_NTZ, date DATE, category STRING, mission STRING)""",
            """CREATE TABLE IF NOT EXISTS diary (
                    day DATE PRIMARY KEY,
                    big_question STRING,
                    tried STRING,
                    found STRING,
                    ai_wrong STRING,
                    next_step STRING,
                    gratitude STRING,
                    kindness STRING,
                    planet STRING
                )""",
            """CREATE TABLE IF NOT EXISTS user_missions (
                    id INTEGER AUTOINCREMENT,
                    created_ts TIMESTAMP_NTZ,
                    title STRING,
                    details STRING,
                    tag STRING,
                    status STRING DEFAULT 'todo'
                )""",
            """CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER AUTOINCREMENT,
                    name STRING,
                    age INTEGER,
                    interests STRING,
                    dream STRING
                )""",
            """CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER AUTOINCREMENT,
                    child_id INTEGER,
                    name STRING,
                    goal STRING,
                    tags STRING,
                    system_prompt STRING,
                    created_ts TIMESTAMP_NTZ,
                    archived BOOLEAN DEFAULT FALSE
                )""",
            """CREATE TABLE IF NOT EXISTS threads (
                    id INTEGER AUTOINCREMENT,
                    project_id INTEGER,
                    title STRING,
                    created_ts TIMESTAMP_NTZ,
                    archived BOOLEAN DEFAULT FALSE
                )""",
            """CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER AUTOINCREMENT,
                    thread_id INTEGER,
                    role STRING,
                    content STRING,
                    created_ts TIMESTAMP_NTZ,
                    model STRING,
                    tokens_in INTEGER,
                    tokens_out INTEGER
                )""",
            """CREATE TABLE IF NOT EXISTS content_feed (
                    id INTEGER AUTOINCREMENT,
                    title STRING,
                    summary STRING,
                    body STRING,
                    tags STRING,
                    cta STRING,
                    zoom_link STRING,
                    resource_link STRING,
                    posted_at DATE
                )""",
            """CREATE TABLE IF NOT EXISTS family_profiles (
                    family_id STRING PRIMARY KEY,
                    parent_email STRING,
                    kid_name STRING,
                    kid_age INTEGER,
                    interests ARRAY,
                    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
                )""",
            """CREATE TABLE IF NOT EXISTS learning_sessions (
                    session_id STRING PRIMARY KEY,
                    family_id STRING,
                    kid_interest STRING,
                    session_type STRING,
                    ai_guidance VARIANT,
                    parent_notes STRING,
                    progress_level INTEGER DEFAULT 0,
                    duration_sec INTEGER
                )""",
            """CREATE TABLE IF NOT EXISTS badges (
                    badge_id STRING PRIMARY KEY,
                    name STRING,
                    description STRING,
                    tag STRING
                )""",
            """CREATE TABLE IF NOT EXISTS family_badges (
                    family_id STRING,
                    badge_id STRING,
                    awarded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
                    PRIMARY KEY (family_id, badge_id)
                )""",
            """CREATE TABLE IF NOT EXISTS subscriptions (
                    family_id STRING PRIMARY KEY,
                    plan STRING,
                    status STRING,
                    renews_at DATE,
                    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
                )""",
        ]
        for stmt in statements:
            cur.execute(stmt)
        print("✅ Snowflake core tables ensured.")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
