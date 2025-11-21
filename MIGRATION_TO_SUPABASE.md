# Migration Guide: Snowflake → Supabase

## Why Migrate?

Current issues:
- **Snowflake not configured**: Credentials are commented out in secrets
- **Dual database complexity**: Supabase (auth) + Snowflake (data) = more latency, cost, complexity
- **Adventures/chats not working**: Snowflake connection is failing

**Solution**: Consolidate everything to Supabase

## ✅ Good News

The Supabase schema (`supabase_schema.sql`) **already has all the Coach tables**:
- `coach_children` (profiles)
- `coach_adventures` (projects)
- `coach_threads` (chats)
- `coach_messages`
- `coach_points_log`
- `coach_missions_log`
- etc.

Tables just need to be created in your Supabase project!

## 🚀 Migration Steps

### Step 1: Create Tables in Supabase

1. Go to your Supabase project dashboard
2. Click "SQL Editor" in sidebar
3. Paste the entire contents of `supabase_schema.sql`
4. Click "Run"
5. Verify tables created under "Table Editor"

### Step 2: Deploy Code Changes

The migration is ready in these files (already committed):
- `db_supabase.py` - New Supabase-based database functions
- `db_utils.py` (new) - Compatibility wrapper that auto-injects Supabase client

Changes needed in `app.py` (I can help with this):
- Remove Snowflake health check (lines ~1070-1088)
- Imports already work (db_utils.py wraps db_supabase.py)

### Step 3: Update requirements.txt

Remove:
```
snowflake-connector-python==3.12.2
```

Already included (no changes needed):
```
supabase==2.10.0
```

### Step 4: Remove Snowflake Secrets

In Streamlit Cloud → Settings → Secrets, remove:
```toml
SNOWFLAKE_ACCOUNT = "..."
SNOWFLAKE_USER = "..."  
SNOWFLAKE_PASSWORD = "..."
SNOWFLAKE_DATABASE = "..."
SNOWFLAKE_SCHEMA = "..."
SNOWFLAKE_WAREHOUSE = "..."
```

### Step 5: Test

1. Deploy to Streamlit Cloud
2. Login with Supabase auth
3. Try creating explorer → adventure → chat
4. Should work instantly with no Snowflake connection errors!

## 🔍 What Changes

### Before (Snowflake)
```python
# db_utils.py - Snowflake connector
conn = snowflake.connector.connect(...)
cursor.execute("SELECT * FROM profiles")
```

### After (Supabase)  
```python
# db_supabase.py - Supabase client
client.table("coach_children").select("*").execute()

# db_utils.py - Wrapper that auto-injects client
def list_child_profiles():
    return db_supabase.list_child_profiles(_get_client())
```

App code stays the same!

## ⚠️ Important Notes

1. **User isolation**: Coach tables use Row Level Security (RLS) - each user only sees their own data
2. **No data migration needed**: You're starting fresh (Snowflake wasn't working anyway)
3. **Column name mapping**: 
   - Snowflake `child_id` → Supabase `child_id` (same)
   - Snowflake `project_id` → Supabase `adventure_id` (renamed for clarity)
4. **Created timestamps**: Supabase auto-populates `created_at` (no need to pass)

## 📊 Schema Differences

| Snowflake Table | Supabase Table | Notes |
|----------------|----------------|-------|
| `profiles` | `coach_children` | Renamed for clarity, linked to auth.users |
| `projects` | `coach_adventures` | Renamed, same structure |
| `threads` | `coach_threads` | Same, FK to `adventure_id` |
| `messages` | `coach_messages` | Same |
| `points_log` | `coach_points_log` | Added `user_id` FK |
| `missions_log` | `coach_missions_log` | Added `user_id` FK |

## 🎯 Next Steps

**Ready to proceed?** I can:

1. **Remove Snowflake health check from app.py** (1 edit)
2. **Update requirements.txt** (remove snowflake-connector-python)
3. **Commit & push**

Then you just need to:
1. Run `supabase_schema.sql` in Supabase SQL Editor
2. Remove Snowflake secrets from Streamlit Cloud
3. Redeploy!

Let me know and I'll make the final code changes! 🚀
