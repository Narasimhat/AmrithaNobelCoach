"""Snowflake persistence helpers for The Silent Room."""

from __future__ import annotations

import datetime
import json
import os
import threading
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

import snowflake.connector
from snowflake.connector import DictCursor, errors as sf_errors

# Note: Streamlit secrets are not automatically exported as environment variables on Streamlit Cloud.
# We therefore attempt a lazy import of streamlit inside the parameter resolution function so that
# local scripts (e.g., migration utilities) that don't depend on Streamlit still work without requiring it.

REQUIRED_VARS = (
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_PASSWORD",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_SCHEMA",
)


def _snowflake_params() -> Dict[str, str]:
    """Resolve Snowflake connection parameters.

    Resolution order per key:
    1. Environment variable
    2. st.secrets[var]
    3. st.secrets["snowflake"][lowercase or exact key]

    This allows users to define either flat secrets:
        SNOWFLAKE_ACCOUNT = "..."
    Or grouped secrets:
        [snowflake]
        account = "..."
        user = "..."

    We keep REQUIRED_VARS strict to avoid partial misconfiguration that would cause
    confusing downstream Snowflake connector errors.
    """
    params: Dict[str, str] = {}
    secrets_obj = None
    # Lazy import - avoids hard dependency when running offline scripts.
    try:
        import streamlit as st  # type: ignore
        secrets_obj = st.secrets
    except Exception:
        secrets_obj = None

    group = None
    if secrets_obj and "snowflake" in secrets_obj:
        group = secrets_obj["snowflake"]

    for var in REQUIRED_VARS:
        val = os.getenv(var)
        if not val and secrets_obj:
            # Direct key in secrets
            if var in secrets_obj:
                val = str(secrets_obj[var])
            else:
                # Try group lookup with lowercase variants
                key_lower = var.replace("SNOWFLAKE_", "").lower()
                if group:
                    for candidate in (
                        key_lower,
                        var.lower(),
                        var,  # allow uppercase keys inside [snowflake]
                        key_lower.upper(),
                        key_lower.capitalize(),
                    ):
                        if candidate in group:
                            val = str(group[candidate])
                            break
        params[var] = val or ""

    missing = [k for k, v in params.items() if not v]
    if missing:
        # Helpful guidance: show examples of expected keys.
        raise RuntimeError(
            "Missing Snowflake configuration: "
            + ", ".join(missing)
            + "\nProvide either environment variables or Streamlit secrets (flat or [snowflake] group)."
        )
    return params


_connection: snowflake.connector.SnowflakeConnection | None = None
_connection_lock = threading.Lock()


def reset_connection() -> None:
    global _connection
    with _connection_lock:
        if _connection is not None:
            try:
                _connection.close()
            except Exception:
                pass
            _connection = None


def get_conn() -> snowflake.connector.SnowflakeConnection:
    global _connection
    params = _snowflake_params()
    with _connection_lock:
        needs_new = False
        if _connection is None:
            needs_new = True
        else:
            try:
                # Snowflake connector provides is_closed()
                if _connection.is_closed():
                    needs_new = True
            except Exception:
                needs_new = True
        if needs_new:
            _connection = snowflake.connector.connect(
                account=params["SNOWFLAKE_ACCOUNT"],
                user=params["SNOWFLAKE_USER"],
                password=params["SNOWFLAKE_PASSWORD"],
                warehouse=params["SNOWFLAKE_WAREHOUSE"],
                database=params["SNOWFLAKE_DATABASE"],
                schema=params["SNOWFLAKE_SCHEMA"],
                autocommit=True,
            )
    return _connection


