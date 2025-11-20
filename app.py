import base64
import datetime
import hashlib
import io
import json
import math
import os
import random
import re
import tempfile
import time
import uuid

import requests
from html import escape
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus
from typing import Dict, List, Optional, Tuple

import streamlit as st
from supabase import Client, create_client
from openai import OpenAI

from content_feed import load_feed, add_feed_entry, delete_feed_entry
from adaptive_learning import AdaptiveLearningEngine
from db_utils import (
    add_points,
    add_user_mission,
    daily_reason_count,
    delete_child_profile,
    get_family_profile,
    init_db,
    list_interest_progress,
    log_mission,
    mark_open_today,
    save_learning_session,
    save_diary,
    upsert_family_profile,
    streak_days,
    total_points,
    last_mission_date,
    recent_tag_counts,
    weekly_summary,
    update_project_details,
    save_adaptive_learning_state,
    get_adaptive_learning_state,
    save_comprehension_assessment,
    upsert_child_mastery,
    get_child_mastery_record,
    list_child_mastery_records,
    log_interaction,
    snowflake_config_status,
)

def _noop_seed() -> None:
    pass

ensure_default_silentgpt_data = _noop_seed

try:
    from db_utils import (
        add_message,
        archive_project,
        archive_thread,
        create_child_profile,
        create_project,
        create_thread,
        get_child_profile,
        get_project,
        get_thread_messages,
        list_child_profiles,
        list_projects,
        list_threads,
        rename_project,
        rename_thread,
        search_messages,
    )
except ImportError as import_exc:
    def _silentgpt_missing(*_, **__):
        raise ImportError(
            "SilentGPT features need the latest db_utils helpers. "
            "Redeploy after pulling the newest code (missing: add_message/archive_project/etc)."
        ) from import_exc

    add_message = archive_project = archive_thread = create_child_profile = create_project = create_thread = (
        get_child_profile
    ) = get_project = get_thread_messages = list_child_profiles = list_projects = list_threads = rename_project = (
        rename_thread
    ) = search_messages = _silentgpt_missing
else:
    def ensure_default_silentgpt_data() -> None:
        """Populate a starter explorer/adventure if deploys start empty."""
        try:
            children = list_child_profiles()
        except Exception:
            return
        if not children:
            child_id = create_child_profile(
                name="Amritha",
                age=9,
                interests="Space, Oceans, Kindness",
                dream="Heal Earth with science",
            )
        else:
            child_id = children[0]["id"]
        try:
            adventures = list_projects(child_id)
        except Exception:
            return
        if not adventures:
            create_project(
                child_id,
                name="Climate Garden",
                goal="Design a mini garden that keeps water clean.",
                tags="Planet, Build, Story",
            )


@st.cache_data(ttl=120, show_spinner=False)  # Increased from 30s to 2min
def cached_child_profiles():
    return list_child_profiles()


@st.cache_data(ttl=120, show_spinner=False)  # Increased from 30s to 2min
def cached_projects(child_id: int, include_archived: bool = False):
    return list_projects(child_id, include_archived)


@st.cache_data(ttl=120, show_spinner=False)  # Increased from 30s to 2min
def cached_threads(project_id: int, include_archived: bool = False):
    return list_threads(project_id, include_archived)


@st.cache_data(ttl=60, show_spinner=False)  # Increased from 30s to 1min
def cached_thread_messages(thread_id: int):
    return get_thread_messages(thread_id)


@st.cache_data(ttl=180, show_spinner=False)  # Increased from 60s to 3min
def cached_recent_tags(days: int = 7):
    return recent_tag_counts(days)


@st.cache_data(ttl=180, show_spinner=False)  # Increased from 60s to 3min
def cached_week_summary(days: int = 7):
    return weekly_summary(days)


@st.cache_data(ttl=300, show_spinner=False)  # Increased from 60s to 5min
def cached_points_total() -> int:
    return total_points()


@st.cache_data(ttl=300, show_spinner=False)  # Increased from 60s to 5min
def cached_streak_length() -> int:
    return streak_days()


def invalidate_progress_caches() -> None:
    """Clear all progress-related caches in one call."""
    cached_recent_tags.clear()
    cached_week_summary.clear()
    cached_points_total.clear()
    cached_streak_length.clear()


def invalidate_coach_caches() -> None:
    """Clear all coach-related caches (profiles, projects, threads, messages)."""
    cached_child_profiles.clear()
    cached_projects.clear()
    cached_threads.clear()
    cached_thread_messages.clear()


@st.cache_data(ttl=300)
def cached_family_profile(family_id: str):
    return get_family_profile(family_id)


@st.cache_data(ttl=120)
def cached_interest_progress(family_id: str):
    return list_interest_progress(family_id)


def invalidate_family_caches() -> None:
    cached_family_profile.clear()
    cached_interest_progress.clear()


@st.cache_data(ttl=180, show_spinner=False)
def cached_child_mastery(child_id: int):
    try:
        return list_child_mastery_records(child_id)
    except Exception:
        return []


@st.cache_resource(show_spinner=False)
def get_openai_client_cached(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)
from silencegpt_prompt import build_system_prompt
from silencegpt_api import chat_completion

APP_NAME = "The Silent Room"
COACH_TITLE = "Inner Mentor"
NAV_TABS = ("Coach", "Knowledge Hub", "Learning Sessions")
APP_ROOT = Path(__file__).resolve().parent
DATA_DIR = APP_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DIARY_DIR = APP_ROOT / "diaries"
DIARY_DIR.mkdir(exist_ok=True)
ASSET_DIR = APP_ROOT / "assets" / "backgrounds"
BACKGROUND_IMAGES = {
    "coach": ASSET_DIR / "lab.jpg",
    "gallery": ASSET_DIR / "space.jpg",
    "mission_cards": ASSET_DIR / "missions.jpg",
    "parents": ASSET_DIR / "warm.jpg",
}

def get_config(name: str, default: Optional[str] = None) -> Optional[str]:
    env_value = os.getenv(name)
    if env_value:
        return env_value
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


SUPABASE_URL = get_config("SUPABASE_URL")
SUPABASE_ANON_KEY = get_config("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = get_config("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_HUB_BUCKET = get_config("SUPABASE_HUB_BUCKET", "knowledge-hub")
SUPABASE_BYPASS = (get_config("SUPABASE_BYPASS", "") or "").lower() in {"1", "true", "yes"}
STRIPE_PRICE_ID_NO_TRIAL = get_config("STRIPE_PRICE_ID_NO_TRIAL")
FREE_TIER_DAILY_MESSAGES = int(get_config("FREE_TIER_DAILY_MESSAGES", "3") or "0")
FREE_TIER_ENABLED = FREE_TIER_DAILY_MESSAGES > 0
ENABLE_BACKGROUNDS = (get_config("ENABLE_BACKGROUNDS", "1") or "1").strip().lower() not in {"0", "false", "no"}


@st.cache_resource(show_spinner=False)
def get_supabase_client() -> Optional[Client]:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def get_supabase_admin_client() -> Optional[Client]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def fetch_total_profiles() -> Optional[int]:
    admin_client = get_supabase_admin_client()
    if admin_client is None:
        return None
    try:
        response = admin_client.table("profiles").select("id", count="exact").limit(1).execute()
        return getattr(response, "count", None)
    except Exception:
        return None


def supabase_logout() -> None:
    st.session_state.pop("supabase_session", None)
    st.session_state.pop("supabase_profile", None)
    st.rerun()


def parse_timestamp(timestamp: Optional[str]) -> Optional[datetime.datetime]:
    if not timestamp:
        return None
    try:
        return datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_supabase_profile(client: Client, user_id: str) -> Optional[dict]:
    try:
        response = client.table("profiles").select(
            "subscription_status, trial_ends_at, stripe_customer_id, email, display_name, hero_dream, avatar_theme"
        ).eq("id", user_id).execute()
    except Exception:
        return None
    data = getattr(response, "data", None)
    if not data:
        return None
    return data[0]


PROFILE_THEMES = {
    "lab": "Lab Explorer",
    "space": "Space Voyager",
    "forest": "Forest Guardian",
    "ocean": "Ocean Protector",
}


def update_supabase_profile(updates: dict) -> Optional[dict]:
    admin_client = get_supabase_admin_client()
    session = st.session_state.get("supabase_session")
    if admin_client is None or not session:
        return None
    user_id = session.get("user_id")
    if not user_id:
        return None
    try:
        response = (
            admin_client.table("profiles")
            .update({**updates, "updated_at": datetime.datetime.utcnow().isoformat() + "Z"})
            .eq("id", user_id)
            .execute()
        )
    except Exception as exc:
        st.error(f"Could not update hero profile: {exc}")
        return None
    data = getattr(response, "data", None)
    if data:
        st.session_state["supabase_profile"] = data[0]
        return data[0]
    # Fallback to merge manually if Supabase returns no row
    profile = st.session_state.get("supabase_profile", {}).copy()
    profile.update(updates)
    st.session_state["supabase_profile"] = profile
    return profile


def upload_hub_media(file) -> Optional[str]:
    """Upload to knowledge-hub and return permanent public URL."""
    if not file:
        return None
    bytes_data = file.getvalue()
    if not bytes_data:
        return None
    admin_client = get_supabase_admin_client()
    if admin_client is None or not SUPABASE_HUB_BUCKET:
        return None
    safe_name = re.sub(r"[^0-9A-Za-z._-]", "_", file.name or "hub_asset")
    file_name = f"{uuid.uuid4()}_{safe_name}"
    try:
        admin_client.storage.from_(SUPABASE_HUB_BUCKET).upload(
            path=file_name,
            file=bytes_data,
            file_options={"content-type": file.type or "application/octet-stream", "upsert": False},
        )
        return admin_client.storage.from_(SUPABASE_HUB_BUCKET).get_public_url(file_name)
    except Exception:
        return None


def render_hero_profile(profile: Optional[dict]) -> None:
    if profile is None:
        return
    st.markdown("### 🌟 Your Hero Profile")
    display_name = profile.get("display_name") or ""
    hero_dream = profile.get("hero_dream") or ""
    avatar_theme = profile.get("avatar_theme") or "space"

    needs_setup = not display_name or not hero_dream
    if needs_setup:
        st.info("Let’s personalize your coach! Tell us how to call you and your big dream.")

    with st.form("hero-profile-form", clear_on_submit=False):
        name_input = st.text_input("What should the coach call you?", value=display_name, placeholder="e.g. Star Captain Amritha")
        dream_input = st.text_area(
            "Your dream as a hero",
            value=hero_dream,
            placeholder="I want to build robots that make the oceans clean again!",
            height=80,
        )
        theme_options = list(PROFILE_THEMES.items())
        theme_keys = [key for key, _ in theme_options]
        theme_labels = [label for _, label in theme_options]
        current_index = theme_keys.index(avatar_theme) if avatar_theme in theme_keys else 0
        theme_choice = st.selectbox("Choose your hero vibe", theme_labels, index=current_index)
        submitted = st.form_submit_button("Save hero profile", use_container_width=True, type="primary")

    if submitted:
        selected_theme = theme_keys[theme_labels.index(theme_choice)]
        updates = {
            "display_name": name_input.strip() or None,
            "hero_dream": dream_input.strip() or None,
            "avatar_theme": selected_theme,
        }
        saved = update_supabase_profile(updates)
        if saved:
            st.success("Hero profile updated! 🚀")
        else:
            st.error("We could not save the hero profile right now. Please try again.")
        st.rerun()


def invoke_supabase_function(name: str, payload: dict) -> Optional[dict]:
    if not SUPABASE_URL:
        return None
    headers = {"Content-Type": "application/json"}
    token = SUPABASE_ANON_KEY or ""
    session = st.session_state.get("supabase_session")
    if session and session.get("access_token"):
        token = session["access_token"]
    if token:
        headers["Authorization"] = f"Bearer {token}"
    endpoint = f"{SUPABASE_URL}/functions/v1/{name}"
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=20)
        if response.status_code >= 400:
            return None
        if response.headers.get("Content-Type", "").startswith("application/json"):
            return response.json()
        return None
    except Exception:
        return None


