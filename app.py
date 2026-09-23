import hashlib
import json
import random
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import auth
import storage

DATA_DIR = Path(__file__).parent

st.set_page_config(page_title="Mum's NCLEX-PN Guide", page_icon="favicon.ico" if (DATA_DIR / "favicon.ico").exists() else None, layout="centered")

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_data
def load_data():
    study = json.loads((DATA_DIR / "study_data.json").read_text())
    questions = json.loads((DATA_DIR / "questions.json").read_text())
    flashcards = json.loads((DATA_DIR / "flashcards.json").read_text())
    return study, questions, flashcards

STUDY, QUESTIONS, FLASHCARDS = load_data()
CATEGORIES = sorted({q["cat"] for q in QUESTIONS})

# ---------------------------------------------------------------------------
# Sign in (Google, or username + password) — each person's progress is
# stored separately and privately, keyed off their own account.
# ---------------------------------------------------------------------------
def google_configured() -> bool:
    try:
        return "auth" in st.secrets and bool(st.secrets["auth"].get("client_id"))
    except Exception:
        return False

def current_identity():
    """Returns (stable_user_id, display_name) for the signed-in person, or (None, None)."""
    try:
        if st.user.is_logged_in:
            uid = "google:" + (st.user.get("email") or st.user.get("sub"))
            name = st.user.get("name") or st.user.get("email") or "there"
            return uid, name
    except Exception:
        pass
    if st.session_state.get("local_user"):
        u = st.session_state["local_user"]
        return "local:" + u, u
    return None, None

user_id, display_name = current_identity()

if user_id is None:
    st.title("My NCLEX-PN Guide")
    st.caption("Sign in to start. Your progress is private to you — nobody else can see it.")

    if google_configured():
        if st.button("Sign in with Google", type="primary", use_container_width=True):
            st.login()
        st.divider()
        st.caption("or use a username and password")
    else:
        st.caption("Sign in with a username and password below.")

    tab_login, tab_signup = st.tabs(["Log in", "Create account"])
    with tab_login:
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Log in", use_container_width=True):
                if auth.verify_login(u, p):
                    st.session_state["local_user"] = auth.normalize_username(u)
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")
    with tab_signup:
        with st.form("signup_form"):
            u2 = st.text_input("Choose a username")
            p2 = st.text_input("Choose a password", type="password")
            p2b = st.text_input("Confirm password", type="password")
            if st.form_submit_button("Create account", use_container_width=True):
                if p2 != p2b:
                    st.error("Passwords don't match.")
                else:
                    ok, msg = auth.create_account(u2, p2)
                    if ok:
                        st.session_state["local_user"] = auth.normalize_username(u2)
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
    st.stop()

# ---------------------------------------------------------------------------
# Per-user progress storage (each account's record is keyed by a hash of
# their account id, never their raw email/username). storage.py picks the
# actual backend: a permanent hosted database when one is configured, local
# files otherwise — this code doesn't need to know which.
# ---------------------------------------------------------------------------
def _uid_hash(uid: str) -> str:
    return hashlib.sha256(uid.encode("utf-8")).hexdigest()

def load_progress(uid: str):
    data = storage.get_progress(_uid_hash(uid))
    return data if data else {"read_chapters": {}, "answers": {}}

def save_progress(uid: str, progress_data):
    storage.save_progress(_uid_hash(uid), progress_data)

if "progress" not in st.session_state or st.session_state.get("progress_owner") != user_id:
    st.session_state.progress = load_progress(user_id)
    st.session_state.progress_owner = user_id

progress = st.session_state.progress

def save_progress_now():
    save_progress(user_id, progress)

# ---------------------------------------------------------------------------
# Text size + styling
# ---------------------------------------------------------------------------
if "text_size" not in st.session_state:
    st.session_state.text_size = "Normal"

with st.sidebar:
    st.success(f"Signed in as **{display_name}**")
    if st.button("Log out"):
        if user_id.startswith("google:"):
            st.logout()
        else:
            st.session_state.pop("local_user", None)
            st.session_state.pop("progress", None)
            st.session_state.pop("progress_owner", None)
            st.rerun()
    st.divider()
    st.header("Settings")
    st.session_state.text_size = st.radio(
        "Text size", ["Normal", "Large", "Extra large"],
        index=["Normal", "Large", "Extra large"].index(st.session_state.text_size),
    )
    st.caption("Choose the text size that's most comfortable to read.")

