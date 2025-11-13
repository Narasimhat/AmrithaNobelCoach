"""Snowflake persistence helpers for The Silent Room."""

from __future__ import annotations

import datetime
import os
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

import snowflake.connector
from snowflake.connector import DictCursor

REQUIRED_VARS = (
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_PASSWORD",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_SCHEMA",
)


def _snowflake_params() -> Dict[str, str]:
    params = {var: os.getenv(var) for var in REQUIRED_VARS}
    missing = [key for key, value in params.items() if not value]
    if missing:
        raise RuntimeError(
            "Missing Snowflake configuration: " + ", ".join(missing)
        )
    return params


def get_conn() -> snowflake.connector.SnowflakeConnection:
    params = _snowflake_params()
    return snowflake.connector.connect(
        account=params["SNOWFLAKE_ACCOUNT"],
        user=params["SNOWFLAKE_USER"],
        password=params["SNOWFLAKE_PASSWORD"],
        warehouse=params["SNOWFLAKE_WAREHOUSE"],
        database=params["SNOWFLAKE_DATABASE"],
        schema=params["SNOWFLAKE_SCHEMA"],
        autocommit=True,
    )


def _execute(query: str, params: Iterable[Any] | None = None, fetch: str = ""):
    params = tuple(params or ())
    with get_conn() as conn:
        cursor = conn.cursor(DictCursor)
        cursor.execute(query, params)
        if fetch == "one":
            return cursor.fetchone()
        if fetch == "all":
            return cursor.fetchall()
        return None


def init_db() -> None:
    statements = [
        """CREATE TABLE IF NOT EXISTS app_open (
                day DATE PRIMARY KEY
            )""",
        """CREATE TABLE IF NOT EXISTS points_log (
                ts TIMESTAMP_NTZ,
                delta INTEGER,
                reason STRING
            )""",
        """CREATE TABLE IF NOT EXISTS missions_log (
                ts TIMESTAMP_NTZ,
                date DATE,
                category STRING,
                mission STRING
            )""",
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
    ]
    for statement in statements:
        _execute(statement)


def mark_open_today() -> None:
    today = datetime.date.today()
    query = """
        MERGE INTO app_open AS target
        USING (SELECT %s::DATE AS day) AS source
        ON target.day = source.day
        WHEN NOT MATCHED THEN
            INSERT (day) VALUES (source.day)
    """
    _execute(query, (today,))


def add_points(delta: int, reason: str) -> None:
    _execute(
        "INSERT INTO points_log (ts, delta, reason) VALUES (%s, %s, %s)",
        (datetime.datetime.utcnow(), delta, reason),
    )


def log_mission(date: str, category: str, mission: str) -> None:
    mission_date = (
        datetime.date.fromisoformat(date) if isinstance(date, str) else date
    )
    _execute(
        "INSERT INTO missions_log (ts, date, category, mission) VALUES (%s, %s, %s, %s)",
        (datetime.datetime.utcnow(), mission_date, category, mission),
    )


def save_diary(day: str, entry: Dict[str, str]) -> None:
    query = """
        MERGE INTO diary AS target
        USING (SELECT %s::DATE AS day) AS source
        ON target.day = source.day
        WHEN MATCHED THEN UPDATE SET
            big_question = %s,
            tried = %s,
            found = %s,
            ai_wrong = %s,
            next_step = %s,
            gratitude = %s,
            kindness = %s,
            planet = %s
        WHEN NOT MATCHED THEN INSERT (
            day, big_question, tried, found, ai_wrong, next_step, gratitude, kindness, planet
        ) VALUES (
            source.day, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """
    values = (
        day,
        entry.get("big_question"),
        entry.get("what_we_tried"),
        entry.get("what_we_found"),
        entry.get("how_ai_might_be_wrong"),
        entry.get("next_step"),
        entry.get("gratitude"),
        entry.get("kindness_act"),
        entry.get("planet_act"),
        entry.get("big_question"),
        entry.get("what_we_tried"),
        entry.get("what_we_found"),
        entry.get("how_ai_might_be_wrong"),
        entry.get("next_step"),
        entry.get("gratitude"),
        entry.get("kindness_act"),
        entry.get("planet_act"),
    )
    _execute(query, values)


def total_points() -> int:
    row = _execute("SELECT COALESCE(SUM(delta), 0) AS total FROM points_log", fetch="one")
    return int(row["TOTAL"] or 0)


def streak_days() -> int:
    rows = _execute("SELECT day FROM app_open ORDER BY day", fetch="all")
    recorded = [row["DAY"] for row in rows]
    if not recorded:
        return 0
    recorded_dates = {day for day in recorded}
    today = datetime.date.today()
    streak = 0
    for offset in range(len(recorded_dates) + 1):
        candidate = today - datetime.timedelta(days=offset)
        if candidate in recorded_dates:
            streak += 1
        else:
            break
    return streak