def handle_checkout_redirect() -> Optional[str]:
    params = st.query_params
    status_list = params.get("status")
    if status_list:
        status = status_list[0]
        st.session_state["checkout_status"] = status
        remaining = {k: v for k, v in params.items() if k != "status"}
        st.experimental_set_query_params(**remaining)
        return status
    return st.session_state.get("checkout_status")


def render_checkout_notice(status: Optional[str], profile: Optional[dict]) -> None:
    if not status:
        return
    status_lower = status.lower()
    if status_lower == "success":
        if profile and (profile.get("subscription_status") or "").lower() in {"active", "trialing"}:
            st.success("Your subscription is confirmed! Welcome aboard.")
            st.balloons()
        else:
            st.info("Thanks! We're finalizing your subscription. Refresh in a few seconds or sign in again.")
    elif status_lower == "cancel":
        st.warning("Checkout was canceled. You can try again whenever you're ready.")
    st.session_state.pop("checkout_status", None)


def supabase_login_ui(client: Client) -> None:
    with st.sidebar:
        st.markdown("### Parent Access")
        auth_mode = st.radio(
            "Choose an option:",
            options=("Sign in", "Create account"),
            horizontal=True,
            key="supabase_auth_mode",
        )
        feedback = st.empty()
        with st.form("supabase-auth-form", clear_on_submit=False):
            email = st.text_input("Email", placeholder="parent@example.com")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Continue")
        if submitted:
            if not email or not password:
                feedback.error("Enter both email and password.")
            else:
                try:
                    if auth_mode == "Create account":
                        result = client.auth.sign_up({"email": email, "password": password})
                        feedback.success("Account created! Check your inbox for a confirmation email, then sign in.")
                        st.stop()
                    else:
                        result = client.auth.sign_in_with_password(
                            {"email": email, "password": password}
                        )
                except Exception as exc:
                    feedback.error(f"{auth_mode} failed: {exc}")
                else:
                    if not getattr(result, "user", None):
                        feedback.error("No user returned. Check credentials or confirm your email.")
                    else:
                        profile = fetch_supabase_profile(client, result.user.id)
                        st.session_state["supabase_session"] = {
                            "access_token": result.session.access_token if result.session else "",
                            "refresh_token": result.session.refresh_token if result.session else "",
                            "user_id": result.user.id,
                            "email": getattr(result.user, "email", email),
                        }
                        st.session_state["supabase_profile"] = profile
                        st.success("Signed in! Loading your coach…")
                        st.rerun()
        st.stop()


def render_subscription_cta(profile: Optional[dict], status: Optional[str]) -> None:
    st.warning(
        "Your Silent Room membership needs an active subscription. Start the free month or manage billing below."
    )
    if status == "success":
        st.info("Thanks! We're confirming your payment. If this page doesn't unlock shortly, please sign in again.")
    elif status == "cancel":
        st.warning("Checkout was cancelled. You can restart it whenever you're ready.")
    user_id = st.session_state.get("supabase_session", {}).get("user_id")
    col_trial, col_paid = st.columns(2)
    if user_id and col_trial.button("Start free month", type="primary", key="start-trial"):
        with st.spinner("Preparing secure checkout…"):
            result = invoke_supabase_function(
                "create-checkout-session",
                {"supabase_user_id": user_id, "plan_type": "trial"},
            )
        if result and result.get("url"):
            st.session_state["pending_checkout_url"] = result["url"]
            st.rerun()
        else:
            st.error("Could not start checkout. Please try again in a moment.")
    if user_id and STRIPE_PRICE_ID_NO_TRIAL and col_paid.button("Pay now", key="pay-now"):
        with st.spinner("Preparing secure checkout…"):
            result = invoke_supabase_function(
                "create-checkout-session",
                {"supabase_user_id": user_id, "plan_type": "paid"},
            )
        if result and result.get("url"):
            st.session_state["pending_checkout_url"] = result["url"]
            st.rerun()
        else:
            st.error("Unable to open checkout currently. Please try again.")
    elif not STRIPE_PRICE_ID_NO_TRIAL:
        col_paid.caption("Direct purchase option coming soon.")
    checkout_url = st.session_state.pop("pending_checkout_url", None)
    if checkout_url:
        st.success("Secure checkout is ready.")
        st.markdown(
            f'<a href="{checkout_url}" target="_blank" rel="noopener noreferrer" '
            'class="stButton" style="display:inline-flex;align-items:center;'
            'justify-content:center;padding:0.6rem 1.2rem;border-radius:6px;'
            'background-color:#FF6F61;color:white;text-decoration:none;font-weight:600;">'
            'Open payment page ↗</a>',
            unsafe_allow_html=True,
        )
        st.caption(
            f"If the tab didn’t open automatically, copy and paste this link into a browser: {checkout_url}"
        )
    if profile and profile.get("stripe_customer_id"):
        if st.button("Manage subscription", key="manage-subscription"):
            with st.spinner("Opening customer portal…"):
                result = invoke_supabase_function(
                    "create-portal-session",
                    {"supabase_user_id": user_id},
                )
            if result and result.get("url"):
                st.session_state["portal_url"] = result["url"]
                st.rerun()
            else:
                st.error("Unable to open customer portal right now.")
    portal_url = st.session_state.pop("portal_url", None)
    if portal_url:
        st.success("Opening customer portal…")
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url={portal_url}" />',
            unsafe_allow_html=True,
        )
    st.session_state.pop("checkout_status", None)


def has_paid_access(profile: Optional[dict]) -> bool:
    if not profile:
        return False
    status = (profile.get("subscription_status") or "").lower()
    if status in {"active", "trialing"}:
        return True
    trial_ends_at = parse_timestamp(profile.get("trial_ends_at"))
    if trial_ends_at and trial_ends_at > datetime.datetime.now(datetime.timezone.utc):
        return True
    return False


def get_free_tier_usage() -> dict:
    today = datetime.date.today().isoformat()
    usage = st.session_state.setdefault("free_tier_usage", {"day": today, "count": 0})
    if usage["day"] != today:
        usage["day"] = today
        usage["count"] = 0
    return usage


def ensure_supabase_access() -> Optional[Client]:
    if SUPABASE_BYPASS:
        return None
    client = get_supabase_client()
    if client is None:
        return None
    session = st.session_state.get("supabase_session")
    if not session:
        supabase_login_ui(client)
    user_id = session.get("user_id")
    profile = st.session_state.get("supabase_profile")
    refresh_needed = bool(st.session_state.get("checkout_status")) and user_id
    if (profile is None or refresh_needed) and user_id:
        profile = fetch_supabase_profile(client, user_id)
        st.session_state["supabase_profile"] = profile
    if not profile:
        st.error(
            "Account setup incomplete. Please finish subscription onboarding or contact support."
        )
        st.stop()
    paid = has_paid_access(profile)
    st.session_state["has_paid_access"] = paid
    st.session_state["free_tier_active"] = False
    st.session_state["free_tier_limit"] = FREE_TIER_DAILY_MESSAGES
    if paid:
        return client
    if FREE_TIER_ENABLED:
        st.session_state["free_tier_active"] = True
        usage = get_free_tier_usage()
        remaining = max(FREE_TIER_DAILY_MESSAGES - usage["count"], 0)
        st.info(
            f"Free Explorer mode: {remaining} of "
            f"{FREE_TIER_DAILY_MESSAGES} daily mentor chats remain. Upgrade anytime for unlimited access."
        )
        return client
    render_subscription_cta(profile, st.session_state.get("checkout_status"))
    st.stop()
    return client

