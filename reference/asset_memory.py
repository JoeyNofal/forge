# ============================================================
# ASSET MEMORY — Permanent Financial Memory
# Uses ChromaDB to store and retrieve financial history
# Never deletes anything — full permanent record
# ============================================================

import chromadb
import os
from datetime import datetime

# ── Path to ASSET's memory storage folder ──────────────────
MEMORY_PATH = r"D:\Projects\NEXUS SYSTEM\memory\asset"

# ── Memory categories ASSET uses ───────────────────────────
# "transaction"  — financial transactions and account changes
# "advice"       — advice ASSET has given Joey
# "goal"         — goal tracking and progress notes
# "market"       — market observations and financial news
# "summary"      — periodic financial summaries
# "conversation" — general conversation history

# ============================================================
# SETUP — Connect to ChromaDB
# ============================================================

def get_memory_client():
    """Creates and returns a connection to ASSET's ChromaDB memory."""
    client = chromadb.PersistentClient(path=MEMORY_PATH)
    collection = client.get_or_create_collection(
        name="asset_memory",
        metadata={"description": "ASSET permanent financial memory — never deleted"}
    )
    return collection


# ============================================================
# SAVE MEMORY
# Stores any piece of information permanently
# ============================================================

def save_memory(content, category, metadata=None):
    """
    Saves a piece of information to ASSET's permanent memory.
    
    content  — the text to remember (a piece of advice, a summary, etc.)
    category — one of: transaction, advice, goal, market, summary, conversation
    metadata — optional extra info (e.g. account name, goal name)
    """
    collection = get_memory_client()

    # Build the metadata dict that gets stored alongside the memory
    entry_metadata = {
        "category": category,
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d")
    }

    # Merge in any extra metadata passed in
    if metadata:
        entry_metadata.update(metadata)

    # Create a unique ID for this memory entry
    memory_id = f"asset_{category}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    # Save to ChromaDB
    collection.add(
        documents=[content],
        metadatas=[entry_metadata],
        ids=[memory_id]
    )

    return memory_id


# ============================================================
# SEARCH MEMORY
# Finds the most relevant memories for a given query
# ============================================================

def search_memory(query, category=None, n_results=5):
    """
    Searches ASSET's memory for entries relevant to the query.
    
    query    — what you're looking for (plain English)
    category — optional filter (e.g. only search "advice" entries)
    n_results — how many results to return (default 5)
    
    Returns a formatted string of relevant memories, or empty string if none.
    """
    collection = get_memory_client()

    # Check how many memories exist before searching
    total = collection.count()
    if total == 0:
        return ""

    # Cap results to what's actually stored
    n_results = min(n_results, total)

    # Build the filter if a category was specified
    where_filter = {"category": category} if category else None

    try:
        if where_filter:
            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter
            )
        else:
            results = collection.query(
                query_texts=[query],
                n_results=n_results
            )

        # Format results into a readable string
        if not results["documents"] or not results["documents"][0]:
            return ""

        memory_lines = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            date_str = meta.get("date", "unknown date")
            cat = meta.get("category", "general")
            memory_lines.append(f"[{date_str} | {cat}] {doc}")

        return "\n".join(memory_lines)

    except Exception as e:
        print(f"[ASSET MEMORY] Search error: {e}")
        return ""


# ============================================================
# SAVE CONVERSATION TURN
# Shortcut for saving a single exchange to memory
# ============================================================

def save_conversation_turn(user_message, asset_reply):
    """
    Saves one full exchange (Joey's message + ASSET's reply) to memory.
    Called automatically after every response in asset.py
    """
    combined = f"Joey asked: {user_message}\nA.S.S.E.T. replied: {asset_reply}"
    save_memory(combined, category="conversation")


# ============================================================
# SAVE ADVICE
# Shortcut for explicitly saving a piece of advice given
# ============================================================

def save_advice(advice_text, topic=None):
    """
    Saves a piece of financial advice ASSET gave to Joey.
    topic — optional label like 'emergency fund' or 'credit score'
    """
    metadata = {}
    if topic:
        metadata["topic"] = topic
    save_memory(advice_text, category="advice", metadata=metadata)


# ============================================================
# GET MEMORY SUMMARY
# Returns a count of how many memories exist per category
# ============================================================

def get_memory_summary():
    """Returns a plain-English summary of how much ASSET remembers."""
    collection = get_memory_client()
    total = collection.count()

    if total == 0:
        return "No memories stored yet."

    return f"ASSET memory contains {total} total entries."


# ============================================================
# TEST — Run this file directly to verify memory works
# ============================================================

if __name__ == "__main__":
    print("Testing ASSET memory...\n")

    # Test 1: Save a memory
    print("Test 1: Saving a memory...")
    save_memory(
        content="Joey's car loan balance is $14,500. Monthly target is $1,500. Loan is 0% interest.",
        category="goal",
        metadata={"topic": "car_loan"}
    )
    print("  Saved successfully.")

    # Test 2: Save a piece of advice
    print("\nTest 2: Saving advice...")
    save_advice(
        advice_text="Recommended Joey focus on building a 3-month emergency fund before increasing car loan payments.",
        topic="emergency_fund"
    )
    print("  Saved successfully.")

    # Test 3: Search memory
    print("\nTest 3: Searching memory for 'car loan'...")
    results = search_memory("car loan")
    if results:
        print("  Found:\n", results)
    else:
        print("  Nothing found.")

    # Test 4: Memory summary
    print("\nTest 4: Memory summary...")
    print(" ", get_memory_summary())

    print("\nAll memory tests complete.")