SIZE_PX = {"Normal": 18, "Large": 21, "Extra large": 25}[st.session_state.text_size]
st.markdown(f"""
<style>
html, body, [class*="css"]  {{ font-size: {SIZE_PX}px !important; }}
h1 {{ font-size: {SIZE_PX + 14}px !important; }}
h2 {{ font-size: {SIZE_PX + 8}px !important; }}
h3 {{ font-size: {SIZE_PX + 3}px !important; }}
.stButton>button {{ font-size: {SIZE_PX - 1}px !important; min-height: 48px; }}
.stRadio label {{ font-size: {SIZE_PX}px !important; }}
</style>
""", unsafe_allow_html=True)


def speak_button(text: str, key: str, label: str = "\U0001F50A Read aloud"):
    """Embeds a small HTML/JS widget that uses the browser's own text-to-speech."""
    safe_text = json.dumps(text)
    components.html(f"""
        <div style="font-family:sans-serif;">
        <button id="btn-{key}" style="min-height:44px;padding:8px 16px;border-radius:10px;
            border:1px solid #ccc;background:#eef2e9;font-size:15px;font-weight:700;cursor:pointer;">
            {label}
        </button>
        </div>
        <script>
        const btn = document.getElementById("btn-{key}");
        let speaking = false;
        btn.addEventListener("click", () => {{
            if (!('speechSynthesis' in window)) return;
            if (speaking) {{
                window.speechSynthesis.cancel();
                speaking = false;
                btn.textContent = "{label}";
                return;
            }}
            window.speechSynthesis.cancel();
            const u = new SpeechSynthesisUtterance({safe_text});
            u.rate = 0.95;
            u.onend = () => {{ speaking = false; btn.textContent = "{label}"; }};
            window.speechSynthesis.speak(u);
            speaking = true;
            btn.textContent = "⏹ Stop reading";
        }});
        </script>
    """, height=64)


st.title("My NCLEX-PN Guide")
st.caption("Large-print study guide & practice, at your own pace")

tab_study, tab_practice, tab_quick, tab_flash, tab_progress = st.tabs(
    ["\U0001F4D6 Study", "✏️ Practice", "⏱️ Quick Test", "\U0001F0CF Flashcards", "\U0001F4CA Progress"]
)

# ---------------------------------------------------------------------------
# Study tab
# ---------------------------------------------------------------------------
with tab_study:
    st.write("Tap a chapter to open it. Mark it as read once you've been through it.")
    for ci, chapter in enumerate(STUDY):
        is_read = progress["read_chapters"].get(str(ci), False)
        icon = "✅" if is_read else "⬜"
        with st.expander(f"{icon} {chapter['title']}"):
            chapter_text = chapter["title"] + ". " + " ".join(
                t["title"] + ". " + " ".join(b["text"] for b in t["blocks"])
                for t in chapter["topics"]
            )
            speak_button(chapter_text, key=f"chap-{ci}", label="\U0001F50A Read this chapter aloud")
            for topic in chapter["topics"]:
                st.subheader(topic["title"])
                for block in topic["blocks"]:
                    if block["type"] == "li":
                        st.markdown(f"- {block['text']}")
                    elif block["type"] == "note":
                        st.info(block["text"])
                    else:
                        st.write(block["text"])
            new_state = st.checkbox("Mark this chapter as read", value=is_read, key=f"read-{ci}")
            if new_state != is_read:
                progress["read_chapters"][str(ci)] = new_state
                save_progress_now()