SYSTEM_PROMPT = f"""
You are "{COACH_TITLE}," the gentle guide inside The Silent Room for a 9-year-old scientist (Amritha).
Goals: grow curiosity, careful thinking, relentless kindness, and the habit of checking AI.
Workflow: 1) Clarify the question. 2) Offer 2–3 paths (read/experiment/build/explain/share).
3) After any answer, ask: "How could I be wrong?" and help her check.
4) End with a mini teach-back prompt.
Guardrails: safety first; no dangerous experiments; credit sources; be kind to people and planet.
Modes: Spark / Build / Think / Write / Share. If unclear, pick one.
Output: shining bullets, one action now, one reflective question, one fun stretch goal.
"""

MODE_OPTIONS: List[Tuple[str, str, str]] = [
    ("Spark", "💡", "Ignite a fresh question or big idea."),
    ("Build", "🔧", "Plan an experiment or hands-on project."),
    ("Think", "🧠", "Slow down, analyze, and reason carefully."),
    ("Write", "✍️", "Turn discoveries into stories, notes, or diagrams."),
    ("Share", "🎤", "Teach someone else and celebrate progress."),
]

MODE_TO_TAG = {
    "Spark": "Curiosity",
    "Build": "Build",
    "Think": "Think",
    "Write": "Write",
    "Share": "Share",
}

GREETINGS = [
    "🌈 Let us chase a new idea today, Amritha!",
    "🧪 Ready to question the universe and test something bold?",
    "✨ Every scientist starts with curiosity—let's light yours!",
    "🚪 Step into The Silent Room—your calm lab awaits!",
    "🌟 Your ideas can heal the world—shall we begin?",
]


MISSIONS = [
    "Find one weird thing about plants and explain it in your own words.",
    "Ask how clouds float and draw a sky story about it.",
    "Design a superhero scientist who protects the oceans.",
    "Spot an AI mistake today and teach the correct answer.",
    "Invent a kindness experiment that makes three friends smile.",
    "Explore how to save energy at home and write a mini-plan.",
    "Create a question about space that no one has answered yet.",
]

HEALTH_TIPS = [
    "Take a pencil break: stretch your hands, roll your shoulders, breathe deeply.",
    "Fuel your brain with water and a rainbow snack—colorful fruits power focus.",
    "Five-jump challenge: leap, laugh, repeat. Movement wakes up ideas!",
    "Sit like a scientist: straight back, relaxed shoulders, gentle breath.",
    "Sunshine check: peek outside for a minute and describe one happy detail.",
]

KINDNESS_CHALLENGES = [
    "Share a thankful note with someone who helped you learn today.",
    "Pick up three tiny pieces of litter and recycle or trash them.",
    "Teach a younger friend the coolest fact you discovered this week.",
    "Listen to a family story and write down what wisdom it carries.",
    "Plant a kindness compliment in someone’s lunchbox or notebook.",
]

EARTH_PROMISES = [
    "Use a reusable bottle all day and note how much water you drink.",
    "Switch off lights when sunshine is enough—be Earth’s energy hero.",
    "Sort today’s recycling and explain why each item fits its bin.",
    "Sketch a tiny poster about protecting trees and hang it proudly.",
    "Save water during tooth brushing and track the difference.",
]

LEGEND_SPOTLIGHTS = [
    ("Mahabharata – Arjuna", "Practice focus like Arjuna aiming at the eye of the bird. Notice one detail deeply today."),
    ("Mahabharata – Bhishma", "Live with integrity like Bhishma. Promise yourself one action that keeps your word."),
    ("Ramayana – Hanuman", "Serve with courage like Hanuman. Help someone today without being asked."),
    ("Ramayana – Sita", "Be resilient like Sita. When a challenge feels hard, pause, breathe, and try one gentle step."),
    ("Global Peacemakers", "Kindness wins. Find a way to reduce conflict or calm hearts around you."),
]

INSPIRATION_SNIPPETS = [
    "Marie Curie said: 'I was taught that the way of progress is neither swift nor easy.'",
    "Katherine Johnson used math to guide rockets—numbers can take you to the stars!",
    "Wangari Maathai planted trees to change a nation. Every small action matters.",
    "Dr. Abdul Kalam called dreams the blueprint of the future. Sketch yours tonight!",
    "Ada Lovelace imagined computers before they existed. Your imagination is world-changing.",
    "Satya Nadella reads poetry for empathy. Mix art and science for superpowers.",
]
TAGGED_INSPIRATIONS = {
    "Planet": [
        "🌍 Try a mini eco-experiment: measure indoor plant growth with and without sunlight.",
        "♻️ Design a recycling superhero who rescues oceans—what powers do they use?",
    ],
    "Kindness": [
        "🤝 Create a gratitude note for someone who made your day brighter.",
        "💬 Practice empathy: ask a friend how they feel and listen deeply.",
    ],
    "Health": [
        "💪 Build a 3-minute energizer routine—mix jumps, stretches, and a smile.",
        "🧘‍♀️ Try a breathing pattern: inhale 4, hold 4, exhale 6—how does it feel?",
    ],
    "Build": [
        "🔧 Sketch a prototype for a gadget that solves a daily problem at home.",
        "🛠️ Rebuild an everyday object using LEGO or cardboard—what improves?",
    ],
    "Think": [
        "🧠 Invent a logic puzzle about your favorite animal—can someone else solve it?",
        "🔍 Fact-check a science claim today. What evidence backs it up?",
    ],
    "Curiosity": [
        "✨ Collect three new questions about the world before dinner.",
        "🔭 Explore a topic you’ve never studied—write one WOW fact.",
    ],
}

LEGEND_ALIGNMENT = {
    "Mahabharata – Arjuna": "Think",
    "Mahabharata – Bhishma": "Kindness",
    "Ramayana – Hanuman": "Build",
    "Ramayana – Sita": "Health",
    "Global Peacemakers": "Planet",
}



ACHIEVEMENT_BADGES = [
    (50, "Curiosity Explorer"),
    (100, "Insight Inventor"),
    (200, "World Changer"),
]

CELEBRATION_MESSAGES = [
    "Incredible spark, Amritha! You just leveled up your science superpowers!",
    "Boom! Another idea blossomed. Keep shining that brilliant mind!",
    "Your curiosity just planted a new tree of knowledge. Well done!",
    "High-five! That effort made the world a little kinder and smarter.",
    "You’re on The Silent Room path—every step like this sends ripples of good."
]


CELEBRATION_BY_TAG = {
    "Curiosity": [
        "Curiosity engines roaring—keep asking wild questions!",
        "Your wonder radar just pinged something amazing!",
    ],
    "Build": [
        "Engineer alert! You just built brilliance out of thin air.",
        "Your maker hands turned an idea into reality!",
    ],
    "Think": [
        "Logic lasers locked on target—fantastic reasoning!",
        "You balanced evidence like a true scientist!",
    ],
    "Write": [
        "Your words sparkle like constellations in a night sky!",
        "Story power activated—keep capturing discoveries!",
    ],
    "Share": [
        "Your voice just lit up someone else's brain!",
        "Teaching others made your knowledge twice as strong!",
    ],
    "Kindness": [
        "Kindness ripple activated—hearts feel safer around you!",
        "You just proved kindness is a real-world superpower!",
    ],
    "Planet": [
        "Earth just smiled because of you!",
        "Planet heroes wear invisible capes—you've got one now!",
    ],
    "Health": [
        "Strong body, bright brain—what a combo!",
        "You treated your body like the lab of your dreams!",
    ],
}

POINT_LABEL_BY_TAG = {
    "Curiosity": "curiosity points",
    "Build": "build points",
    "Think": "thinking points",
    "Write": "story points",
    "Share": "sharing points",
    "Kindness": "kindness points",
    "Planet": "planet points",
    "Health": "health points",
}


def celebration_for(tag: Optional[str]) -> str:
    pool = CELEBRATION_BY_TAG.get(tag)
    if pool:
        return random.choice(pool)
    return random.choice(CELEBRATION_MESSAGES)


def targeted_choice(tag: str, options: List[str], counts: Dict[str, int], fallback: Optional[str] = None) -> str:
    counts = counts or {}
    options = options or []
    if not options:
        return ""
    today_key = datetime.date.today().isoformat()
    if tag and counts.get(tag, 0):
        seed = f"{tag}-{counts.get(tag)}-{today_key}"
        rnd = random.Random(seed)
        return rnd.choice(options)
    if fallback and counts.get(fallback, 0):
        seed = f"{fallback}-{counts.get(fallback)}-{today_key}"
        rnd = random.Random(seed)
        return rnd.choice(options)
    return random.choice(options)


def choose_legend_story(tag_counts: Dict[str, int]) -> Tuple[str, str]:
    if not tag_counts:
        return random.choice(LEGEND_SPOTLIGHTS)
    for tag, _ in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True):
        for title, story in LEGEND_SPOTLIGHTS:
            if LEGEND_ALIGNMENT.get(title) == tag:
                return title, story
    return random.choice(LEGEND_SPOTLIGHTS)


SNOWFLAKE_INIT_ERROR: Optional[Exception] = None
try:
    init_db()
    mark_open_today()
    ensure_default_silentgpt_data()
except Exception as exc:
    SNOWFLAKE_INIT_ERROR = exc


@lru_cache(maxsize=1)
def _load_base_css() -> str:
    css_path = APP_ROOT / "styles.css"
    try:
        return css_path.read_text()
    except FileNotFoundError:
        return ""


