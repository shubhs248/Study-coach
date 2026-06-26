"""
Ingest your practice-lab markdown into a local vector database.

Run this once (and again whenever you update your labs):

    python ingest.py

It walks each lab folder, splits the markdown into overlapping chunks,
embeds them with your local embedding model, and stores everything in a
file-based Chroma DB inside this project. Nothing leaves your machine.
"""

from __future__ import annotations

import hashlib
import re

from rich.console import Console
from rich.progress import track

import config
import core

console = Console()


def find_markdown_files() -> list:
    """Collect markdown files from every configured lab folder."""
    files: list = []
    folders = config.resolve_lab_folders()
    if not folders:
        console.print(
            f"[yellow]No lab folders found under[/] {config.LABS_ROOT}.\n"
            "Set COACH_LABS_ROOT to the folder that holds your *-lab folders "
            "(e.g. your cloned devops-practice-labs repo)."
        )
    for folder in folders:
        folder = folder.strip()
        if not folder:
            continue
        lab_dir = config.LABS_ROOT / folder
        if not lab_dir.exists():
            console.print(f"[yellow]skip[/] {folder} (not found at {lab_dir})")
            continue
        for path in lab_dir.rglob("*"):
            if path.suffix.lower() in config.INCLUDE_EXTENSIONS and path.is_file():
                files.append(path)
    return files


def split_into_chunks(text: str) -> list[str]:
    """Split on headings first, then pack into ~CHUNK_SIZE pieces with overlap."""
    # Break the document at markdown headings so chunks stay topically coherent.
    sections = re.split(r"(?m)^(?=#{1,6}\s)", text)

    chunks: list[str] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= config.CHUNK_SIZE:
            chunks.append(section)
            continue
        # Section is large: slide a window over it.
        start = 0
        while start < len(section):
            end = start + config.CHUNK_SIZE
            chunks.append(section[start:end])
            start = end - config.CHUNK_OVERLAP
    return chunks


def first_heading(text: str) -> str:
    """Best-effort title for a chunk, used when citing sources."""
    match = re.search(r"(?m)^#{1,6}\s+(.+)$", text)
    return match.group(1).strip() if match else ""


def main() -> None:
    core.require_ollama()

    files = find_markdown_files()
    if not files:
        console.print("[red]No markdown found.[/] Check COACH_LABS_ROOT / LAB_FOLDERS in config.py")
        return

    console.print(f"Found [bold]{len(files)}[/] markdown files. Building index...\n")

    collection = core.get_collection(create=True)

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:  # pragma: no cover - defensive
            console.print(f"[yellow]skip[/] {path}: {exc}")
            continue

        rel = path.relative_to(config.LABS_ROOT)
        lab = rel.parts[0] if rel.parts else "unknown"

        for i, chunk in enumerate(split_into_chunks(text)):
            uid = hashlib.sha1(f"{rel}-{i}".encode()).hexdigest()
            ids.append(uid)
            documents.append(chunk)
            metadatas.append(
                {
                    "lab": lab,
                    "source": str(rel).replace("\\", "/"),
                    "heading": first_heading(chunk),
                }
            )

    console.print(f"Embedding [bold]{len(documents)}[/] chunks with [cyan]{config.EMBED_MODEL}[/]...")

    # Embed + upsert in batches so we don't hold everything in memory at once.
    batch = 32
    for start in track(range(0, len(documents), batch), description="Indexing"):
        d = documents[start : start + batch]
        vectors = core.embed(d)
        collection.upsert(
            ids=ids[start : start + batch],
            documents=d,
            metadatas=metadatas[start : start + batch],
            embeddings=vectors,
        )

    console.print(
        f"\n[green]Done.[/] Indexed {len(documents)} chunks into "
        f"[bold]{config.COLLECTION}[/] at {config.CHROMA_DIR}"
    )
    console.print("Now run: [bold]python coach.py[/]")


if __name__ == "__main__":
    main()
