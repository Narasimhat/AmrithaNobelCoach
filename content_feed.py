import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict

DATA_FILE = Path("data/content_feed.json")
DEFAULT_FEED: List[Dict[str, str]] = [
    {
        "slug": "20251105-silent-missions-live",
        "title": "Silent Missions Live",
        "summary": "Weekly Zoom circle where kids share discoveries and build kindness plans.",
        "body": "Bring your notebook and one question. Coach guides a 10‑minute project share, 5‑minute reflection, and a group kindness pledge.",
        "tags": ["Zoom", "Community"],
        "cta": "Join Wednesday 6pm CET",
        "zoom_link": "https://zoom.us/j/1234567890?pwd=silentroom",
        "resource_link": "",
        "posted_at": "2025-11-05",
    },
    {
        "slug": "20251104-calm-tech-toolkit",
        "title": "Calm-Tech Toolkit",
        "summary": "Printable exercises for breathing, curiosity prompts, and mindful tech breaks.",
        "body": "Download the Calm-Tech PDF pack with mini-meditations, science sparks, and unplugged missions for parents to facilitate.",
        "tags": ["Download", "Parents"],
        "cta": "Download toolkit",
        "zoom_link": "",
        "resource_link": "https://example.com/calm-tech-toolkit.pdf",
        "posted_at": "2025-11-04",
    },
    {
        "slug": "20251103-planet-guardians",
        "title": "Planet Guardians Lesson",
        "summary": "Self-paced lesson about micro-plastics, including an experiment video.",
        "body": "Watch the 7-minute explainer, then follow the checklist to build a mini water filter. Submit photos to earn the Planet badge.",
        "tags": ["Lesson", "Planet"],
        "cta": "Start lesson",
        "zoom_link": "",
        "resource_link": "https://example.com/planet-guardians",
        "posted_at": "2025-11-03",
    },
    {
        "slug": "20251102-parent-briefing",
        "title": "Parent Briefing – Month Startup",
        "summary": "Live briefing for parents outlining rituals, free tier limits, and progress metrics.",
        "body": "Coach walks through the 21-minute flow, answers Q&A, and shares how to translate chats into real-world practice.",
        "tags": ["Parents", "Zoom"],
        "cta": "Reserve seat",
        "zoom_link": "https://zoom.us/j/0987654321?pwd=parentcall",
        "resource_link": "",
        "posted_at": "2025-11-02",
    },
]


def _ensure_feed_file() -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        DATA_FILE.write_text(json.dumps(DEFAULT_FEED, indent=2))


def load_feed() -> List[Dict[str, str]]:
    _ensure_feed_file()
    try:
        feed = json.loads(DATA_FILE.read_text())
    except json.JSONDecodeError:
        feed = DEFAULT_FEED.copy()
    updated = False
    for item in feed:
        item.setdefault("tags", [])
        item.setdefault("posted_at", datetime.utcnow().date().isoformat())
        if not item.get("slug"):
            item["slug"] = _generate_slug(item.get("title", ""))
            updated = True
    if updated:
        save_feed(feed)
    return sorted(feed, key=lambda x: x.get("posted_at", ""), reverse=True)


def save_feed(feed: List[Dict[str, str]]) -> None:
    DATA_FILE.write_text(json.dumps(feed, indent=2))


def _generate_slug(title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") if title else ""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    suffix = base or uuid.uuid4().hex[:6]
    return f"{timestamp}-{suffix}"


def add_feed_entry(title: str, summary: str, body: str, tags: List[str], cta: str, zoom_link: str, resource_link: str) -> None:
    feed = load_feed()
    slug = _generate_slug(title)
    feed.insert(0, {
        "slug": slug,
        "title": title,
        "summary": summary,
        "body": body,
        "tags": tags,
        "cta": cta,
        "zoom_link": zoom_link,
        "resource_link": resource_link,
        "posted_at": datetime.utcnow().date().isoformat(),
    })
    save_feed(feed)
