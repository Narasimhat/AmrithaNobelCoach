# Copilot Instructions for The Silent Room

## Project Overview
The Silent Room is a **Streamlit-based AI coaching app** for children (primary user: Amritha, age 9) that provides 21-minute guided learning rituals. The app combines Streamlit UI with Snowflake persistence, Supabase auth/subscriptions, OpenAI chat completion, and Stripe payments.

**Core Mission**: Foster curiosity, critical thinking, kindness, and planet consciousness through structured AI-mentored conversations.

## Architecture

### Three-Tier Structure
1. **Frontend**: Single Streamlit app (`app.py`, ~1300 LOC) with tab-based navigation (Coach, Knowledge Hub, Learning Sessions)
2. **Persistence**: Dual-database strategy
   - **Snowflake** (via `db_utils.py`): Primary data warehouse for points, missions, diary entries, child profiles, adventures, threads, messages
   - **Supabase**: Auth, subscription status, knowledge feed posts (`content_feed.py`)
3. **AI Layer**: OpenAI GPT-4o-mini via `silencegpt_api.py` with persona prompts from `silencegpt_prompt.py`

### Key Data Flows
- **Coach Chat**: User → `render_coach_tab()` → `chat_completion()` → Snowflake message storage → UI rerun
- **Subscriptions**: Stripe webhook → Supabase Edge Function → `profiles.subscription_status` update → Streamlit access check
- **Progress Tracking**: Action (ritual/kindness/planet) → `add_points()` + `log_mission()` → cached metrics refresh

## Critical Developer Workflows

### Local Development
```bash
# Setup
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."
export SNOWFLAKE_ACCOUNT="..." SNOWFLAKE_USER="..." # (see REQUIRED_VARS in db_utils.py)
export SUPABASE_URL="..." SUPABASE_ANON_KEY="..." SUPABASE_SERVICE_ROLE_KEY="..."

# Run
streamlit run app.py
```

### Testing Subscription Flow
- Set `SUPABASE_BYPASS=true` in secrets to skip auth during development
- Use `FREE_TIER_ENABLED=true` and `FREE_TIER_DAILY_MESSAGES=3` to test free tier limits
- Stripe test mode: deploy webhook to Supabase function, use Stripe CLI for local webhook testing

### Docker Deployment
```bash
docker build -t the-silent-room .
docker run -e OPENAI_API_KEY="..." -p 8501:8501 the-silent-room
```

### Database Migrations
- **Snowflake**: Tables auto-created by `init_db()` on first run (see `db_utils.py:104-225`)
- **Supabase**: Run `supabase_schema.sql` manually in SQL Editor; includes auth trigger for profile creation

## Project-Specific Conventions

### Caching Strategy
**Heavy use of Streamlit caching to avoid Snowflake query spam:**
```python
@st.cache_data(ttl=30)  # Short TTL for user-generated content
def cached_child_profiles(): return list_child_profiles()

@st.cache_data(ttl=60)  # Medium TTL for metrics
def cached_points_total(): return total_points()
```
**Pattern**: Every `db_utils` read function has a cached wrapper in `app.py`. Always call `cached_*` versions, not raw DB functions. Clear caches explicitly after mutations:
```python
add_points(5, "kindness_act")
invalidate_progress_caches()  # Clears points/streak/tags caches
```

### State Management
- **Session state keys**:
  - `silence_child_id`, `silence_project_id`, `silence_thread_id`: Current SilenceGPT context
  - `supabase_session`, `supabase_profile`: Auth state
  - `has_paid_access`, `free_tier_active`: Access control flags
  - `tag_counts`: Recent tag usage for adaptive content (legend stories, inspirations)
- **Never mutate state without `st.rerun()`** — Streamlit requires explicit reruns after state changes

### Points & Gamification
- **Points logic**: 15 pts for 21-min ritual, 5 pts for kindness/planet acts, logged via `add_points(delta, reason)`
- **Tags**: `Curiosity`, `Build`, `Think`, `Write`, `Share`, `Kindness`, `Planet`, `Health` — used for badge unlocking and personalized recommendations
- **Streak**: Consecutive days with `open_log` entries (tracked by `mark_open_today()` on app load)

### AI Persona (SilenceGPT)
- **System prompt construction**: `build_system_prompt()` creates child-specific prompts with age, interests, dream, project goal
- **Chat flow**: History stored per thread; system prompt prepended before each `chat_completion()` call
- **Temperature**: 0.7 for creative exploration vs. 0.0 for fact verification (not currently implemented)

### Subscription Access Control
```python
# Pattern used throughout app.py
client = ensure_supabase_access()  # Halts execution (st.stop()) if no valid subscription
# ... protected content ...
```
- **Bypass**: `SUPABASE_BYPASS=true` skips auth (dev only)
- **Free tier**: Limits daily messages via `get_free_tier_usage()` dict tracking
- **Subscription states**: `active`, `trialing`, `past_due`, `canceled` (from Stripe via webhook)

## Integration Points

### Supabase Edge Functions
Located in `supabase/functions/`:
- **create-checkout-session**: Stripe Checkout link generation
- **create-portal-session**: Customer portal for subscription management
- **stripe-webhook**: Sync `subscription_status` and `trial_ends_at` to profiles table

