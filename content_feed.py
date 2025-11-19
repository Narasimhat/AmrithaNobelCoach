import os
import re
import uuid
from datetime import datetime
from functools import lru_cache
from typing import Dict, List, Optional

import streamlit as st
from supabase import Client, create_client

TABLE_NAME = "knowledge_feed"
DEFAULT_FEED: List[Dict[str, str]] = []


@lru_cache(maxsize=1)
def _get_supabase_client() -> Optional[Client]:
    cfg = st.secrets.get("supabase", {})
    url = cfg.get("url") or os.getenv("SUPABASE_URL")
    key = (
        cfg.get("service_role_key")
        or cfg.get("anon_key")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
    )
    if not url or not key:
        return None
    return create_client(url, key)


def _generate_slug(title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") if title else ""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    suffix = base or uuid.uuid4().hex[:6]
    return f"{timestamp}-{suffix}"


def load_feed() -> List[Dict[str, str]]:
    client = _get_supabase_client()
    if client is None:
        return DEFAULT_FEED
    try:
        response = (
            client.table(TABLE_NAME)
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
    except Exception:
        return DEFAULT_FEED
    rows = getattr(response, "data", []) or []
    feed: List[Dict[str, str]] = []
    for row in rows:
        slug = str(row.get("slug") or row.get("id") or _generate_slug(row.get("title", "")))
        feed.append(
            {
                "slug": slug,
                "title": row.get("title") or "",
                "summary": "",
                "body": row.get("body") or "",
                "tags": row.get("tags") or [],
                "cta": row.get("cta") or "",
                "zoom_link": row.get("zoom_link") or "",
                "resource_link": row.get("resource_link") or "",
                "posted_at": row.get("created_at") or row.get("updated_at") or "",
                "image_urls": row.get("image_urls") or [],
            }
        )
    return feed


def add_feed_entry(
    title: str,
    summary: str,
    body: str,
    tags: List[str],
    cta: str,
    zoom_link: str,
    resource_link: str,
    image_urls: Optional[List[str]] = None,
) -> None:
    client = _get_supabase_client()
    if client is None:
        return
    payload = {
        "title": title,
        "body": body,
        "resource_link": resource_link,
        "image_urls": image_urls or [],
    }
    try:
        client.table(TABLE_NAME).insert(payload).execute()
    except Exception as exc:
        st.error(f"Could not save post: {exc}")


def delete_feed_entry(slug: str) -> None:
    client = _get_supabase_client()
    if client is None:
        return
    try:
        client.table(TABLE_NAME).delete().eq("slug", slug).execute()
    except Exception as exc:
        st.error(f"Could not delete post: {exc}")
