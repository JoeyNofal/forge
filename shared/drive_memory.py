"""
DRIVE's permanent memory (increment (c), Part 1: the STORE). Local ChromaDB, its own collection
('drive_memory'), completely separate from CIPHER's and NEXUS's (Lesson #3's per-agent isolation).

What it guarantees:
- ONLY the six categories Joey approved are ever stored, enforced HERE at the storage layer
  (not just up in the code that calls it). Nothing like "every conversation turn" ever lands here.
- A memory is ONE short fact (at most MAX_FACT_CHARS). Too long is refused, never cut in half:
  a half-saved preference could mean something different.
- A near-identical fact is never stored twice (checked under a lock, so concurrent saves can't both pass).
- Searches only return memories within a relevance cutoff, closest first, so unrelated "background"
  never reaches the model.
- Embeddings run locally through Ollama (shared/ollama_embeddings.py). A failure PROPAGATES; nothing is
  swallowed (the old drive_memory.py returned [] on any error).

This module never labels memory as background and never decides WHAT to remember: the calling code
(Part 2) does both. It only stores, finds, lists and deletes plain facts.
"""
import os
import re
import threading
import uuid
from datetime import datetime

import chromadb

from shared.ollama_embeddings import OllamaEmbeddingFunction


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw is None else float(raw)          # a bad value fails LOUDLY at import


# D:\Projects\forge\memory\drive on Youssef's machine (memory/ is in .gitignore: never uploaded).
DRIVE_MEMORY_PATH = os.getenv("DRIVE_MEMORY_PATH", r"D:\Projects\forge\memory\drive")
COLLECTION_NAME = "drive_memory"

# What DRIVE may remember (Joey's decision). Money facts belong to ASSET, workouts to ATLAS; logged car data
# (mileage, services, fill-ups, issues, Carfax, recalls) lives in the vehicle file and is never copied here.
DRIVE_MEMORY_CATEGORIES = frozenset({"decision", "preference", "correction", "goal", "plan", "project_fact"})

MAX_FACT_CHARS = 500
MAX_QUERY_CHARS = 1500
MAX_METADATA_KEYS = 20
MAX_METADATA_TEXT = 200

# Cosine distance: 0 = identical meaning, 1 = unrelated, 2 = opposite. THESE TWO NUMBERS ARE STARTING GUESSES;
# the real-embedding test (test_drive_memory_l3) prints actual distances so they can be tuned.
# Tuned from REAL nomic-embed-text distances (test_drive_memory_l3): related questions' best match was
# 0.28-0.44, unrelated questions' best match 0.557-0.593, so the cutoff sits in the gap. Small sample: adjustable.
# The duplicate threshold is deliberately TIGHT: embeddings can't tell "0W-20" from "5W-30", and swallowing a
# CHANGED fact as a "duplicate" would keep the stale one.
# Real data: a CHANGED fact (0W-20 -> 5W-30) measured 0.041, razor-thin against 0.04, so the embedding rule
# is now only for essentially identical text AND identical numbers (see save_memory). Identical words are
# caught by _same_words instead.
DUPLICATE_DISTANCE = _env_float("DRIVE_MEMORY_DUPLICATE_DISTANCE", 0.005)
DEFAULT_MAX_DISTANCE = _env_float("DRIVE_MEMORY_MAX_DISTANCE", 0.50)

_embedding_function_factory = OllamaEmbeddingFunction       # tests swap this for a network-free fake
_client = None
_collection = None
_init_lock = threading.Lock()
_write_lock = threading.Lock()


def _open_collection(client):
    embed = _embedding_function_factory()
    try:
        return client.get_or_create_collection(
            name=COLLECTION_NAME, embedding_function=embed,
            configuration={"hnsw": {"space": "cosine"}},       # type: ignore[arg-type]
        )
    except TypeError:                                          # an older chromadb without 'configuration'
        return client.get_or_create_collection(
            name=COLLECTION_NAME, embedding_function=embed, metadata={"hnsw:space": "cosine"},
        )


def _get_collection():
    """Lazy connect, thread-safe (double-checked locking: the cold-start race found in CIPHER's/NEXUS's L4 tests)."""
    global _client, _collection
    if _collection is None:
        with _init_lock:
            if _collection is None:
                os.makedirs(DRIVE_MEMORY_PATH, exist_ok=True)
                client = chromadb.PersistentClient(path=DRIVE_MEMORY_PATH)
                collection = _open_collection(client)
                _client = client
                _collection = collection                       # assigned LAST: other threads never see half a setup
    return _collection


def _clean_fact(content) -> str:
    """One clean line of printable text; anything that isn't text at all becomes ''."""
    if not isinstance(content, str):
        return ""
    printable = "".join(ch if ch.isprintable() else " " for ch in content)
    return " ".join(printable.split())


