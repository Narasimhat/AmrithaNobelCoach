import json
import uuid
import snowflake.connector

conn = snowflake.connector.connect(
    account='RXPBZWS-BL07714',
    user='ntelugu',
    password='84N+85A@16a***',
    warehouse='SR_WH',
    database='THESLIENTROOM',
    schema='PUBLIC'
)
cur = conn.cursor()
json_data = {
  "wonder_whisper": "Did you know that space is so big that there are billions of stars and planets? 🌌 Imagine traveling to a planet made of ice or a star that's much bigger than our Sun! What do you think is out there?",
  "steps": [
    "Create a simple model of the solar system with balls of different sizes.",
    "Look up at the night sky together and identify a planet or bright star.",
    "Make a space journal to draw / write daily learnings about space."
  ],
  "parent_prompt": "What is your favorite thing about space? Share it with Amritha!",
  "quiet_moment": "Take a deep breath and imagine floating gently through space."
}
cur.execute(
    """
    INSERT INTO learning_sessions
      (session_id, family_id, kid_interest, session_type, ai_guidance, progress_level, duration_sec)
    SELECT %s, %s, %s, %s, PARSE_JSON(%s), %s, %s
    """,
    (
        str(uuid.uuid4()),
        'fam_demo',
        'space',
        'spark',
        json.dumps(json_data, ensure_ascii=False),
        1,
        0,
    ),
)
conn.commit()
cur.close()
conn.close()
print('Inserted test session for fam_demo.')