base_css = _load_base_css()
if base_css:
    st.markdown(f"<style>{base_css}</style>", unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def _encoded_bg(image_path: str) -> str:
    path = Path(image_path)
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode()


def add_bg(image_path: Path) -> None:
    if not ENABLE_BACKGROUNDS:
        return
    encoded = _encoded_bg(str(image_path))
    if not encoded:
        return
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-image: url('data:image/jpg;base64,{encoded}');
            background-size: cover;
            background-attachment: fixed;
            background-position: center;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def initialize_state() -> None:
    if "history" not in st.session_state:
        st.session_state.history = [{"role": "system", "content": SYSTEM_PROMPT}]
    st.session_state.setdefault("mode", MODE_OPTIONS[0][0])
    st.session_state.setdefault("missions_completed", 0)
    st.session_state.setdefault("greeting", random.choice(GREETINGS))
    st.session_state.setdefault("mission", random.choice(MISSIONS))
    st.session_state.setdefault("health_tip", random.choice(HEALTH_TIPS))
    st.session_state.setdefault("kindness", random.choice(KINDNESS_CHALLENGES))
    st.session_state.setdefault("earth_tip", random.choice(EARTH_PROMISES))
    st.session_state.setdefault("legend", random.choice(LEGEND_SPOTLIGHTS))
    st.session_state.setdefault("inspiration", random.choice(INSPIRATION_SNIPPETS))
    st.session_state.setdefault("last_saved_diary", "")
    st.session_state.setdefault("current_difficulty", 2)  # Start at Elementary level
    st.session_state.setdefault("show_learning_insights", False)


def refresh_daily_cards() -> None:
    st.session_state.greeting = random.choice(GREETINGS)
    st.session_state.mission = random.choice(MISSIONS)
    st.session_state.health_tip = random.choice(HEALTH_TIPS)
    st.session_state.kindness = random.choice(KINDNESS_CHALLENGES)
    st.session_state.earth_tip = random.choice(EARTH_PROMISES)
    st.session_state.legend = random.choice(LEGEND_SPOTLIGHTS)
    st.session_state.inspiration = random.choice(INSPIRATION_SNIPPETS)


def badge_list(points: int) -> List[str]:
    return [label for threshold, label in ACHIEVEMENT_BADGES if points >= threshold]


def diary_summary_from_history(history: List[dict]) -> Dict[str, str]:
    user_msgs = [msg["content"] for msg in history if msg["role"] == "user"]
    coach_msgs = [msg["content"] for msg in history if msg["role"] == "assistant"]
    summary = {
        "big_question": user_msgs[0] if user_msgs else "",
        "what_we_tried": "\n\n".join(user_msgs[1:3]) if len(user_msgs) > 1 else "",
        "what_we_found": coach_msgs[-1] if coach_msgs else "",
        "how_ai_might_be_wrong": "",
        "next_step": coach_msgs[-1] if coach_msgs else "",
        "gratitude": "",
        "kindness_act": "",
        "planet_act": "",
    }
    return summary


def save_diary_entry() -> Optional[Path]:
    if len(st.session_state.history) <= 1:
        return None
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    diary_file = DIARY_DIR / f"diary_{timestamp}.json"
    with diary_file.open("w", encoding="utf-8") as handle:
        json.dump(st.session_state.history, handle, indent=2)
    summary = diary_summary_from_history(st.session_state.history)
    save_diary(datetime.date.today().isoformat(), summary)
    st.session_state.last_saved_diary = diary_file.name
    return diary_file


def reset_conversation() -> None:
    st.session_state.history = [{"role": "system", "content": SYSTEM_PROMPT}]
    refresh_daily_cards()
def transcribe_audio(audio_bytes: bytes, client: OpenAI) -> Optional[str]:
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "voice.wav"
    try:
        response = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=audio_file,
        )
    except Exception:
        return None
    text = getattr(response, "text", "")
    return text.strip() if text else None


def render_sidebar() -> None:
    st.sidebar.markdown("## 🧭 Your Journey")
    profile = st.session_state.get("supabase_profile")
    if profile:
        display_label = profile.get("display_name")
        hero_dream = profile.get("hero_dream")
        if display_label:
            st.sidebar.markdown(f"### {escape(display_label)}")
        else:
            st.sidebar.caption("Set your hero name to personalize the coach.")
        if hero_dream:
            st.sidebar.caption(f"⭐ Dream: {escape(hero_dream)}")
        status = (profile.get("subscription_status") or "unknown").title()
        trial_end = parse_timestamp(profile.get("trial_ends_at"))
        badge = f"Status: **{status}**"
        if trial_end:
            badge += f" • Trial ends {trial_end.date().isoformat()}"
        st.sidebar.info(badge)
        if st.sidebar.button("Sign out"):
            supabase_logout()

    points = cached_points_total()
    streak = cached_streak_length()
    tag_counts = cached_recent_tags()
    st.session_state["tag_counts"] = tag_counts

    col_points, col_streak = st.sidebar.columns(2)
    with col_points:
        st.metric("🏆 Points", points)
    with col_streak:
        st.metric("🔥 Streak", streak)
    
    # Adaptive Learning: Show current difficulty level
    difficulty_labels = {
        1: "🌱 Beginner",
        2: "🌿 Elementary", 
        3: "🌳 Intermediate",
        4: "🏔️ Advanced",
        5: "🚀 Expert"
    }
    current_diff = st.session_state.get("current_difficulty", 2)
    st.sidebar.caption(f"Learning Level: {difficulty_labels[current_diff]}")
    
    # 📈 Mastery snapshot
    child_id_for_mastery = st.session_state.get("silence_child_id")
    if child_id_for_mastery:
        mastery_rows = cached_child_mastery(child_id_for_mastery) or []
        with st.sidebar.expander("📈 Learning Progress", expanded=False):
            if mastery_rows:
                # Sort by most recently updated
                try:
                    # Snowflake returns uppercase keys by default
                    sort_rows = sorted(
                        mastery_rows,
                        key=lambda r: r.get("UPDATED_AT") or r.get("updated_at") or r.get("LAST_SEEN") or r.get("last_seen"),
                        reverse=True,
                    )
                except Exception:
                    sort_rows = mastery_rows
                top = sort_rows[:5]
                for row in top:
                    topic = row.get("TOPIC") or row.get("topic") or "(topic)"
                    mastery = float(row.get("MASTERY") or row.get("mastery") or 0)
                    pct = max(0, min(100, int(round(mastery * 100))))
                    st.caption(f"{topic}: {pct}%")
                    st.progress(pct)
            else:
                st.caption("No mastery data yet — start a chat with your coach to begin tracking.")
    
    total_profiles = fetch_total_profiles()
    if total_profiles is not None:
        st.sidebar.metric("👪 Parent accounts", total_profiles)
    if profile and profile.get("stripe_customer_id"):
        if st.sidebar.button("Manage subscription", use_container_width=True, key="sidebar-manage-subscription"):
            result = invoke_supabase_function(
                "create-portal-session",
                {"supabase_user_id": st.session_state.get("supabase_session", {}).get("user_id")},
            )
            if result and result.get("url"):
                st.session_state["portal_url"] = result["url"]
                st.rerun()
            else:
                st.sidebar.error("Unable to open customer portal right now.")

    badges = badge_list(points)
    if badges:
        badges_text = " ".join(f"🏅 {badge}" for badge in badges)
        st.sidebar.markdown(f"**Unlocked Badges:** {badges_text}")
    else:
        st.sidebar.caption("Collect curiosity points to unlock badges!")

    st.sidebar.markdown("### 🎯 Ritual Rewards")
    
    # Adaptive Learning: Show learning insights
    engine = st.session_state.get("adaptive_engine")
    if engine and st.sidebar.button("📊 Show My Learning Insights", use_container_width=True):
        st.session_state["show_learning_insights"] = not st.session_state.get("show_learning_insights", False)
    
    if st.session_state.get("show_learning_insights", False) and engine:
        child = get_child_profile(st.session_state.get("silence_child_id"))
        child_name = (child or {}).get("name") or "Explorer"
        try:
            insights = engine.get_learning_insights(child_name)
        except Exception as exc:
            st.sidebar.error(f"Could not load insights: {exc}")
            insights = {}
        with st.sidebar.expander("💡 Your Learning Journey", expanded=True):
            strengths = insights.get("strengths") or []
            growth_areas = insights.get("growth_areas") or []
            recommendations = insights.get("recommendations") or []
            if strengths:
                st.markdown("**🌟 Your Strengths:**")
                for strength in strengths[:3]:
                    if isinstance(strength, dict):
                        st.caption(f"✓ {strength.get('topic', strength)} (lvl {strength.get('level','')})")
                    else:
                        st.caption(f"✓ {strength}")
            
            if growth_areas:
                st.markdown("**🌱 Growth Areas:**")
                for area in growth_areas[:3]:
                    if isinstance(area, dict):
                        st.caption(f"→ {area.get('topic', area)} (lvl {area.get('level','')})")
                    else:
                        st.caption(f"→ {area}")
            
            if recommendations:
                st.markdown("**🎯 Next Steps:**")
                for rec in recommendations[:2]:
                    st.caption(f"• {rec}")
    
    # Adaptive Learning: Suggest next topic (persist suggestion in state so it stays visible after click)
    if engine and st.sidebar.button("🔮 What should I learn next?", use_container_width=True):
        child = get_child_profile(st.session_state.get("silence_child_id"))
        if child:
            # Get recent topics from conversation
            recent_topics = []
            projects = cached_projects(st.session_state.get("silence_child_id"))
            for proj in projects[-3:]:
                tags = (proj.get("tags") or "").split(",")
                recent_topics.extend([t.strip() for t in tags if t.strip()])
            
            interests = (child.get("interests") or "").split(",")
            interests = [i.strip() for i in interests if i.strip()]
            
            suggestion = engine.suggest_next_topic(recent_topics[-5:], interests)
            if suggestion:
                topic_text = suggestion["topic"] if isinstance(suggestion, dict) else suggestion
                reason_text = suggestion.get("reason") if isinstance(suggestion, dict) else "This fits your interests or sweet spot."
                st.session_state["next_topic_suggestion"] = {"topic": topic_text, "reason": reason_text}
    if st.session_state.get("next_topic_suggestion"):
        s = st.session_state["next_topic_suggestion"]
        st.sidebar.info(f"🎯 Try exploring: **{s.get('topic','?')}**\n\n{s.get('reason','')}")
    
    if st.sidebar.button("🕒 We completed our 21-minute ritual", use_container_width=True):
        today = datetime.date.today().isoformat()
        log_mission(today, "Ritual", "21-minute Silent Room ritual")
        add_points(15, "ritual_chat")
        invalidate_progress_caches()
        label = POINT_LABEL_BY_TAG.get("Curiosity", "points")
        message = celebration_for("Curiosity")
        st.sidebar.success(f"{message} (+15 {label}!)")
        st.balloons()
        st.sidebar.caption("Great job! Come back tomorrow for more points.")
    if st.sidebar.button("🤝 I did a Kindness Act", use_container_width=True):
        add_points(5, "kindness_act")
        invalidate_progress_caches()
        message = celebration_for("Kindness")
        label = POINT_LABEL_BY_TAG.get("Kindness", "points")
        st.sidebar.success(f"{message} (+5 {label}!)")
        st.balloons()
    if st.sidebar.button("🌍 I did a Planet Act", use_container_width=True):
        add_points(5, "planet_act")
        invalidate_progress_caches()
        message = celebration_for("Planet")
        label = POINT_LABEL_BY_TAG.get("Planet", "points")
        st.sidebar.success(f"{message} (+5 {label}!)")
        st.balloons()

    if st.sidebar.button("💾 Save to Discovery Diary", use_container_width=True):
        saved = save_diary_entry()
        if saved:
            st.sidebar.success(f"Saved insights to {saved.name}")
        else:
            st.sidebar.warning("Chat with your coach before saving a diary entry.")

    st.sidebar.divider()
    top_tag = None
    if tag_counts:
        top_tag = max(tag_counts.items(), key=lambda x: x[1])[0]
    if top_tag not in TAGGED_INSPIRATIONS:
        top_tag = "Curiosity"
    st.session_state.setdefault("inspiration_tag", top_tag)
    if st.session_state.get("inspiration_tag") != top_tag:
        st.session_state["inspiration_tag"] = top_tag
        st.session_state["inspiration"] = targeted_choice(
            top_tag,
            TAGGED_INSPIRATIONS.get(top_tag, INSPIRATION_SNIPPETS),
            tag_counts,
        )

    legend_title, legend_story = choose_legend_story(tag_counts)
    st.session_state.legend = (legend_title, legend_story)
    st.sidebar.markdown("## 🪷 Wisdom Spotlight")
    st.sidebar.markdown(f"**{legend_title}**")
    st.sidebar.write(legend_story)

    if st.sidebar.button("🧹 Start fresh chat", use_container_width=True):
        reset_conversation()
        st.rerun()


