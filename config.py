"""
Central configuration for the DevOps Study Coach.

Everything here can be overridden with environment variables, so you never
have to edit code to point it at a different machine, model, or labs folder.
"""

import os
from pathlib import Path

# --- Paths -----------------------------------------------------------------

# Where this project lives.
PROJECT_DIR = Path(__file__).resolve().parent


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines from a .env file without overriding real env vars.

    Written by `setup.py` when you pick a hardware profile, so your choice
    persists across runs. We avoid the python-dotenv dependency on purpose.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Real environment variables always win over the .env file.
        os.environ.setdefault(key, value)


# Apply saved choices (if any) before we read configuration below.
_load_env_file(PROJECT_DIR / ".env")

# Root folder that contains your practice labs. By default we look one level
# up (the folder that holds devops-study-coach alongside the *-lab folders).
LABS_ROOT = Path(os.getenv("COACH_LABS_ROOT", PROJECT_DIR.parent)).resolve()

# Which sub-folders (relative to LABS_ROOT) to index.
#   "auto" (default) = every sub-folder whose name ends in "-lab" or "-labs".
#   Or set a comma-separated list, e.g. "docker-practice-lab,terraform-practice-lab".
# "auto" means it works whether your labs are siblings of this project OR live
# inside a single cloned `devops-practice-labs` repo (just point COACH_LABS_ROOT there).
LAB_FOLDERS = os.getenv("COACH_LAB_FOLDERS", "auto").split(",")


def resolve_lab_folders() -> list[str]:
    """Turn the LAB_FOLDERS setting into a concrete list of folder names."""
    raw = [f.strip() for f in LAB_FOLDERS if f.strip()]
    if len(raw) == 1 and raw[0].lower() == "auto":
        try:
            return [
                p.name
                for p in sorted(LABS_ROOT.iterdir())
                if p.is_dir() and (p.name.endswith("-lab") or p.name.endswith("-labs"))
            ]
        except OSError:
            return []
    return raw

# Where the local vector database is stored (created on first ingest).
CHROMA_DIR = Path(os.getenv("COACH_DB_DIR", PROJECT_DIR / "chroma_db")).resolve()
COLLECTION = os.getenv("COACH_COLLECTION", "devops_labs")

# --- Models (served locally by Ollama) -------------------------------------

# Small, CPU-friendly defaults chosen for a laptop without a dedicated GPU.
# Bump these on a stronger machine, e.g. CHAT_MODEL=llama3.1:8b
CHAT_MODEL = os.getenv("COACH_CHAT_MODEL", "llama3.2:3b")
EMBED_MODEL = os.getenv("COACH_EMBED_MODEL", "nomic-embed-text")

# Ollama server location (default is the local one Ollama starts for you).
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# --- Retrieval / chunking knobs --------------------------------------------

CHUNK_SIZE = int(os.getenv("COACH_CHUNK_SIZE", "1200"))      # characters per chunk
CHUNK_OVERLAP = int(os.getenv("COACH_CHUNK_OVERLAP", "150"))  # overlap between chunks
TOP_K = int(os.getenv("COACH_TOP_K", "5"))                   # chunks fed to the model

# File types we treat as study material.
INCLUDE_EXTENSIONS = {".md", ".markdown"}
