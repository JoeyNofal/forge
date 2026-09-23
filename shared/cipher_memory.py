"""
CIPHER's permanent memory. Local ChromaDB, one collection.

Fixes Lesson #3 directly: only categories in
shared.memory_context.MEMORY_WORTHY_CATEGORIES ever get saved. The old
ATLAS/NEXUS memory saved every single turn unfiltered, which let a
wrong statement get recalled, restated, and re-saved until it became
the agent's confident "truth."

This module never labels retrieved memory as background — that's
chat.py's job via shared.memory_context.format_memory_context()
(Lesson #2). This module only stores and retrieves plain strings.
"""
import os
import uuid
from datetime import datetime

import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings
import requests

from shared.memory_context import is_memory_worthy

# D:\Projects\forge\memory\cipher on Youssef's machine.
CIPHER_MEMORY_PATH = os.getenv("CIPHER_MEMORY_PATH", r"D:\Projects\forge\memory\cipher")

# Embeddings run through Ollama (already installed/used for local chat
# models) instead of ChromaDB's default — keeps memory fully under the
# one local runtime, no separate model-download mechanism (Decision,
# Session 4: option 2 — local-first over convenience).
OLLAMA_EMBED_URL = os.getenv("OLLAMA_EMBED_URL", "http://localhost:11434/api/embeddings")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# Memory items are meant to be short, standalone facts (per CIPHER's own
# prompt instructions) — this also protects against nomic-embed-text's
# context limit, which a raw ~50,000-char save blew straight past
# (found in L5 testing, Session 4: Ollama returned a 500 rather than a
# usable error).
MAX_MEMORY_CONTENT_CHARS = 2000


class OllamaEmbeddingFunction(EmbeddingFunction):
    """Embeds text via a local Ollama server. Requires `ollama pull nomic-embed-text` once."""

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = []
        for text in input:
            try:
                response = requests.post(
                    OLLAMA_EMBED_URL,
                    json={"model": OLLAMA_EMBED_MODEL, "prompt": text},
                    timeout=30,
                )
                response.raise_for_status()
            except requests.exceptions.ConnectionError as e:
                raise RuntimeError(
                    "CIPHER's memory needs Ollama running locally to create embeddings "
                    f"(tried {OLLAMA_EMBED_URL}). Start Ollama and make sure "
                    f"`ollama pull {OLLAMA_EMBED_MODEL}` has been run."
                ) from e
            except requests.exceptions.HTTPError as e:
                raise RuntimeError(
                    f"Ollama rejected an embedding request ({e}). This usually means "
                    f"the content was too long — keep memory content under "
                    f"{MAX_MEMORY_CONTENT_CHARS} characters."
                ) from e
            embeddings.append(response.json()["embedding"])
        return embeddings


_client = None
_collection = None


def _get_collection():
    """Lazy connect — so importing this module never touches disk by itself."""
    global _client, _collection
    if _collection is None:
        os.makedirs(CIPHER_MEMORY_PATH, exist_ok=True)
        _client = chromadb.PersistentClient(path=CIPHER_MEMORY_PATH)
        _collection = _client.get_or_create_collection(
            name="cipher_memory", embedding_function=OllamaEmbeddingFunction()
        )
    return _collection


def save_memory(category: str, content: str, metadata: dict | None = None) -> bool:
    """
    Saves one memory item — but ONLY if `category` is in the shared
    worth-saving list. Returns True if it was actually saved, False if
    it was filtered out (wrong category, or empty content).

    This is the filter Lesson #3 says has to exist BEFORE the write,
    not as a cleanup pass after memory gets noisy.
    """
    if not is_memory_worthy(category):
        return False
    if not content or not content.strip():
        return False

    content = content.strip()
    if len(content) > MAX_MEMORY_CONTENT_CHARS:
        content = content[:MAX_MEMORY_CONTENT_CHARS] + " ... (truncated - memory items should be concise facts)"

    meta = dict(metadata or {})
    meta["category"] = category
    meta["saved_at"] = datetime.now().isoformat()

    collection = _get_collection()
    collection.add(
        documents=[content],
        metadatas=[meta],
        ids=[str(uuid.uuid4())],
    )
    return True


def search_memory(query: str, n_results: int = 3) -> list[str]:
    """
    Returns up to n_results saved memory items relevant to `query`, as
    plain strings — NOT labeled as background here. The caller
    (chat.py) is responsible for wrapping the result with
    format_memory_context() before it goes anywhere near the model
    prompt.
    """
    if not query or not query.strip():
        return []

    collection = _get_collection()
    count = collection.count()
    if count == 0:
        return []

    results = collection.query(query_texts=[query], n_results=min(n_results, count))
    documents = results.get("documents") if results else None
    if not documents:
        return []
    return list(documents[0])


def get_memory_summary() -> str:
    """Quick debug helper — how much is actually stored right now."""
    collection = _get_collection()
    return f"CIPHER memory contains {collection.count()} entries."
