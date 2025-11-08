"""
Utility helpers for persisting The Silent Room progress in SQLite.

The database lives under data/app.db relative to the project root.
"""

import datetime
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, Tuple, List, Optional, Any

DB_PATH = Path("data/app.db")
DB_PATH.parent.mkdir(exist_ok=True)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Ensure all tables exist."""
    with get_conn() as con:
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app_open (
                day TEXT PRIMARY KEY
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS points_log (
                ts TEXT,
                delta INTEGER,
                reason TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS health_log (
                ts TEXT,
                water INTEGER DEFAULT 0,
                breaths INTEGER DEFAULT 0,
                moves INTEGER DEFAULT 0
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS missions_log (
                ts TEXT,
                date TEXT,
                category TEXT,
                mission TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS diary (
                day TEXT PRIMARY KEY,
                big_question TEXT,
                tried TEXT,
                found TEXT,
                ai_wrong TEXT,
                next_step TEXT,
                gratitude TEXT,
                kindness TEXT,
                planet TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS profile (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_missions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_ts TEXT,
                title TEXT,
                details TEXT,
                tag TEXT,
                status TEXT DEFAULT 'todo'
            )
            """
        )
        # child profiles
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                age INTEGER,
                interests TEXT,
                dream TEXT
            )
            """
        )
        # SilenceGPT projects / threads / messages
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                child_id INTEGER,
                name TEXT NOT NULL,
                goal TEXT,
                tags TEXT,
                system_prompt TEXT,
                created_ts TEXT,
                archived INTEGER DEFAULT 0
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                title TEXT,
                created_ts TEXT,
                archived INTEGER DEFAULT 0
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER,
                role TEXT,
                content TEXT,
                created_ts TEXT,
                model TEXT,
                tokens_in INTEGER,
                tokens_out INTEGER
            )
            """
        )
        cur.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content,
                thread_id UNINDEXED,
                message_id UNINDEXED,
                tokenize='porter'
            )
            """
        )
        cur.execute(
            """
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, content, thread_id, message_id)
                VALUES (new.id, new.content, new.thread_id, new.id);
            END;
            """
        )
        cur.execute(
            """
            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content)
                VALUES('delete', old.id, old.content);
            END;
            """
        )
        cur.execute(
            """
            CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content)
                VALUES('delete', old.id, old.content);
                INSERT INTO messages_fts(rowid, content, thread_id, message_id)
                VALUES (new.id, new.content, new.thread_id, new.id);
            END;
            """
        )
        con.commit()



def mark_open_today() -> None:
    today = datetime.date.today().isoformat()
    with get_conn() as con:
        con.execute("INSERT OR IGNORE INTO app_open(day) VALUES (?)", (today,))
        con.commit()


def add_points(delta: int, reason: str) -> None:
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    with get_conn() as con:
        con.execute(
            "INSERT INTO points_log(ts, delta, reason) VALUES (?, ?, ?)",
            (ts, delta, reason),
        )
        con.commit()


def log_health(*, water: int = 0, breaths: int = 0, moves: int = 0) -> None:
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    with get_conn() as con:
        con.execute(
            "INSERT INTO health_log(ts, water, breaths, moves) VALUES (?, ?, ?, ?)",
            (ts, water, breaths, moves),
        )
        con.commit()


def log_mission(date: str, category: str, mission: str) -> None:
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    with get_conn() as con:
        con.execute(
            "INSERT INTO missions_log(ts, date, category, mission) VALUES (?, ?, ?, ?)",
            (ts, date, category, mission),
        )
        con.commit()


def save_diary(day: str, entry: Dict[str, str]) -> None:
    with get_conn() as con:
        con.execute(
            """
            INSERT INTO diary(
                day, big_question, tried, found, ai_wrong,
                next_step, gratitude, kindness, planet
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(day) DO UPDATE SET
                big_question=excluded.big_question,
                tried=excluded.tried,
                found=excluded.found,
                ai_wrong=excluded.ai_wrong,
                next_step=excluded.next_step,
                gratitude=excluded.gratitude,
                kindness=excluded.kindness,
                planet=excluded.planet
            """,
            (
                day,
                entry.get("big_question", ""),
                entry.get("what_we_tried", ""),
                entry.get("what_we_found", ""),
                entry.get("how_ai_might_be_wrong", ""),
                entry.get("next_step", ""),
                entry.get("gratitude", ""),
                entry.get("kindness_act", ""),
                entry.get("planet_act", ""),
            ),
        )
        con.commit()


def recent_diary(limit: int = 14) -> Iterable[Tuple[str, str, str]]:
    with get_conn() as con:
        return con.execute(
            "SELECT day, big_question, found FROM diary ORDER BY day DESC LIMIT ?",
            (limit,),
        ).fetchall()


def total_points() -> int:
    with get_conn() as con:
        value = con.execute("SELECT COALESCE(SUM(delta), 0) FROM points_log").fetchone()[0]
    return value or 0


def streak_days() -> int:
    with get_conn() as con:
        rows = con.execute("SELECT day FROM app_open ORDER BY day").fetchall()
    if not rows:
        return 0
    recorded_days = [datetime.date.fromisoformat(day) for (day,) in rows]
    today = datetime.date.today()
    streak = 0
    for offset in range(len(recorded_days)):
        target_day = today - datetime.timedelta(days=offset)
        if target_day in recorded_days:
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
    with get_conn() as con:
        result = con.execute(
            "SELECT COUNT(*) FROM points_log WHERE reason=?",
            (reason,),
        ).fetchone()[0]
    return result or 0


def daily_reason_count(reason: str, day: Optional[str] = None) -> int:
    target_day = day or datetime.date.today().isoformat()
    with get_conn() as con:
        result = con.execute(
            "SELECT COUNT(*) FROM points_log WHERE reason=? AND substr(ts, 1, 10)=?",
            (reason, target_day),
        ).fetchone()[0]
    return result or 0


def daily_reason_count(reason: str, day: Optional[str] = None) -> int:
    target_day = day or datetime.date.today().isoformat()
    with get_conn() as con:
        result = con.execute(
            "SELECT COUNT(*) FROM points_log WHERE reason=? AND substr(ts, 1, 10)=?",
            (reason, target_day),
        ).fetchone()[0]
    return result or 0


def time_series_points() -> Iterable[Tuple[str, int]]:
    with get_conn() as con:
        return con.execute(
            """
            SELECT substr(ts, 1, 10) AS day, SUM(delta) AS points
            FROM points_log
            GROUP BY day
            ORDER BY day
            """
        ).fetchall()


def mission_tag_counts() -> Dict[str, int]:
    with get_conn() as con:
        rows = con.execute(
            "SELECT category, COUNT(*) FROM missions_log GROUP BY category"
        ).fetchall()
    totals: Dict[str, int] = defaultdict(int)
    for category, amount in rows:
        if not category:
            continue
        tag = MODE_TAG_MAP.get(category, category)
        totals[tag] += amount
    return dict(totals)


def recent_missions(limit: int = 5) -> List[str]:
    with get_conn() as con:
        rows = con.execute(
            "SELECT category FROM missions_log WHERE category IS NOT NULL ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [row[0] for row in rows]


def last_mission_date() -> Optional[datetime.date]:
    with get_conn() as con:
        row = con.execute("SELECT date FROM missions_log ORDER BY ts DESC LIMIT 1").fetchone()
    if not row or not row[0]:
        return None
    return datetime.date.fromisoformat(row[0])


def add_user_mission(title: str, details: str, tag: str) -> None:
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    with get_conn() as con:
        con.execute(
            """
            INSERT INTO user_missions (created_ts, title, details, tag, status)
            VALUES (?, ?, ?, ?, 'todo')
            """,
            (ts, title, details, tag),
        )
        con.commit()


def list_user_missions(status: str = "todo", limit: int = 100) -> List[Tuple[int, str, str, str, str, str]]:
    with get_conn() as con:
        return con.execute(
            """
            SELECT id, created_ts, title, details, tag, status
            FROM user_missions
            WHERE status = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (status, limit),
        ).fetchall()


