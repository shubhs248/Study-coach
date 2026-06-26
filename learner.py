"""
The learner model - what makes this a tutor, not a chatbot.

It remembers you across sessions: per-topic mastery, accuracy, and a
spaced-repetition schedule (SM-2) so weak topics resurface at the right time.
Everything is stored locally in a small SQLite file (no server, git-ignored).

This is the single biggest thing a generic ChatGPT/Claude/Gemini tutor lacks:
persistent, personalized memory of *your* progress.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config

DB_PATH = Path(config.PROJECT_DIR) / "learner.db"

# A curated starter set of topics per lab so the adaptive engine always has
# something sensible to suggest. New topics are added automatically whenever
# you study something not in this list.
SEED_TOPICS: dict[str, list[str]] = {
    "linux-shell-practice-lab": [
        "file permissions and chmod",
        "pipes and redirection",
        "grep, awk and sed",
        "process management and signals",
        "shell loops and conditionals",
    ],
    "python-devops-practice-lab": [
        "parsing JSON and YAML in Python",
        "the subprocess module",
        "log parsing with regex",
        "reading and writing files safely",
        "error handling and exit codes",
    ],
    "git-scenarios-lab": [
        "resolving merge conflicts",
        "interactive rebase",
        "git reflog recovery",
        "git bisect",
        "branching strategies",
    ],
    "yaml-practice-lab": [
        "YAML anchors and aliases",
        "common YAML gotchas",
        "multi-document YAML",
        "data types and quoting",
    ],
    "groovy-practice-lab": [
        "Jenkins declarative pipelines",
        "Jenkins scripted pipelines",
        "Groovy closures",
        "shared libraries",
    ],
    "docker-practice-lab": [
        "multi-stage builds",
        "image layers and caching",
        "Dockerfile best practices",
        "Docker Compose basics",
        "reducing image size",
    ],
    "kubernetes-practice-lab": [
        "readiness and liveness probes",
        "debugging CrashLoopBackOff",
        "services and networking",
        "deployments and rollouts",
        "requests and limits",
    ],
    "terraform-practice-lab": [
        "state and drift",
        "modules",
        "the plan/apply workflow",
        "variables and outputs",
        "remote backends",
    ],
    "cloud-fundamentals-lab": [
        "core compute services (AWS/Azure/GCP)",
        "IAM and least privilege",
        "object storage basics",
        "VPC and networking basics",
    ],
    "system-design-practice-lab": [
        "designing a CI/CD pipeline",
        "designing an observability platform",
        "rate limiting",
        "high availability and scaling",
        "the 7-step design framework",
    ],
}

DEFAULT_EASE = 2.5
MIN_EASE = 1.3


DAILY_GOAL = 10  # questions/day target shown in the UI; tune to taste


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _today_str() -> str:
    return _now().date().isoformat()


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(seed: bool = True) -> None:
    """Create the table and (optionally) seed starter topics."""
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS topics (
                name        TEXT PRIMARY KEY,
                lab         TEXT,
                reps        INTEGER NOT NULL DEFAULT 0,
                ease        REAL    NOT NULL DEFAULT 2.5,
                interval    REAL    NOT NULL DEFAULT 0,
                due         TEXT,
                attempts    INTEGER NOT NULL DEFAULT 0,
                correct     INTEGER NOT NULL DEFAULT 0,
                last_score  INTEGER,
                created     TEXT,
                updated     TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activity (
                day      TEXT PRIMARY KEY,
                answered INTEGER NOT NULL DEFAULT 0
            )
            """
        )
    if seed:
        for lab, topics in SEED_TOPICS.items():
            for topic in topics:
                ensure_topic(topic, lab)


def ensure_topic(name: str, lab: str = "ad-hoc") -> None:
    """Insert a topic if it doesn't exist yet (due immediately)."""
    name = name.strip().lower()
    if not name:
        return
    now = _iso(_now())
    with _conn() as conn:
        existing = conn.execute("SELECT name FROM topics WHERE name = ?", (name,)).fetchone()
        if existing:
            return
        conn.execute(
            "INSERT INTO topics (name, lab, due, created, updated) VALUES (?, ?, ?, ?, ?)",
            (name, lab, now, now, now),
        )


