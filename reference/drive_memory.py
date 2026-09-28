# D.R.I.V.E. — Memory System
# Permanent long-term memory using ChromaDB
# Nothing is ever deleted — full vehicle history kept forever

import chromadb
import uuid
from datetime import datetime

# ── Where the memory database lives on your laptop ──────────────────────────
MEMORY_PATH = r"D:\Projects\NEXUS SYSTEM\memory\drive"

# ── Connect to (or create) the ChromaDB database ────────────────────────────
client = chromadb.PersistentClient(path=MEMORY_PATH)

# ── Create (or load) DRIVE's memory collection ──────────────────────────────
# A "collection" in ChromaDB is like a folder of saved memories
memory = client.get_or_create_collection(name="drive_memory")


# ── SAVE a memory ────────────────────────────────────────────────────────────
# category: what type of memory this is (see list above)
# content:  the actual text to remember
# metadata: optional extra info stored alongside (date, mileage, etc.)
def save_memory(category: str, content: str, metadata: dict = None):
    if metadata is None:
        metadata = {}

    # Always stamp every memory with the date and category
    metadata["category"] = category
    metadata["saved_at"] = datetime.now().isoformat()

    memory.add(
        documents=[content],
        metadatas=[metadata],
        ids=[str(uuid.uuid4())]  # unique ID for every memory
    )


# ── SEARCH memory ────────────────────────────────────────────────────────────
# query:    what you're looking for in plain English
# n:        how many results to return (default 3)
# category: optional — only search within one category
def search_memory(query: str, n: int = 3, category: str = None) -> list:
    where = {"category": category} if category else None

    try:
        results = memory.query(
            query_texts=[query],
            n_results=n,
            where=where
        )
        return results["documents"][0] if results["documents"] else []
    except Exception:
        return []


# ── SAVE a conversation turn ─────────────────────────────────────────────────
# Saves both what Joey said and what DRIVE replied, as one memory entry
def save_conversation_turn(user_message: str, drive_response: str):
    content = f"Joey: {user_message}\nDRIVE: {drive_response}"
    save_memory(
        category="conversation",
        content=content,
        metadata={"type": "conversation_turn"}
    )


# ── SAVE a maintenance log entry ─────────────────────────────────────────────
# Called whenever a maintenance event is logged
def save_maintenance_log(summary: str, mileage: int = None, service_type: str = None):
    metadata = {"type": "maintenance"}
    if mileage:
        metadata["mileage"] = str(mileage)
    if service_type:
        metadata["service_type"] = service_type

    save_memory(
        category="maintenance_log",
        content=summary,
        metadata=metadata
    )


# ── SAVE a recall notice ─────────────────────────────────────────────────────
def save_recall(content: str):
    save_memory(
        category="recall",
        content=content,
        metadata={"type": "recall_notice"}
    )


# ── SAVE advice DRIVE has given ──────────────────────────────────────────────
def save_advice(advice: str):
    save_memory(
        category="advice",
        content=advice,
        metadata={"type": "advice"}
    )


# ── GET a plain-English summary of what's in memory ─────────────────────────
# Used to give DRIVE a quick overview of what it remembers
def get_memory_summary() -> str:
    try:
        total = memory.count()
        return f"DRIVE memory contains {total} total entries."
    except Exception:
        return "Memory summary unavailable."


# ── TEST — run this file directly to confirm memory works ───────────────────
if __name__ == "__main__":
    print("Testing DRIVE memory system...")

    # Save a test memory
    save_memory(
        category="maintenance_log",
        content="Oil change completed at 45,000 miles. Full synthetic 0W-20.",
        metadata={"mileage": "45000", "service_type": "oil_change"}
    )

    # Search for it
    results = search_memory("oil change")
    print(f"Search results: {results}")

    # Summary
    print(get_memory_summary())

    print("Memory test complete.")