def complete_user_mission(mid: int) -> None:
    with get_conn() as con:
        con.execute("UPDATE user_missions SET status='done' WHERE id=?", (mid,))
        con.commit()


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


def recent_tag_counts(days: int = 7) -> Dict[str, int]:
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    cutoff_iso = cutoff.isoformat(timespec="seconds")
    totals: Dict[str, int] = defaultdict(int)

    with get_conn() as con:
        for ts, reason in con.execute(
            "SELECT ts, reason FROM points_log WHERE ts >= ?",
            (cutoff_iso,),
        ):
            tag = POINT_REASON_TAG_MAP.get(reason)
            if tag:
                totals[tag] += 1

        for ts, category in con.execute(
            "SELECT ts, category FROM missions_log WHERE ts >= ?",
            (cutoff_iso,),
        ):
            if not category:
                continue
            tag = MODE_TAG_MAP.get(category, category)
            totals[tag] += 1

        for created_ts, tag, status in con.execute(
            "SELECT created_ts, tag, status FROM user_missions WHERE created_ts >= ?",
            (cutoff_iso,),
        ):
            if tag:
                totals[tag] += 1

    return dict(totals)


def weekly_summary(days: int = 7) -> List[Dict[str, Any]]:
    days = max(1, days)
    today = datetime.date.today()
    start = today - datetime.timedelta(days=days - 1)
    summary_index = {
        (start + datetime.timedelta(days=offset)).isoformat(): {
            'date': start + datetime.timedelta(days=offset),
            'missions': 0,
            'kindness': False,
            'planet': False,
            'health': False,
            'points': 0,
        }
        for offset in range(days)
    }

    start_date_iso = start.isoformat()
    start_ts_iso = f"{start_date_iso}T00:00:00"

    with get_conn() as con:
        for date_value, count_value in con.execute(
            'SELECT date, COUNT(*) FROM missions_log WHERE date >= ? GROUP BY date',
            (start_date_iso,),
        ):
            if date_value in summary_index:
                summary_index[date_value]['missions'] = count_value or 0

        for day_value, total_points in con.execute(
            'SELECT substr(ts, 1, 10) AS day, COALESCE(SUM(delta), 0) FROM points_log WHERE ts >= ? GROUP BY day',
            (start_ts_iso,),
        ):
            if day_value in summary_index:
                summary_index[day_value]['points'] = total_points or 0

        for day_value, reason_value, _ in con.execute(
            'SELECT substr(ts, 1, 10) AS day, reason, COUNT(*) FROM points_log WHERE ts >= ? GROUP BY day, reason',
            (start_ts_iso,),
        ):
            if day_value not in summary_index:
                continue
            if reason_value == 'kindness_act':
                summary_index[day_value]['kindness'] = True
            elif reason_value == 'planet_act':
                summary_index[day_value]['planet'] = True
            elif reason_value in {'water', 'breaths', 'moves'}:
                summary_index[day_value]['health'] = True

    ordered = [summary_index[(start + datetime.timedelta(days=offset)).isoformat()] for offset in range(days)]
    return ordered


