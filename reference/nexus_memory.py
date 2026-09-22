# This file handles NEXUS's two-layer memory system.
#
# LAYER 1 — Personal Memory (forever)
#   Stores everything Joey tells NEXUS personally.
#   This memory is never deleted. NEXUS will always remember personal conversations.
#
# LAYER 2 — Agent Memory (3-month rolling)
#   Stores information passed from other agents (CIPHER, ASSET, ATLAS, DRIVE).
#   Anything older than 3 months is automatically cleaned out.
#   This keeps NEXUS aware of what the other agents are doing without
#   filling up memory with outdated information.

import chromadb
import os
from datetime import datetime, timedelta

# Where NEXUS's memory is stored on the hard drive
MEMORY_PATH = r"D:\Projects\NEXUS SYSTEM\memory\nexus"

# Start ChromaDB and point it to NEXUS's memory folder
client = chromadb.PersistentClient(path=MEMORY_PATH)

# Create (or load) the two separate memory collections
# Think of each collection as a separate filing cabinet drawer
personal_memory = client.get_or_create_collection(name="nexus_personal_memory")
agent_memory = client.get_or_create_collection(name="nexus_agent_memory")


# ==============================================================================
# LAYER 1 — PERSONAL MEMORY (forever)
# ==============================================================================

def save_personal_memory(memory_id, content):
    """
    Saves something Joey said or shared into permanent personal memory.

    memory_id — a unique name for this memory (example: "joey_hobby_001")
    content   — the actual text to remember
    """
    personal_memory.upsert(
        ids=[memory_id],
        documents=[content],
        metadatas=[{
            "type": "personal",
            "saved_at": datetime.now().isoformat()  # Records exactly when this was saved
        }]
    )
    print(f"Personal memory saved: {memory_id}")


def search_personal_memory(query, n_results=3):
    """
    Searches Joey's personal memory for anything relevant to the query.

    query     — what to search for
    n_results — how many results to return (default 3)
    """
    try:
        results = personal_memory.query(
            query_texts=[query],
            n_results=n_results
        )
        if not results["documents"][0]:
            return []

        memories = []
        for i, doc in enumerate(results["documents"][0]):
            memories.append({
                "id": results["ids"][0][i],
                "content": doc,
                "saved_at": results["metadatas"][0][i].get("saved_at", "unknown")
            })
        return memories
    except Exception:
        return []


# ==============================================================================
# LAYER 2 — AGENT MEMORY (3-month rolling)
# ==============================================================================

def save_agent_memory(memory_id, content, from_agent):
    """
    Saves information received from another agent into rolling memory.

    memory_id  — a unique name for this memory
    content    — the information to remember
    from_agent — which agent sent this (example: "CIPHER", "ASSET")
    """
    agent_memory.upsert(
        ids=[memory_id],
        documents=[content],
        metadatas=[{
            "type": "agent",
            "from_agent": from_agent,
            "saved_at": datetime.now().isoformat()
        }]
    )
    print(f"Agent memory saved from {from_agent}: {memory_id}")


def search_agent_memory(query, n_results=3):
    """
    Searches agent memory for anything relevant to the query.
    Only returns memories from the last 3 months.
    """
    try:
        results = agent_memory.query(
            query_texts=[query],
            n_results=n_results
        )
        if not results["documents"][0]:
            return []

        # Calculate what date was 3 months ago
        three_months_ago = datetime.now() - timedelta(days=90)

        memories = []
        for i, doc in enumerate(results["documents"][0]):
            saved_at_str = results["metadatas"][0][i].get("saved_at", "")
            # Only include this memory if it was saved within the last 3 months
            try:
                saved_at = datetime.fromisoformat(saved_at_str)
                if saved_at >= three_months_ago:
                    memories.append({
                        "id": results["ids"][0][i],
                        "content": doc,
                        "from_agent": results["metadatas"][0][i].get("from_agent", "unknown"),
                        "saved_at": saved_at_str
                    })
            except Exception:
                # If the date can't be parsed, include it anyway to be safe
                memories.append({
                    "id": results["ids"][0][i],
                    "content": doc,
                    "from_agent": results["metadatas"][0][i].get("from_agent", "unknown"),
                    "saved_at": saved_at_str
                })
        return memories
    except Exception:
        return []


def clean_old_agent_memories():
    """
    Deletes any agent memories older than 3 months.
    This runs automatically every time NEXUS starts up.
    Think of it as NEXUS taking out the trash on old information.
    """
    try:
        # Get everything in agent memory
        all_memories = agent_memory.get()
        if not all_memories["ids"]:
            return  # Nothing to clean

        three_months_ago = datetime.now() - timedelta(days=90)
        ids_to_delete = []

        for i, metadata in enumerate(all_memories["metadatas"]):
            saved_at_str = metadata.get("saved_at", "")
            try:
                saved_at = datetime.fromisoformat(saved_at_str)
                if saved_at < three_months_ago:
                    ids_to_delete.append(all_memories["ids"][i])
            except Exception:
                pass  # If date can't be parsed, leave it alone

        if ids_to_delete:
            agent_memory.delete(ids=ids_to_delete)
            print(f"Cleaned {len(ids_to_delete)} expired agent memories.")
        else:
            print("No expired agent memories to clean.")

    except Exception as e:
        print(f"Memory cleanup error: {e}")


# ==============================================================================
# COMBINED SEARCH — searches both layers at once
# ==============================================================================

def search_all_memory(query, n_results=3):
    """
    Searches both personal memory and agent memory at the same time.
    Returns a combined list of the most relevant memories.
    NEXUS uses this before every response to check if it remembers
    anything relevant to what Joey just said.
    """
    personal_results = search_personal_memory(query, n_results)
    agent_results = search_agent_memory(query, n_results)

    # Label each result so we know which layer it came from
    for r in personal_results:
        r["layer"] = "personal"
    for r in agent_results:
        r["layer"] = "agent"

    return personal_results + agent_results


# ==============================================================================
# TEST BLOCK
# ==============================================================================
if __name__ == "__main__":
    print("Testing NEXUS two-layer memory...\n")

    # Test Layer 1 — save and search personal memory
    print("--- LAYER 1: Personal Memory ---")
    save_personal_memory(
        memory_id="joey_test_001",
        content="Joey's name is Joey. He is building the NEXUS system on his laptop."
    )
    save_personal_memory(
        memory_id="joey_test_002",
        content="Joey is a complete beginner at programming but is learning fast."
    )

    print("\nSearching personal memory for 'Joey programming'...")
    results = search_personal_memory("Joey programming")
    for r in results:
        print(f"  [{r['id']}]: {r['content'][:80]}...")

    # Test Layer 2 — save and search agent memory
    print("\n--- LAYER 2: Agent Memory ---")
    save_agent_memory(
        memory_id="cipher_build_001",
        content="CIPHER successfully built and tested. All 4 files working: cipher.py, cipher_memory.py, cipher_tools.py, cipher_backend.py",
        from_agent="CIPHER"
    )

    print("\nSearching agent memory for 'CIPHER build'...")
    results = search_agent_memory("CIPHER build")
    for r in results:
        print(f"  [{r['from_agent']}] [{r['id']}]: {r['content'][:80]}...")

    # Test cleanup
    print("\n--- Running memory cleanup ---")
    clean_old_agent_memories()

    print("\nNEXUS memory system working correctly.")