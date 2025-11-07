
# The Silent Room — Upgrade Pack
This pack helps you apply the UX/AI upgrades we discussed to your existing Streamlit app.

## Files included
- `styles.css` — polished styles (cards, chips, primary button).
- `recommender.py` — rule-based adaptive engine that suggests next actions.
- `curiosity_tree.py` — simple Curiosity Tree progress (swap for SVG later).

## How to install
1. Copy these files into your app root (same folder as `app.py`).
2. In `app.py` (top, after imports), add:
   ```python
   import streamlit as st
   from curiosity_tree import render_curiosity_tree
   st.markdown('<style>' + open('styles.css').read() + '</style>', unsafe_allow_html=True)
   ```

3. On **Home** (or your main header area), render the Curiosity Tree:
   ```python
   from db_utils import total_points, streak_days, count
   render_curiosity_tree(points=total_points(), streak=streak_days(), missions=count('missions'))
   ```

4. Replace Coach mode dropdown with **mode chips** (conceptual example):
   ```python
   if 'mode' not in st.session_state:
       st.session_state['mode'] = 'Spark'
   cols = st.columns(5)
   modes = [('💡','Spark'),('🔧','Build'),('🧠','Think'),('✍️','Write'),('🎤','Share')]
   for i,(icon,label) in enumerate(modes):
       if cols[i].button(f"{icon} {label}", key=f"chip_{label}"):
           st.session_state['mode'] = label
   st.write("Current mode:", st.session_state['mode'])
   ```

5. Wire the **recommender** where you show suggestions (Home or Parents page):
   ```python
   from recommender import recommend
   profile = {
       'tags_counts': {'Planet': 4, 'Build': 3, 'Think': 2},  # TODO: compute from your DB
       'streak': streak_days(),
       'recent_idle_days': 0,
       'last_completed_tags': []
   }
   for s in recommend(profile):
       st.info(f"🧭 Suggested • {s['type']} → {s['id']} — {s['reason']}")
   ```

## Run with Docker (optional)
If macOS permissions get in the way, you can containerize the ritual app:

1. Build the image from the project root:
   ```bash
  docker build -t the-silent-room .
   ```
2. Run it while passing your OpenAI key and exposing the Streamlit port:
   ```bash
  docker run -e OPENAI_API_KEY="sk-..." -p 8501:8501 the-silent-room
   ```
3. Visit http://localhost:8501 in your browser.

Need to keep diaries/data outside the container? Mount them:
```bash
docker run -e OPENAI_API_KEY="sk-..." \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/diaries:/app/diaries" \
  -p 8501:8501 the-silent-room
```

## Deploy to Streamlit Community Cloud
1. Push this folder to a public GitHub repo (be sure **not** to commit secrets or personal diary data).
   ```bash
   git init
  git remote add origin git@github.com:yourname/the-silent-room.git
   git add .
   git commit -m "Initial coach upload"
   git push origin main
   ```
2. In Streamlit Community Cloud (https://share.streamlit.io), choose “New app”, select the repo, branch, and set the main file to `app.py`. In the app settings, rename the deployment to **The Silent Room** so the hosted title matches the in-app branding.
3. In the app’s **Secrets** panel, add:
   ```toml
   OPENAI_API_KEY = "sk-..."
   ```
4. Streamlit Cloud automatically installs Python deps from `requirements.txt`; the companion `packages.txt` ensures `ffmpeg` is available for audio recording.
5. Click “Deploy” – the coach should come online at a shareable URL. Update secrets there any time you rotate keys.

## Enable subscriptions with Supabase + Stripe
1. **Create Supabase project**: enable email/password auth. Run the SQL in `supabase_schema.sql` (SQL Editor → Run) to provision the `profiles` table and trigger.
2. **Deploy Stripe webhook**: copy `supabase/functions/stripe-webhook` into your Supabase project and deploy with the Supabase CLI, e.g. `supabase functions deploy stripe-webhook --no-verify-jwt`. Configure function environment variables: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_URL`.
3. **Configure Stripe Billing**:
   - Create two prices: one with the 30-day free trial and one without a trial (for direct purchase).
   - When initiating a Checkout session, pass the Supabase user id via `metadata = {'supabase_user_id': user.id}`.
   - Point Stripe’s webhook endpoint at the deployed Supabase function URL.
   - Save the Stripe REST IDs as environment variables on the Supabase functions: `STRIPE_PRICE_ID` (with trial), `STRIPE_PRICE_ID_NO_TRIAL` (no trial), `STRIPE_CHECKOUT_SUCCESS_URL`, `STRIPE_CHECKOUT_CANCEL_URL`, `STRIPE_PORTAL_RETURN_URL`, plus the secrets you already added (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_URL`).
4. **Wire Streamlit**: set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and optionally `SUPABASE_SERVICE_ROLE_KEY` (for the sidebar metric) in your Streamlit secrets. Leave `SUPABASE_BYPASS` unset/`false` so parents must sign in.
5. **Parent experience**: parents log in via the sidebar. If their status is inactive, the app offers a “Start free month” button (Stripe Checkout) and a “Manage subscription” button (customer portal). Stripe webhooks keep `profiles.subscription_status` in sync, so trials expire and paid plans unlock automatically.
