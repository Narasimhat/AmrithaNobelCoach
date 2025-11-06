import base64
import datetime
import hashlib
import io
import json
import os
import random
import re
import tempfile
import requests
from html import escape
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from audio_recorder_streamlit import audio_recorder
from supabase import Client, create_client
from openai import OpenAI

from recommender import recommend
from db_utils import (
    add_points,
    add_user_mission,
    count,
    complete_user_mission,
    init_db,
    log_health,
    log_mission,
    mark_open_today,
    mission_tag_counts,
    recent_diary,
    recent_missions,
    list_user_missions,
    save_diary,
    streak_days,
    time_series_points,
    total_points,
    last_mission_date,
    recent_tag_counts,
    weekly_summary,
)

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
PIN_FILE = DATA_DIR / "parent_pin.txt"
DEFAULT_PIN = "2580"

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
SUPABASE_BYPASS = (get_config("SUPABASE_BYPASS", "") or "").lower() in {"1", "true", "yes"}
STRIPE_PRICE_ID_NO_TRIAL = get_config("STRIPE_PRICE_ID_NO_TRIAL")


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
        "Your Nobel Coach account needs an active subscription. Start the free month or manage billing below."
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
        st.success("Opening checkout in a new tab…")
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url={checkout_url}" />',
            unsafe_allow_html=True,
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
    status = (profile.get("subscription_status") or "").lower()
    trial_ends_at = parse_timestamp(profile.get("trial_ends_at"))
    now = datetime.datetime.now(datetime.timezone.utc)
    if status in {"active", "trialing"}:
        return client
    if trial_ends_at and trial_ends_at > now:
        return client
    render_subscription_cta(profile, st.session_state.get("checkout_status"))
    st.stop()
    return client

