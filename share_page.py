import os
from typing import Optional

import streamlit as st

from content_feed import load_feed

st.set_page_config(page_title="Silent Room Sharing", page_icon="🌙", layout="centered")

feed = load_feed()
slug = st.query_params.get("post") if hasattr(st, "query_params") else None
if isinstance(slug, list):
    slug = slug[0]
elif not slug:
    slug = st.experimental_get_query_params().get("post", [None])[0]

post: Optional[dict] = next((item for item in feed if item.get("slug") == slug), None)

if not post:
    st.error("Shared post not found.")
    st.stop()

app_base_url = st.secrets.get("APP_BASE_URL", os.getenv("APP_BASE_URL", "")).rstrip("/")
canonical_url = f"{app_base_url}?post={slug}" if app_base_url else f"?post={slug}"
image_url = (post.get("image_urls") or [None])[0]

og_tags = f"""
<meta property="og:title" content="{post['title']}" />
<meta property="og:type" content="article" />
<meta property="og:url" content="{canonical_url}" />
<meta property="og:description" content="{post.get('body','')[:140]}" />
"""
if image_url:
    og_tags += f'<meta property="og:image" content="{image_url}" />'

st.markdown(f"<head>{og_tags}</head>", unsafe_allow_html=True)

if image_url:
    st.image(image_url, use_container_width=True)

st.markdown(f"### {post['title']}")
st.markdown(post.get("body") or "", unsafe_allow_html=True)
if post.get("resource_link"):
    st.markdown(f"[🔗 Read more]({post['resource_link']})")
