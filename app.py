"""
DevOps Study Coach - browser UI (Streamlit).

A friendlier face on the same local, offline tutor: a dashboard with your
streak, daily goal, and mastery charts, plus Study / Interview / Ask pages.

Run it with:
    streamlit run app.py

Everything still runs locally via Ollama - nothing leaves your machine.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import config
import core
import learner
from coach import SCORE_RE, TUTOR_SYSTEM

st.set_page_config(page_title="DevOps Study Coach", page_icon="🎓", layout="wide")

PAGES = ["📊 Dashboard", "🧠 Study", "🎤 Mock interview", "💬 Ask"]


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #

@st.cache_resource(show_spinner=False)
def _init_once() -> bool:
    """Prepare the learner DB exactly once for this server process."""
    learner.init_db()
    return True


def _service_status() -> dict:
    """Check Ollama + index freshly on every run (so it updates live)."""
    index = True
    try:
        core.get_collection(create=False)
    except Exception:
        index = False
    return {"ollama": core.ollama_up(), "index": index}


def _context_for(query: str, k: int | None = None):
    hits = core.retrieve(query, top_k=k or max(config.TOP_K, 6))
    parts = []
    for i, h in enumerate(hits, 1):
        src = h["meta"].get("source", "?")
        head = h["meta"].get("heading", "")
        label = f"[{i}] {src}" + (f"  ({head})" if head else "")
        parts.append(f"{label}\n{h['text']}")
    return "\n\n---\n\n".join(parts), hits


def _question_messages(topic: str, style: str, context: str) -> list[dict]:
    return [
        {"role": "system", "content": TUTOR_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Context from my labs:\n\n{context}\n\n"
                f"Ask me ONE {style} question about '{topic}'. Specific and practical. "
                "Ask the question only - do NOT reveal or hint at the answer yet."
            ),
        },
    ]


def _grade_messages(topic: str, question: str, answer: str, context: str) -> list[dict]:
    return [
        {"role": "system", "content": TUTOR_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Context from my labs:\n\n{context}\n\n"
                f"You asked: {question}\n\nMy answer: {answer}\n\n"
                "Grade my answer. Start with exactly 'SCORE: <0-5>' "
                "(5=perfect, 3=acceptable, 0=blank), then 2-4 lines: what was "
                "right, what was missing (correct answer from the context), and a tip."
            ),
        },
    ]


def _mastery_color(pct: int) -> str:
    if pct >= 75:
        return "🟢"
    if pct >= 45:
        return "🟡"
    return "🔴"


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #

_init_once()
status = _service_status()

with st.sidebar:
    st.title("🎓 Study Coach")
    st.caption("Local · offline · private")

    ollama_ok = status["ollama"]
    index_ok = status["index"]
    all_ready = ollama_ok and index_ok

    def _status_line(ok: bool, name: str, ok_text: str, bad_text: str) -> str:
        return f"{'✅' if ok else '❌'} **{name}:** {ok_text if ok else bad_text}"

    with st.container(border=True):
        header = "✅ Setup status · ready" if all_ready else "⚠️ Setup status · action needed"
        st.markdown(f"**{header}**")
        st.markdown(
            f"{_status_line(ollama_ok, 'Ollama', 'running', 'not running')}  \n"
            f"{_status_line(index_ok, 'Labs', 'indexed', 'not indexed')}"
        )
        if not all_ready:
            with st.expander("Steps to fix", expanded=True):
                step = 1
                if not ollama_ok:
                    st.markdown(
                        f"**{step}. Start Ollama** and pull the models:\n"
                        f"```\nollama pull {config.CHAT_MODEL}\n"
                        f"ollama pull {config.EMBED_MODEL}\n```"
                    )
                    step += 1
                if not index_ok:
                    st.markdown(f"**{step}. Index your labs:**\n```\npython ingest.py\n```")
                st.caption("This panel turns green once both are ready.")

    st.caption(f"chat `{config.CHAT_MODEL}` · embed `{config.EMBED_MODEL}`")

    # Index-based nav so buttons elsewhere can switch pages without widget-key clashes.
    if "nav" not in st.session_state:
        st.session_state["nav"] = PAGES[0]
    pending = st.session_state.pop("pending_nav", None)
    if pending in PAGES:
        st.session_state["nav"] = pending

    page = st.radio(
        "Go to",
        PAGES,
        index=PAGES.index(st.session_state["nav"]),
        label_visibility="collapsed",
    )
    st.session_state["nav"] = page

    streak = learner.get_streak()
    today = learner.today_count()
    st.divider()
    st.metric("🔥 Streak", f"{streak} day{'s' if streak != 1 else ''}")
    st.progress(min(today / learner.DAILY_GOAL, 1.0), text=f"Today: {today}/{learner.DAILY_GOAL}")


def _require_services() -> bool:
    if not status["ollama"]:
        st.error("Ollama isn't running. Start it, then refresh this page.")
        return False
    if not status["index"]:
        st.error("No lab index found. Run `python ingest.py`, then refresh.")
        return False
    return True


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #

def page_dashboard() -> None:
    st.header("📊 Your learning dashboard")
    s = learner.stats()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avg mastery", f"{s['avg_mastery']}%")
    c2.metric("Accuracy", f"{s['accuracy']}%")
    c3.metric("Due now", s["due_now"])
    c4.metric("Topics studied", f"{s['topics_studied']}/{s['topics_total']}")

    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("Mastery by lab")
        labs = learner.lab_mastery()
        if labs:
            df = pd.DataFrame(labs).set_index("lab")
            st.bar_chart(df, height=280)
        else:
            st.caption("Study a few topics to see this chart.")

    with right:
        st.subheader("Activity (last 30 days)")
        act = learner.activity_recent(30)
        df = pd.DataFrame(act)
        df["day"] = pd.to_datetime(df["day"]).dt.strftime("%m-%d")
        st.bar_chart(df.set_index("day"), height=280)

    st.divider()
    st.subheader("⏰ Due today (top priorities)")
    due = learner.due_topics(limit=12)
    if not due:
        st.success("Nothing due — you're all caught up!")
    else:
        for r in due:
            m = learner.mastery_pct(r)
            st.write(f"{_mastery_color(m)} **{r['name']}**  ·  _{r.get('lab','')}_  ·  mastery {m}%")
        if st.button("▶️ Go to Study tab", type="primary"):
            st.session_state["pending_nav"] = "🧠 Study"
            st.rerun()

    st.divider()
    st.subheader("Weakest topics")
    studied = [r for r in learner.all_topics() if (r.get("attempts", 0) or 0) > 0]
    if studied:
        studied.sort(key=learner.mastery_pct)
        rows = [
            {
                "topic": r["name"],
                "lab": r.get("lab", ""),
                "mastery %": learner.mastery_pct(r),
                "accuracy %": round(100 * (r.get("correct", 0) or 0) / (r.get("attempts", 1) or 1)),
                "times seen": r.get("attempts", 0),
                "next review": (r.get("due") or "")[:10],
            }
            for r in studied[:15]
        ]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.caption("No attempts yet. Head to the Study tab to begin.")


# --------------------------------------------------------------------------- #
# Study / Interview (shared engine)
# --------------------------------------------------------------------------- #

def _start_session(mode: str, lab: str | None, rounds: int) -> None:
    picks = learner.pick_study_topics(n=rounds, lab=lab)
    st.session_state[f"{mode}_queue"] = picks
    st.session_state[f"{mode}_idx"] = 0
    st.session_state[f"{mode}_scores"] = []
    st.session_state[f"{mode}_question"] = None
    st.session_state[f"{mode}_phase"] = "ask"
    st.session_state[f"{mode}_active"] = True


def _current_topic(mode: str):
    queue = st.session_state.get(f"{mode}_queue", [])
    idx = st.session_state.get(f"{mode}_idx", 0)
    if idx < len(queue):
        return queue[idx]
    return None


def _run_session_ui(mode: str, style: str, title: str, accent: str) -> None:
    if not st.session_state.get(f"{mode}_active"):
        return

    queue = st.session_state[f"{mode}_queue"]
    idx = st.session_state[f"{mode}_idx"]
    row = _current_topic(mode)

    if row is None:
        scores = st.session_state.get(f"{mode}_scores", [])
        if scores:
            avg = sum(scores) / len(scores)
            st.success(f"Session complete — answered {len(scores)}, average {avg:.1f}/5.")
            if mode == "interview":
                verdict = (
                    "Strong hire" if avg >= 4.3 else
                    "Hire" if avg >= 3.5 else
                    "Lean no — more prep needed" if avg >= 2.5 else
                    "No — revise the fundamentals"
                )
                st.info(f"**Verdict:** {verdict}")
        if st.button("Done", key=f"{mode}_done"):
            st.session_state[f"{mode}_active"] = False
            st.rerun()
        return

    topic = row["name"]
    lab = row.get("lab", "ad-hoc")
    st.caption(f"{title} · question {idx + 1} of {len(queue)} · _{lab}_")
    st.subheader(f"{accent} {topic}")

    # Generate the question once (retrieving context only then), keep across reruns.
    if st.session_state.get(f"{mode}_question") is None:
        context, _ = _context_for(topic)
        st.session_state[f"{mode}_context"] = context
        with st.chat_message("assistant"):
            text = st.write_stream(core.chat(_question_messages(topic, style, context), stream=True))
        st.session_state[f"{mode}_question"] = text
    else:
        with st.chat_message("assistant"):
            st.markdown(st.session_state[f"{mode}_question"])

    phase = st.session_state.get(f"{mode}_phase", "ask")

    if phase == "ask":
        with st.form(key=f"{mode}_form_{idx}", clear_on_submit=False):
            answer = st.text_area("Your answer", height=140, key=f"{mode}_answer_{idx}")
            cols = st.columns([1, 1, 4])
            submit = cols[0].form_submit_button("Submit", type="primary")
            skip = cols[1].form_submit_button("Skip")
        if submit and answer.strip():
            question = st.session_state[f"{mode}_question"]
            ctx = st.session_state[f"{mode}_context"]
            with st.chat_message("assistant"):
                feedback = st.write_stream(
                    core.chat(_grade_messages(topic, question, answer, ctx), stream=True)
                )
            match = SCORE_RE.search(feedback)
            score = int(match.group(1)) if match else 3
            learner.record_result(topic, score, lab)
            st.session_state[f"{mode}_scores"].append(score)
            st.session_state[f"{mode}_last_score"] = score
            st.session_state[f"{mode}_feedback"] = feedback
            st.session_state[f"{mode}_phase"] = "graded"
            st.rerun()
        elif skip:
            _advance(mode)
            st.rerun()

    elif phase == "graded":
        feedback = st.session_state.get(f"{mode}_feedback", "")
        if feedback:
            with st.chat_message("assistant"):
                st.markdown(feedback)
        score = st.session_state.get(f"{mode}_last_score", 3)
        new_row = learner.get_topic(topic) or {}
        m = learner.mastery_pct(new_row)
        st.markdown(f"**Scored {score}/5** — mastery for _{topic}_ is now **{m}%** {_mastery_color(m)}")
        st.progress(m / 100)
        if st.button("Next question ▶️", key=f"{mode}_next_{idx}", type="primary"):
            _advance(mode)
            st.rerun()


def _advance(mode: str) -> None:
    st.session_state[f"{mode}_idx"] += 1
    st.session_state[f"{mode}_question"] = None
    st.session_state[f"{mode}_feedback"] = None
    st.session_state[f"{mode}_phase"] = "ask"


def _lab_options() -> list[str]:
    labs = sorted({r.get("lab", "ad-hoc") for r in learner.all_topics()})
    return ["(everything I need most)"] + labs


def page_study() -> None:
    st.header("🧠 Adaptive study session")
    st.caption("The coach picks what you most need (due + weak), asks, and grades you.")
    if not _require_services():
        return

    if not st.session_state.get("study_active"):
        c1, c2 = st.columns(2)
        lab_choice = c1.selectbox("Focus", _lab_options(), key="study_lab_sel")
        rounds = c2.slider("Questions", 3, 10, 5, key="study_rounds")
        if st.button("▶️ Start session", type="primary"):
            lab = None if lab_choice.startswith("(") else lab_choice
            _start_session("study", lab, rounds)
            st.rerun()
    else:
        _run_session_ui("study", "recall", "Adaptive study", "🧠")
        if st.button("End session", key="study_end"):
            st.session_state["study_active"] = False
            st.rerun()


def page_interview() -> None:
    st.header("🎤 Mock interview")
    st.caption("Several scored questions, then an honest hire / no-hire verdict.")
    if not _require_services():
        return

    if not st.session_state.get("interview_active"):
        c1, c2 = st.columns(2)
        lab_choice = c1.selectbox("Focus area", _lab_options(), key="iv_lab_sel")
        rounds = c2.slider("Questions", 3, 10, 5, key="iv_rounds")
        if st.button("🎬 Start interview", type="primary"):
            lab = None if lab_choice.startswith("(") else lab_choice
            _start_session("interview", lab, rounds)
            st.rerun()
    else:
        _run_session_ui("interview", "interview-style", "Mock interview", "🎤")
        if st.button("End interview", key="iv_end"):
            st.session_state["interview_active"] = False
            st.rerun()


# --------------------------------------------------------------------------- #
# Ask
# --------------------------------------------------------------------------- #

def page_ask() -> None:
    st.header("💬 Ask the coach")
    st.caption("Grounded in your labs. Great for a quick explanation.")
    if not _require_services():
        return

    if "ask_history" not in st.session_state:
        st.session_state["ask_history"] = []

    for msg in st.session_state["ask_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    question = st.chat_input("e.g. how do readiness and liveness probes differ?")
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        st.session_state["ask_history"].append({"role": "user", "content": question})

        context, hits = _context_for(question, k=config.TOP_K)
        messages = [
            {"role": "system", "content": TUTOR_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Context from my labs:\n\n{context}\n\nQuestion: {question}\n\n"
                    "Explain clearly, then end with one short check-question (don't answer it)."
                ),
            },
        ]
        with st.chat_message("assistant"):
            answer = st.write_stream(core.chat(messages, stream=True))
            labs = sorted({h["meta"].get("lab", "?") for h in hits})
            st.caption("Sources: " + ", ".join(labs))
        st.session_state["ask_history"].append({"role": "assistant", "content": answer})


# --------------------------------------------------------------------------- #
# Router
# --------------------------------------------------------------------------- #

if page == "📊 Dashboard":
    page_dashboard()
elif page == "🧠 Study":
    page_study()
elif page == "🎤 Mock interview":
    page_interview()
elif page == "💬 Ask":
    page_ask()