# ---------------------------------------------------------------------------
# Practice tab  (random question order + random answer-choice order every time)
# ---------------------------------------------------------------------------
with tab_practice:
    if "quiz_cat" not in st.session_state:
        st.session_state.quiz_cat = None

    def cat_questions(cat):
        return [dict(q, _idx=i) for i, q in enumerate(QUESTIONS) if q["cat"] == cat]

    def cat_stats(cat):
        qs = cat_questions(cat)
        ci = CATEGORIES.index(cat)
        attempted = correct = 0
        for q in qs:
            key = f"{ci}:{q['_idx']}"
            rec = progress["answers"].get(key)
            if rec:
                attempted += 1
                if rec.get("correct"):
                    correct += 1
        return len(qs), attempted, correct

    def start_quiz(cat):
        qs = cat_questions(cat)
        random.shuffle(qs)  # NEW order every time you start this topic
        shuffled = []
        for q in qs:
            correct_text = q["options"][q["correct"]]
            opts = q["options"][:]
            random.shuffle(opts)  # NEW answer-choice order every time
            shuffled.append({**q, "options": opts, "correct": opts.index(correct_text)})
        st.session_state.quiz_cat = cat
        st.session_state.quiz_order = shuffled
        st.session_state.quiz_idx = 0
        st.session_state.quiz_answered = False
        st.session_state.quiz_correct_count = 0
        st.session_state.quiz_choice = None

    if st.session_state.quiz_cat is None:
        st.write("Pick a topic. Each time you practice, the questions and answer order are shuffled fresh.")
        for cat in CATEGORIES:
            total, attempted, correct = cat_stats(cat)
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{cat}**")
                st.caption(f"{attempted} of {total} answered · {correct} correct")
                st.progress(correct / total if total else 0)
            with col2:
                if st.button("Practice", key=f"start-{cat}"):
                    start_quiz(cat)
                    st.rerun()
    else:
        cat = st.session_state.quiz_cat
        order = st.session_state.quiz_order
        idx = st.session_state.quiz_idx

        if idx >= len(order):
            correct_count = st.session_state.quiz_correct_count
            total = len(order)
            pct = round(correct_count / total * 100) if total else 0
            st.subheader(f"{cat}: {correct_count} / {total}")
            if pct == 100:
                st.success("Perfect score! Wonderful work.")
            elif pct >= 75:
                st.success("Really solid work on this topic.")
            elif pct < 50:
                st.warning("A good topic to review again — that's exactly what practice is for.")
            else:
                st.info("Nice work — keep going.")
            c1, c2 = st.columns(2)
            if c1.button("Practice this topic again (new order)"):
                start_quiz(cat)
                st.rerun()
            if c2.button("Choose another topic"):
                st.session_state.quiz_cat = None
                st.rerun()
        else:
            q = order[idx]
            letters = ["A", "B", "C", "D"]
            if st.button("← All topics"):
                st.session_state.quiz_cat = None
                st.rerun()
            st.caption(f"{cat} · Question {idx + 1} of {len(order)}")
            st.markdown(f"### {q['q']}")
            speak_text = q["q"] + ". " + ". ".join(f"{letters[i]}. {opt}" for i, opt in enumerate(q["options"]))
            speak_button(speak_text, key=f"q-{idx}-{cat}", label="\U0001F50A Read question aloud")

            choice = st.radio(
                "Choose an answer:",
                options=list(range(len(q["options"]))),
                format_func=lambda i: f"{letters[i]}. {q['options'][i]}",
                index=None,
                key=f"radio-{idx}-{cat}",
            )

            if choice is not None and not st.session_state.quiz_answered:
                st.session_state.quiz_answered = True
                st.session_state.quiz_choice = choice
                is_correct = choice == q["correct"]
                if is_correct:
                    st.session_state.quiz_correct_count += 1
                ci = CATEGORIES.index(cat)
                progress["answers"][f"{ci}:{q['_idx']}"] = {"correct": is_correct}
                save_progress_now()

            if st.session_state.quiz_answered:
                is_correct = st.session_state.quiz_choice == q["correct"]
                if is_correct:
                    st.success(f"That's right. {q['rationale']}")
                else:
                    st.error(f"Not quite. The correct answer is {letters[q['correct']]}. {q['rationale']}")
                if st.button("Next question →"):
                    st.session_state.quiz_idx += 1
                    st.session_state.quiz_answered = False
                    st.session_state.quiz_choice = None
                    st.rerun()

