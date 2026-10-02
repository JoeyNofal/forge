"""
DRIVE — Phase 4, increment (a): core chat.

Deliberately NOT here yet (each is its own tested increment):
  (b) still to come: add/switch vehicle, typed Carfax entries, recall search
      that saves results. (Logging mileage/services/fill-ups/issues is DONE:
      proposals are appended after the reply — see drive_extract.py.)
  (c) permanent memory
  (d) photo/file support (dashboard warning lights, receipts — no image
      infrastructure exists in FORGE yet, same call as ATLAS)

What this does:
- Refuses non-automotive questions with the word-boundary gate
  (Lesson #6), in Clarkson's voice — using DRIVE's OWN line from its
  prompt, not a generic one.
- "Show me my logged data" questions are answered directly from the
  vehicle file with NO model call, same reasoning as ATLAS.
- Everything else: the live vehicle summary goes into the prompt, the
  model answers in voice. A real data-load failure becomes an explicit
  "unavailable" note (Lesson #12) instead of a crash or a silent skip.
- Web search only when the message looks like it needs one, using
  shared/web_search.py — the old code searched on EVERY message inside
  a bare except: pass, which is both Lesson #2 (phantom search) and
  Lesson #8 (unconditional search) at once. A failed search is passed
  through as a failure, never hidden.
- Goes through stream_by_tier — the same shared model path as every
  other agent (Lesson #1/#11). model_tier=None means "DRIVE's live
  default" (free_cloud). The caller owns conversation history.
"""
from typing import Optional

from shared.keyword_gate import should_refuse, contains_keyword
from shared.agent_topics import (
    DRIVE_NON_TOPIC, DRIVE_INTENT, DRIVE_SEARCH_TRIGGERS,
    DRIVE_HISTORY_PHRASES, DRIVE_HISTORY_QUANTITY, DRIVE_HISTORY_SUBJECTS,
    DRIVE_ADVICE_SIGNALS, DRIVE_REPORT_PHRASES,
    DRIVE_MAINTENANCE_WORDS, DRIVE_GAS_WORDS, DRIVE_ISSUE_WORDS,
)
from shared.web_search import web_search, WEB_SEARCH_FAILED_PREFIX
from shared.model_client import stream_by_tier
from shared.memory_context import format_memory_context
from agents.drive.prompt import DRIVE_PROMPT
from agents.drive import drive_tools
from agents.drive.drive_extract import extract_and_propose

# Context for the model: it cannot save anything itself. A model that says
# "logged!" without a real save is making a false memory (Lesson #3).
LOGGING_NOTE = (
    "[LOGGING: You cannot save, log or change any record yourself, and you do not know what, "
    "if anything, the system will offer to log. Never say you have logged, saved or recorded "
    "anything, and never mention or promise a proposal, an entry or an approval. "
    "When Joey is only reporting something routine (a fill-up, his mileage, a service that went fine), "
    "react in character in a few sentences; do not speculate about problems he did not mention, "
    "do not recommend a service or a dealership he did not ask about, and do not work out prices, "
    "per-gallon figures or other numbers yourself. Just respond to what Joey said.]"
)

# DRIVE's own line, straight from its prompt — not a generic refusal.
REFUSAL_MESSAGE = "That's well outside my area of expertise — and my interest, frankly. NEXUS will sort you out."


def is_history_question(message: str) -> bool:
    """True when the message is asking to SEE logged data (answered with no model call)."""
    if contains_keyword(message, DRIVE_REPORT_PHRASES):
        return False  # reporting new work, not asking for history
    if contains_keyword(message, DRIVE_ADVICE_SIGNALS):
        return False  # asking for advice, not a data dump
    if contains_keyword(message, DRIVE_HISTORY_PHRASES):
        return True
    return (
        contains_keyword(message, DRIVE_HISTORY_QUANTITY)
        and contains_keyword(message, DRIVE_HISTORY_SUBJECTS)
    )


def history_answer(message: str) -> str:
    """Picks which slice of the data to show. May raise RuntimeError if the data can't be read."""
    if contains_keyword(message, DRIVE_ISSUE_WORDS):
        return drive_tools.get_open_issues()
    gas = contains_keyword(message, DRIVE_GAS_WORDS)
    maint = contains_keyword(message, DRIVE_MAINTENANCE_WORDS)
    if gas and not maint:
        return drive_tools.get_gas_summary()
    if maint and not gas:
        return drive_tools.get_recent_maintenance(10)
    return (
        drive_tools.get_vehicle_info() + "\n\n"
        + drive_tools.get_recent_maintenance(10) + "\n\n"
        + drive_tools.get_gas_summary()
    )


def stream_drive(message: str, history: Optional[list] = None, location: str = "",
                 model_tier: Optional[str] = None):
    """
    history: list of {"role": "user"|"assistant", "content": str}, or None
    Yields text chunks. The caller owns conversation-history persistence.
    """
    if should_refuse(message, DRIVE_NON_TOPIC, DRIVE_INTENT):
        yield REFUSAL_MESSAGE
        return

    if is_history_question(message):
        try:
            yield history_answer(message)
        except RuntimeError as e:
            yield f"I can't read your vehicle data right now: {e}"
        return

    context_blocks = []

    try:
        context_blocks.append(
            f"[Live vehicle data:\n{drive_tools.get_data_summary_for_llm()}]"
        )
    except RuntimeError as e:
        context_blocks.append(f"[VEHICLE DATA UNAVAILABLE: {e}]")

    context_blocks.append(LOGGING_NOTE)

    if contains_keyword(message, DRIVE_SEARCH_TRIGGERS):
        search_result = web_search(message)
        if search_result.startswith(WEB_SEARCH_FAILED_PREFIX):
            context_blocks.append(search_result)
        else:
            context_blocks.append(format_memory_context([search_result], label="web search results"))

    full_message = "\n\n".join(context_blocks + [f"Joey says: {message}"])

    messages = list(history) if history else []
    messages.append({"role": "user", "content": full_message})

    yield from stream_by_tier("drive", model_tier, DRIVE_PROMPT, messages, location)

    # Only reached if the reply streamed fully (an error above propagates).
    # Uses Joey's own message only — never DRIVE's reply (Lesson #3). A failure
    # here must never lose the reply he already has: it becomes a visible note.
    try:
        notes = extract_and_propose(message)
    except Exception as e:
        notes = [f"I couldn't check that message for anything to log ({type(e).__name__}: {e}). Nothing was proposed."]
    if notes:
        yield "\n\n" + "\n\n".join(notes)