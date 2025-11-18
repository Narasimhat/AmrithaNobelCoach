"""
Streamlit utility to upload Knowledge Hub media to Supabase Storage and archive
articles in Snowflake. Run with: `streamlit run upload_module.py`.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import snowflake.connector
import streamlit as st
from supabase import Client, create_client


@st.cache_resource(show_spinner=False)
def get_supabase_client() -> Client:
    supabase_cfg = st.secrets.get("supabase", {})
    url = supabase_cfg.get("url")
    key = supabase_cfg.get("service_role_key") or supabase_cfg.get("anon_key")
    if not url or not key:
        raise RuntimeError("Missing Supabase configuration in secrets.toml")
    return create_client(url, key)


@st.cache_resource(show_spinner=False)
def get_snowflake_conn():
    snow_cfg = st.secrets.get("snowflake", {})
    required = ["user", "password", "account", "warehouse", "database", "schema"]
    missing = [field for field in required if field not in snow_cfg]
    if missing:
        raise RuntimeError(f"Missing Snowflake secrets: {', '.join(missing)}")
    return snowflake.connector.connect(
        user=snow_cfg["user"],
        password=snow_cfg["password"],
        account=snow_cfg["account"],
        warehouse=snow_cfg["warehouse"],
        database=snow_cfg["database"],
        schema=snow_cfg["schema"],
        role=snow_cfg.get("role", "ACCOUNTADMIN"),
    )


def upload_image_to_supabase(file, bucket_name: str, signed: bool = False) -> str:
    supabase = get_supabase_client()
    file_id = f"{uuid.uuid4()}_{file.name}"
    supabase.storage.from_(bucket_name).upload(
        file_id,
        file.read(),
        file_options={"content-type": file.type or "application/octet-stream"},
    )
    if signed:
        signed_url = supabase.storage.from_(bucket_name).create_signed_url(
            file_id, expires_in=60 * 60 * 24 * 365
        )
        return signed_url["signedURL"]
    return supabase.storage.from_(bucket_name).get_public_url(file_id)


def save_article_to_snowflake(title: str, content: str) -> None:
    if not title.strip() and not content.strip():
        st.warning("Write something before saving.")
        return
    conn = get_snowflake_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO articles (title, content, created_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP())
            """,
            (
                title.strip() or f"Untitled — {datetime.utcnow():%Y-%m-%d}",
                content.strip(),
            ),
        )
    conn.commit()
    st.success("Article saved to Snowflake!")


def main() -> None:
    st.set_page_config(page_title="Knowledge Hub Uploader", page_icon="📝", layout="wide")
    st.title("✦ Knowledge Hub — Article Uploader")

    bucket_name = st.secrets.get("supabase", {}).get("bucket_name", "knowledge-hub")
    use_signed = st.toggle("Generate signed URLs", value=False)

    title = st.text_input("Article Title", placeholder="My amazing article…", key="article_writer_title")
    content = st.text_area(
        "Article body (Markdown supported)", height=400, key="article_writer_content"
    )

    uploaded_files = st.file_uploader(
        "Upload images", type=["png", "jpg", "jpeg", "gif", "webp"], accept_multiple_files=True
    )
    image_urls: list[str] = []

    if uploaded_files:
        with st.spinner("Uploading images to Supabase…"):
            for file in uploaded_files:
                url = upload_image_to_supabase(file, bucket_name, signed=use_signed)
                image_urls.append(url)
                st.image(url, width=120)
                st.code(f"![{file.name}]({url})", language="markdown")

    if image_urls and st.button("Append image links to article"):
        buff = st.session_state.get("article_writer_content", "")
        for idx, url in enumerate(image_urls, start=1):
            buff += f"\n\n![image {idx}]({url})"
        st.session_state["article_writer_content"] = buff
        st.rerun()

    if content:
        st.markdown("---")
        st.markdown("### Preview")
        st.markdown(content, unsafe_allow_html=True)

    if st.button("💾 Save Article", type="primary"):
        final_content = content
        if image_urls:
            final_content += "\n\n" + "\n\n".join(f"![uploaded image]({url})" for url in image_urls)
        save_article_to_snowflake(title, final_content)


if __name__ == "__main__":
    main()
