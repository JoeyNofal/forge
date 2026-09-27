"""
CIPHER's permanent memory. Local ChromaDB, one collection.
Embedding logic itself now lives in shared/ollama_embeddings.py, shared
with NEXUS's memory (Lesson #9 — merged before it could spread to 9
duplicate copies).

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

from shared.memory_context import is_memory_worthy
from shared.ollama_embeddings import OllamaEmbeddingFunction, MAX_MEMORY_CONTENT_CHARS

# D:\Projects\forge\memory\cipher on Youssef's machine.
CIPHER_MEMORY_PATH = os.getenv("CIPHER_MEMORY_PATH", r"D:\Projects\forge\memory\cipher")


import threading

_client = None
_collection = None
_init_lock = threading.Lock()


def _get_collection():
    """
    Lazy connect, thread-safe. A real race found via NEXUS's L4 testing
    (identical code shape here — Lesson #9's whole point is exactly this
    kind of shared bug): multiple threads calling
    chromadb.PersistentClient() on the same path for the FIRST time
    simultaneously (cold start, singleton not yet warmed up) can throw
    an AttributeError deep inside ChromaDB's Rust bindings.
    Double-checked locking: cheap to skip the lock once warmed up, safe
    on the cold-start race that matters.
    """
    global _client, _collection
    if _collection is None:
        with _init_lock:
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