def count(kind: str) -> int:
    reason_map = {
        "missions": "mission_done",
        "kindness": "kindness_act",
        "planet": "planet_act",
    }
    reason = reason_map.get(kind)
    if not reason:
        return 0
    row = _execute(
        "SELECT COUNT(*) AS cnt FROM points_log WHERE reason=%s",
        (reason,),
        fetch="one",
    )
    return int(row["CNT"] or 0)


def daily_reason_count(reason: str, day: Optional[str] = None) -> int:
    target = day or datetime.date.today().isoformat()
    row = _execute(
        "SELECT COUNT(*) AS cnt FROM points_log WHERE reason=%s AND DATE(ts)=%s",
        (reason, target),
        fetch="one",
    )
    return int(row["CNT"] or 0)


def time_series_points() -> Iterable[Tuple[str, int]]:
    rows = _execute(
        "SELECT TO_CHAR(DATE(ts), 'YYYY-MM-DD') AS day, SUM(delta) AS points "
        "FROM points_log GROUP BY DATE(ts) ORDER BY DATE(ts)",
        fetch="all",
    )
    return [(row["DAY"], int(row["POINTS"] or 0)) for row in rows]


def mission_tag_counts() -> Dict[str, int]:
    rows = _execute(
        "SELECT category, COUNT(*) AS cnt FROM missions_log GROUP BY category",
        fetch="all",
    )
    totals: Dict[str, int] = defaultdict(int)
    for row in rows:
        category = row["CATEGORY"]
        if not category:
            continue
        tag = MODE_TAG_MAP.get(category, category)
        totals[tag] += int(row["CNT"] or 0)
    return dict(totals)


def recent_missions(limit: int = 5) -> List[str]:
    rows = _execute(
        "SELECT category FROM missions_log ORDER BY ts DESC LIMIT %s",
        (limit,),
        fetch="all",
    )
    return [row["CATEGORY"] for row in rows if row["CATEGORY"]]


def last_mission_date() -> Optional[datetime.date]:
    row = _execute(
        "SELECT date FROM missions_log ORDER BY ts DESC LIMIT 1",
        fetch="one",
    )
    if not row or not row["DATE"]:
        return None
    return row["DATE"]


def add_user_mission(title: str, details: str, tag: str) -> None:
    _execute(
        "INSERT INTO user_missions (created_ts, title, details, tag, status) VALUES (%s, %s, %s, %s, 'todo')",
        (datetime.datetime.utcnow(), title, details, tag),
    )


def list_user_missions(status: str = "todo", limit: int = 100) -> List[Tuple[int, str, str, str, str, str]]:
    rows = _execute(
        "SELECT id, created_ts, title, details, tag, status "
        "FROM user_missions WHERE status=%s ORDER BY id DESC LIMIT %s",
        (status, limit),
        fetch="all",
    )
    return [
        (
            row["ID"],
            row["CREATED_TS"].isoformat() if row["CREATED_TS"] else None,
            row["TITLE"],
            row["DETAILS"],
            row["TAG"],
            row["STATUS"],
        )
        for row in rows
    ]


def complete_user_mission(mid: int) -> None:
    _execute("UPDATE user_missions SET status='done' WHERE id=%s", (mid,))


def recent_diary(limit: int = 14):
    rows = _execute(
        "SELECT day, big_question, found FROM diary ORDER BY day DESC LIMIT %s",
        (limit,),
        fetch="all",
    )
    return [
        (
            row["DAY"].isoformat() if row["DAY"] else None,
            row["BIG_QUESTION"],
            row["FOUND"],
        )
        for row in rows
    ]


def save_content_feed(entry: Dict[str, Any]) -> None:
    _execute(
        "INSERT INTO content_feed (title, summary, body, tags, cta, zoom_link, resource_link, posted_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            entry.get("title"),
            entry.get("summary"),
            entry.get("body"),
            entry.get("tags"),
            entry.get("cta"),
            entry.get("zoom_link"),
            entry.get("resource_link"),
            entry.get("posted_at"),
        ),
    )


def create_child_profile(name: str, age: Optional[int] = None, interests: str = "", dream: str = "") -> int:
    row = _execute(
        "INSERT INTO profiles (name, age, interests, dream) VALUES (%s, %s, %s, %s) RETURNING id",
        (name, age, interests, dream),
        fetch="one",
    )
    return int(row["ID"])


