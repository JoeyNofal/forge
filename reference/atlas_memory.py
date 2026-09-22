# atlas_memory.py
# A.T.L.A.S. permanent memory — never forgets anything
# Uses ChromaDB to store workout logs, plans, advice, and research locally

import chromadb
import uuid
from datetime import datetime

# This is the path where ATLAS stores its memory database on your laptop
ATLAS_MEMORY_PATH = r"D:\Projects\NEXUS SYSTEM\memory\atlas"

# Connect to ChromaDB and open (or create) ATLAS's memory collection
client = chromadb.PersistentClient(path=ATLAS_MEMORY_PATH)
collection = client.get_or_create_collection(name="atlas_memory")


def save_memory(content: str, category: str, metadata: dict = None):
    """
    Saves any piece of information to ATLAS's memory.
    
    content   — the text to remember (a workout log, advice given, etc.)
    category  — what type of memory this is (see list below)
    metadata  — optional extra tags (e.g. date, workout type)
    
    Valid categories:
    - "workout_log"    — a workout Joey reported and ATLAS logged
    - "plan"           — a training plan or session ATLAS generated
    - "progress"       — a progress note (weight, form improvement, etc.)
    - "advice"         — coaching advice ATLAS gave
    - "research"       — fitness/swimming research ATLAS found
    - "conversation"   — general conversation turns
    - "nexus_request"  — requests that came in from NEXUS
    """
    if metadata is None:
        metadata = {}

    # Always stamp the memory with today's date and its category
    metadata["category"] = category
    metadata["timestamp"] = datetime.now().isoformat()

    # Give it a unique ID so ChromaDB can store it without collisions
    memory_id = str(uuid.uuid4())

    collection.add(
        documents=[content],
        metadatas=[metadata],
        ids=[memory_id]
    )


def search_memory(query: str, n_results: int = 5) -> list:
    """
    Searches ATLAS's memory for anything related to the query.
    Returns the most relevant past memories.
    
    query      — what you're looking for (e.g. "breaststroke workout")
    n_results  — how many results to return (default: 5)
    """
    # Don't search if memory is empty — ChromaDB throws an error if you do
    if collection.count() == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, collection.count())
    )

    # Pull out just the text of each memory found
    memories = []
    if results and results["documents"]:
        for doc in results["documents"][0]:
            memories.append(doc)

    return memories


def save_conversation_turn(user_message: str, atlas_response: str):
    """
    Saves one back-and-forth exchange between Joey and ATLAS.
    Called automatically after every message.
    """
    content = f"Joey: {user_message}\nATLAS: {atlas_response}"
    save_memory(content, category="conversation")


def save_workout_log(log_text: str, workout_type: str = "general"):
    """
    Saves a logged workout specifically tagged as a workout_log.
    
    log_text     — the full workout description
    workout_type — "swim", "gym", or "general"
    """
    save_memory(log_text, category="workout_log", metadata={"workout_type": workout_type})


def save_plan(plan_text: str, plan_type: str = "general"):
    """
    Saves a training plan that ATLAS generated.
    
    plan_text  — the full plan text
    plan_type  — "swim", "gym", or "general"
    """
    save_memory(plan_text, category="plan", metadata={"plan_type": plan_type})


def get_memory_summary() -> str:
    """
    Returns a quick summary of how much is stored in ATLAS's memory.
    Useful for debugging.
    """
    total = collection.count()
    return f"ATLAS memory contains {total} total entries."