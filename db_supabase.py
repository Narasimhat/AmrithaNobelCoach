"""Supabase persistence helpers for The Silent Room Coach data."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from supabase import Client


# ============================================================================
# Child Profiles (coach_children)
# ============================================================================

def create_child_profile(
    client: Client, name: str, age: Optional[int] = None, interests: str = "", dream: str = ""
) -> int:
    """Create a new child profile and return its ID."""
    user_id = client.auth.get_user().user.id
    result = client.table("coach_children").insert({
        "user_id": user_id,
        "name": name,
        "age": age,
        "interests": interests,
        "dream": dream,
    }).execute()
    return result.data[0]["id"] if result.data else 1


def list_child_profiles(client: Client) -> List[Dict[str, Any]]:
    """List all child profiles for the authenticated user."""
    user_id = client.auth.get_user().user.id
    result = client.table("coach_children").select("id, name, age, interests, dream").eq("user_id", user_id).order("id").execute()
    return result.data


def get_child_profile(client: Client, child_id: int) -> Optional[Dict[str, Any]]:
    """Get a single child profile by ID."""
    user_id = client.auth.get_user().user.id
    result = client.table("coach_children").select("*").eq("id", child_id).eq("user_id", user_id).execute()
    return result.data[0] if result.data else None


def delete_child_profile(client: Client, child_id: int) -> None:
    """Delete a child profile (cascades to adventures, threads, messages)."""
    user_id = client.auth.get_user().user.id
    client.table("coach_children").delete().eq("id", child_id).eq("user_id", user_id).execute()


# ============================================================================
# Projects/Adventures (coach_adventures)
# ============================================================================

def create_project(
    client: Client, child_id: int, name: str, goal: str = "", tags: str = "", system_prompt: str = ""
) -> int:
    """Create a new project/adventure and return its ID."""
    result = client.table("coach_adventures").insert({
        "child_id": child_id,
        "name": name,
        "goal": goal,
        "tags": tags,
        "system_prompt": system_prompt,
    }).execute()
    return result.data[0]["id"] if result.data else 1


def list_projects(client: Client, child_id: int, include_archived: bool = False) -> List[Dict[str, Any]]:
    """List all projects for a child."""
    query = client.table("coach_adventures").select("id, name, goal, tags, archived, system_prompt").eq("child_id", child_id)
    if not include_archived:
        query = query.eq("archived", False)
    result = query.order("id", desc=True).execute()
    return result.data


def get_project(client: Client, project_id: int) -> Optional[Dict[str, Any]]:
    """Get a single project by ID."""
    result = client.table("coach_adventures").select("*").eq("id", project_id).execute()
    return result.data[0] if result.data else None


def rename_project(client: Client, project_id: int, name: str) -> None:
    """Rename a project."""
    client.table("coach_adventures").update({"name": name}).eq("id", project_id).execute()


def update_project_details(client: Client, project_id: int, goal: str, tags: str) -> None:
    """Update project goal and tags."""
    client.table("coach_adventures").update({"goal": goal, "tags": tags}).eq("id", project_id).execute()


def archive_project(client: Client, project_id: int, archived: int = 1) -> None:
    """Archive or unarchive a project."""
    client.table("coach_adventures").update({"archived": bool(archived)}).eq("id", project_id).execute()


# ============================================================================
# Threads/Chat Pages (coach_threads)
# ============================================================================

def create_thread(client: Client, project_id: int, title: str) -> int:
    """Create a new thread/chat page and return its ID."""
    result = client.table("coach_threads").insert({
        "adventure_id": project_id,
        "title": title,
    }).execute()
    return result.data[0]["id"] if result.data else 1


def list_threads(client: Client, project_id: int, include_archived: bool = False) -> List[Dict[str, Any]]:
    """List all threads for a project."""
    query = client.table("coach_threads").select("id, title, created_at, archived").eq("adventure_id", project_id)
    if not include_archived:
        query = query.eq("archived", False)
    result = query.order("id", desc=True).execute()
    return result.data


def rename_thread(client: Client, thread_id: int, title: str) -> None:
    """Rename a thread."""
    client.table("coach_threads").update({"title": title}).eq("id", thread_id).execute()


def archive_thread(client: Client, thread_id: int, archived: int = 1) -> None:
    """Archive or unarchive a thread."""
    client.table("coach_threads").update({"archived": bool(archived)}).eq("id", thread_id).execute()


# ============================================================================
# Messages (coach_messages)
# ============================================================================

def add_message(
    client: Client,
    thread_id: int,
    role: str,
    content: str,
    model: Optional[str] = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> int:
    """Add a message to a thread and return its ID."""
    result = client.table("coach_messages").insert({
        "thread_id": thread_id,
        "role": role,
        "content": content,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }).execute()
    return result.data[0]["id"] if result.data else 1


def get_thread_messages(client: Client, thread_id: int) -> List[Dict[str, Any]]:
    """Get all messages in a thread, ordered by creation time."""
    result = client.table("coach_messages").select("id, role, content, created_at, model, tokens_in, tokens_out").eq("thread_id", thread_id).order("id").execute()
    return result.data


def search_messages(client: Client, child_id: int, query: str) -> List[Dict[str, Any]]:
    """Search messages across all threads for a child."""
    user_id = client.auth.get_user().user.id
    # Note: This is a simplified search - Supabase full-text search would be better
    result = client.table("coach_messages").select(
        "id, thread_id, content"
    ).ilike("content", f"%{query}%").limit(20).execute()
    
    # Filter to only messages from this child's threads
    # TODO: This is inefficient - should use a proper join or view
    filtered = []
    for msg in result.data:
        thread = client.table("coach_threads").select("adventure_id").eq("id", msg["thread_id"]).execute()
        if thread.data:
            adventure = client.table("coach_adventures").select("child_id").eq("id", thread.data[0]["adventure_id"]).execute()
            if adventure.data and adventure.data[0]["child_id"] == child_id:
                filtered.append({
                    "thread_id": msg["thread_id"],
                    "snippet": msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"],
                })
    return filtered


# ============================================================================
# Points & Gamification (coach_points_log)
# ============================================================================

def add_points(client: Client, delta: int, reason: str, child_id: Optional[int] = None) -> None:
    """Add points to the log."""
    user_id = client.auth.get_user().user.id
    client.table("coach_points_log").insert({
        "user_id": user_id,
        "child_id": child_id,
        "delta": delta,
        "reason": reason,
    }).execute()


def total_points(client: Client, child_id: Optional[int] = None) -> int:
    """Get total points for a user or child."""
    user_id = client.auth.get_user().user.id
    query = client.table("coach_points_log").select("delta").eq("user_id", user_id)
    if child_id:
        query = query.eq("child_id", child_id)
    result = query.execute()
    return sum(row["delta"] for row in result.data)


# ============================================================================
# Missions Log (coach_missions_log)
# ============================================================================

def log_mission(client: Client, category: str, mission: str, child_id: Optional[int] = None) -> None:
    """Log a completed mission."""
    user_id = client.auth.get_user().user.id
    today = datetime.date.today()
    client.table("coach_missions_log").insert({
        "user_id": user_id,
        "child_id": child_id,
        "date": today.isoformat(),
        "category": category,
        "mission": mission,
    }).execute()


def recent_tag_counts(client: Client, days: int = 7) -> Dict[str, int]:
    """Get count of missions by tag in the last N days."""
    user_id = client.auth.get_user().user.id
    cutoff = datetime.date.today() - datetime.timedelta(days=days)
    result = client.table("coach_missions_log").select("category").eq("user_id", user_id).gte("date", cutoff.isoformat()).execute()
    
    counts: Dict[str, int] = {}
    for row in result.data:
        category = row.get("category", "")
        counts[category] = counts.get(category, 0) + 1
    return counts


# ============================================================================
# Diary (coach_diary)
# ============================================================================

def mark_open_today(client: Client, child_id: Optional[int] = None) -> None:
    """Mark that the app was opened today."""
    user_id = client.auth.get_user().user.id
    today = datetime.date.today()
    client.table("coach_app_open").upsert({
        "user_id": user_id,
        "child_id": child_id,
        "day": today.isoformat(),
    }).execute()


def streak_days(client: Client, child_id: Optional[int] = None) -> int:
    """Calculate current streak of consecutive days with app opens."""
    user_id = client.auth.get_user().user.id
    query = client.table("coach_app_open").select("day").eq("user_id", user_id)
    if child_id:
        query = query.eq("child_id", child_id)
    result = query.order("day", desc=True).execute()
    
    if not result.data:
        return 0
    
    dates = [datetime.date.fromisoformat(row["day"]) for row in result.data]
    streak = 1
    for i in range(len(dates) - 1):
        if (dates[i] - dates[i + 1]).days == 1:
            streak += 1
        else:
            break
    return streak


# ============================================================================
# Initialization (no-op for Supabase - tables created via migrations)
# ============================================================================

def init_db() -> None:
    """No-op for Supabase - tables are created via SQL migrations."""
    pass
