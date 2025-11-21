# Daily Knowledge Hub Post Generator

## 📋 Overview
Automatically generates 1 educational post per day using OpenAI and stores it in Supabase.

## 🚀 Setup Instructions

### 1. Deploy the Edge Function

```bash
# Install Supabase CLI if you haven't
npm install -g supabase

# Login to Supabase
supabase login

# Link to your project
supabase link --project-ref YOUR_PROJECT_REF

# Deploy the function
supabase functions deploy generate-daily-post
```

### 2. Set Environment Variables

In your Supabase Dashboard → Edge Functions → generate-daily-post → Secrets:

```env
OPENAI_API_KEY=sk-your-openai-key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

### 3. Create the Posts Table (if not exists)

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

-- Only service role can insert (via Edge Function)
CREATE POLICY "Service role can insert posts" ON public.posts
  FOR INSERT TO service_role
  WITH CHECK (true);
```

### 4. Set Up Daily Cron Job

In Supabase Dashboard → Database → Cron Jobs:

```sql
-- Run daily at 6:00 AM UTC (adjust timezone as needed)
SELECT cron.schedule(
  'generate-daily-post',
  '0 6 * * *', -- Every day at 6 AM
  $$
  SELECT
    net.http_post(
      url := 'https://YOUR_PROJECT_REF.supabase.co/functions/v1/generate-daily-post',
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', 'Bearer ' || current_setting('app.settings.service_role_key')
      ),
      body := '{}'::jsonb
    ) as request_id;
  $$
);
```

**Note**: Replace `YOUR_PROJECT_REF` with your actual Supabase project reference.

### 5. Test Manually

```bash
# Test the function locally
supabase functions serve generate-daily-post

# Or invoke via HTTP
curl -X POST 'https://YOUR_PROJECT_REF.supabase.co/functions/v1/generate-daily-post' \
  -H "Authorization: Bearer YOUR_ANON_KEY" \
  -H "Content-Type: application/json"
```

## 📝 How It Works

1. **Daily Trigger**: Cron job runs at 6 AM UTC every day
2. **Topic Selection**: Rotates through 15 curated topics based on day of year
3. **Content Generation**: OpenAI GPT-4o-mini generates age-appropriate content
4. **Storage**: Post is saved to `posts` table in Supabase
5. **Display**: App's Knowledge Hub shows the post via `content_feed.py`

## 🎯 Topics Covered

- Science (stars, plants, electricity, etc.)
- Nature (seasons, oceans, birds, etc.)
- Space (black holes, planets)
- Technology (internet, airplanes)
- Values (kindness, creativity, planet care)

## 📊 Post Structure

Each post includes:
- **Title**: Catchy, child-friendly (max 60 chars)
- **Content**: 200-300 words, age-appropriate for 9-year-olds
- **Category**: Science|Nature|Space|Technology|Kindness|Planet|Creativity
- **Emoji**: Visual hook
- **Question**: Thought-provoking ending to inspire reflection

## 🔧 Customization

Edit `supabase/functions/generate-daily-post/index.ts`:

- **Topics**: Add/remove from the `topics` array (line 28)
- **System Prompt**: Adjust tone/style (line 57)
- **Post Frequency**: Change cron schedule (default: daily)
- **Post Length**: Modify `max_tokens` parameter (line 102)

## 📈 Monitoring

Check function logs in Supabase Dashboard:
- Edge Functions → generate-daily-post → Logs
- Look for successful posts or errors

## 💰 Cost Estimate

- OpenAI API: ~$0.001 per post (GPT-4o-mini)
- Supabase Edge Functions: Free tier includes 500K invocations/month
- **Total**: ~$0.03/month for daily posts

## 🔒 Security

- Service role key is only in Supabase secrets (not exposed)
- Posts table has RLS enabled
- Users can only read posts, not create/modify
- Edge Function uses CORS headers for secure access