def _safe_metadata(metadata) -> dict:
    """Only simple values ChromaDB accepts; the reserved keys can't be overridden by the caller."""
    out = {}
    if not isinstance(metadata, dict):
        return out
    for key, value in metadata.items():
        if len(out) >= MAX_METADATA_KEYS:
            break
        if not isinstance(key, str) or not key or key in ("category", "saved_at"):
            continue
        if isinstance(value, bool):
            out[key[:60]] = value
        elif isinstance(value, (int, float)):
            if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
                continue
            out[key[:60]] = value
        elif isinstance(value, str):
            out[key[:60]] = value[:MAX_METADATA_TEXT]
    return out


def _same_words(a: str, b: str) -> bool:
    """True if two facts are the same words (ignoring case, punctuation and spacing): always a duplicate."""
    return bool(a and b) and re.findall(r"[a-z0-9]+", a.lower()) == re.findall(r"[a-z0-9]+", b.lower())


def save_memory(category, content, metadata=None) -> dict:
    """
    Stores ONE fact. Returns {"status": "saved" | "duplicate" | "filtered", "id": str | None, "reason": str}
    ("duplicate" also carries the existing fact's "existing" text and its id).
    A failure to embed (Ollama down) RAISES; nothing is partly saved.
    """
    if not isinstance(category, str) or category not in DRIVE_MEMORY_CATEGORIES:     # a list/dict must not crash the 'in' test
        return {"status": "filtered", "id": None, "reason": f"{category!r} is not a category DRIVE remembers"}
    fact = _clean_fact(content)
    if not fact:
        return {"status": "filtered", "id": None, "reason": "nothing to remember"}
    if len(fact) > MAX_FACT_CHARS:
        return {"status": "filtered", "id": None,
                "reason": f"too long ({len(fact)} characters): a memory is one short fact (max {MAX_FACT_CHARS})"}

    with _write_lock:                                            # check + add together, so concurrent saves can't both pass
        collection = _get_collection()
        if collection.count() > 0:
            nearest = collection.query(query_texts=[fact], n_results=1)
            ids = (nearest.get("ids") or [[]])[0]
            dists = (nearest.get("distances") or [[]])[0]
            docs = (nearest.get("documents") or [[]])[0]
            if ids and dists and dists[0] is not None:
                existing = docs[0] if docs else ""
                same_numbers = re.findall(r"\d+", existing) == re.findall(r"\d+", fact)
                if (dists[0] <= DUPLICATE_DISTANCE and same_numbers) or _same_words(existing, fact):
                    return {"status": "duplicate", "id": ids[0], "reason": "already remembered", "existing": existing}
        meta = _safe_metadata(metadata)
        meta["category"] = category
        meta["saved_at"] = datetime.now().isoformat()
        memory_id = str(uuid.uuid4())
        collection.add(documents=[fact], metadatas=[meta], ids=[memory_id])
        return {"status": "saved", "id": memory_id, "reason": ""}


def search_memories(query, n_results: int = 3, max_distance=None) -> list:
    """
    The memories closest in meaning to `query`, closest first, ONLY those within the relevance cutoff:
    [{"id", "text", "category", "saved_at", "distance"}]. A blank query or a bad n_results gives [].
    """
    text = _clean_fact(query)[:MAX_QUERY_CHARS]
    if not text:
        return []
    if isinstance(n_results, bool) or not isinstance(n_results, int) or n_results < 1:
        return []
    limit = DEFAULT_MAX_DISTANCE if max_distance is None else max_distance
    if isinstance(limit, bool) or not isinstance(limit, (int, float)) or limit != limit:
        raise ValueError("max_distance must be a number")

    collection = _get_collection()
    count = collection.count()
    if count == 0:
        return []
    result = collection.query(query_texts=[text], n_results=min(n_results, count))
    ids = (result.get("ids") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    found = []
    for memory_id, doc, meta, dist in zip(ids, docs, metas, dists):
        if dist is None or dist > limit:
            continue
        meta = meta or {}
        found.append({"id": memory_id, "text": doc, "category": meta.get("category", ""),
                      "saved_at": meta.get("saved_at", ""), "distance": float(dist)})
    return found


def list_memories(limit=None) -> list:
    """Every memory, newest first: [{"id", "text", "category", "saved_at"}]. An invalid limit is ignored."""
    collection = _get_collection()
    got = collection.get()
    ids = got.get("ids") or []
    docs = got.get("documents") or []
    metas = got.get("metadatas") or []
    items = []
    for memory_id, doc, meta in zip(ids, docs, metas):
        meta = meta or {}
        items.append({"id": memory_id, "text": doc, "category": meta.get("category", ""),
                      "saved_at": meta.get("saved_at", "")})
    items.sort(key=lambda m: m["saved_at"], reverse=True)
    if isinstance(limit, int) and not isinstance(limit, bool) and limit >= 0:
        items = items[:limit]
    return items


def delete_memory(memory_id) -> bool:
    """Deletes ONE memory by its exact id. True if it existed and is now gone, False otherwise."""
    if not isinstance(memory_id, str) or not memory_id.strip() or len(memory_id) > 200:
        return False
    memory_id = memory_id.strip()
    with _write_lock:
        collection = _get_collection()
        if not (collection.get(ids=[memory_id]).get("ids") or []):
            return False
        collection.delete(ids=[memory_id])
        return True


def memory_count() -> int:
    return _get_collection().count()