def get_topic(name: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM topics WHERE name = ?", (name.strip().lower(),)).fetchone()
        return dict(row) if row else None


def mastery_pct(row: dict) -> int:
    """A friendly 0-100 mastery estimate from reps, ease and accuracy."""
    attempts = row.get("attempts", 0) or 0
    if attempts == 0:
        return 0
    accuracy = (row.get("correct", 0) or 0) / attempts
    reps = row.get("reps", 0) or 0
    rep_factor = min(reps / 5.0, 1.0)  # ~5 good reps = strong familiarity
    ease_factor = (row.get("ease", DEFAULT_EASE) - MIN_EASE) / (3.0 - MIN_EASE)
    ease_factor = max(0.0, min(ease_factor, 1.0))
    score = 0.6 * accuracy + 0.3 * rep_factor + 0.1 * ease_factor
    return int(round(score * 100))


def record_result(name: str, quality: int, lab: str = "ad-hoc") -> dict:
    """Update a topic with an answer quality (0-5) using the SM-2 algorithm."""
    name = name.strip().lower()
    ensure_topic(name, lab)
    quality = max(0, min(5, int(quality)))

    row = get_topic(name) or {}
    ease = row.get("ease", DEFAULT_EASE) or DEFAULT_EASE
    reps = row.get("reps", 0) or 0
    interval = row.get("interval", 0) or 0

    if quality < 3:
        # Got it wrong: reset the streak, see it again very soon.
        reps = 0
        interval = 1
    else:
        if reps == 0:
            interval = 1
        elif reps == 1:
            interval = 6
        else:
            interval = round(interval * ease)
        reps += 1
        # SM-2 ease adjustment.
        ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        ease = max(MIN_EASE, ease)

    due = _now() + timedelta(days=max(interval, 0.5))
    attempts = (row.get("attempts", 0) or 0) + 1
    correct = (row.get("correct", 0) or 0) + (1 if quality >= 3 else 0)
    now = _iso(_now())

    with _conn() as conn:
        conn.execute(
            """
            UPDATE topics
            SET reps = ?, ease = ?, interval = ?, due = ?, attempts = ?,
                correct = ?, last_score = ?, updated = ?
            WHERE name = ?
            """,
            (reps, ease, interval, _iso(due), attempts, correct, quality, now, name),
        )
    log_activity(1)
    return get_topic(name) or {}


# --------------------------------------------------------------------------- #
# Activity, streaks and daily goal
# --------------------------------------------------------------------------- #

def log_activity(count: int = 1) -> None:
    """Record that you answered `count` questions today (for streaks/goals)."""
    day = _today_str()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO activity (day, answered) VALUES (?, ?)
            ON CONFLICT(day) DO UPDATE SET answered = answered + ?
            """,
            (day, count, count),
        )


def today_count() -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT answered FROM activity WHERE day = ?", (_today_str(),)
        ).fetchone()
    return int(row["answered"]) if row else 0


def get_streak() -> int:
    """Consecutive days (ending today or yesterday) with at least one answer."""
    from datetime import date, timedelta as _td

    with _conn() as conn:
        rows = conn.execute(
            "SELECT day FROM activity WHERE answered > 0"
        ).fetchall()
    days = set()
    for r in rows:
        try:
            days.add(date.fromisoformat(r["day"]))
        except (ValueError, TypeError):
            continue
    if not days:
        return 0

    today = _now().date()
    # Allow the streak to count even if today hasn't been studied yet.
    start = today if today in days else today - _td(days=1)
    if start not in days:
        return 0
    streak = 0
    cursor = start
    while cursor in days:
        streak += 1
        cursor -= _td(days=1)
    return streak


def activity_recent(days: int = 30) -> list[dict]:
    """Answered-count per day for the last `days` days (oldest first)."""
    from datetime import date, timedelta as _td

    with _conn() as conn:
        rows = conn.execute("SELECT day, answered FROM activity").fetchall()
    counts = {r["day"]: int(r["answered"]) for r in rows}
    today = _now().date()
    out: list[dict] = []
    for i in range(days - 1, -1, -1):
        d = today - _td(days=i)
        out.append({"day": d.isoformat(), "answered": counts.get(d.isoformat(), 0)})
    return out


def due_topics(limit: int = 20) -> list[dict]:
    """Topics whose review is due (or never studied), soonest first."""
    now = _iso(_now())
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM topics WHERE due IS NULL OR due <= ? ORDER BY due ASC LIMIT ?",
            (now, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def weak_topics(limit: int = 20) -> list[dict]:
    """Topics with the lowest mastery (only those you've actually attempted)."""
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM topics WHERE attempts > 0").fetchall()
    rows = [dict(r) for r in rows]
    rows.sort(key=mastery_pct)
    return rows[:limit]


def pick_study_topics(n: int = 5, lab: str | None = None) -> list[dict]:
    """Choose what to study next: due items first, then never-seen, then weak."""
    with _conn() as conn:
        if lab:
            rows = conn.execute("SELECT * FROM topics WHERE lab = ?", (lab,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM topics").fetchall()
    rows = [dict(r) for r in rows]
    now = _now()

    def sort_key(r: dict):
        attempts = r.get("attempts", 0) or 0
        due = r.get("due")
        try:
            due_dt = datetime.fromisoformat(due) if due else now
        except ValueError:
            due_dt = now
        is_due = due_dt <= now
        # Priority: due (0) before not-due (1); never-attempted before attempted;
        # then lower mastery; then earliest due.
        return (0 if is_due else 1, attempts > 0, mastery_pct(r), due_dt)

    rows.sort(key=sort_key)
    return rows[:n]


def all_topics() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM topics ORDER BY lab, name").fetchall()
    return [dict(r) for r in rows]


def lab_mastery() -> list[dict]:
    """Average mastery per lab (only counting topics you've attempted)."""
    rows = all_topics()
    by_lab: dict[str, list[int]] = {}
    for r in rows:
        if (r.get("attempts", 0) or 0) == 0:
            continue
        by_lab.setdefault(r.get("lab", "ad-hoc"), []).append(mastery_pct(r))
    return [
        {"lab": lab, "mastery": round(sum(v) / len(v))}
        for lab, v in sorted(by_lab.items())
    ]


def stats() -> dict:
    rows = all_topics()
    studied = [r for r in rows if (r.get("attempts", 0) or 0) > 0]
    total_attempts = sum(r.get("attempts", 0) or 0 for r in rows)
    total_correct = sum(r.get("correct", 0) or 0 for r in rows)
    avg_mastery = round(sum(mastery_pct(r) for r in studied) / len(studied)) if studied else 0
    return {
        "topics_total": len(rows),
        "topics_studied": len(studied),
        "due_now": len(due_topics(limit=10_000)),
        "total_attempts": total_attempts,
        "accuracy": round(100 * total_correct / total_attempts) if total_attempts else 0,
        "avg_mastery": avg_mastery,
    }
