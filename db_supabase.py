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
) -> str:
    """Create a new child profile and return its UUID."""
    user_id = client.auth.get_user().user.id
    # Map old schema (age, interests, dream) to new schema (dob, avatar_url)
    # For now, we'll store age/interests/dream in metadata or skip them
    dob = None
    if age:
        # Approximate DOB from age
        birth_year = datetime.date.today().year - age
        dob = f"{birth_year}-01-01"
    
    result = client.table("coach_children").insert({
        "user_id": user_id,
        "name": name,
        "dob": dob,
        # Store interests/dream in description field if we add it later
    }).execute()
    return result.data[0]["id"] if result.data else ""


def list_child_profiles(client: Client) -> List[Dict[str, Any]]:
    """List all child profiles for the authenticated user."""
    user_id = client.auth.get_user().user.id
    result = client.table("coach_children").select("id, name, dob, avatar_url, created_at").eq("user_id", user_id).order("created_at", desc=True).execute()
    
    # Convert dob to age for backward compatibility
    profiles = []
    for row in result.data:
        profile = dict(row)
        if profile.get("dob"):
            try:
                birth_date = datetime.date.fromisoformat(profile["dob"])
                today = datetime.date.today()
                age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                profile["age"] = age
            except:
                profile["age"] = None
        else:
            profile["age"] = None
        profile["interests"] = ""  # Not in new schema
        profile["dream"] = ""  # Not in new schema
        profiles.append(profile)
    return profiles


def get_child_profile(client: Client, child_id: str) -> Optional[Dict[str, Any]]:
    """Get a single child profile by UUID."""
    user_id = client.auth.get_user().user.id
    result = client.table("coach_children").select("*").eq("id", child_id).eq("user_id", user_id).execute()
    
    if result.data:
        profile = dict(result.data[0])
        # Add backward compatibility fields
        if profile.get("dob"):
            try:
                birth_date = datetime.date.fromisoformat(profile["dob"])
                today = datetime.date.today()
                age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                profile["age"] = age
            except:
                profile["age"] = None
        else:
            profile["age"] = None
        profile["interests"] = ""
        profile["dream"] = ""
        return profile
    return None


def delete_child_profile(client: Client, child_id: str) -> None:
    """Delete a child profile (cascades to adventures, threads, messages)."""
    user_id = client.auth.get_user().user.id
    client.table("coach_children").delete().eq("id", child_id).eq("user_id", user_id).execute()


# ============================================================================
# Projects/Adventures (coach_adventures)
# ============================================================================

def create_project(
    client: Client, child_id: str, name: str, goal: str = "", tags: str = "", system_prompt: str = ""
) -> str:
    """Create a new project/adventure and return its UUID."""
    user_id = client.auth.get_user().user.id
    result = client.table("coach_adventures").insert({
        "user_id": user_id,
        "child_id": child_id if child_id else None,
        "title": name,  # New schema uses 'title', not 'name'
        "description": goal,  # Map 'goal' to 'description'
        "status": "active",
        # Note: 'tags' and 'system_prompt' not in new schema - storing in metadata would require schema update
    }).execute()
    return result.data[0]["id"] if result.data else ""


def list_projects(client: Client, child_id: str, include_archived: bool = False) -> List[Dict[str, Any]]:
    """List all projects for a child."""
    user_id = client.auth.get_user().user.id
    query = client.table("coach_adventures").select("id, title, description, status, created_at").eq("user_id", user_id)
    
    if child_id:
        query = query.eq("child_id", child_id)
    
    if not include_archived:
        query = query.eq("status", "active")
    
    result = query.order("created_at", desc=True).execute()
    
    # Map new schema fields to old field names for compatibility
    projects = []
    for row in result.data:
        project = {
            "id": row["id"],
            "name": row["title"],  # Map 'title' back to 'name'
            "goal": row.get("description", ""),  # Map 'description' to 'goal'
            "tags": "",  # Not in new schema
            "archived": row["status"] != "active",
            "system_prompt": "",  # Not in new schema
        }
        projects.append(project)
    return projects


