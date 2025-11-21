#!/usr/bin/env python3
"""
Generate daily Knowledge Hub post using OpenAI and store in Supabase.
Designed to run via GitHub Actions on a daily schedule.
"""

import os
import sys
from datetime import datetime
from openai import OpenAI
from supabase import create_client, Client

# Topics for 9-year-old Amritha (rotates through these)
TOPICS = [
    "Why do stars twinkle? Explain light refraction in a fun way",
    "How do plants talk to each other? Teach about mycorrhizal networks",
    "What makes a rainbow appear? Explore light and water science",
    "Why is the ocean salty? Journey through water cycles",
    "How do birds know where to migrate? Discuss navigation and instinct",
    "What is electricity and how does it power our homes?",
    "Why do seasons change? Explain Earth's tilt and orbit",
    "How do airplanes fly? Introduce aerodynamics simply",
    "What makes volcanoes erupt? Explore plate tectonics",
    "Why do we dream? Simple neuroscience for kids",
    "How does the internet work? Explain data and connections",
    "What are black holes? Make space physics accessible",
    "Why is kindness important? Discuss empathy and community",
    "How can we help the planet? Practical environmental actions",
    "What is creativity and how can we practice it?",
]

SYSTEM_PROMPT = """You are a creative educator for The Silent Room app. Create engaging, age-appropriate content for 9-year-old children like Amritha who are curious, creative, and care about the planet.

Your posts should:
- Be 200-300 words
- Use simple language but don't talk down
- Include a fascinating fact or story
- Ask a thought-provoking question at the end
- Inspire curiosity, kindness, or planet consciousness
- Be warm and encouraging in tone

Format your response as JSON with these fields:
{
  "title": "Catchy title (max 60 chars)",
  "content": "Main educational content (200-300 words)",
  "category": "one of: Science|Nature|Space|Technology|Kindness|Planet|Creativity",
  "emoji": "single relevant emoji",
  "question": "Thought-provoking question to end with"
}"""


def get_today_topic():
    """Get today's topic based on day of year."""
    day_of_year = datetime.now().timetuple().tm_yday
    return TOPICS[day_of_year % len(TOPICS)]


def generate_post_content(openai_client: OpenAI, topic: str) -> dict:
    """Generate post content using OpenAI."""
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Create today's Knowledge Hub post about: {topic}"}
        ],
        temperature=0.8,
        max_tokens=600,
    )
    
    content = response.choices[0].message.content
    
    # Parse JSON response
    import json
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Fallback if OpenAI doesn't return valid JSON
        return {
            "title": "Today's Discovery",
            "content": content,
            "category": "Science",
            "emoji": "🌟",
            "question": "What do you think about this?"
        }


def save_to_supabase(supabase: Client, post: dict) -> dict:
    """Save post to Supabase posts table."""
    result = supabase.table("posts").insert({
        "title": post["title"],
        "content": f"{post['emoji']} {post['content']}\n\n💭 {post['question']}",
        "category": post["category"],
        "author": "The Silent Room Coach",
        "published_at": datetime.now().isoformat(),
        "is_featured": True,
    }).execute()
    
    return result.data[0] if result.data else None


def main():
    """Main execution function."""
    # Get environment variables
    openai_api_key = os.getenv("OPENAI_API_KEY")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not all([openai_api_key, supabase_url, supabase_key]):
        print("❌ Error: Missing required environment variables")
        print("Required: OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY")
        sys.exit(1)
    
    # Initialize clients
    openai_client = OpenAI(api_key=openai_api_key)
    supabase = create_client(supabase_url, supabase_key)
    
    # Get today's topic
    topic = get_today_topic()
    print(f"📚 Generating post for topic: {topic}")
    
    # Generate content
    try:
        post = generate_post_content(openai_client, topic)
        print(f"✅ Generated post: {post['title']}")
    except Exception as e:
        print(f"❌ Error generating content: {e}")
        sys.exit(1)
    
    # Save to Supabase
    try:
        saved_post = save_to_supabase(supabase, post)
        if saved_post:
            print(f"✅ Post saved to Supabase (ID: {saved_post.get('id')})")
            print(f"📝 Title: {post['title']}")
            print(f"📂 Category: {post['category']}")
        else:
            print("⚠️ Warning: Post may not have been saved correctly")
    except Exception as e:
        print(f"❌ Error saving to Supabase: {e}")
        sys.exit(1)
    
    print("🎉 Daily post generation complete!")


if __name__ == "__main__":
    main()
