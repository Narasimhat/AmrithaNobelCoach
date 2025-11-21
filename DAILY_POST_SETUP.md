# Daily Post Generator - GitHub Actions Setup

## ✅ What's Included

- **GitHub Workflow**: `.github/workflows/daily-post-generator.yml` - Runs daily at 6 AM UTC
- **Python Script**: `scripts/generate_daily_post.py` - Generates and saves posts

## 🚀 Setup Instructions

### 1. Add GitHub Secrets

Go to your GitHub repo → Settings → Secrets and variables → Actions → New repository secret

Add these 3 secrets:

1. **OPENAI_API_KEY**
   - Value: Your OpenAI API key (starts with `sk-...`)
   
2. **SUPABASE_URL**
   - Value: Your Supabase project URL
   - Format: `https://xxxxx.supabase.co`
   - Find it: Supabase Dashboard → Settings → API → Project URL

3. **SUPABASE_SERVICE_ROLE_KEY**
   - Value: Your Supabase service role key
   - Find it: Supabase Dashboard → Settings → API → service_role key (secret)

### 2. Create Posts Table (if not exists)

Run this in Supabase SQL Editor:

```sql
CREATE TABLE IF NOT EXISTS public.posts (
  id BIGSERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  category TEXT,
  author TEXT DEFAULT 'The Silent Room Coach',
  published_at TIMESTAMPTZ DEFAULT NOW(),
  is_featured BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS policies (posts are public, read-only for users)
ALTER TABLE public.posts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Posts are viewable by everyone" ON public.posts
  FOR SELECT TO authenticated
  USING (true);

-- Grant insert permission to service role (used by GitHub Actions)
GRANT INSERT ON public.posts TO service_role;
```

### 3. Test the Workflow

**Option A: Wait for scheduled run** (next day at 6 AM UTC)

**Option B: Manual trigger (recommended for testing)**
1. Go to GitHub repo → Actions tab
2. Click "Generate Daily Knowledge Hub Post" workflow
3. Click "Run workflow" button
4. Click green "Run workflow" button
5. Watch it run (takes ~30 seconds)

### 4. Verify It Worked

Check Supabase:
- Go to Table Editor → posts
- You should see a new row with today's post!

## ⏰ Schedule Details

- **Runs**: Daily at 6:00 AM UTC
- **Timezone conversion**:
  - 6 AM UTC = 1 AM EST / 10 PM PST (previous day)
  - 6 AM UTC = 11:30 AM IST

**To change the schedule**, edit `.github/workflows/daily-post-generator.yml`:
```yaml
schedule:
  - cron: '0 6 * * *'  # Change to your preferred time
```

Cron format: `minute hour day month weekday`
- `0 6 * * *` = 6:00 AM UTC every day
- `0 12 * * *` = 12:00 PM UTC every day
- `30 18 * * *` = 6:30 PM UTC every day

## 📊 What Gets Generated

Each post includes:
- **Title**: Catchy, child-friendly (max 60 chars)
- **Content**: 200-300 words, age-appropriate for 9-year-olds
- **Category**: Science, Nature, Space, Technology, Kindness, Planet, or Creativity
- **Emoji**: Visual hook
- **Question**: Thought-provoking ending

## 🔍 Monitoring

**Check workflow runs**:
- GitHub repo → Actions tab
- Click on any run to see logs
- Green checkmark = success ✅
- Red X = failure (check logs for error)

**Check posts in app**:
- Login to your Streamlit app
- Go to Knowledge Hub tab
- New posts should appear automatically

## 💰 Cost

- **GitHub Actions**: Free for public repos (2000 minutes/month)
- **OpenAI API**: ~$0.001 per post (GPT-4o-mini)
- **Total**: ~$0.03/month for daily posts

## 🛠️ Troubleshooting

**Workflow fails with "Missing environment variables"**
- Check that all 3 secrets are added in GitHub repo settings
- Secret names must match exactly (case-sensitive)

**Post generated but not visible in app**
- Check `content_feed.py` - make sure it reads from Supabase `posts` table
- Verify RLS policies allow authenticated users to SELECT

**OpenAI API error**
- Check your OpenAI API key is valid and has credits
- Check `OPENAI_API_KEY` secret in GitHub

## ✨ Optional Enhancements

**Change topics**: Edit `TOPICS` list in `scripts/generate_daily_post.py`

**Change post style**: Modify `SYSTEM_PROMPT` in the script

**Run multiple times per day**: Add more cron schedules in workflow file
