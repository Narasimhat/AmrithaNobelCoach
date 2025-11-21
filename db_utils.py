"""Compatibility wrapper for db_supabase that matches old Snowflake API.

This module wraps db_supabase functions to automatically inject the Supabase client,
allowing app.py to call database functions without passing the client explicitly.
"""

import streamlit as st
from typing import Any, Dict, List, Optional
import db_supabase


def _get_client():
    """Get Supabase client from session state."""
    client = st.session_state.get("supabase_client")
    if not client:
        raise RuntimeError("Supabase client not initialized. Please authenticate first.")
    return client


# Child Profiles
def create_child_profile(name: str, age: Optional[int] = None, interests: str = "", dream: str = "") -> int:
    return db_supabase.create_child_profile(_get_client(), name, age, interests, dream)

def list_child_profiles() -> List[Dict[str, Any]]:
    return db_supabase.list_child_profiles(_get_client())

def get_child_profile(child_id: int) -> Optional[Dict[str, Any]]:
    return db_supabase.get_child_profile(_get_client(), child_id)

def delete_child_profile(child_id: int) -> None:
    db_supabase.delete_child_profile(_get_client(), child_id)


# Projects/Adventures
def create_project(child_id: int, name: str, goal: str = "", tags: str = "", system_prompt: str = "") -> int:
    return db_supabase.create_project(_get_client(), child_id, name, goal, tags, system_prompt)

def list_projects(child_id: int, include_archived: bool = False) -> List[Dict[str, Any]]:
    return db_supabase.list_projects(_get_client(), child_id, include_archived)

def get_project(project_id: int) -> Optional[Dict[str, Any]]:
    return db_supabase.get_project(_get_client(), project_id)

def rename_project(project_id: int, name: str) -> None:
    db_supabase.rename_project(_get_client(), project_id, name)

def update_project_details(project_id: int, goal: str, tags: str) -> None:
    db_supabase.update_project_details(_get_client(), project_id, goal, tags)

def archive_project(project_id: int, archived: int = 1) -> None:
    db_supabase.archive_project(_get_client(), project_id, archived)


# Threads
def create_thread(project_id: int, title: str) -> int:
    return db_supabase.create_thread(_get_client(), project_id, title)

def list_threads(project_id: int, include_archived: bool = False) -> List[Dict[str, Any]]:
    return db_supabase.list_threads(_get_client(), project_id, include_archived)

def rename_thread(thread_id: int, title: str) -> None:
    db_supabase.rename_thread(_get_client(), thread_id, title)

def archive_thread(thread_id: int, archived: int = 1) -> None:
    db_supabase.archive_thread(_get_client(), thread_id, archived)


# Messages
def add_message(thread_id: int, role: str, content: str, model: Optional[str] = None, tokens_in: int = 0, tokens_out: int = 0) -> int:
    return db_supabase.add_message(_get_client(), thread_id, role, content, model, tokens_in, tokens_out)

def get_thread_messages(thread_id: int) -> List[Dict[str, Any]]:
    return db_supabase.get_thread_messages(_get_client(), thread_id)

def search_messages(child_id: int, query: str) -> List[Dict[str, Any]]:
    return db_supabase.search_messages(_get_client(), child_id, query)


# Points & Gamification
def add_points(delta: int, reason: str, child_id: Optional[int] = None) -> None:
    db_supabase.add_points(_get_client(), delta, reason, child_id)

def total_points(child_id: Optional[int] = None) -> int:
    return db_supabase.total_points(_get_client(), child_id)


# Missions
def log_mission(category: str, mission: str, child_id: Optional[int] = None) -> None:
    db_supabase.log_mission(_get_client(), category, mission, child_id)

def recent_tag_counts(days: int = 7) -> Dict[str, int]:
    return db_supabase.recent_tag_counts(_get_client(), days)


# Diary & Streak
def mark_open_today(child_id: Optional[int] = None) -> None:
    db_supabase.mark_open_today(_get_client(), child_id)

def streak_days(child_id: Optional[int] = None) -> int:
    return db_supabase.streak_days(_get_client(), child_id)


# Stubs for functions not yet implemented
def save_diary(day: str, data: dict) -> None:
    pass

def weekly_summary(days: int = 7) -> Dict[str, Any]:
    return {}

def get_family_profile(family_id: str) -> Optional[Dict[str, Any]]:
    return None

def list_interest_progress(family_id: str) -> List[Dict[str, Any]]:
    return []

def add_user_mission(title: str, details: str, tag: str) -> None:
    pass

def daily_reason_count(reason: str) -> int:
    return 0

def last_mission_date(category: str) -> Optional[str]:
    return None

def save_learning_session(family_id: str, session_data: dict) -> None:
    pass

def upsert_family_profile(family_id: str, data: dict) -> None:
    pass

def init_db() -> None:
    pass
