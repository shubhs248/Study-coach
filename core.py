"""
Shared helpers: Ollama embeddings/chat and the local Chroma vector store.

Kept deliberately small and dependency-light so it runs on a modest laptop.
"""

from __future__ import annotations

import sys
from typing import Iterable

import chromadb
import ollama

import config

# A single Ollama client pointed at your local server.
_client = ollama.Client(host=config.OLLAMA_HOST)


def ollama_up() -> bool:
    """Return True if the local Ollama server is reachable."""
    try:
        _client.list()
        return True
    except Exception:
        return False


def require_ollama() -> None:
    """Exit with a friendly message if Ollama isn't running."""
    if not ollama_up():
        print(
            "Could not reach Ollama at "
            f"{config.OLLAMA_HOST}.\n"
            "  1. Install it from https://ollama.com\n"
            "  2. Start it (it usually runs in the background after install)\n"
            f"  3. Pull the models:\n"
            f"       ollama pull {config.CHAT_MODEL}\n"
            f"       ollama pull {config.EMBED_MODEL}",
            file=sys.stderr,
        )
        sys.exit(1)


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts with the local embedding model."""
    vectors: list[list[float]] = []
    for text in texts:
        resp = _client.embeddings(model=config.EMBED_MODEL, prompt=text)
        vectors.append(resp["embedding"])
    return vectors


def chat(messages: list[dict], stream: bool = True):
    """Send a chat request to the local model. Yields text chunks if streaming."""
    if stream:
        for part in _client.chat(model=config.CHAT_MODEL, messages=messages, stream=True):
            yield part["message"]["content"]
    else:
        resp = _client.chat(model=config.CHAT_MODEL, messages=messages, stream=False)
        yield resp["message"]["content"]


def get_collection(create: bool = False):
    """Open (or create) the persistent Chroma collection."""
    db = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    if create:
        return db.get_or_create_collection(
            name=config.COLLECTION, metadata={"hnsw:space": "cosine"}
        )
    return db.get_collection(name=config.COLLECTION)


def retrieve(question: str, top_k: int | None = None) -> list[dict]:
    """Return the most relevant lab chunks for a question."""
    top_k = top_k or config.TOP_K
    collection = get_collection(create=False)
    q_vec = embed([question])[0]
    res = collection.query(query_embeddings=[q_vec], n_results=top_k)

    hits: list[dict] = []
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        hits.append({"text": doc, "meta": meta, "distance": dist})
    return hits


def batched(items: list, size: int) -> Iterable[list]:
    """Yield successive size-length chunks from items."""
    for i in range(0, len(items), size):
        yield items[i : i + size]