# ---------------------------------------------------------------------------
# SilenceGPT helpers (children → projects → threads → messages)
# ---------------------------------------------------------------------------

def create_child_profile(name: str, age: Optional[int] = None, interests: str = "", dream: str = "") -> int:
    with get_conn() as con:
        cur = con.execute(
            """
            INSERT INTO profiles (name, age, interests, dream)
            VALUES (?, ?, ?, ?)
            """,
            (name.strip(), age, interests.strip(), dream.strip()),
        )
        con.commit()
        return cur.lastrowid


def list_child_profiles() -> List[sqlite3.Row]:
    with get_conn() as con:
        return con.execute(
            "SELECT id, name, age, interests, dream FROM profiles ORDER BY id ASC"
        ).fetchall()


def get_child_profile(child_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as con:
        return con.execute(
            "SELECT id, name, age, interests, dream FROM profiles WHERE id=?",
            (child_id,),
        ).fetchone()


def create_project(child_id: int, name: str, goal: str = "", tags: str = "", system_prompt: str = "") -> int:
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    with get_conn() as con:
        cur = con.execute(
            """
            INSERT INTO projects (child_id, name, goal, tags, system_prompt, created_ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (child_id, name.strip(), goal.strip(), tags.strip(), system_prompt.strip(), ts),
        )
        con.commit()
        return cur.lastrowid


def list_projects(child_id: int, include_archived: bool = False) -> List[sqlite3.Row]:
    query = "SELECT id, name, goal, tags, archived, system_prompt FROM projects WHERE child_id=?"
    if not include_archived:
        query += " AND archived=0"
    query += " ORDER BY id DESC"
    with get_conn() as con:
        return con.execute(query, (child_id,)).fetchall()


def rename_project(project_id: int, name: str) -> None:
    with get_conn() as con:
        con.execute("UPDATE projects SET name=? WHERE id=?", (name.strip(), project_id))
        con.commit()


def archive_project(project_id: int, archived: int = 1) -> None:
    with get_conn() as con:
        con.execute("UPDATE projects SET archived=? WHERE id=?", (archived, project_id))
        con.commit()


def get_project(project_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as con:
        return con.execute(
            "SELECT id, child_id, name, goal, tags, system_prompt FROM projects WHERE id=?",
            (project_id,),
        ).fetchone()


def create_thread(project_id: int, title: str = "New chat") -> int:
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    with get_conn() as con:
        cur = con.execute(
            """
            INSERT INTO threads (project_id, title, created_ts)
            VALUES (?, ?, ?)
            """,
            (project_id, title.strip(), ts),
        )
        con.commit()
        return cur.lastrowid


def list_threads(project_id: int, include_archived: bool = False) -> List[sqlite3.Row]:
    query = "SELECT id, title, created_ts, archived FROM threads WHERE project_id=?"
    if not include_archived:
        query += " AND archived=0"
    query += " ORDER BY id DESC"
    with get_conn() as con:
        return con.execute(query, (project_id,)).fetchall()


def rename_thread(thread_id: int, title: str) -> None:
    with get_conn() as con:
        con.execute("UPDATE threads SET title=? WHERE id=?", (title.strip(), thread_id))
        con.commit()


def archive_thread(thread_id: int, archived: int = 1) -> None:
    with get_conn() as con:
        con.execute("UPDATE threads SET archived=? WHERE id=?", (archived, thread_id))
        con.commit()


def add_message(
    thread_id: int,
    role: str,
    content: str,
    *,
    model: str = "gpt-4o-mini",
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
) -> int:
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    with get_conn() as con:
        cur = con.execute(
            """
            INSERT INTO messages (thread_id, role, content, created_ts, model, tokens_in, tokens_out)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (thread_id, role, content, ts, model, tokens_in, tokens_out),
        )
        con.commit()
        return cur.lastrowid


def get_thread_messages(thread_id: int) -> List[sqlite3.Row]:
    with get_conn() as con:
        return con.execute(
            """
            SELECT role, content, created_ts
            FROM messages
            WHERE thread_id=?
            ORDER BY id ASC
            """,
            (thread_id,),
        ).fetchall()


def search_messages(child_id: int, query: str, limit: int = 50) -> List[sqlite3.Row]:
    with get_conn() as con:
        return con.execute(
            """
            SELECT m.thread_id,
                   m.id AS message_id,
                   snippet(messages_fts, 0, '[', ']', '…', 8) AS snippet
            FROM messages_fts
            JOIN messages m ON m.id = messages_fts.rowid
            JOIN threads t ON t.id = m.thread_id
            JOIN projects p ON p.id = t.project_id
            WHERE p.child_id = ?
              AND messages_fts MATCH ?
            ORDER BY m.id DESC
            LIMIT ?
            """,
            (child_id, query, limit),
        ).fetchall()
