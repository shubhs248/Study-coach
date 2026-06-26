# 🎓 DevOps Study Coach

> A **100% free, open-source, fully-local** study agent that turns *your own*
> [DevOps practice labs](../devops-practice-labs) into an interactive tutor.
> It runs offline on a normal laptop — no GPU, no API keys, no cloud bills,
> nothing leaves your machine.

It reads your lab READMEs, cheatsheets, and interview Q&A, builds a local search
index, and then answers your questions, **quizzes** you, and generates **hands-on
exercises** — all grounded in the material *you* wrote, in your own plain-English
style.

---

## 🆚 Why this beats asking ChatGPT/Claude/Gemini to "be my tutor"

| | Generic chatbot | DevOps Study Coach |
|---|---|---|
| **Remembers you** | ❌ forgets every session | ✅ persistent learner model (mastery per topic) |
| **Schedules review** | ❌ never brings anything back | ✅ spaced repetition (SM-2) resurfaces weak topics |
| **Teaches vs. tells** | ⚠️ dumps answers | ✅ Socratic: asks, you answer, it grades honestly |
| **Grounded in your stuff** | ❌ generic | ✅ answers from *your* labs, with sources |
| **Tracks progress** | ❌ none | ✅ a mastery dashboard you can watch grow |
| **Private & free** | ❌ cloud, limits | ✅ 100% local, offline, no keys |

The big idea: real learning needs **memory + active recall + spaced repetition**.
A stateless chat can't do that. This can, because it keeps a small local model of
what *you* know in `learner.db`.

---

## 🧩 How it works

```
Your *-practice-lab markdown
        │  (ingest.py)
        ▼
  split into chunks ──► embed locally (Ollama) ──► Chroma vector DB (on disk)
        │
        ▼  (coach.py)
  your question ──► find relevant chunks ──► local LLM answers using them
        │
        ▼  (learner.py)
  grade your answers ──► update mastery + spaced-repetition schedule (learner.db)
```

