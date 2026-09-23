"""
Wraps retrieved memory/search results so they're never presented to
the model as equally authoritative to the live conversation.

Fixes Lesson #2 — was only applied to ATLAS in the old code, missing
from CIPHER/ASSET/DRIVE/FLAME/CASE/PULSE. This makes it one function
every agent calls, so it can't be forgotten per-agent again.
"""

def format_memory_context(memory_items: list[str], label: str = "memory") -> str:
    """
    memory_items — list of retrieved memory/search-result strings
    label        — what kind of background this is, e.g. "memory",
                   "past work", "search results" (used in the header)

    Returns an empty string if memory_items is empty, otherwise a
    clearly-labeled block to append to the prompt.
    """
    if not memory_items:
        return ""

    joined = "\n".join(str(item) for item in memory_items)
    return (
        f"\n\n--- Background {label} (may be outdated or unrelated — "
        f"the current conversation is authoritative) ---\n"
        f"{joined}\n"
        f"--- End background {label} ---"
    )


# Categories worth permanently saving. Routine back-and-forth doesn't
# need to live forever — this is what Lesson #3's "filter before
# saving" actually means in code, not "save literally everything."
MEMORY_WORTHY_CATEGORIES = {
    "decision", "preference", "correction", "goal",
    "workout_log", "plan", "financial_fact", "project_fact",
}

def is_memory_worthy(category: str) -> bool:
    """Gate before calling save_memory() — skip routine conversation turns."""
    return category in MEMORY_WORTHY_CATEGORIES