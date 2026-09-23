# Mum's NCLEX-PN Guide (Streamlit app)

A large-print study guide, quiz, and flashcards for NCLEX-PN prep, with real
per-person accounts — everyone signs in (with Google, or a username and
password) and gets their own private progress that nobody else can see.
Every time you start a topic, the questions and answer-choice order are
freshly shuffled.

## What's inside
- `app.py` — the app itself (sign-in gate, then Study / Practice / Flashcards / Progress tabs)
- `auth.py` — username/password accounts (passwords are salted + hashed, never stored in plain text)
- `study_data.json`, `questions.json` (119 questions), `flashcards.json` (48 cards) — the content
- `requirements.txt` — dependencies (Streamlit + Authlib)
- `.streamlit/secrets.toml.example` — template for Google sign-in credentials (optional)

## Quick start — no setup at all (username/password only)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`. People create an account with just a
username and password, directly in the app — no external service needed.
This works immediately, locally or once deployed, with zero configuration.

## Optional: add "Sign in with Google"

This step is optional — the app works fine without it. Do this only if you
specifically want the Google button too. It requires a one-time setup in
Google's own developer console (only you can do this part, since it needs
your Google account):

1. Go to **console.cloud.google.com** and create a new project (any name,
   e.g. "Mum NCLEX App").
2. In the left menu: **APIs & Services -> OAuth consent screen**.
   - User type: **External**. Fill in the app name, your email, and save.
   - You can leave it in "Testing" mode and add your mum + friends' Google
     emails as "test users" — no Google review needed for a small private
     app like this.
3. In the left menu: **APIs & Services -> Credentials -> Create Credentials
   -> OAuth client ID**.
   - Application type: **Web application**.
   - Under **Authorized redirect URIs**, add:
     - `http://localhost:8501/oauth2callback` (for testing on your computer)
     - `https://YOUR-APP-NAME.streamlit.app/oauth2callback` (once you know
       your deployed app's URL — you can add this later and edit it)
   - Click Create. Copy the **Client ID** and **Client secret** it shows you.
4. In this project folder, copy `.streamlit/secrets.toml.example` to
   `.streamlit/secrets.toml` and fill in:
   - `client_id` and `client_secret` from step 3
   - `cookie_secret` — generate your own random value with:
     `python3 -c "import secrets; print(secrets.token_hex(32))"`
   - `redirect_uri` — matching whichever URL you're running at
5. Run `streamlit run app.py` again — you'll now see a "Sign in with Google"
   button above the username/password form.

**Never commit `.streamlit/secrets.toml` to GitHub** — it's already listed
in `.gitignore`. When you deploy to Streamlit Community Cloud (below),
paste its contents into that app's **Settings -> Secrets** box instead —
that's the secure place for it, not a file in your repository.

## Put it online so everyone can reach it from any device

1. Create a free GitHub account if you don't have one, and create a new
   **private** repository (private is fine — Streamlit Cloud can deploy
   from a private repo too).
2. Upload every file in this folder **except** `.streamlit/secrets.toml`,
   `users.json`, and the `progress/` folder if they exist (`.gitignore`
   already keeps these out if you're using git normally).
3. Go to **share.streamlit.io**, sign in with GitHub.
4. Click **New app**, pick your repository, set the main file to `app.py`,
   and deploy.
5. If you set up Google sign-in: open the deployed app's **Settings ->
   Secrets** in the Streamlit Cloud dashboard and paste in the contents of
   your local `secrets.toml`, updating `redirect_uri` to your real
   `https://YOUR-APP-NAME.streamlit.app/oauth2callback` URL. Also go back to
   Google Cloud Console and add that same URL to your OAuth client's
   authorized redirect URIs.
6. You'll get a permanent link like `https://your-app-name.streamlit.app` —
   that's the one link everyone uses; each person creates their own account
   (or signs in with their own Google account) the first time they open it.

## How privacy works here
- Each account's progress is saved to its own file, named from a one-way
  hash of the account's id — never from the person's raw email or username.
- Nobody, including whoever manages the deployment, can casually browse
  from one person's file to figure out whose it is by looking at the
  filename.
- Passwords for username/password accounts are salted and hashed with
  PBKDF2-SHA256 (200,000 iterations) — the plain password is never written
  to disk anywhere.

**One honest limitation:** on Streamlit Community Cloud's free tier,
storage isn't guaranteed to persist forever across app restarts or
redeploys. Accounts and progress are most durable when the app runs
continuously on your own computer or a paid host; the free tier is great
for accessibility and cost, just not a guarantee against an occasional
reset if the app has been asleep a long time.

## Adding more questions later
Open `questions.json` in any text editor — each entry looks like:
```json
{"cat": "Category Name", "q": "Question text?",
 "options": ["A text", "B text", "C text", "D text"],
 "correct": 0, "rationale": "Why that answer is correct."}
```
Add new entries in the same format and save. No code changes needed.
