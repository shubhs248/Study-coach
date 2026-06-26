"""
DevOps Study Coach - a local, offline tutor that beats a generic chatbot.

Why it's better than asking ChatGPT/Claude/Gemini to "be my tutor":
  * It remembers you. A persistent learner model tracks mastery per topic.
  * It schedules. Spaced repetition (SM-2) resurfaces weak topics at the right time.
  * It teaches, not tells. Socratic prompts force active recall, then grade you.
  * It's grounded. Every answer is built from YOUR practice labs, with sources.
  * It's private & free. Runs fully offline on your machine via Ollama.

Modes (type these at the prompt):
    study [lab]         Adaptive session: it picks what you most need to revise.
    interview [lab]     Mock interview: several questions, scored, with a summary.
    quiz <topic>        One graded question on a topic.
    exercise <topic>    A hands-on exercise + solution.
    ask <question>      Explain a concept, grounded in your labs (also the default).
    progress            Your mastery dashboard (what's strong / weak / due).
    topics              List tracked topics.
    sources             Show the lab sources used for the last answer.
    help                Show this help.
    exit / quit         Leave.

Just typing a plain question is treated as `ask`.
"""

from __future__ import annotations

import re
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

import config
import core
import learner

console = Console()
_last_sources: list[dict] = []

SCORE_RE = re.compile(r"SCORE\s*[:=]\s*([0-5])", re.IGNORECASE)


TUTOR_SYSTEM = (
    "You are the DevOps Study Coach, an expert, demanding-but-kind tutor for a "
    "Senior DevOps & Platform Engineer who is revising. Follow these principles:\n"
    "1. Teach with active recall: prefer guiding questions and hints over walls of text.\n"
    "2. Be grounded: use the provided context from the user's OWN labs. If context is "
    "thin, say so and clearly label any guidance as 'beyond your labs'.\n"
    "3. Be concrete: prefer real commands, short examples, and gotchas over theory.\n"
    "4. Be concise and plain-English. Format with markdown. No filler.\n"
    "5. Be honest: never inflate praise; point out exactly what was missing."
)


def _context_block(hits: list[dict]) -> str:
    parts = []
    for i, h in enumerate(hits, 1):
        src = h["meta"].get("source", "?")
        head = h["meta"].get("heading", "")
        label = f"[{i}] {src}" + (f"  ({head})" if head else "")
        parts.append(f"{label}\n{h['text']}")
    return "\n\n---\n\n".join(parts)


def _stream_answer(messages: list[dict]) -> str:
    """Stream the model's reply to the terminal and return the full text."""
    buffer = ""
    console.print()
    for token in core.chat(messages, stream=True):
        buffer += token
        console.print(token, end="", soft_wrap=True)
    console.print("\n")
    return buffer


def _retrieve_context(query: str, k: int | None = None) -> tuple[str, list[dict]]:
    global _last_sources
    hits = core.retrieve(query, top_k=k or config.TOP_K)
    _last_sources = hits
    return _context_block(hits), hits


def _lab_of(hits: list[dict]) -> str:
    for h in hits:
        lab = h["meta"].get("lab")
        if lab:
            return lab
    return "ad-hoc"


# --------------------------------------------------------------------------- #
# Core graded-question loop (shared by study / interview / quiz)
# --------------------------------------------------------------------------- #

def _ask_one_question(topic: str, style: str, context: str) -> str:
    messages = [
        {"role": "system", "content": TUTOR_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Context from my labs:\n\n{context}\n\n"
                f"Ask me ONE {style} question about '{topic}'. Make it specific and "
                "practical. Ask the question only - do NOT reveal or hint at the answer yet."
            ),
        },
    ]
    return _stream_answer(messages)


def _grade(topic: str, question_text: str, user_answer: str, context: str) -> int:
    messages = [
        {"role": "system", "content": TUTOR_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Context from my labs:\n\n{context}\n\n"
                f"You asked: {question_text}\n\n"
                f"My answer: {user_answer}\n\n"
                "Grade my answer. Respond in this exact format:\n"
                "SCORE: <0-5>   (5=perfect, 4=minor gap, 3=acceptable, "
                "2=partly wrong, 1=mostly wrong, 0=no idea/blank)\n"
                "Then 2-4 lines: what was right, what was missing (the correct "
                "answer grounded in the context), and one quick tip to remember it."
            ),
        },
    ]
    feedback = _stream_answer(messages)
    match = SCORE_RE.search(feedback)
    return int(match.group(1)) if match else 3