def _execute(query: str, params: Iterable[Any] | None = None, fetch: str = ""):
    params = tuple(params or ())
    attempts = 0
    while True:
        conn = get_conn()
        cursor = conn.cursor(DictCursor)
        try:
            cursor.execute(query, params)
            if fetch == "one":
                return cursor.fetchone()
            if fetch == "all":
                return cursor.fetchall()
            return None
        except sf_errors.Error as exc:
            cursor.close()
            if attempts == 0 and "Connection not open" in str(exc):
                attempts += 1
                reset_connection()
                continue
            raise
        finally:
            try:
                cursor.close()
            except Exception:
                pass


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
                duration_sec INTEGER,
                created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
            )""",
        """CREATE TABLE IF NOT EXISTS badges (
                badge_id STRING PRIMARY KEY,
                name STRING,
                criteria_json VARIANT
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
        """CREATE TABLE IF NOT EXISTS adaptive_learning_state (
                child_id INTEGER PRIMARY KEY,
                state_data VARIANT NOT NULL,
                updated_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
            )""",
        """CREATE TABLE IF NOT EXISTS comprehension_assessments (
                id INTEGER AUTOINCREMENT,
                child_id INTEGER NOT NULL,
                thread_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                topic STRING,
                difficulty INTEGER,
                comprehension_score FLOAT,
                curiosity_score FLOAT,
                confidence_score FLOAT,
                assessed_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
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
    _execute(
        "INSERT INTO profiles (name, age, interests, dream) VALUES (%s, %s, %s, %s)",
        (name, age, interests, dream),
    )
    row = _execute("SELECT MAX(id) AS id FROM profiles", fetch="one")
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
    _execute(
        "INSERT INTO projects (child_id, name, goal, tags, system_prompt, created_ts) VALUES (%s, %s, %s, %s, %s, %s)",
        (child_id, name, goal, tags, system_prompt, datetime.datetime.utcnow()),
    )
    row = _execute("SELECT MAX(id) AS id FROM projects", fetch="one")
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
    _execute("UPDATE projects SET archived=%s WHERE id=%s", (int(bool(archived)), project_id))


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


def update_project_details(project_id: int, goal: str, tags: str) -> None:
    _execute(
        "UPDATE projects SET goal=%s, tags=%s WHERE id=%s",
        (goal, tags, project_id),
    )


def create_thread(project_id: int, title: str = "New chat") -> int:
    _execute(
        "INSERT INTO threads (project_id, title, created_ts) VALUES (%s, %s, %s)",
        (project_id, title, datetime.datetime.utcnow()),
    )
    row = _execute("SELECT MAX(id) AS id FROM threads", fetch="one")
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
    _execute("UPDATE threads SET archived=%s WHERE id=%s", (int(bool(archived)), thread_id))


def add_message(thread_id: int, role: str, content: str, model: str = "") -> int:
    _execute(
        "INSERT INTO messages (thread_id, role, content, created_ts, model) VALUES (%s, %s, %s, %s, %s)",
        (thread_id, role, content, datetime.datetime.utcnow(), model),
    )
    row = _execute("SELECT MAX(id) AS id FROM messages", fetch="one")
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
        "SELECT DATE(date) AS day, COUNT(*) AS cnt FROM missions_log WHERE date >= %s GROUP BY DATE(date)",
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


def get_family_profile(family_id: str) -> Optional[Dict[str, Any]]:
    row = _execute(
        "SELECT family_id, parent_email, kid_name, kid_age, interests "
        "FROM family_profiles WHERE family_id=%s",
        (family_id,),
        fetch="one",
    )
    if not row:
        return None
    interests = row.get("INTERESTS")
    if isinstance(interests, str):
        try:
            import json

            interests = json.loads(interests)
        except Exception:
            interests = []
    return {
        "family_id": row["FAMILY_ID"],
        "parent_email": row.get("PARENT_EMAIL"),
        "kid_name": row.get("KID_NAME"),
        "kid_age": row.get("KID_AGE"),
        "interests": interests or [],
    }


def upsert_family_profile(family_id: str, parent_email: str, kid_name: str, kid_age: int, interests: List[str]) -> None:
    interests_json = json.dumps(interests)
    _execute(
        """
        MERGE INTO family_profiles t USING (SELECT %s AS family_id) s
        ON t.family_id = s.family_id
        WHEN MATCHED THEN UPDATE SET parent_email=%s, kid_name=%s, kid_age=%s, interests=parse_json(%s)
        WHEN NOT MATCHED THEN
            INSERT (family_id, parent_email, kid_name, kid_age, interests)
            VALUES (%s, %s, %s, %s, parse_json(%s))
        """,
        (
            family_id,
            parent_email,
            kid_name,
            kid_age,
            interests_json,
            family_id,
            parent_email,
            kid_name,
            kid_age,
            interests_json,
        ),
    )


def save_learning_session(
    session_id: str,
    family_id: str,
    kid_interest: str,
    session_type: str,
    ai_guidance: Dict[str, Any],
    parent_notes: str = "",
    progress_level: int = 1,
    duration_sec: int = 0,
) -> None:
    _execute(
        """
        INSERT INTO learning_sessions
        (session_id, family_id, kid_interest, session_type, ai_guidance, parent_notes, progress_level, duration_sec)
        SELECT %s, %s, %s, %s, parse_json(%s), %s, %s, %s
        """,
        (
            session_id,
            family_id,
            kid_interest,
            session_type,
            json.dumps(ai_guidance),
            parent_notes,
            progress_level,
            duration_sec,
        ),
    )


def list_interest_progress(family_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    rows = _execute(
        """
        SELECT kid_interest, avg_level, sessions_completed, last_seen
        FROM v_interest_progress
        WHERE family_id=%s
        ORDER BY last_seen DESC
        LIMIT %s
        """,
        (family_id, limit),
        fetch="all",
    )
    return [
        {
            "kid_interest": row["KID_INTEREST"],
            "avg_level": float(row["AVG_LEVEL"]) if row["AVG_LEVEL"] is not None else 0,
            "sessions_completed": int(row["SESSIONS_COMPLETED"]),
            "last_seen": row["LAST_SEEN"],
        }
        for row in rows
    ]


def save_adaptive_learning_state(child_id: int, state_data: str) -> None:
    """Save adaptive learning engine state for a child."""
    _execute(
        """
        MERGE INTO adaptive_learning_state AS target
        USING (SELECT %s AS child_id, parse_json(%s) AS state_data, CURRENT_TIMESTAMP() AS updated_at) AS source
        ON target.child_id = source.child_id
        WHEN MATCHED THEN 
            UPDATE SET state_data = source.state_data, updated_at = source.updated_at
        WHEN NOT MATCHED THEN
            INSERT (child_id, state_data, updated_at) 
            VALUES (source.child_id, source.state_data, source.updated_at)
        """,
        (child_id, state_data),
    )


def get_adaptive_learning_state(child_id: int) -> Optional[str]:
    """Retrieve adaptive learning engine state for a child."""
    row = _execute(
        "SELECT state_data FROM adaptive_learning_state WHERE child_id=%s",
        (child_id,),
        fetch="one",
    )
    return row["STATE_DATA"] if row else None


def save_comprehension_assessment(
    child_id: int,
    thread_id: int,
    message_id: int,
    topic: str,
    difficulty: int,
    comprehension_score: float,
    curiosity_score: float,
    confidence_score: float
) -> None:
    """Save a comprehension assessment for analytics."""
    _execute(
        """
        INSERT INTO comprehension_assessments
        (child_id, thread_id, message_id, topic, difficulty, 
         comprehension_score, curiosity_score, confidence_score, assessed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP())
        """,
        (child_id, thread_id, message_id, topic, difficulty,
         comprehension_score, curiosity_score, confidence_score),
    )


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