**Critical**: These functions use `SUPABASE_SERVICE_ROLE_KEY` for admin operations, not `ANON_KEY`

### Snowflake Connection Pattern
```python
# db_utils.py maintains a singleton connection with auto-retry
conn = get_conn()  # Thread-safe, lazy-initialized
_execute(query, params, fetch="all")  # Wrapper handles reconnection on stale connections
```
**Environment vars**: All `SNOWFLAKE_*` vars must be set (see `REQUIRED_VARS` tuple)

### OpenAI API
- **Model**: `gpt-4.1-mini` (typo? should be `gpt-4o-mini` or `gpt-3.5-turbo-1106`)
- **Key sources**: `SILENCE_GPT_API_KEY` > `OPENAI_API_KEY` (env) > `st.secrets`
- **Client caching**: `@st.cache_resource` on `get_openai_client_cached()` to reuse client instance

## File Reference

### Core Application Files
- **app.py**: Main Streamlit app (~1300 LOC); tab routing, UI rendering, auth flow
- **db_utils.py**: Snowflake persistence layer (864 LOC); all CRUD operations
- **silencegpt_api.py**: Thin OpenAI wrapper for chat completion
- **silencegpt_prompt.py**: System prompt builder for child-specific personas
- **content_feed.py**: Supabase integration for Knowledge Hub posts

### Configuration & Deployment
- **requirements.txt**: Python dependencies (Streamlit, OpenAI, Snowflake, Supabase, Stripe via `requests`)
- **Dockerfile**: Python 3.10-slim with ffmpeg for audio features
- **supabase_schema.sql**: Auth profiles, RLS policies, coach data tables

### Data Directories
- **data/**: Content feed cache, parent PIN (not tracked in git)
- **diaries/**: JSON exports of chat sessions (timestamped diary entries)
- **scripts/**: One-off utilities for SQLite→Snowflake migration, session inserts

## Common Patterns to Follow

### Adding a New Feature Tab
1. Define tab name in `NAV_TABS` tuple (app.py:54)
2. Add background image key to `BACKGROUND_IMAGES` dict if needed
3. Create `render_<feature>_tab()` function following pattern in `render_coach_tab()`
4. Add routing case in `main()` after `st.segmented_control` selection

### Adding a New Snowflake Table
1. Add `CREATE TABLE IF NOT EXISTS` DDL in `init_db()` (db_utils.py)
2. Write CRUD functions (`create_*`, `list_*`, `get_*`, `update_*`, `delete_*`)
3. Add cached wrapper in `app.py` with appropriate TTL
4. Clear cache after mutations via custom `invalidate_*` function

### Adding a New Points Category
1. Add tag to relevant constants (`MODE_TO_TAG`, `CELEBRATION_BY_TAG`, `POINT_LABEL_BY_TAG`)
2. Update gamification logic in sidebar (search `st.sidebar.button` calls in `render_sidebar()`)
3. Ensure `add_points()` calls use consistent `reason` string for analytics

## Performance Best Practices

### Cache Management
- **Use longer TTLs for stable data**: Profiles (120s), points/streaks (300s) vs. messages (60s)
- **Always use cached wrappers**: Never call `db_utils` functions directly from UI
- **Consolidate cache invalidation**: Use `invalidate_coach_caches()` or `invalidate_progress_caches()` instead of individual `.clear()` calls
- **Hide cache spinners**: Add `show_spinner=False` to avoid UI flicker

### Database Optimization
- **Batch queries where possible**: Combine related queries into single round-trip
- **Connection singleton pattern**: Already implemented in `get_conn()` with auto-retry
- **Use cache decorators liberally**: Every read operation should have a cached wrapper

### UI Performance
- **Disable backgrounds for speed**: Set `ENABLE_BACKGROUNDS=false` for 60-70% faster loads
- **Lazy load heavy components**: Only render active tab content
- **Minimize `st.rerun()` calls**: Consider `@st.fragment` for isolated updates (Phase 2 optimization)

## Anti-Patterns to Avoid

- **Don't call `db_utils` functions directly in UI code** → always use `cached_*` wrappers
- **Don't use short cache TTLs** → causes excessive Snowflake queries; use 120s+ for stable data
- **Don't clear caches individually** → use consolidated `invalidate_*()` functions
- **Don't forget `st.rerun()` after session state updates** → leads to stale UI
- **Don't hardcode Stripe/Supabase URLs** → always use env vars/secrets
- **Don't commit secrets** → use `.streamlit/secrets.toml` (gitignored) or env vars
- **Don't use `st.experimental_*` APIs** → deprecated; migrate to stable equivalents
- **Don't encode large images inline** → consider CDN or disable with `ENABLE_BACKGROUNDS=false`

## Testing & Debugging

### Common Issues
- **"Connection not open" Snowflake errors**: Auto-handled by retry logic in `_execute()`
- **Stale cached data**: Call `cached_*.clear()` after DB writes
- **Missing env vars**: Check `REQUIRED_VARS` tuple; app will raise `RuntimeError` on startup
- **Supabase RLS blocking queries**: Ensure user is authenticated; check policy definitions in schema

### Logging
- No structured logging framework; use `st.error()`, `st.warning()`, `st.info()` for user-facing messages
- OpenAI errors surface via exception catch blocks in `render_coach_tab()`