- **[Ollama](https://ollama.com)** serves the models locally.
- **Chroma** stores the search index in a folder (`chroma_db/`).
- **No internet needed** after the one-time model download.

## 🛠️ Tech (all free & open source)

| Piece | Tool | Why |
|------|------|-----|
| Local LLM runtime | Ollama | Free, runs models on CPU |
| Chat model | `llama3.2:3b` | Small, fast, laptop-friendly |
| Embeddings | `nomic-embed-text` | Tiny, accurate, CPU-friendly |
| Vector DB | Chroma | File-based, zero setup |
| Terminal UI | Rich | Clean, readable output |

---

## 🚀 Setup (one time)

**1. Install Ollama** → <https://ollama.com/download> (Windows/macOS/Linux). After
installing it runs in the background.

**2. Install Python deps** (Python 3.10+):

```bash
cd devops-study-coach
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
```

**3. Pick your hardware profile** — this detects whether you have a GPU and how
much RAM you have, recommends the right model, and lets you choose:

```bash
python setup.py
```

You'll see something like:

```
Detected hardware
 GPU          No dedicated GPU detected (CPU only)
 RAM          16.0 GB
 Recommended  light - Light - CPU only / no GPU (8-16 GB RAM)
```

| Profile | Best for | Chat model |
|---------|----------|------------|
| `light` | CPU only / no GPU (8-16 GB) | `llama3.2:3b` |
| `mid` | 16-32 GB RAM or a modest GPU | `llama3.1:8b` |
| `strong` | Good GPU / 32 GB+ | `qwen2.5:14b` |

Your choice is saved to a local `.env` file, so the app remembers it. Re-run
`python setup.py` any time to change. Shortcuts: `python setup.py --auto`
(accept the recommendation) or `python setup.py --profile mid` (force one).

**4. Pull the models it recommended** (the setup screen prints the exact lines):

```bash
ollama pull llama3.2:3b        # whatever your profile chose
ollama pull nomic-embed-text
```

**5. Build the index from your labs:**

```bash
python ingest.py
```

`ingest.py` prints which lab folders it found. It looks for `*-lab` / `*-labs`
folders next to this project by default — if you cloned this on its own, see
[Running it on your home machine](#-running-it-on-your-home-machine-clone--setup)
to point `COACH_LABS_ROOT` at your labs.

---

## 💬 Use it

```bash
python coach.py
```

Then at the `coach>` prompt:

| Command | What it does |
|---------|--------------|
| `study` | **Adaptive session** — it picks what you most need to revise (due + weak topics), asks, grades, updates your mastery |
| `study kubernetes-practice-lab` | Same, focused on one lab |
| `interview` | **Mock interview** — several scored questions + a hire/no-hire summary |
| `interview docker-practice-lab` | Mock interview focused on one lab |
| `quiz docker multi-stage builds` | One graded question on a topic |
| `exercise git rebase` | Generates a hands-on exercise + solution |
| `how does a readiness probe work?` | Explains, grounded in your labs (default mode) |
| `progress` | **Your mastery dashboard** — strong/weak/due topics |
| `topics` | List all tracked topics |
| `sources` | Shows which lab files the last answer used |
| `help` | Shows all commands |
| `exit` | Quit |

## 🖥️ Prefer a browser? Use the UI

There's a full Streamlit app with a dashboard, charts, and the same study /
interview / ask modes — click instead of type.

```bash
streamlit run app.py
```

It gives you:
- **📊 Dashboard** — streak 🔥, daily goal, avg mastery, accuracy, mastery-by-lab
  and a 30-day activity chart, plus "due today" priorities and your weakest topics.
- **🧠 Study** — adaptive sessions with streamed questions and instant grading.
- **🎤 Mock interview** — scored sessions with a hire/no-hire verdict.
- **💬 Ask** — a chat view grounded in your labs, with sources.

Same local models, same `learner.db` — the CLI and UI share your progress.

### A typical learning loop

1. `study` — answer 5 adaptive questions; weak ones get scheduled to return sooner.
2. `progress` — watch your mastery bars climb over days/weeks.
3. `interview` — pressure-test yourself before a real interview.
4. Repeat. The coach keeps bringing back exactly what you keep getting wrong.

---

## ⚙️ Configuration

Most people just run `python setup.py` and never touch this. But every setting is
overridable with environment variables (which always win over the saved `.env`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `COACH_CHAT_MODEL` | `llama3.2:3b` | Set by `setup.py`; or override manually |
| `COACH_EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `COACH_LABS_ROOT` | parent folder | The folder that holds your `*-lab` folders |
| `COACH_LAB_FOLDERS` | `auto` | `auto` = index every `*-lab`/`*-labs` sub-folder, or a comma list |
| `COACH_TOP_K` | `5` | How many chunks feed the model |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |

Example (PowerShell):

```powershell
$env:COACH_CHAT_MODEL = "llama3.1:8b"; python coach.py
```

After changing which labs you index, or editing your labs, just re-run
`python ingest.py`.

---

## 🧳 Running it on your home machine (clone + setup)

The coach needs to *find your labs*. By default it looks for `*-lab` / `*-labs`
folders **next to** the `devops-study-coach` folder, so the easiest layout is:

```
my-study/
├── devops-study-coach/      # this repo
├── docker-practice-lab/     # your labs (siblings)
├── kubernetes-practice-lab/
└── ...
```

Two common ways to get there:

**Option A — labs as siblings (matches this project's layout):**

```bash
mkdir my-study && cd my-study
git clone https://github.com/<you>/devops-study-coach.git
git clone https://github.com/shubhs248/devops-practice-labs.git
# if your labs are subfolders of devops-practice-labs, point the coach at it:
#   PowerShell:  $env:COACH_LABS_ROOT = "$PWD\devops-practice-labs"
#   bash:        export COACH_LABS_ROOT="$PWD/devops-practice-labs"
```

**Option B — point at labs anywhere:** set `COACH_LABS_ROOT` to whatever folder
contains your `*-lab` folders, then run `python ingest.py`.

Then:

1. `cd devops-study-coach`
2. `pip install -r requirements.txt`
3. `python setup.py` — re-detects *this* machine's hardware (a beefier home PC can
   auto-pick a bigger model).
4. Pull the models it prints, then `python ingest.py`.
5. `python coach.py` (terminal) or `streamlit run app.py` (browser).

> Tip: run `python ingest.py` — it prints exactly which lab folders it found. If
> it finds none, fix `COACH_LABS_ROOT` and re-run.

The `chroma_db/`, `learner.db`, and `.env` are git-ignored and per-machine, so
they never need to travel with you.

---

## 🗺️ Roadmap / easy next steps

- ✅ **Mock interview mode** — scored sessions with a hire/no-hire summary.
- ✅ **Spaced repetition** — SM-2 learner model that resurfaces weak topics.
- ✅ **Streamlit UI** — browser dashboard with live mastery + activity charts.
- ✅ **Streaks & daily goals** — streak counter and a daily question goal.
- **Lab grader** — pipe your Dockerfile/YAML/Terraform through real linters + LLM feedback.
- **Export/import progress** — sync `learner.db` between machines.

---

Made for **Shubham Sharma** — Senior DevOps & Platform Engineer.
MIT licensed: free to use, fork, and share.