SYSTEM_PROMPT = """
You are "Nobel Coach," a joyful, rigorous mentor for a 9-year-old scientist (Amritha).
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
    "🚀 Captain Amritha, your Nobel Coach is fueled and ready!",
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
    ("Nobel Peace Laureates", "Kindness wins. Find a way to reduce conflict or calm hearts around you."),
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
    "Nobel Peace Laureates": "Planet",
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
    "You’re on a Nobel path—every step like this sends ripples of good."
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


init_db()
mark_open_today()

try:
    st.markdown('<style>' + open('styles.css').read() + '</style>', unsafe_allow_html=True)
except FileNotFoundError:
    pass

if "singularity" not in st.session_state:
    st.session_state["singularity"] = True

with st.sidebar:
    st.markdown("### 🪐 Singularity")
    st.session_state["singularity"] = st.toggle(
        "Enable Singularity Mode", value=st.session_state["singularity"]
    )

if st.session_state["singularity"] and os.path.exists("singularity.css"):
    st.markdown('<style>' + open('singularity.css').read() + '</style>', unsafe_allow_html=True)


def add_bg(image_path: Path) -> None:
    if not image_path.exists():
        return
    data = image_path.read_bytes()
    encoded = base64.b64encode(data).decode()
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


def ensure_pin_file() -> None:
    if not PIN_FILE.exists():
        PIN_FILE.write_text(DEFAULT_PIN, encoding="utf-8")


def read_parent_pin() -> str:
    ensure_pin_file()
    return PIN_FILE.read_text(encoding="utf-8").strip()


def update_parent_pin(new_pin: str) -> None:
    PIN_FILE.write_text(new_pin.strip(), encoding="utf-8")


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
    st.session_state.setdefault("prefilled_voice", "")


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

    points = total_points()
    streak = streak_days()
    missions_done = count("missions")

    tag_counts = recent_tag_counts()
    st.session_state["tag_counts"] = tag_counts

    col_points, col_streak = st.sidebar.columns(2)
    with col_points:
        st.metric("🏆 Points", points)
    with col_streak:
        st.metric("🔥 Streak", streak)
    st.sidebar.metric("🎯 Missions", missions_done)
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

    st.sidebar.markdown("### Quick Wins")
    mission_tag = MODE_TO_TAG.get(st.session_state.mode, "Curiosity")
    if st.sidebar.button("🎯 Mark Today’s Mission Done", use_container_width=True):
        today = datetime.date.today().isoformat()
        log_mission(today, st.session_state.mode, st.session_state.mission)
        add_points(10, "mission_done")
        label = POINT_LABEL_BY_TAG.get(mission_tag, "points")
        message = celebration_for(mission_tag)
        st.sidebar.success(f"{message} (+10 {label}!)")
        st.balloons()
    if st.sidebar.button("🤝 I did a Kindness Act", use_container_width=True):
        add_points(5, "kindness_act")
        message = celebration_for("Kindness")
        label = POINT_LABEL_BY_TAG.get("Kindness", "points")
        st.sidebar.success(f"{message} (+5 {label}!)")
        st.balloons()
    if st.sidebar.button("🌍 I did a Planet Act", use_container_width=True):
        add_points(5, "planet_act")
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
    health_tip = targeted_choice("Health", HEALTH_TIPS, tag_counts)
    kindness_tip = targeted_choice("Kindness", KINDNESS_CHALLENGES, tag_counts)
    earth_tip = targeted_choice("Planet", EARTH_PROMISES, tag_counts, fallback="Curiosity")
    st.session_state.health_tip = health_tip
    st.session_state.kindness = kindness_tip
    st.session_state.earth_tip = earth_tip

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

    st.sidebar.markdown("## 🌱 Daily Flourish")
    st.sidebar.info(f"💓 Health reminder: {health_tip}")
    st.sidebar.info(f"🌍 Earth promise: {earth_tip}")
    st.sidebar.info(f"🤝 Kindness challenge: {kindness_tip}")

    st.sidebar.markdown("### 🌿 Health Boosters")
    if st.sidebar.button("🥤 + Water", use_container_width=True):
        log_health(water=1)
        add_points(1, "water")
        label = POINT_LABEL_BY_TAG.get("Health", "points")
        st.sidebar.success(f"{celebration_for('Health')} (+1 {label}!)")
    if st.sidebar.button("🫁 + 5 Calm Breaths", use_container_width=True):
        log_health(breaths=5)
        add_points(2, "breaths")
        label = POINT_LABEL_BY_TAG.get("Health", "points")
        st.sidebar.success(f"{celebration_for('Health')} (+2 {label}!)")
    if st.sidebar.button("🚶 + 2 min Move", use_container_width=True):
        log_health(moves=2)
        add_points(2, "moves")
        label = POINT_LABEL_BY_TAG.get("Health", "points")
        st.sidebar.success(f"{celebration_for('Health')} (+2 {label}!)")

    legend_title, legend_story = choose_legend_story(tag_counts)
    st.session_state.legend = (legend_title, legend_story)
    st.sidebar.markdown("## 🪷 Wisdom Spotlight")
    st.sidebar.markdown(f"**{legend_title}**")
    st.sidebar.write(legend_story)

    if st.sidebar.button("🔁 Refresh tips", use_container_width=True):
        st.session_state.health_tip = random.choice(HEALTH_TIPS)
        st.session_state.kindness = random.choice(KINDNESS_CHALLENGES)
        st.session_state.earth_tip = random.choice(EARTH_PROMISES)
        st.session_state.legend = random.choice(LEGEND_SPOTLIGHTS)
        st.sidebar.success("New inspiration delivered!")

    if st.sidebar.button("🧹 Start fresh chat", use_container_width=True):
        reset_conversation()
        st.rerun()


def render_coach_tab(client: OpenAI) -> None:
    add_bg(BACKGROUND_IMAGES.get("coach", Path()))

    tag_counts = st.session_state.get("tag_counts", {})

    st.markdown("## 🧠 Nobel Coach")
    st.markdown('<div class="nc-chips">', unsafe_allow_html=True)
    chip_cols = st.columns(len(MODE_OPTIONS))
    for col, (mode_name, mode_emoji, _) in zip(chip_cols, MODE_OPTIONS):
        with col:
            if st.button(f"{mode_emoji} {mode_name}", key=f"chip_{mode_name}", use_container_width=True):
                st.session_state.mode = mode_name
                inferred_tag = MODE_TO_TAG.get(mode_name, st.session_state.get("inspiration_tag", "Curiosity"))
                st.session_state["inspiration_tag"] = inferred_tag
                st.session_state["inspiration"] = targeted_choice(
                    inferred_tag,
                    TAGGED_INSPIRATIONS.get(inferred_tag, INSPIRATION_SNIPPETS),
                    tag_counts,
                )
            active = "active" if st.session_state.mode == mode_name else ""
            st.markdown(f'<span class="nc-chip {active}"></span>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    name, emoji, description = next((opt for opt in MODE_OPTIONS if opt[0] == st.session_state.mode), MODE_OPTIONS[0])

    st.success(f"{emoji} {name} mode: {description}")

    col_main, col_side = st.columns([3, 1])
    with col_main:
        st.info(f"🎯 **Today's Mission:** {st.session_state.mission}")
    with col_side:
        inspire_tag = None
        if tag_counts:
            inspire_tag = max(tag_counts.items(), key=lambda x: x[1])[0]
        if inspire_tag not in TAGGED_INSPIRATIONS:
            inspire_tag = "Curiosity"
        if inspire_tag:
            st.session_state.setdefault("inspiration_tag", inspire_tag)
            if st.session_state.get("inspiration_tag") != inspire_tag:
                st.session_state["inspiration_tag"] = inspire_tag
                st.session_state["inspiration"] = targeted_choice(
                    inspire_tag,
                    TAGGED_INSPIRATIONS.get(inspire_tag, INSPIRATION_SNIPPETS),
                    tag_counts,
                )
        if st.button("🔭 Inspire Me", use_container_width=True):
            source_tag = st.session_state.get("inspiration_tag", inspire_tag or "Curiosity")
            st.session_state["inspiration"] = targeted_choice(
                source_tag,
                TAGGED_INSPIRATIONS.get(source_tag, INSPIRATION_SNIPPETS),
                tag_counts,
            )
        inspiration_message = st.session_state.get(
            "inspiration",
            targeted_choice(
                inspire_tag or "Curiosity",
                TAGGED_INSPIRATIONS.get(inspire_tag or "Curiosity", INSPIRATION_SNIPPETS),
                tag_counts,
            ),
        )
        st.markdown(f"🪄 {inspiration_message}")
        st.session_state["inspiration"] = inspiration_message

    audio_bytes: Optional[bytes] = None
    with st.expander("🎤 Prefer to talk?", expanded=False):
        st.markdown(
            '<div class="nc-card" style="margin-bottom:0;padding:14px 16px;">'
            "<strong>Hold the mic button</strong> and speak naturally—your coach will turn it into text."
            "</div>",
            unsafe_allow_html=True,
        )
        audio_bytes = audio_recorder(text="🎙️ Hold to record", pause_threshold=2.0)
        if st.session_state.get("prefilled_voice"):
            st.caption(f'Last transcript: “{st.session_state["prefilled_voice"]}”')

    if audio_bytes:
        voice_hash = hashlib.md5(audio_bytes).hexdigest()
        if st.session_state.get("voice_hash") != voice_hash:
            st.session_state["voice_hash"] = voice_hash
            with st.spinner("Transcribing your question…"):
                transcript = transcribe_audio(audio_bytes, client)
            if transcript:
                st.session_state["prefilled_voice"] = transcript
                st.success(f"Coach heard: “{transcript}”")
            else:
                st.warning("Hmm, I couldn't catch that—try speaking a little clearer and try again!")
    st.divider()
    st.markdown("### 📔 Conversation Log")
    chat_messages = st.session_state.history[1:]
    st.markdown('<div class="nc-chat-window">', unsafe_allow_html=True)
    if not chat_messages:
        st.info("Your notebook is blank. Ask a question or share a mission first!")
    else:
        for message in chat_messages:
            role = message["role"]
            speaker = "assistant" if role == "assistant" else "user"
            avatar = "🧠" if speaker == "assistant" else "🙂"
            with st.chat_message(speaker, avatar=avatar):
                st.markdown(message["content"])
    st.markdown("</div>", unsafe_allow_html=True)

    placeholder = f"{emoji} {name} mode: share your question, idea, or discovery."
    user_input = st.chat_input(placeholder=placeholder)
    pending_input = user_input
    if st.session_state.get("prefilled_voice"):
        st.caption("Transcribed voice note ready to send.")
        col_send, col_clear = st.columns(2)
        with col_send:
            if st.button("Send transcription", use_container_width=True, key="send_transcript_btn"):
                pending_input = st.session_state["prefilled_voice"]
                st.session_state["prefilled_voice"] = ""
        with col_clear:
            if st.button("Discard transcription", use_container_width=True, key="discard_transcript_btn"):
                st.session_state["prefilled_voice"] = ""
                pending_input = None

    if pending_input and str(pending_input).strip():
        content = str(pending_input).strip()
        st.session_state["prefilled_voice"] = ""
        st.session_state.history.append({"role": "user", "content": f"[Mode: {name}] {content}"})
        try:
            with st.spinner("Your Nobel Coach is thinking deeply…"):
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=st.session_state.history,
                    temperature=0.6,
                )
            answer = response.choices[0].message.content
            st.session_state.history.append({"role": "assistant", "content": answer})
            st.rerun()
        except Exception:
            st.error("Coach ran into a glitch. Check your connection and try again.")
            st.session_state.history.pop()

    with st.expander("➕ Turn this into a mission", expanded=False):
        last_answer = ""
        for msg in reversed(st.session_state.history):
            if msg["role"] == "assistant":
                last_answer = msg.get("content", "")
                break

        default_title = ""
        default_details = ""
        if last_answer:
            lines = [line for line in re.split(r"\r?\n", last_answer.strip()) if line.strip()]
            if lines:
                snippet = lines[0]
                default_title = (snippet[:60] + "…") if len(snippet) > 60 else snippet
            default_details = last_answer[:500]

        col_title, col_tag = st.columns([3, 1])
        mission_title = col_title.text_input("Mission title", value=default_title)
        mission_tag = col_tag.selectbox("Tag", ["Planet", "Health", "Build", "Think", "Story", "Art", "Logic"], index=2)
        mission_details = st.text_area("Details (optional)", value=default_details)

        if st.button("Save to My Missions ✅", use_container_width=True):
            add_user_mission(mission_title.strip() or "New Mission", mission_details.strip(), mission_tag)
            add_points(5, "mission_create")
            st.toast("Saved to My Missions. Finish it later from the Missions tab!")
            st.balloons()

    st.divider()
    col1, col2 = st.columns(2)
    if col1.button("🎖️ Celebrate today's effort", use_container_width=True):
        add_points(5, "celebrate")
        label = POINT_LABEL_BY_TAG.get("Curiosity", "points")
        st.success(f"{celebration_for('Curiosity')} (+5 {label}!)")
        st.balloons()
    if col2.button("🌟 Refresh mission & greeting", use_container_width=True):
        refresh_daily_cards()
        st.rerun()


def render_gallery_tab() -> None:
    add_bg(BACKGROUND_IMAGES.get("gallery", Path()))

    st.markdown("## 🖼️ Experiment Gallery")

    summaries = list(recent_diary(24))
    if summaries:
        st.markdown("### Diary Highlights")
        for day, question, found in summaries:
            st.markdown(f"**{day}** — {question or '(no question recorded)'}")
            if found:
                st.caption(found[:160])
    else:
        st.info("No diary highlights yet. Save a discovery to build your wall of science.")

    st.markdown("### Conversation Library")
    diary_files = sorted(DIARY_DIR.glob("diary_*.json"), reverse=True)
    if not diary_files:
        st.info("No saved conversations yet. Use the sidebar diary save button first.")
        return

    cols = st.columns(3)
    for idx, diary_path in enumerate(diary_files[:24]):
        with diary_path.open(encoding="utf-8") as handle:
            entries = json.load(handle)
        first_user = next((m["content"] for m in entries if m["role"] == "user"), "(No question yet)")
        first_answer = next((m["content"] for m in entries if m["role"] == "assistant"), "(No answer yet)")
        preview = first_answer.split("\n")[0][:140]
        with cols[idx % 3]:
            title = diary_path.stem.replace("diary_", "").replace("_", " ")
            st.markdown(f"**{title}**")
            st.caption(first_user)
            st.write("— " + preview)
            with st.expander("Open entry"):
                for message in entries[1:]:
                    role = "Coach" if message["role"] == "assistant" else "You"
                    st.markdown(f"**{role}:** {message['content']}")


def render_missions_tab() -> None:
    add_bg(BACKGROUND_IMAGES.get("mission_cards", Path()))

    st.markdown('<div class=\"nc-card\">', unsafe_allow_html=True)
    st.markdown("## 📋 My Missions (from Coach)")
    rows = list_user_missions(status="todo", limit=50)
    if not rows:
        st.caption("No saved missions yet. Convert any Coach answer into a mission!")
    else:
        for mid, ts, title, details, tag, status in rows:
            with st.expander(f"✅ {title} — [{tag}]"):
                st.caption(f"Created: {ts}")
                if details:
                    st.write(details)
                if st.button(f"Mark Done (#{mid})", key=f"mission_done_{mid}"):
                    complete_user_mission(mid)
                    add_points(10, "mission_done")
                    st.success("Mission completed! +10 points")
                    st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

def render_parent_tab() -> None:
    add_bg(BACKGROUND_IMAGES.get("parents", Path()))

    st.markdown("## 👪 Parents’ Dashboard (Locked)")
    pin_value = read_parent_pin()
    pin_try = st.text_input("Enter parent PIN", type="password")
    if pin_try != pin_value:
        st.stop()

    st.success("Welcome! You now have guardian access.")

    st.subheader("Usage & Progress")
    st.write(f"- Points: **{total_points()}**")
    st.write(f"- Streak days: **{streak_days()}**")
    st.write(f"- Missions completed: **{count('missions')}**")
    st.write(f"- Kindness acts: **{count('kindness')}**")
    st.write(f"- Planet acts: **{count('planet')}**")

    st.subheader("Points Over Time")
    rows = list(time_series_points())
    if rows:
        df = pd.DataFrame(rows, columns=["day", "points"])
        df["day"] = pd.to_datetime(df["day"])
        df = df.set_index("day")
        st.line_chart(df["points"], height=240)
    else:
        st.info("No points yet to chart. Encourage a mission or two!")

    tag_counts = mission_tag_counts()
    last_mission = last_mission_date()
    idle_days = (datetime.date.today() - last_mission).days if last_mission else 999
    profile_for_recs = {
        "tags_counts": tag_counts,
        "streak": streak_days(),
        "recent_idle_days": idle_days,
        "last_completed_tags": recent_missions(5),
    }
    recs = recommend(profile_for_recs)
    if recs:
        st.markdown('<div class="nc-card hero">', unsafe_allow_html=True)
        st.markdown("### 🧭 Suggested Next Steps")
        for s in recs:
            st.info(f"• {s['type']} → {s['id']} — {s['reason']}")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("### 📈 Suggestions")
    st.markdown("- Read diary entries together and ask for teach-back moments.")
    st.markdown("- Celebrate badges with small rituals (family high-five, victory song).")
    st.markdown("- Encourage real-world experiments—keep safety gear ready.")

    st.markdown("### 🔐 Update PIN")
    new_pin = st.text_input("New PIN", type="password")
    if st.button("Update PIN"):
        if new_pin.strip():
            update_parent_pin(new_pin)
            st.success("PIN updated. Remember the new code!")
        else:
            st.warning("PIN cannot be empty.")


def main() -> None:
    st.set_page_config(
        page_title="Amritha's Nobel Coach",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    checkout_status = handle_checkout_redirect()
    ensure_supabase_access()
    initialize_state()
    profile = st.session_state.get("supabase_profile")
    render_checkout_notice(checkout_status, profile)
    render_sidebar()
    portal_url = st.session_state.pop("portal_url", None)
    if portal_url:
        st.success("Opening customer portal…")
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url={portal_url}" />',
            unsafe_allow_html=True,
        )

    points = total_points()
    streak = streak_days()
    missions_this_week = count("missions")

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
    <span class="nc-pill">🌱 Missions this week: {missions_this_week}</span>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
        st.caption(
            "Together we learn by doing, care for health, protect nature, and honor wisdom from Ramayana, Mahabharata, and modern science."
        )

    render_hero_profile(profile)


    cards = [
        ("💓 Health Booster", st.session_state.get("health_tip", "Listen to your body.")),
        ("🌍 Planet Promise", st.session_state.get("earth_tip", "Do one tiny thing for the planet today.")),
        ("🤝 Kindness Mission", st.session_state.get("kindness", "Offer a smile or kind word.")),
        ("🪄 Inspire Me", st.session_state.get("inspiration", "Find a fact that makes you say WOW.")),
    ]
    card_cols = st.columns(len(cards), gap="large")
    for col, (title, body) in zip(card_cols, cards):
        with col:
            st.markdown(
                f"""