def get_project(client: Client, project_id: str) -> Optional[Dict[str, Any]]:
    """Get a single project by UUID."""
    result = client.table("coach_adventures").select("*").eq("id", project_id).execute()
    
    if result.data:
        row = result.data[0]
        return {
            "id": row["id"],
            "name": row["title"],
            "goal": row.get("description", ""),
            "tags": "",
            "archived": row["status"] != "active",
            "system_prompt": "",
        }
    return None


def rename_project(client: Client, project_id: str, name: str) -> None:
    """Rename a project."""
    client.table("coach_adventures").update({"title": name}).eq("id", project_id).execute()


def update_project_details(client: Client, project_id: str, goal: str, tags: str) -> None:
    """Update project goal and tags."""
    client.table("coach_adventures").update({"description": goal}).eq("id", project_id).execute()


def archive_project(client: Client, project_id: str, archived: int = 1) -> None:
    """Archive or unarchive a project."""
    status = "archived" if archived else "active"
    client.table("coach_adventures").update({"status": status}).eq("id", project_id).execute()


# ============================================================================
# Threads/Chat Pages (coach_threads)
# ============================================================================

def create_thread(client: Client, project_id: str, title: str) -> str:
    """Create a new thread/chat page and return its UUID."""
    user_id = client.auth.get_user().user.id
    result = client.table("coach_threads").insert({
        "user_id": user_id,
        "adventure_id": project_id,
        "title": title,
    }).execute()
    return result.data[0]["id"] if result.data else ""


def list_threads(client: Client, project_id: str, include_archived: bool = False) -> List[Dict[str, Any]]:
    """List all threads for a project."""
    user_id = client.auth.get_user().user.id
    query = client.table("coach_threads").select("id, title, created_at, metadata").eq("user_id", user_id).eq("adventure_id", project_id)
    
    # Check metadata for archived status
    result = query.order("created_at", desc=True).execute()
    
    threads = []
    for row in result.data:
        metadata = row.get("metadata", {})
        archived = metadata.get("archived", False)
        if include_archived or not archived:
            threads.append({
                "id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "archived": archived,
            })
    return threads


def rename_thread(client: Client, thread_id: str, title: str) -> None:
    """Rename a thread."""
    client.table("coach_threads").update({"title": title}).eq("id", thread_id).execute()


def archive_thread(client: Client, thread_id: str, archived: int = 1) -> None:
    """Archive or unarchive a thread."""
    # Store archived status in metadata
    result = client.table("coach_threads").select("metadata").eq("id", thread_id).execute()
    metadata = result.data[0].get("metadata", {}) if result.data else {}
    metadata["archived"] = bool(archived)
    client.table("coach_threads").update({"metadata": metadata}).eq("id", thread_id).execute()


# ============================================================================
# Messages (coach_messages)
# ============================================================================