def list_child_profiles() -> List[Dict[str, Any]]:
    rows = _execute(
        "SELECT id, name, age, interests, dream FROM profiles ORDER BY id ASC",
        fetch="all",
    )
    return [
        {
            "id": row["ID"],
            "name": row["NAME"],
            "age": row.get("AGE"),
            "interests": row.get("INTERESTS"),
            "dream": row.get("DREAM"),
        }
        for row in rows
    ]


def get_child_profile(child_id: int) -> Optional[Dict[str, Any]]:
    row = _execute(
        "SELECT id, name, age, interests, dream FROM profiles WHERE id=%s",
        (child_id,),
        fetch="one",
    )
    if not row:
        return None
    return {
        "id": row["ID"],
        "name": row["NAME"],
        "age": row.get("AGE"),
        "interests": row.get("INTERESTS"),
        "dream": row.get("DREAM"),
    }


def create_project(child_id: int, name: str, goal: str = "", tags: str = "", system_prompt: str = "") -> int:
    row = _execute(
        "INSERT INTO projects (child_id, name, goal, tags, system_prompt, created_ts) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (child_id, name, goal, tags, system_prompt, datetime.datetime.utcnow()),
        fetch="one",
    )
    return int(row["ID"])


def list_projects(child_id: int, include_archived: bool = False) -> List[Dict[str, Any]]:
    query = "SELECT id, name, goal, tags, archived, system_prompt FROM projects WHERE child_id=%s"
    params: Tuple[Any, ...] = (child_id,)
    if not include_archived:
        query += " AND archived=FALSE"
    query += " ORDER BY id DESC"
    rows = _execute(query, params, fetch="all")
    return [
        {
            "id": row["ID"],
            "name": row["NAME"],
            "goal": row.get("GOAL"),
            "tags": row.get("TAGS"),
            "archived": bool(row.get("ARCHIVED")),
            "system_prompt": row.get("SYSTEM_PROMPT"),
        }
        for row in rows
    ]


def rename_project(project_id: int, name: str) -> None:
    _execute("UPDATE projects SET name=%s WHERE id=%s", (name, project_id))


def archive_project(project_id: int, archived: int = 1) -> None:
    _execute("UPDATE projects SET archived=%s WHERE id=%s", (bool(archived), project_id))


def get_project(project_id: int) -> Optional[Dict[str, Any]]:
    row = _execute(
        "SELECT id, child_id, name, goal, tags, system_prompt FROM projects WHERE id=%s",
        (project_id,),
        fetch="one",
    )
    if not row:
        return None
    return {
        "id": row["ID"],
        "child_id": row["CHILD_ID"],
        "name": row["NAME"],
        "goal": row.get("GOAL"),
        "tags": row.get("TAGS"),
        "system_prompt": row.get("SYSTEM_PROMPT"),
    }


def create_thread(project_id: int, title: str = "New chat") -> int:
    row = _execute(
        "INSERT INTO threads (project_id, title, created_ts) VALUES (%s, %s, %s) RETURNING id",
        (project_id, title, datetime.datetime.utcnow()),
        fetch="one",
    )
    return int(row["ID"])


def list_threads(project_id: int, include_archived: bool = False) -> List[Dict[str, Any]]:
    query = "SELECT id, title, created_ts, archived FROM threads WHERE project_id=%s"
    params = (project_id,)
    if not include_archived:
        query += " AND archived=FALSE"
    query += " ORDER BY id DESC"
    rows = _execute(query, params, fetch="all")
    return [
        {
            "id": row["ID"],
            "title": row.get("TITLE") or f"Page {row['ID']}",
            "created_ts": row.get("CREATED_TS"),
            "archived": bool(row.get("ARCHIVED")),
        }
        for row in rows
    ]


def rename_thread(thread_id: int, title: str) -> None:
    _execute("UPDATE threads SET title=%s WHERE id=%s", (title, thread_id))


def archive_thread(thread_id: int, archived: int = 1) -> None:
    _execute("UPDATE threads SET archived=%s WHERE id=%s", (bool(archived), thread_id))


def add_message(thread_id: int, role: str, content: str, model: str = "") -> int:
    row = _execute(
        "INSERT INTO messages (thread_id, role, content, created_ts, model) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (thread_id, role, content, datetime.datetime.utcnow(), model),
        fetch="one",
    )
    return int(row["ID"])


def get_thread_messages(thread_id: int) -> List[Dict[str, Any]]:
    rows = _execute(
        "SELECT id, role, content, created_ts FROM messages WHERE thread_id=%s ORDER BY id ASC",
        (thread_id,),
        fetch="all",
    )
    return [
        {
            "id": row["ID"],
            "role": row["ROLE"],
            "content": row["CONTENT"],
            "created_ts": row.get("CREATED_TS"),
        }
        for row in rows
    ]