<div class="nc-card mini">
  <h4>{title}</h4>
  <p>{escape(body or '')}</p>
</div>
""",
                unsafe_allow_html=True,
            )

    week = weekly_summary(7)
    st.markdown("#### 🗓️ Mission Week")
    today = datetime.date.today()
    if week:
        st.markdown('<div class=\"nc-week-grid\">', unsafe_allow_html=True)
        week_cols = st.columns(len(week), gap="small")
        for col, day in zip(week_cols, week):
            badges = []
            if day['missions']:
                label = 'mission' if day['missions'] == 1 else 'missions'
                badges.append(f"🌱 {day['missions']} {label}")
            if day['kindness']:
                badges.append('🤝 Kindness')
            if day['planet']:
                badges.append('🌍 Planet')
            if day['health']:
                badges.append('💓 Health')
            if day['points'] and day['points'] > 0:
                badges.append(f"🏆 +{day['points']} pts")
            summary = '<br>'.join(badges) if badges else 'Plan a tiny win today!'
            classes = ['nc-day-card']
            if day['date'] == today:
                classes.append('today')
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
        st.markdown('</div>', unsafe_allow_html=True)

    tag_counts = mission_tag_counts()
    last_mission = last_mission_date()
    idle_days = (datetime.date.today() - last_mission).days if last_mission else 999
    profile = {
        "tags_counts": tag_counts,
        "streak": streak,
        "recent_idle_days": idle_days,
        "last_completed_tags": recent_missions(5),
    }
    suggestions = recommend(profile)
    if suggestions:
        with st.expander("🧭 Coach Suggestions", expanded=False):
            for suggestion in suggestions:
                st.info(f"{suggestion['type']} • {suggestion['id']} — {suggestion['reason']}")

    api_key = st.secrets.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY"))
    if not api_key:
        st.error("Add your OPENAI_API_KEY to .streamlit/secrets.toml or export it in the environment.")
        return

    client = OpenAI(api_key=api_key)

    coach_tab, gallery_tab, missions_tab, parents_tab = st.tabs([
        "Coach",
        "Gallery",
        "Missions",
        "Parents",
    ])

    with coach_tab:
        render_coach_tab(client)
    with gallery_tab:
        render_gallery_tab()
    with missions_tab:
        render_missions_tab()
    with parents_tab:
        render_parent_tab()


if __name__ == "__main__":
    main()