def render_coach_tab(client: OpenAI, profile: Optional[dict], default_api_key: Optional[str]) -> None:
    add_bg(BACKGROUND_IMAGES.get("coach", Path()))

    st.markdown('<div class="section-heading">🤖 SilenceGPT — The Nobel Coach</div>', unsafe_allow_html=True)
    st.caption("A calm ritual: choose your explorer, pick an adventure, chat, then act.")

    silence_api_key = (
        st.secrets.get("SILENCE_GPT_API_KEY")
        or default_api_key
        or os.getenv("SILENCE_GPT_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )

    # session keys
    child_key = "silence_child_id"
    project_key = "silence_project_id"
    thread_key = "silence_thread_id"
    free_limit = st.session_state.get("free_tier_limit", FREE_TIER_DAILY_MESSAGES)
    is_paid = st.session_state.get("has_paid_access", False)
    profile = profile or st.session_state.get("supabase_profile")
    
    # Initialize Adaptive Learning Engine
    if "adaptive_engine" not in st.session_state:
        child_id = st.session_state.get(child_key)
        saved_state = None
        if child_id:
            # Load saved state from database
            saved_state = get_adaptive_learning_state(child_id)
        st.session_state["adaptive_engine"] = AdaptiveLearningEngine(saved_state)

    def step_indicator(current: int) -> None:
        labels = ["1. Explorer", "2. Adventure", "3. Chat"]
        cols = st.columns(3)
        for idx, col in enumerate(cols, start=1):
            with col:
                status = "🟢" if idx <= current else "⚪️"
                st.markdown(f"**{status} {labels[idx-1]}**")

    # Step 1: explorer cards
    children = cached_child_profiles()
    with st.expander("➕ Add explorer", expanded=(len(children) == 0)):
        new_child_name = st.text_input("Explorer name", key="silence_new_child_name")
        new_child_age = st.slider("Age", min_value=5, max_value=16, value=9, key="silence_new_child_age")
        new_child_interests = st.text_input("Favorite topics", help="e.g., Space, oceans, robots", key="silence_new_child_interests")
        new_child_dream = st.text_input("Big dream", help="e.g., Build a coral robot", key="silence_new_child_dream")
        if st.button("Save explorer", key="silence_create_child"):
            if new_child_name.strip():
                child_id = create_child_profile(
                    new_child_name.strip(),
                    int(new_child_age),
                    new_child_interests.strip(),
                    new_child_dream.strip(),
                )
                invalidate_coach_caches()
                st.session_state[child_key] = child_id
                st.session_state.pop(project_key, None)
                st.session_state.pop(thread_key, None)
                st.success("Explorer ready!")
                st.rerun()
            else:
                st.warning("Please add a name.")

    selected_child_id = st.session_state.get(child_key)
    child_ids = {child["id"] for child in children}
    if children and (selected_child_id not in child_ids):
        st.session_state[child_key] = children[0]["id"]
        st.rerun()

    selected_project_id = st.session_state.get(project_key)

    stage = 1
    if selected_child_id:
        stage = 2
    if selected_project_id:
        stage = 3

    step_indicator(stage)

    if not children:
        st.info("Add an explorer to start tonight's 21-minute ritual.")
        return

    st.markdown("### Choose your explorer")
    cols = st.columns(min(len(children), 3))
    for idx, child in enumerate(children):
        column = cols[idx % len(cols)]
        with column:
            active = child["id"] == st.session_state[child_key]
            card = st.container(border=True)
            with card:
                st.markdown(f"#### {'🌟' if active else '🙂'} {child['name']}")
                st.caption(f"Dream: {child['dream'] or 'Still exploring'}")
                btn_cols = st.columns(2)
                with btn_cols[0]:
                    if st.button(
                        "Start ritual" if not active else "Current explorer",
                        key=f"pick_child_{child['id']}",
                        disabled=active,
                        use_container_width=True,
                    ):
                        st.session_state[child_key] = child["id"]
                        st.session_state.pop(project_key, None)
                        st.session_state.pop(thread_key, None)
                        st.rerun()
                with btn_cols[1]:
                    if st.button(
                        "Remove",
                        key=f"remove_child_{child['id']}",
                        type="secondary",
                        use_container_width=True,
                    ):
                        delete_child_profile(child["id"])
                        if st.session_state.get(child_key) == child["id"]:
                            st.session_state.pop(child_key, None)
                            st.session_state.pop(project_key, None)
                            st.session_state.pop(thread_key, None)
                        invalidate_coach_caches()
                        st.success(f"Removed explorer {child['name']}.")
                        st.rerun()

    selected_child = get_child_profile(st.session_state[child_key])
    if not selected_child:
        st.warning("Explorer missing. Please add one again.")
        return

    # Step 2: adventures (projects)
    adventures = cached_projects(child_id=st.session_state[child_key])
    if not adventures:
        step_indicator(2)
        st.info("Create the first adventure for this explorer.")
        with st.form("create_first_adventure"):
            col_goal, col_tags = st.columns(2)
            adventure_name = col_goal.text_input("Adventure name", key="silence_proj_name")
            adventure_goal = col_goal.text_area("What are we building or discovering?", key="silence_proj_goal")
            adventure_tags = col_tags.text_input("Mood or tags", key="silence_proj_tags")
            submitted_first = st.form_submit_button("Create adventure")
            if submitted_first:
                if adventure_name.strip():
                    project_id = create_project(
                        st.session_state[child_key],
                        adventure_name.strip(),
                        adventure_goal.strip(),
                        adventure_tags.strip(),
                    )
                    invalidate_coach_caches()
                    st.session_state[project_key] = project_id
                    st.session_state.pop(thread_key, None)
                    st.success("Adventure ready. Time to chat!")
                    st.rerun()
                else:
                    st.warning("Adventure name required.")
        return

    if project_key not in st.session_state or st.session_state[project_key] not in {proj["id"] for proj in adventures}:
        st.session_state[project_key] = adventures[0]["id"]
        st.rerun()
    st.markdown("### Pick tonight's adventure")
    adventure_cols = st.columns(min(len(adventures), 3))
    for idx, proj in enumerate(adventures):
        column = adventure_cols[idx % len(adventure_cols)]
        with column:
            active = proj["id"] == st.session_state[project_key]
            card = st.container(border=True)
            with card:
                st.markdown(f"#### {'🚀' if active else '🗂️'} {proj['name']}")
                st.caption(proj["goal"] or "Set a mission goal")
                tags = ", ".join(tag.strip() for tag in (proj["tags"] or "").split(",") if tag.strip())
                if tags:
                    st.caption(f"Tags: {tags}")
                choose_label = "Open adventure" if not active else "Currently active"
                if st.button(choose_label, key=f"pick_project_{proj['id']}", disabled=active, use_container_width=True):
                    st.session_state[project_key] = proj["id"]
                    st.session_state.pop(thread_key, None)
                    st.rerun()

    with st.expander("➕ Add another adventure", expanded=False):
        with st.form("add_adventure_form"):
            col_goal, col_tags = st.columns(2)
            extra_name = col_goal.text_input("Adventure name", key="extra_adventure_name")
            extra_goal = col_goal.text_area("Goal or outcome", key="extra_adventure_goal")
            extra_tags = col_tags.text_input("Tags", key="extra_adventure_tags")
            submitted_extra = st.form_submit_button("Save adventure")
            if submitted_extra:
                if extra_name.strip():
                    new_project_id = create_project(
                        st.session_state[child_key],
                        extra_name.strip(),
                        extra_goal.strip(),
                        extra_tags.strip(),
                    )
                    invalidate_coach_caches()
                    st.session_state[project_key] = new_project_id
                    st.session_state.pop(thread_key, None)
                    st.success("Adventure added.")
                    st.rerun()
                else:
                    st.warning("Adventure name required.")

    selected_project = get_project(st.session_state[project_key])
    if not selected_project:
        st.warning("Adventure could not be loaded.")
        return

    with st.expander("🎛️ Adventure settings", expanded=False):
        new_name = st.text_input("Adventure name", value=selected_project["name"], key="active_adventure_name")
        new_goal = st.text_area("Goal", value=selected_project["goal"] or "", key="active_adventure_goal")
        new_tags = st.text_input("Tags", value=selected_project["tags"] or "", key="active_adventure_tags")
        if st.button("Save adventure details", key="save_active_adventure"):
            if new_name.strip() != selected_project["name"]:
                rename_project(selected_project["id"], new_name.strip())
            update_project_details(selected_project["id"], new_goal.strip(), new_tags.strip())
            invalidate_coach_caches()
            st.success("Adventure updated.")
            st.rerun()
        if st.button("Archive this adventure", key="archive_active_adventure"):
            archive_project(selected_project["id"], 1)
            st.session_state.pop(project_key, None)
            st.session_state.pop(thread_key, None)
            invalidate_coach_caches()
            st.info("Adventure archived. Start a new one when ready.")
            st.rerun()

    # Step 3: chat stage
    st.markdown("### 3. Chat with SilenceGPT")

    # Adaptive learning status card
    engine = st.session_state.get("adaptive_engine")
    project_tags = [t.strip() for t in (selected_project.get("tags") or "").split(",") if t.strip()]
    current_topic = project_tags[0] if project_tags else (selected_project.get("goal") or "General Knowledge")
    difficulty_labels = {
        1: "🌱 Beginner",
        2: "🌿 Elementary",
        3: "🌳 Intermediate",
        4: "🏔️ Advanced",
        5: "🚀 Expert",
    }
    current_diff = st.session_state.get("current_difficulty", 2)
    with st.container(border=True):
        st.caption("Adaptive learning")
        st.markdown(f"**Topic:** {current_topic}")
        st.markdown(f"**Level:** {difficulty_labels.get(current_diff, current_diff)}")
        if engine:
            if st.button("💾 Save adaptive state now", key="save_adaptive_state"):
                try:
                    state_data = engine.get_state()
                    save_adaptive_learning_state(st.session_state[child_key], state_data)
                    st.success("Saved adaptive state for this explorer.")
                except Exception as exc:
                    st.error(f"Could not save adaptive state: {exc}")
        else:
            st.caption("Adaptive engine will activate after your first message on this adventure.")

    threads = cached_threads(selected_project["id"])
    if thread_key not in st.session_state or (st.session_state.get(thread_key) and st.session_state[thread_key] not in {thr["id"] for thr in threads}):
        st.session_state.pop(thread_key, None)

    if st.button("➕ New page in notebook", key="new_thread_btn"):
        new_tid = create_thread(selected_project["id"], "New page")
        cached_threads.clear()
        cached_thread_messages.clear()
        st.session_state[thread_key] = new_tid
        st.rerun()

    if not threads:
        new_tid = create_thread(selected_project["id"], "First page")
        cached_threads.clear()
        cached_thread_messages.clear()
        threads = cached_threads(selected_project["id"])
        st.session_state[thread_key] = new_tid

    if st.session_state.get(thread_key) is None and threads:
        st.session_state[thread_key] = threads[0]["id"]

    current_thread_id = st.session_state.get(thread_key)
    if current_thread_id is None:
        st.info("Tap “New page in notebook” to begin.")
        return

    col_pages, col_chat = st.columns([1, 3], gap="large")

    with col_pages:
        st.markdown("#### 📒 Notebook pages")
        for thread in threads:
            tid = thread["id"]
            title = thread["title"] or f"Page {tid}"
            active = tid == current_thread_id
            label = f"**{'➡️' if active else '🗂️'} {title}**"
            if st.button(label, key=f"jump_thread_{tid}", use_container_width=True, disabled=active):
                st.session_state[thread_key] = tid
                st.rerun()
            with st.expander("Options", expanded=False):
                new_name = st.text_input("Rename page", value=title, key=f"rename_thread_{tid}")
                if st.button("Rename page", key=f"rename_btn_{tid}"):
                    rename_thread(tid, new_name or "Notebook page")
                    st.rerun()
                if st.button("Archive page", key=f"archive_btn_{tid}"):
                    archive_thread(tid, 1)
                    if st.session_state.get(thread_key) == tid:
                        st.session_state.pop(thread_key, None)
                    st.rerun()

        with st.expander("🔍 Find a memory", expanded=False):
            search_query = st.text_input("Search all pages", placeholder="e.g., volcano OR kindness", key="silence_search")
            if search_query.strip():
                hits = search_messages(st.session_state[child_key], search_query.strip())
                if hits:
                    for hit in hits[:6]:
                        st.caption(f"Page #{hit['thread_id']} · {hit['snippet']}")
                else:
                    st.caption("No matching notes yet.")

    with col_chat:
        msgs = cached_thread_messages(current_thread_id)
        with st.container(border=True):
            st.markdown(f"**Explorer:** {selected_child['name']} · **Adventure:** {selected_project['name']}**")
        st.caption(selected_project["goal"] or "Define a small win for this adventure.")
        if not is_paid and FREE_TIER_ENABLED:
            usage = get_free_tier_usage()
            remaining = max(free_limit - usage["count"], 0)
            st.warning(
                f"Free Explorer mode — {remaining} of {free_limit} mentor chats remain today. "
                "Upgrade for unlimited access."
            )

        chat_container = st.container()
        with chat_container:
            if not msgs:
                st.caption("✨ This page is blank. Ask your mentor anything to start!")
            for row in msgs:
                speaker = "user" if row["role"] == "user" else "assistant"
                avatar = "🙂" if speaker == "user" else "🧠"
                with st.chat_message(speaker, avatar=avatar):
                    st.markdown(row["content"])

        if not silence_api_key:
            st.warning("Add SILENCE_GPT_API_KEY (or reuse your OPENAI_API_KEY) in Secrets to chat.")

    prompt = st.chat_input("Type or paste what you’re curious about…", disabled=not silence_api_key)
    if prompt and silence_api_key:
        if not is_paid and FREE_TIER_ENABLED:
            usage = get_free_tier_usage()
            if usage["count"] >= free_limit:
                st.warning("Free Explorer limit reached for today. Upgrade to continue chatting.")
                render_subscription_cta(profile, st.session_state.get("checkout_status"))
                prompt = None
            else:
                usage["count"] += 1
        if prompt:
            add_message(current_thread_id, "user", prompt.strip(), model="gpt-4.1-mini")
            cached_thread_messages.clear()
            
            # Adaptive Learning: Assess comprehension from user's message
            engine = st.session_state.get("adaptive_engine")
            selected_child = get_child_profile(st.session_state[child_key])
            if engine and selected_child:
                # Determine current topic from project tags
                project_tags = (selected_project.get("tags") or "").split(",")
                current_topic = project_tags[0].strip() if project_tags else "General Knowledge"
                
                # Get conversation context (last few messages)
                recent_msgs = cached_thread_messages(current_thread_id)[-5:]
                context = "\n".join([f"{m['role']}: {m['content']}" for m in recent_msgs])
                
                # Assess child's comprehension
                assessment = engine.assess_comprehension(prompt.strip(), {})
                
                # Save assessment to database (need message_id from last added message)
                last_msg_id = None  # We don't track message IDs currently, use thread_id as fallback
                save_comprehension_assessment(
                    st.session_state[child_key],
                    current_thread_id,
                    last_msg_id or current_thread_id,  # Use thread_id as proxy for message_id
                    current_topic,
                    st.session_state.get("current_difficulty", 2),
                    assessment["comprehension_score"],
                    assessment["curiosity_score"],
                    assessment["confidence_score"]
                )
                
                # Update skill level based on performance
                performance_score = (
                    assessment["comprehension_score"] * 0.5 +
                    assessment["curiosity_score"] * 0.3 +
                    assessment["confidence_score"] * 0.2
                )
                engine.update_skill_level(current_topic, st.session_state.get("current_difficulty", 2), performance_score)
                # Track in-engine history for prompt personalization
                try:
                    engine.comprehension_history.append(assessment)
                except Exception:
                    pass
                
                # Telemetry: log interaction and update mastery in Snowflake
                try:
                    all_msgs_now = cached_thread_messages(current_thread_id)
                    turn_num = len(all_msgs_now)
                    session_id = f"thread-{current_thread_id}"
                    question_id = f"user-{turn_num}"
                    level = st.session_state.get("current_difficulty", 2)
                    difficulty_norm = max(0.0, min(1.0, (level - 1) / 4.0))
                    score = float(performance_score)
                    confidence = float(assessment.get("confidence_score", 0.5))
                    latency_sec = 0.0
                    hints_used = 0
                    # Log the interaction
                    log_interaction(
                        st.session_state[child_key],
                        session_id,
                        turn_num,
                        current_topic,
                        level,
                        question_id,
                        difficulty_norm,
                        score,
                        confidence,
                        latency_sec,
                        hints_used,
                    )
                    # Update mastery via EMA
                    rec = get_child_mastery_record(st.session_state[child_key], current_topic)
                    existing_mastery = None
                    if rec:
                        existing_mastery = rec.get("MASTERY") or rec.get("mastery")
                    base = float(existing_mastery) if existing_mastery is not None else 0.5
                    alpha = 0.3
                    new_mastery = alpha * score + (1 - alpha) * base
                    correct_delta = 1 if score >= 0.7 else 0
                    upsert_child_mastery(
                        st.session_state[child_key],
                        current_topic,
                        float(new_mastery),
                        attempts_delta=1,
                        correct_delta=correct_delta,
                        avg_latency_sec=latency_sec,
                    )
                    # Invalidate mastery cache so sidebar reflects updates immediately
                    try:
                        cached_child_mastery.clear()
                    except Exception:
                        pass
                except Exception:
                    # Non-fatal; continue chat even if telemetry fails
                    pass
                
                # Adjust difficulty if needed
                new_difficulty = engine.get_optimal_difficulty(current_topic, st.session_state.get("current_difficulty", 2))
                st.session_state["current_difficulty"] = new_difficulty
            
            # Build enhanced system prompt with adaptive learning
            base_prompt = (
                selected_project["system_prompt"]
                or build_system_prompt(
                    selected_child["name"],
                    selected_child["age"],
                    selected_child["interests"],
                    selected_child["dream"],
                    selected_project["goal"],
                    selected_project["tags"],
                )
            )
            
            # Add adaptive learning enhancements to prompt
            if engine:
                adaptive_prompt = engine.generate_adaptive_prompt(
                    current_topic,
                    st.session_state.get("current_difficulty", 2),
                    selected_child["name"],
                    engine.comprehension_history,
                )
                system_prompt = f"{base_prompt}\n\n{adaptive_prompt}"
            else:
                system_prompt = base_prompt
            
            history = [{"role": "system", "content": system_prompt}]
            for entry in cached_thread_messages(current_thread_id):
                history.append({"role": entry["role"], "content": entry["content"]})
            try:
                reply = chat_completion(
                    history,
                    api_key=silence_api_key,
                    model="gpt-4.1-mini",
                    temperature=0.7,
                )
            except Exception as exc:
                st.error(f"Model error: {exc}")
            else:
                add_message(current_thread_id, "assistant", reply, model="gpt-4.1-mini")
                cached_thread_messages.clear()
                
                # Save adaptive learning state periodically (every 5 messages)
                if engine and len(cached_thread_messages(current_thread_id)) % 5 == 0:
                    state_data = engine.get_state()
                    save_adaptive_learning_state(st.session_state[child_key], state_data)
                
                st.rerun()

        with st.expander("✨ Turn this into a mission", expanded=False):
            if msgs:
                last_msg = msgs[-1]["content"]
                title = last_msg.split("\n")[0][:50]
                mission_title = st.text_input("Mission title", value=title or "New mission")
                if st.button("Save mission from chat", key="mission_from_chat"):
                    add_user_mission(mission_title.strip(), last_msg[:400], tag="Build")
                    add_points(5, "mission_create")
                    invalidate_progress_caches()
                    st.success("Added to My Missions.")


@st.cache_data(ttl=30, show_spinner=False)
def cached_feed() -> List[Dict[str, str]]:
    return load_feed()


def render_mission_week() -> None:
    week = cached_week_summary(7)
    if not week:
        return
    today = datetime.date.today()
    st.markdown("#### 🗓️ Mission Week")
    st.markdown('<div class="nc-week-grid">', unsafe_allow_html=True)
    week_cols = st.columns(len(week), gap="small")
    for col, day in zip(week_cols, week):
        badges = []
        if day["missions"]:
            label = "mission" if day["missions"] == 1 else "missions"
            badges.append(f"🌱 {day['missions']} {label}")
        if day["kindness"]:
            badges.append("🤝 Kindness")
        if day["planet"]:
            badges.append("🌍 Planet")
        if day["health"]:
            badges.append("💓 Health")
        if day["points"] and day["points"] > 0:
            badges.append(f"🏆 +{day['points']} pts")
        summary = "<br>".join(badges) if badges else "Plan a tiny win today!"
        classes = ["nc-day-card"]
        if day["date"] == today:
            classes.append("today")
        with col:
            st.markdown(
                f"""
<div class="{' '.join(classes)}">
  <div class="nc-day-card__header">{day['date'].strftime('%a')}</div>
  <div class="nc-day-card__date">{day['date'].day}</div>
  <div class="nc-day-card__body">{summary}</div>
</div>
""",
                unsafe_allow_html=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)


def ensure_app_initialized() -> None:
    if st.session_state.get("app_initialized"):
        return
    client = get_supabase_client()
    if client is not None:
        st.session_state["supabase_client"] = client
    cached_feed()
    st.session_state["app_initialized"] = True
    st.session_state["just_logged_in"] = True


def render_knowledge_hub() -> None:
    add_bg(BACKGROUND_IMAGES.get("gallery", Path()))
    st.markdown('<div class="section-heading">📚 Knowledge Hub</div>', unsafe_allow_html=True)
    st.markdown(
        """
<style>
.share-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
  flex-wrap: wrap;
}
.share-row input.share-link {
  flex: 1;
  min-width: 200px;
  padding: 0.2rem 0.4rem;
  border-radius: 6px;
  border: 1px solid #ccc;
  font-size: 0.85rem;
}
.share-row a.share-icon {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #f4f4f4;
  transition: transform 0.1s ease-in-out;
}
.share-row a.share-icon:hover {
  transform: scale(1.1);
}
.share-row a.share-icon img {
  width: 18px;
  height: 18px;
}
.post-header.highlight {
  border-left: 4px solid #7c4dff;
  padding-left: 0.6rem;
}
</style>
""",
        unsafe_allow_html=True,
    )
    feed = cached_feed()
    query_params = st.query_params
    target_slug = query_params.get("post")
    if isinstance(target_slug, list):
        target_slug = target_slug[0]
    configured_base = st.secrets.get("APP_BASE_URL", os.getenv("APP_BASE_URL", "")).strip()
    share_base = st.secrets.get("SHARE_APP_BASE_URL", os.getenv("SHARE_APP_BASE_URL", "")).strip()
    configured_base = configured_base.rstrip("/") if configured_base else ""
    share_base = share_base.rstrip("/") if share_base else ""
    fallback_base = ""
    if not configured_base:
        server_addr = st.get_option("browser.serverAddress")
        server_port = st.get_option("browser.serverPort")
        scheme = "https" if str(server_addr).startswith("https") else "http"
        if server_addr:
            if str(server_addr).startswith("http"):
                fallback_base = server_addr.rstrip("/")
            else:
                fallback_base = f"{scheme}://{server_addr}"
        else:
            fallback_base = "http://localhost"
        if server_port and str(server_port) not in ("80", "443"):
            fallback_base = f"{fallback_base.rstrip('/')}" f":{server_port}"
        fallback_base = fallback_base.rstrip("/")
    app_base_url = configured_base or fallback_base
    base_was_guessed = bool(not configured_base and app_base_url)
    if base_was_guessed:
        st.caption(
            "Sharing links use your current host address. Set APP_BASE_URL in secrets for a fixed public URL."
        )
    with st.form("new_post_form", clear_on_submit=True):
        st.subheader("✨ Create New Knowledge Hub Post")
        title_input = st.text_input("Title", max_chars=80, key="feed_title")
        body = st.text_area("Your message (Markdown supported)", height=180, key="feed_body_simple")
        resource_link = st.text_input("Optional external link", key="feed_resource_link")
        uploaded_images = st.file_uploader(
            "Add images",
            accept_multiple_files=True,
            type=["png", "jpg", "jpeg", "webp", "gif"],
            key="feed_images",
        )
        submitted = st.form_submit_button("Publish Permanently")
        if submitted:
            title_text = title_input.strip()
            body_text = body.strip()
            if not title_text:
                st.error("Please add a title for this post.")
            elif not body_text:
                st.error("Please write a message before publishing.")
            else:
                image_urls: List[str] = []
                if uploaded_images:
                    with st.spinner("Uploading images to Supabase…"):
                        for uploaded in uploaded_images:
                            url = upload_hub_media(uploaded)
                            if url:
                                image_urls.append(url)
                add_feed_entry(
                    title=title_text,
                    summary="",
                    body=body_text,
                    tags=[],
                    cta="",
                    zoom_link="",
                    resource_link=(resource_link or "").strip(),
                    image_urls=image_urls,
                )
                cached_feed.clear()
                st.success("Shared with the community.")
                st.session_state["active_tab"] = "Knowledge Hub"
                st.rerun()

    st.markdown("---")
    st.markdown("## 🏛 Knowledge Hub Feed")
    if not feed:
        st.info("No posts yet — be the first to share!")
        return

    for post in feed:
        posted_at = post.get("posted_at", "") or post.get("created_at", "")
        resource_link = post.get("resource_link", "")
        image_urls = post.get("image_urls") or []
        is_target = target_slug and post.get("slug") == target_slug
        share_slug = post.get("slug")
        share_url = ""
        if share_slug:
            if share_base:
                share_url = f"{share_base}?post={share_slug}"
            else:
                share_url = f"{app_base_url}?post={share_slug}" if app_base_url else f"?post={share_slug}"
        with st.container():
            if is_target:
                st.success("You’re viewing the shared post.")
            if image_urls:
                st.image(image_urls[0], use_container_width=True)
            st.markdown(f"### {post['title']}")
            body_text = post.get("body") or post.get("summary") or ""
            if body_text:
                st.markdown(body_text, unsafe_allow_html=True)
            if resource_link:
                st.markdown(f"[🔗 Read more]({resource_link})")
            if len(image_urls) > 1:
                with st.expander(f"See all {len(image_urls)} images"):
                    for url in image_urls:
                        st.image(url, use_container_width=True)
            if posted_at:
                st.caption(posted_at)
            action_cols = st.columns([3, 1])
            with action_cols[0]:
                if share_url:
                    share_text = f"{post['title']} — check this Silent Room update: {share_url}"
                    encoded = quote_plus(share_text)
                    whatsapp = f"https://wa.me/?text={encoded}"
                    twitter = f"https://twitter.com/intent/tweet?text={encoded}"
                    instagram_hint = "https://www.instagram.com/create/story/"
                    safe_share_url = escape(share_url, quote=True)
                    icons_html = f"""
<div class="share-row">
  <input type="text" value="{safe_share_url}" readonly class="share-link" />
  <a class="share-icon" href="{safe_share_url}" target="_blank" title="Open post link" rel="noopener">🔗</a>
  <a class="share-icon" href="{escape(whatsapp, quote=True)}" target="_blank" title="Share on WhatsApp" rel="noopener">
    <img src="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/whatsapp.svg" alt="WhatsApp" />
  </a>
  <a class="share-icon" href="{escape(twitter, quote=True)}" target="_blank" title="Share on X" rel="noopener">
    <img src="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/x.svg" alt="X" />
  </a>
  <a class="share-icon" href="{escape(instagram_hint, quote=True)}" target="_blank" title="Post on Instagram" rel="noopener">
    <img src="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/instagram.svg" alt="Instagram" />
  </a>
</div>
"""
                    st.markdown(icons_html, unsafe_allow_html=True)
            with action_cols[1]:
                if st.button("🗑️ Delete", key=f"delete_post_{post['slug']}", type="secondary", use_container_width=True):
                    delete_feed_entry(post["slug"])
                    cached_feed.clear()
                    st.success("Post removed.")
                    st.rerun()
        st.divider()

def render_learning_lab_tab(api_key: Optional[str]) -> None:
    st.markdown('<div class="section-heading">🧠 AI Ritual Builder</div>', unsafe_allow_html=True)
    st.caption("Create nightly 21-minute moments with SilenceGPT guiding parents and kids together.")
    family_id = st.text_input("Family ID", value=st.session_state.get("learning_family_id", "fam_demo"))
    if not family_id.strip():
        st.stop()
    family_id = family_id.strip()
    st.session_state["learning_family_id"] = family_id

    profile = cached_family_profile(family_id)
    if profile is None:
        upsert_family_profile(
            family_id,
            "demo@silentroom.app",
            "Amritha",
            9,
            ["space", "robots", "kindness"],
        )
        invalidate_family_caches()
        profile = cached_family_profile(family_id)

    kid_name = profile.get("kid_name") or "Explorer"
    kid_age = profile.get("kid_age") or 9
    interests = profile.get("interests") or []

    st.success(f"Welcome {kid_name} (age {kid_age}) 👋")

    col_left, col_right = st.columns([2, 1])
    with col_left:
        interest = st.text_input("What are you curious about today?", value=interests[0] if interests else "space")
        notes = st.text_area("Parent notes (optional)", height=80)
        if st.button("Ask SilenceGPT", type="primary"):
            if not api_key:
                st.error("Add OPENAI_API_KEY to secrets before generating guidance.")
                st.stop()
            client = get_openai_client_cached(api_key)
            system_prompt = (
                "You are SilenceGPT, the Nobel Coach: calm, wise, and playful. "
                f"Audience: a kid aged {kid_age} and their parent. "
                f'Goal: guide exploration of "{interest}" with simple facts, tiny experiments, co-learning questions, and a short quiet reflection. '
                "Rules: 200–300 words max, simple language, emojis sparingly. "
                "Always include sections: Wonder Whisper, Do-Together Steps (3 bullets), Parent Prompt, Quiet Moment. "
                "Encourage safety and curiosity; never give risky instructions. "
                "Return JSON with keys wonder_whisper, steps (array), parent_prompt, quiet_moment."
            )
            user_prompt = (
                f"Family: {family_id}; Kid: {kid_name} ({kid_age}). "
                f"Past interests: {', '.join(interests) or 'general curiosity'}. "
                f"Current focus: {interest}."
            )
            start = time.time()
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.7,
                    max_tokens=500,
                )
                content = response.choices[0].message.content
            except Exception as exc:
                st.error(f"Generation failed: {exc}")
                st.stop()

            try:
                guidance = json.loads(content)
            except Exception:
                guidance = {
                    "wonder_whisper": content,
                    "steps": [],
                    "parent_prompt": "",
                    "quiet_moment": "",
                }

            st.subheader("Wonder Whisper")
            st.write(guidance.get("wonder_whisper", ""))
            st.subheader("Do-Together Steps")
            for step in guidance.get("steps", [])[:3]:
                st.write(f"- {step}")
            st.subheader("Parent Prompt")
            st.write(guidance.get("parent_prompt", ""))
            st.subheader("Quiet Moment")
            st.write(guidance.get("quiet_moment", ""))

            save_learning_session(
                session_id=str(uuid.uuid4()),
                family_id=family_id,
                kid_interest=interest,
                session_type="spark",
                ai_guidance=guidance,
                parent_notes=notes,
                progress_level=1,
                duration_sec=int(time.time() - start),
            )
            invalidate_family_caches()
            st.success("Session saved to your Snowflake learning log.")

    with col_right:
        st.markdown("### Progress Galaxy")
        rows = cached_interest_progress(family_id) or []
        if not rows:
            st.caption("Complete your first ritual to see your galaxy grow.")
        else:
            for row in rows:
                st.write(f"**{row['kid_interest']}** — lvl {round(row['avg_level'], 1)} · {row['sessions_completed']} sessions")
                last_seen = row.get("last_seen")
                try:
                    last_seen = last_seen.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass
                st.caption(f"Last: {last_seen}")


def main() -> None:
    st.set_page_config(
        page_title=APP_NAME,
        page_icon="🌙",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    if SNOWFLAKE_INIT_ERROR:
        st.error("Snowflake credentials are still missing or unreadable.")
        status = snowflake_config_status()
        missing = [k for k, ok in status.items() if not ok]
        if status:
            st.caption("Detected keys (True means found):")
            st.json(status)
        if missing:
            st.warning(
                "Add these keys to this app's Secrets (flat or [snowflake] group), then redeploy: "
                + ", ".join(missing)
            )
        st.stop()
    if not st.session_state.get("app_initialized"):
        with st.spinner("Waking up The Silent Room…"):
            ensure_app_initialized()
    else:
        ensure_app_initialized()

    checkout_status = handle_checkout_redirect()
    ensure_supabase_access()
    initialize_state()
    profile = st.session_state.get("supabase_profile")
    render_checkout_notice(checkout_status, profile)
    render_sidebar()
    ensure_app_initialized()
    if st.session_state.pop("just_logged_in", False):
        st.rerun()
    portal_url = st.session_state.pop("portal_url", None)
    if portal_url:
        st.success("Opening customer portal…")
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url={portal_url}" />',
            unsafe_allow_html=True,
        )

    points = cached_points_total()
    streak = cached_streak_length()

    icon_path = APP_ROOT / "icon.png"
    top_left, top_right = st.columns([1, 3], gap="large")
    with top_left:
        if icon_path.exists():
            st.image(str(icon_path), use_container_width=True)
    with top_right:
        hero_line = random.choice([
            "Hello, Young Innovator.",
            "Online. Ready to explore.",
            "Systems check: Curiosity at 100%.",
        ])
        st.markdown(
            f"""
<div class="nc-card hero">
  <h2 style="margin-bottom: 6px;">🪐 {hero_line}</h2>
  <p style="font-size: 1.05rem;">{escape(st.session_state.greeting)}</p>
    <div class="nc-pill-row">
    <span class="nc-pill">🏆 Points: {points}</span>
    <span class="nc-pill">🔥 Streak: {streak} days</span>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
        st.caption(
            "21 quiet minutes to breathe, listen, and rediscover the world together—curiosity, kindness, and calm in one ritual."
        )

    profile = st.session_state.get("supabase_profile")
    api_key = st.secrets.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY"))
    if not api_key:
        st.error("Add your OPENAI_API_KEY to .streamlit/secrets.toml or export it in the environment.")
        return

    client = get_openai_client_cached(api_key)

    st.session_state.setdefault("active_tab", NAV_TABS[0])
    st.markdown(
        """
        <style>
        div[data-testid="stSegmentedControl"] > div {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 0.5rem;
        }
        div[data-testid="stSegmentedControl"] button {
            font-size: 1.05rem !important;
            font-weight: 700 !important;
            padding: 10px 18px !important;
            border-radius: 999px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    default_tab = st.session_state["active_tab"]
    try:
        default_index = NAV_TABS.index(default_tab)
    except ValueError:
        default_index = 0
    selected_tab = st.segmented_control(
        "Navigate",
        options=NAV_TABS,
        default=NAV_TABS[default_index],
        label_visibility="collapsed",
        key="nav_selector",
    )
    selected_tab = selected_tab or NAV_TABS[default_index]
    st.session_state["active_tab"] = selected_tab

    if selected_tab == "Coach":
        render_hero_profile(profile)
        render_mission_week()
        render_coach_tab(client, profile, api_key)
    elif selected_tab == "Knowledge Hub":
        render_knowledge_hub()
    else:
        render_learning_lab_tab(api_key)


if __name__ == "__main__":
    main()