def add_message(
    client: Client,
    thread_id: str,
    role: str,
    content: str,
    model: Optional[str] = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> str:
    """Add a message to a thread and return its UUID."""
    user_id = client.auth.get_user().user.id
    # Store model and token counts in metadata
    metadata = {}
    if model:
        metadata["model"] = model
    if tokens_in:
        metadata["tokens_in"] = tokens_in
    if tokens_out:
        metadata["tokens_out"] = tokens_out
    
    result = client.table("coach_messages").insert({
        "user_id": user_id,
        "thread_id": thread_id,
        "role": role,
        "content": content,
        "metadata": metadata,
    }).execute()
    return result.data[0]["id"] if result.data else ""


def get_thread_messages(client: Client, thread_id: str) -> List[Dict[str, Any]]:
    """Get all messages in a thread, ordered by creation time."""
    result = client.table("coach_messages").select("id, role, content, created_at, metadata").eq("thread_id", thread_id).order("created_at").execute()
    
    # Extract model and token info from metadata for backward compatibility
    messages = []
    for row in result.data:
        metadata = row.get("metadata", {})
        messages.append({
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "created_at": row["created_at"],
            "model": metadata.get("model"),
            "tokens_in": metadata.get("tokens_in", 0),
            "tokens_out": metadata.get("tokens_out", 0),
        })
    return messages


def search_messages(client: Client, child_id: str, query: str) -> List[Dict[str, Any]]:
    """Search messages across all threads for a child."""
    user_id = client.auth.get_user().user.id
    # Simplified search - filter by user and search content
    result = client.table("coach_messages").select(
        "id, thread_id, content"
    ).eq("user_id", user_id).ilike("content", f"%{query}%").limit(20).execute()
    
    # Filter to only messages from this child's threads
    filtered = []
    for msg in result.data:
        thread = client.table("coach_threads").select("adventure_id").eq("id", msg["thread_id"]).execute()
        if thread.data:
            adventure = client.table("coach_adventures").select("child_id").eq("id", thread.data[0]["adventure_id"]).execute()
            if adventure.data and adventure.data[0].get("child_id") == child_id:
                filtered.append({
                    "thread_id": msg["thread_id"],
                    "snippet": msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"],
                })
    return filtered


# ============================================================================
# Points & Gamification (coach_points_log)
# ============================================================================

def add_points(client: Client, delta: int, reason: str, child_id: Optional[str] = None) -> None:
    """Add points to the log."""
    user_id = client.auth.get_user().user.id
    client.table("coach_points_log").insert({
        "user_id": user_id,
        "child_id": child_id if child_id else None,
        "points": delta,  # New schema uses 'points', not 'delta'
        "reason": reason,
    }).execute()


def total_points(client: Client, child_id: Optional[str] = None) -> int:
    """Get total points for a user or child."""
    user_id = client.auth.get_user().user.id
    query = client.table("coach_points_log").select("points").eq("user_id", user_id)
    if child_id:
        query = query.eq("child_id", child_id)
    result = query.execute()
    return sum(row["points"] for row in result.data)


# ============================================================================
# Missions Log (coach_missions_log)
# ============================================================================

def log_mission(client: Client, category: str, mission: str, child_id: Optional[str] = None) -> None:
    """Log a completed mission."""
    user_id = client.auth.get_user().user.id
    # Store category in details jsonb
    details = {"category": category}
    client.table("coach_missions_log").insert({
        "user_id": user_id,
        "child_id": child_id if child_id else None,
        "mission": mission,
        "status": "completed",
        "details": details,
    }).execute()


def recent_tag_counts(client: Client, days: int = 7) -> Dict[str, int]:
    """Get count of missions by tag in the last N days."""
    user_id = client.auth.get_user().user.id
    cutoff = datetime.date.today() - datetime.timedelta(days=days)
    result = client.table("coach_missions_log").select("details, created_at").eq("user_id", user_id).gte("created_at", cutoff.isoformat()).execute()
    
    counts: Dict[str, int] = {}
    for row in result.data:
        details = row.get("details", {})
        category = details.get("category", "")
        if category:
            counts[category] = counts.get(category, 0) + 1
    return counts


# ============================================================================
# Diary (coach_diary)
# ============================================================================

def mark_open_today(client: Client, child_id: Optional[str] = None) -> None:
    """Mark that the app was opened today. (Table not in new schema - no-op for now)"""
    # TODO: Add coach_app_open table to schema if streak tracking is needed
    pass


def streak_days(client: Client, child_id: Optional[str] = None) -> int:
    """Calculate current streak of consecutive days with app opens. (Table not in new schema - returns 0)"""
    # TODO: Add coach_app_open table to schema if streak tracking is needed
    return 0


# ============================================================================
# Initialization (no-op for Supabase - tables created via migrations)
# ============================================================================

def init_db() -> None:
    """No-op for Supabase - tables are created via SQL migrations."""
    pass
