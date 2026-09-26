"""
NEXUS's permanent memory. Local ChromaDB, own collection, completely
separate from CIPHER's (Lesson #3's "isolated per-agent memory" pattern
— no agent recalls another agent's saved facts).

Fixes Lesson #3 directly: only categories in NEXUS's own accepted set
(agents/nexus/chat.py's NEXUS_MEMORY_SAVE_CATEGORIES) ever get saved —
never every turn unfiltered.

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

# D:\Projects\forge\memory\nexus on Youssef's machine.
NEXUS_MEMORY_PATH = os.getenv("NEXUS_MEMORY_PATH", r"D:\Projects\forge\memory\nexus")

_client = None
_collection = None


def _get_collection():
    """Lazy connect — so importing this module never touches disk by itself."""
    global _client, _collection
    if _collection is None:
        os.makedirs(NEXUS_MEMORY_PATH, exist_ok=True)
        _client = chromadb.PersistentClient(path=NEXUS_MEMORY_PATH)
        _collection = _client.get_or_create_collection(
            name="nexus_memory", embedding_function=OllamaEmbeddingFunction()
        )
    return _collection


# NEXUS deliberately never stores financial facts, no matter what calls
# this function — ASSET's exclusive domain (Decision). Enforced HERE,
# at the storage layer, not only up in chat.py's extract_memory_saves()
# — a real L5 test (Test 11) caught that relying on the caller alone
# left a gap: financial_fact IS in the shared worth-saving list (it's
# valid for ASSET), so is_memory_worthy() alone would have let it
# through if anything ever called save_memory() directly with it.
_NEXUS_EXCLUDED_CATEGORIES = {"financial_fact"}


def save_memory(category: str, content: str, metadata: dict | None = None) -> bool:
    """
    Saves one memory item — but ONLY if `category` is in the shared
    worth-saving list AND not one of NEXUS's own excluded categories.
    Returns True if it was actually saved, False if it was filtered
    out (wrong category, excluded category, or empty content).

    This is the filter Lesson #3 says has to exist BEFORE the write,
    not as a cleanup pass after memory gets noisy.
    """
    if category in _NEXUS_EXCLUDED_CATEGORIES:
        return False
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
    return f"NEXUS memory contains {collection.count()} entries."