def _graded_round(topic: str, style: str, lab: str = "ad-hoc") -> int | None:
    """Run one ask -> answer -> grade -> record cycle. Returns score or None if skipped."""
    context, hits = _retrieve_context(topic, k=max(config.TOP_K, 6))
    if lab == "ad-hoc":
        lab = _lab_of(hits)

    console.rule(f"[bold]{topic}[/]")
    question_text = _ask_one_question(topic, style, context)

    user_answer = Prompt.ask("[bold cyan]Your answer[/] [dim](or 'skip'/'stop')[/]")
    cmd = user_answer.strip().lower()
    if cmd == "stop":
        return None
    if cmd == "skip" or not cmd:
        console.print("[dim]Skipped.[/]")
        return None

    score = _grade(topic, question_text, user_answer, context)
    row = learner.record_result(topic, score, lab)
    mastery = learner.mastery_pct(row)
    bar = _mastery_bar(mastery)
    console.print(f"[dim]Scored {score}/5 - mastery for '{topic}': {bar} {mastery}%[/]")
    return score


def _mastery_bar(pct: int, width: int = 12) -> str:
    filled = int(round(pct / 100 * width))
    return "[green]" + "#" * filled + "[/]" + "[dim]" + "." * (width - filled) + "[/]"


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #

def ask(question: str) -> None:
    context, hits = _retrieve_context(question)
    messages = [
        {"role": "system", "content": TUTOR_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Context from my labs:\n\n{context}\n\nQuestion: {question}\n\n"
                "Explain clearly, then end with a single short check-question to test "
                "my understanding (don't answer that check-question)."
            ),
        },
    ]
    _stream_answer(messages)
    labs = sorted({h["meta"].get("lab", "?") for h in hits})
    console.print(f"[dim]Sources: {', '.join(labs)}  -  type 'sources' for details[/]")


def quiz(topic: str) -> None:
    _graded_round(topic, style="quiz", lab="ad-hoc")


def study(lab: str | None = None, rounds: int = 5) -> None:
    learner.init_db()
    picks = learner.pick_study_topics(n=rounds, lab=lab)
    if not picks:
        console.print("[dim]No topics found. Try `quiz <topic>` to start one.[/]")
        return

    console.print(
        Panel.fit(
            f"[bold]Adaptive study session[/] - {len(picks)} topics "
            f"{'(' + lab + ')' if lab else '(picked from what you most need)'}\n"
            "Answer each, or type 'skip' / 'stop'.",
            border_style="green",
        )
    )

    scores: list[int] = []
    for row in picks:
        result = _graded_round(row["name"], style="recall", lab=row.get("lab", "ad-hoc"))
        if result is None and Prompt.ask("[dim]Continue session?[/]", choices=["y", "n"], default="y") == "n":
            break
        if result is not None:
            scores.append(result)

    if scores:
        avg = sum(scores) / len(scores)
        console.print(
            Panel.fit(
                f"Session done. Answered {len(scores)} - average {avg:.1f}/5.\n"
                "Weak topics will come back sooner. Run [bold]progress[/] to see your map.",
                border_style="green",
            )
        )


def interview(lab: str | None = None, rounds: int = 5) -> None:
    learner.init_db()
    # Prefer a focused lab; otherwise mix due/weak topics for a broad interview.
    picks = learner.pick_study_topics(n=rounds, lab=lab)
    if not picks:
        console.print("[dim]No topics to interview on yet.[/]")
        return

    console.print(
        Panel.fit(
            f"[bold]Mock interview[/] - {len(picks)} questions "
            f"{'on ' + lab if lab else '(mixed DevOps/SRE)'}\n"
            "Answer like you would to an interviewer. Type 'stop' to end early.",
            border_style="magenta",
        )
    )

    scores: list[int] = []
    for i, row in enumerate(picks, 1):
        console.print(f"\n[bold magenta]Question {i}/{len(picks)}[/]")
        result = _graded_round(row["name"], style="interview-style", lab=row.get("lab", "ad-hoc"))
        if result is None and i < len(picks):
            if Prompt.ask("[dim]Continue interview?[/]", choices=["y", "n"], default="y") == "n":
                break
        if result is not None:
            scores.append(result)

    if scores:
        avg = sum(scores) / len(scores)
        verdict = (
            "Strong hire" if avg >= 4.3 else
            "Hire" if avg >= 3.5 else
            "Lean no - more prep needed" if avg >= 2.5 else
            "No - revise the fundamentals"
        )
        console.print(
            Panel.fit(
                f"[bold]Interview summary[/]\n"
                f"Questions answered: {len(scores)}\n"
                f"Average score: {avg:.1f}/5\n"
                f"Verdict: [bold]{verdict}[/]\n"
                "Run [bold]progress[/] to see which areas dragged you down.",
                border_style="magenta",
            )
        )


