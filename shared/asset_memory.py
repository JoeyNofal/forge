"""
ASSET's permanent memory. Local ChromaDB, own collection, isolated from
every other agent's memory (Lesson #3's isolation pattern).

Uses its own category vocabulary — NOT shared/memory_context.py's
MEMORY_WORTHY_CATEGORIES (that list is for CIPHER/NEXUS's own memory).
ASSET's real save-worthiness gate already lived correctly in the old
stream_asset (a MEMORY_WORTHY keyword check before ever calling this),
just with the Lesson #6 plain-substring bug — chat.py fixes that part;
this module just stores/retrieves.

Fixed vs. the old asset_memory.py: it used ChromaDB's DEFAULT embedding
function (silently downloads a model from HuggingFace on first use) —
backwards for the one agent where local-first matters most. Now uses
shared/ollama_embeddings.py, same as CIPHER/NEXUS.
"""
import os
import threading
import uuid
from datetime import datetime

import chromadb

from shared.ollama_embeddings import OllamaEmbeddingFunction, MAX_MEMORY_CONTENT_CHARS

ASSET_MEMORY_PATH = os.getenv("ASSET_MEMORY_PATH", r"D:\Projects\forge\memory\asset")

ASSET_MEMORY_CATEGORIES = {"advice", "goal", "market", "summary", "conversation"}

_client = None
_collection = None
_init_lock = threading.Lock()


def _get_collection():
    """Lazy connect, thread-safe (same cold-start race fix as cipher_memory.py/nexus_memory.py)."""
    global _client, _collection
    if _collection is None:
        with _init_lock:
            if _collection is None:
                os.makedirs(ASSET_MEMORY_PATH, exist_ok=True)
                _client = chromadb.PersistentClient(path=ASSET_MEMORY_PATH)
                _collection = _client.get_or_create_collection(
                    name="asset_memory", embedding_function=OllamaEmbeddingFunction()
                )
    return _collection


def save_conversation_turn(user_message: str, assistant_response: str, category: str = "conversation") -> bool:
    """
    Saves one exchange. The CALLER (chat.py) decides whether this
    exchange is actually worth saving — this function trusts that
    decision and only validates the category itself.
    """
    if category not in ASSET_MEMORY_CATEGORIES:
        return False

    content = f"Joey: {user_message}\nASSET: {assistant_response}"
    if len(content) > MAX_MEMORY_CONTENT_CHARS:
        content = content[:MAX_MEMORY_CONTENT_CHARS] + " ... (truncated)"

    collection = _get_collection()
    collection.add(
        documents=[content],
        metadatas=[{"category": category, "saved_at": datetime.now().isoformat()}],
        ids=[str(uuid.uuid4())],
    )
    return True


def search_memory(query: str, n_results: int = 5) -> list[str]:
    """Returns up to n_results saved memory items relevant to query, as plain strings."""
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