# ---------------------------------------------------------------------------
# Quick Test tab — a short, timed, mixed-category set. Exam-style: answers
# aren't revealed until you finish (or time runs out), then a full review.
# ---------------------------------------------------------------------------
with tab_quick:
    QT_SECONDS_PER_Q = 60

    if "qt_active" not in st.session_state:
        st.session_state.qt_active = False
        st.session_state.qt_finished = False
        st.session_state.qt_saved = False

    if not st.session_state.qt_active:
        st.write("A short practice set pulled from every topic at once, with a time limit — "
                  "closer to real exam pacing than practicing one topic at a time.")
        n_questions = st.selectbox("Number of questions", [10, 20, 30], index=1, key="qt_n_select")
        time_limit_min = n_questions * QT_SECONDS_PER_Q // 60
        st.caption(f"Time limit: about {time_limit_min} minutes ({QT_SECONDS_PER_Q} seconds per question, on average). "
                   f"You won't see whether an answer is right or wrong until you finish — just like the real exam. "
                   f"You can move back and forth between questions before submitting.")
        if st.button("Start quick test", type="primary"):
            pool = [dict(q, _idx=i) for i, q in enumerate(QUESTIONS)]
            random.shuffle(pool)
            selected = pool[:n_questions]
            shuffled = []
            for q in selected:
                correct_text = q["options"][q["correct"]]
                opts = q["options"][:]
                random.shuffle(opts)
                shuffled.append({**q, "options": opts, "correct": opts.index(correct_text)})
            st.session_state.qt_questions = shuffled
            st.session_state.qt_idx = 0
            st.session_state.qt_answers = {}
            st.session_state.qt_start = time.time()
            st.session_state.qt_limit = n_questions * QT_SECONDS_PER_Q
            st.session_state.qt_active = True
            st.session_state.qt_finished = False
            st.session_state.qt_saved = False
            st.rerun()
    else:
        qs = st.session_state.qt_questions
        elapsed = time.time() - st.session_state.qt_start
        remaining = max(0, st.session_state.qt_limit - elapsed)
        time_up = remaining <= 0
        letters = ["A", "B", "C", "D"]

        if not st.session_state.qt_finished and not time_up:
            idx = st.session_state.qt_idx
            q = qs[idx]

            timer_color = "#B23A2E" if remaining < 60 else "inherit"
            # Live-ticking clock between interactions; the server-side `remaining`
            # above is the authoritative value, recomputed on every real rerun.
            components.html(f"""
                <div id="qt-clock" style="text-align:right;font-family:sans-serif;color:{timer_color};
                    font-weight:700;font-size:14px;"></div>
                <script>
                let s = {int(remaining)};
                const el = document.getElementById("qt-clock");
                const tick = () => {{
                    if (s <= 0) {{ el.textContent = "Time's up — click anywhere to continue"; return; }}
                    const m = Math.floor(s/60), sec = s%60;
                    el.textContent = "⏱️ " + String(m).padStart(2,'0') + ":" + String(sec).padStart(2,'0') + " remaining";
                    s -= 1;
                    setTimeout(tick, 1000);
                }};
                tick();
                </script>
            """, height=24)

            st.progress(idx / len(qs))
            st.caption(f"Question {idx + 1} of {len(qs)} · {q['cat']}")
            st.markdown(f"### {q['q']}")

            prev_choice = st.session_state.qt_answers.get(idx)
            choice = st.radio(
                "Choose an answer:",
                options=list(range(len(q["options"]))),
                format_func=lambda i: f"{letters[i]}. {q['options'][i]}",
                index=prev_choice,
                key=f"qt-radio-{idx}",
            )
            if choice is not None:
                st.session_state.qt_answers[idx] = choice

            c1, c2, c3 = st.columns(3)
            if idx > 0:
                if c1.button("← Previous", key="qt-prev"):
                    st.session_state.qt_idx -= 1
                    st.rerun()
            if idx < len(qs) - 1:
                if c2.button("Next →", key="qt-next"):
                    st.session_state.qt_idx += 1
                    st.rerun()
            if c3.button("Submit test now", type="primary"):
                st.session_state.qt_finished = True
                st.rerun()
        else:
            st.session_state.qt_finished = True
            total = len(qs)
            answered = len(st.session_state.qt_answers)
            correct = sum(1 for i, q in enumerate(qs) if st.session_state.qt_answers.get(i) == q["correct"])

            if not st.session_state.qt_saved:
                for i, q in enumerate(qs):
                    chosen = st.session_state.qt_answers.get(i)
                    if chosen is not None:
                        ci = CATEGORIES.index(q["cat"])
                        progress["answers"][f"{ci}:{q['_idx']}"] = {"correct": chosen == q["correct"]}
                save_progress_now()
                st.session_state.qt_saved = True

            if time_up and answered < total:
                st.warning("Time's up! Here's how you did on what you answered.")
            st.subheader(f"Score: {correct} / {total}")
            st.caption(f"You answered {answered} of {total} questions.")

            for i, q in enumerate(qs):
                chosen = st.session_state.qt_answers.get(i)
                is_correct = chosen == q["correct"]
                icon = "✅" if is_correct else ("⬜" if chosen is None else "❌")
                short_q = q["q"] if len(q["q"]) <= 70 else q["q"][:70] + "..."
                with st.expander(f"{icon} Question {i + 1} ({q['cat']}): {short_q}"):
                    st.write(q["q"])
                    for j, opt in enumerate(q["options"]):
                        tag = ""
                        if j == q["correct"]:
                            tag = " ✓ correct answer"
                        elif j == chosen:
                            tag = " ← your answer"
                        st.write(f"{letters[j]}. {opt}{tag}")
                    st.info(q["rationale"])

            if st.button("Take another quick test"):
                st.session_state.qt_active = False
                st.session_state.qt_finished = False
                st.session_state.qt_saved = False
                st.rerun()