def exercise(topic: str) -> None:
    context, _ = _retrieve_context(topic, k=max(config.TOP_K, 6))
    messages = [
        {"role": "system", "content": TUTOR_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Context from my labs:\n\n{context}\n\n"
                f"Design ONE realistic, hands-on exercise about '{topic}' I can do "
                "for free on my own machine. Include: a scenario, clear tasks, "
                "success criteria, and a 'Solution' section at the very end."
            ),
        },
    ]
    _stream_answer(messages)


def progress() -> None:
    learner.init_db()
    s = learner.stats()
    console.print(
        Panel.fit(
            f"Topics tracked: [bold]{s['topics_total']}[/]   "
            f"studied: [bold]{s['topics_studied']}[/]   "
            f"due now: [bold]{s['due_now']}[/]\n"
            f"Total questions answered: [bold]{s['total_attempts']}[/]   "
            f"accuracy: [bold]{s['accuracy']}%[/]   "
            f"avg mastery: [bold]{s['avg_mastery']}%[/]",
            title="Your progress",
            border_style="cyan",
        )
    )

    studied = [r for r in learner.all_topics() if (r.get("attempts", 0) or 0) > 0]
    if not studied:
        console.print("[dim]Nothing studied yet. Try `study` or `interview` to begin.[/]")
        return

    studied.sort(key=learner.mastery_pct)
    table = Table(title="Topics (weakest first)")
    table.add_column("Topic")
    table.add_column("Lab", style="dim")
    table.add_column("Mastery")
    table.add_column("Acc.", justify="right")
    table.add_column("Seen", justify="right")
    table.add_column("Due", style="dim")
    for r in studied[:25]:
        m = learner.mastery_pct(r)
        acc = round(100 * (r.get("correct", 0) or 0) / (r.get("attempts", 1) or 1))
        due = (r.get("due") or "")[:10]
        table.add_row(
            r["name"], r.get("lab", ""), f"{_mastery_bar(m)} {m}%",
            f"{acc}%", str(r.get("attempts", 0)), due,
        )
    console.print(table)


def topics() -> None:
    learner.init_db()
    rows = learner.all_topics()
    table = Table(title=f"Tracked topics ({len(rows)})")
    table.add_column("Lab", style="dim")
    table.add_column("Topic")
    table.add_column("Mastery", justify="right")
    for r in rows:
        m = learner.mastery_pct(r) if (r.get("attempts", 0) or 0) > 0 else 0
        table.add_row(r.get("lab", ""), r["name"], f"{m}%")
    console.print(table)


def show_sources() -> None:
    if not _last_sources:
        console.print("[dim]No sources yet - ask something first.[/]")
        return
    for i, h in enumerate(_last_sources, 1):
        head = h["meta"].get("heading", "")
        title = f"[{i}] {h['meta'].get('source', '?')}" + (f" - {head}" if head else "")
        preview = h["text"][:400] + ("..." if len(h["text"]) > 400 else "")
        console.print(Panel(preview, title=title, border_style="dim"))


def help_text() -> None:
    console.print(Markdown(__doc__ or ""))


def ensure_index() -> None:
    try:
        core.get_collection(create=False)
    except Exception:
        console.print(
            "[red]No index found.[/] Run [bold]python ingest.py[/] first to build it."
        )
        sys.exit(1)


def main() -> None:
    core.require_ollama()
    ensure_index()
    learner.init_db()

    console.print(
        Panel.fit(
            "[bold]DevOps Study Coach[/]\n"
            f"chat: [cyan]{config.CHAT_MODEL}[/]  -  embed: [cyan]{config.EMBED_MODEL}[/]\n"
            "study / interview / quiz / exercise / ask / progress / topics / help / exit",
            border_style="green",
        )
    )

    handlers_with_arg = {
        "quiz": quiz,
        "exercise": exercise,
        "ask": ask,
    }

    while True:
        try:
            line = Prompt.ask("\n[bold green]coach>[/]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nBye!")
            break

        if not line:
            continue

        cmd, _, rest = line.partition(" ")
        cmd_lower = cmd.lower()
        rest = rest.strip()

        if cmd_lower in {"exit", "quit"}:
            console.print("Bye! Keep your streak going.")
            break
        elif cmd_lower == "help":
            help_text()
        elif cmd_lower == "sources":
            show_sources()
        elif cmd_lower == "progress":
            progress()
        elif cmd_lower == "topics":
            topics()
        elif cmd_lower == "study":
            study(lab=rest or None)
        elif cmd_lower == "interview":
            interview(lab=rest or None)
        elif cmd_lower in handlers_with_arg and rest:
            handlers_with_arg[cmd_lower](rest)
        else:
            ask(line)


if __name__ == "__main__":
    main()
