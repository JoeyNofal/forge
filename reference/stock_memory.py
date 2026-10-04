# stock_memory.py
# This is STOCK's long-term memory system.
# It uses ChromaDB — a local database that stores text in a way that lets
# us search for similar meaning, not just exact words.
# STOCK never forgets anything. Nothing is ever deleted.

import chromadb
import uuid
from datetime import datetime

# This is where ChromaDB will store STOCK's memories on your hard drive.
MEMORY_PATH = r"D:\Projects\NEXUS SYSTEM\memory\stock"

# Connect to the ChromaDB database stored at that path.
# get_or_create_client means: open it if it exists, create it if it doesn't.
client = chromadb.PersistentClient(path=MEMORY_PATH)

# A "collection" is like a folder inside the database.
# All of STOCK's memories live in one collection called "stock_memory".
collection = client.get_or_create_collection(name="stock_memory")


def save_memory(content: str, category: str, metadata: dict = None):
    """
    Saves a piece of information to STOCK's memory.

    content  — the text to remember (e.g. "Joey added 2 liters of milk")
    category — what kind of memory this is (see list below)
    metadata — optional extra details stored alongside the memory

    Valid categories:
    - pantry_update   : something was added to or removed from the pantry
    - grocery_list    : something was added to or removed from the grocery list
    - out_of_stock    : something ran out
    - shopping_trip   : Joey went shopping and updated stock
    - preference      : a food preference Joey mentioned
    - conversation    : general conversation turn
    - nexus_request   : a request that came in from NEXUS
    """

    # Build the metadata dictionary.
    # Metadata is extra information stored alongside the memory text.
    meta = {
        "category": category,
        "timestamp": datetime.now().isoformat(),
    }

    # If extra metadata was passed in, add it to our dictionary.
    if metadata:
        for key, value in metadata.items():
            # ChromaDB only accepts simple types — strings, numbers, booleans.
            # We convert everything to a string just to be safe.
            meta[key] = str(value)

    # Save to ChromaDB.
    # Each memory needs a unique ID — we generate a random one with uuid4().
    collection.add(
        documents=[content],
        metadatas=[meta],
        ids=[str(uuid.uuid4())]
    )


def search_memory(query: str, n_results: int = 5, category: str = None):
    """
    Searches STOCK's memory for entries relevant to the query.

    query     — what you're looking for (e.g. "milk", "grocery list")
    n_results — how many results to return (default: 5)
    category  — optional filter to only search one category

    Returns a list of matching memory strings.
    """

    # Build the filter if a category was specified.
    where_filter = {"category": category} if category else None

    # Count how many memories exist (so we don't ask for more than exist).
    total = collection.count()
    if total == 0:
        return []

    # Don't ask for more results than we have stored.
    n = min(n_results, total)

    # Run the search.
    try:
        if where_filter:
            results = collection.query(
                query_texts=[query],
                n_results=n,
                where=where_filter
            )
        else:
            results = collection.query(
                query_texts=[query],
                n_results=n
            )

        # Extract and return the matching text entries.
        return results["documents"][0] if results["documents"] else []

    except Exception:
        return []


def save_conversation_turn(user_message: str, agent_response: str):
    """
    Saves one full back-and-forth exchange to memory.
    This is called automatically after every conversation turn.
    """
    content = f"Joey said: {user_message}\nSTOCK responded: {agent_response}"
    save_memory(content, category="conversation")


def get_memory_summary():
    """
    Returns a count of how many memories STOCK has stored in total.
    Used for diagnostics and startup info.
    """
    total = collection.count()
    return f"STOCK memory contains {total} total entries."