def search_messages(child_id: int, query: str, limit: int = 50) -> List[Dict[str, Any]]:
    search = f"%{query}%"
    rows = _execute(
        """
        SELECT m.thread_id, m.id AS message_id, SUBSTR(m.content, 1, 160) AS snippet
        FROM messages m
        JOIN threads t ON m.thread_id = t.id
        JOIN projects p ON t.project_id = p.id
        WHERE p.child_id=%s AND m.content ILIKE %s
        ORDER BY m.id DESC
        LIMIT %s
        """,
        (child_id, search, limit),
        fetch="all",
    )
    return [
        {
            "thread_id": row["THREAD_ID"],
            "message_id": row["MESSAGE_ID"],
            "snippet": row["SNIPPET"],
        }
        for row in rows
    ]


def delete_child_profile(child_id: int) -> None:
    _execute(
        "DELETE FROM messages WHERE thread_id IN (SELECT id FROM threads WHERE project_id IN (SELECT id FROM projects WHERE child_id=%s))",
        (child_id,),
    )
    _execute(
        "DELETE FROM threads WHERE project_id IN (SELECT id FROM projects WHERE child_id=%s)",
        (child_id,),
    )
    _execute("DELETE FROM projects WHERE child_id=%s", (child_id,))
    _execute("DELETE FROM profiles WHERE id=%s", (child_id,))


def recent_tag_counts(days: int = 7) -> Dict[str, int]:
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    rows = _execute(
        "SELECT reason, COUNT(*) AS cnt FROM points_log WHERE ts >= %s GROUP BY reason",
        (cutoff,),
        fetch="all",
    )
    totals: Dict[str, int] = defaultdict(int)
    for row in rows:
        reason = row["REASON"]
        tag = POINT_REASON_TAG_MAP.get(reason)
        if tag:
            totals[tag] += int(row["CNT"] or 0)
    mission_rows = _execute(
        "SELECT category, COUNT(*) AS cnt FROM missions_log WHERE ts >= %s GROUP BY category",
        (cutoff,),
        fetch="all",
    )
    for row in mission_rows:
        category = row["CATEGORY"]
        tag = MODE_TAG_MAP.get(category, category)
        totals[tag] += int(row["CNT"] or 0)
    return dict(totals)


def weekly_summary(days: int = 7) -> List[Dict[str, Any]]:
    days = max(1, days)
    today = datetime.date.today()
    start = today - datetime.timedelta(days=days - 1)
    summary = {
        (start + datetime.timedelta(days=i)).isoformat(): {
            "date": start + datetime.timedelta(days=i),
            "missions": 0,
            "kindness": False,
            "planet": False,
            "health": False,
            "points": 0,
        }
        for i in range(days)
    }

    point_rows = _execute(
        "SELECT DATE(ts) AS day, SUM(delta) AS pts FROM points_log WHERE ts >= %s GROUP BY DATE(ts)",
        (start,),
        fetch="all",
    )
    for row in point_rows:
        key = row["DAY"].isoformat()
        if key in summary:
            summary[key]["points"] = int(row["PTS"] or 0)

    mission_rows = _execute(
        "SELECT DATE(date) AS day, COUNT(*) AS cnt FROM missions_log WHERE date \>= %s GROUP BY DATE(date)",
        (start,),
        fetch="all",
    )
    for row in mission_rows:
        key = row["DAY"].isoformat()
        if key in summary:
            summary[key]["missions"] = int(row["CNT"] or 0)

    activity_rows = _execute(
        "SELECT DATE(ts) AS day, reason FROM points_log "
        "WHERE reason IN ('kindness_act','planet_act','water','breaths','moves') AND ts >= %s",
        (start,),
        fetch="all",
    )
    for row in activity_rows:
        key = row["DAY"].isoformat()
        if key not in summary:
            continue
        reason = row["REASON"]
        if reason == "kindness_act":
            summary[key]["kindness"] = True
        elif reason == "planet_act":
            summary[key]["planet"] = True
        else:
            summary[key]["health"] = True

    return [summary[key] for key in sorted(summary.keys())]


POINT_REASON_TAG_MAP = {
    "mission_done": "Build",
    "mission_create": "Build",
    "ritual_chat": "Curiosity",
    "focus_block": "Curiosity",
    "kindness_act": "Kindness",
    "planet_act": "Planet",
    "water": "Health",
    "breaths": "Health",
    "moves": "Health",
    "celebrate": "Curiosity",
}

MODE_TAG_MAP = {
    "Spark": "Curiosity",
    "Build": "Build",
    "Think": "Think",
    "Write": "Write",
    "Share": "Share",
    "Ritual": "Curiosity",
}