# ---------------------------------------------------------------------------
# Flashcards tab
# ---------------------------------------------------------------------------
with tab_flash:
    st.write("Flip through the highest-yield facts. Shuffle any time for a fresh order.")
    if "flash_order" not in st.session_state:
        st.session_state.flash_order = list(range(len(FLASHCARDS)))
        st.session_state.flash_idx = 0
        st.session_state.flash_show_answer = False

    if st.button("\U0001F500 Shuffle flashcards"):
        random.shuffle(st.session_state.flash_order)
        st.session_state.flash_idx = 0
        st.session_state.flash_show_answer = False
        st.rerun()

    fi = st.session_state.flash_idx % len(FLASHCARDS)
    card = FLASHCARDS[st.session_state.flash_order[fi]]
    st.caption(f"Card {fi + 1} of {len(FLASHCARDS)}")
    st.markdown(f"### {card['q']}")
    if st.session_state.flash_show_answer:
        st.info(card["a"])
    c1, c2, c3 = st.columns(3)
    if c1.button("Show / hide answer"):
        st.session_state.flash_show_answer = not st.session_state.flash_show_answer
        st.rerun()
    if c2.button("← Previous", key="flash-prev"):
        st.session_state.flash_idx = (st.session_state.flash_idx - 1) % len(FLASHCARDS)
        st.session_state.flash_show_answer = False
        st.rerun()
    if c3.button("Next →", key="flash-next"):
        st.session_state.flash_idx = (st.session_state.flash_idx + 1) % len(FLASHCARDS)
        st.session_state.flash_show_answer = False
        st.rerun()

# ---------------------------------------------------------------------------
# Progress tab
# ---------------------------------------------------------------------------
with tab_progress:
    total_chapters = len(STUDY)
    read_count = sum(1 for v in progress["read_chapters"].values() if v)
    total_q = len(QUESTIONS)
    attempted = sum(1 for v in progress["answers"].values())
    correct = sum(1 for v in progress["answers"].values() if v.get("correct"))

    c1, c2, c3 = st.columns(3)
    c1.metric("Chapters read", f"{read_count}/{total_chapters}")
    c2.metric("Questions tried", f"{attempted}/{total_q}")
    c3.metric("Correct so far", f"{round(correct/attempted*100) if attempted else 0}%")

    st.subheader("By topic")

    def _cat_stats(cat):
        qs = [q for q in QUESTIONS if q["cat"] == cat]
        ci = CATEGORIES.index(cat)
        att = corr = 0
        for i, q in enumerate(QUESTIONS):
            if q["cat"] != cat:
                continue
            key = f"{ci}:{i}"
            rec = progress["answers"].get(key)
            if rec:
                att += 1
                if rec.get("correct"):
                    corr += 1
        return len(qs), att, corr

    for cat in CATEGORIES:
        total, att, corr = _cat_stats(cat)
        st.write(f"**{cat}** — {att}/{total} answered")
        st.progress(att / total if total else 0)

    st.info("Every chapter you read and every question you try is real progress. There's no rush — come back any time and pick up right where you left off.")
    if storage.using_database():
        st.caption("Progress is saved to a permanent online database — safe even if this app restarts or is redeployed.")
    else:
        st.caption("Note: no database is connected, so progress is saved to a local file next to this app. If this app is "
                   "hosted on a free cloud service, progress may reset if the app restarts or redeploys. See README.md "
                   "for how to connect a free database and make this permanent.")