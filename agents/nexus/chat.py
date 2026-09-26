"""
NEXUS — Phase 2, core chat.

No memory yet (Decision: deferred as its own tested increment, same
split CIPHER used in Sessions 3/4).
No bridges, no approval workflow, no multi-step tool loop yet
(Decision: core chat first, same phased approach as CIPHER — those are
separate later increments, not built in one shot).
NEXUS is fully unrestricted (Core Reference: "Restriction: None") — no
keyword refusal gate, unlike CIPHER/ASSET/ATLAS/DRIVE/CASE.

Web search (Decision): kept close to the old system's actual behavior —
fires on nearly every message, not gated behind a trigger-keyword list
like CIPHER's — but made SAFE: goes through shared/web_search.py (which
returns a clear WEB_SEARCH_FAILED_PREFIX marker on a real failure —
Lesson #2's direct fix), and that failure is never silently swallowed
the way the old code's bare `except: pass` did.

NEXUS's carried-over prompt (Decision: kept unchanged) still instructs
the model to write tool/bridge/record-keeping commands for systems that
don't exist yet in FORGE this increment — reminders, app launching,
folder/file reading, the 8 ASK_* bridges, backup/record/task-tracking.
strip_unexecuted_action_markers() below replaces any of those with one
clear placeholder — never left as dead syntax, and never silently
dropped either (a silent drop would look like nothing was asked for,
when something was).
"""
import re
from typing import Optional
from shared.web_search import web_search, WEB_SEARCH_FAILED_PREFIX
from shared.model_client import stream_by_tier
from shared.memory_context import format_memory_context
from agents.nexus.prompt import NEXUS_PROMPT

# Every marker NEXUS's carried-over prompt describes that FORGE hasn't
# built a real processor for yet, this increment.
_LINE_MARKERS = [
    "OPEN_APP:", "SET_REMINDER:", "SEARCH_WEB:", "LIST_FOLDER:", "READ_FILE:",
    "ASK_CIPHER:", "ASK_ASSET:", "ASK_ATLAS:", "ASK_DRIVE:", "ASK_STOCK:",
    "ASK_FLAME:", "ASK_CASE:", "ASK_PULSE:",
    "CREATE_BACKUP:", "WRITE_RECORD:", "TRACK_TASK:",
]
_PLACEHOLDER = "(That capability isn't built yet in FORGE.)"


def strip_unexecuted_action_markers(text: str) -> str:
    """
    Replaces every marker above — wherever it appears, start of line or
    mid-paragraph — with one clear placeholder, cutting the rest of
    that line. LIST_REMINDERS has no colon and no argument, so it needs
    its own whole-word check instead of the "marker + rest of line"
    pattern the others use.
    """
    text = re.sub(r"\bLIST_REMINDERS\b", _PLACEHOLDER, text)
    for marker in _LINE_MARKERS:
        text = re.sub(rf"{re.escape(marker)}.*", _PLACEHOLDER, text)
    return text


def _build_search_query(message: str, location: str) -> str:
    """
    Mirrors the old system's location-aware query building (Decision:
    keep the "search nearly everything" behavior, just done safely).
    """
    msg_lower = message.lower()
    if any(w in msg_lower for w in ["weather", "forecast", "temperature", "rain", "snow"]):
        return f"weather forecast {location} tomorrow" if location else message
    return f"{message} near {location}" if location else message


def stream_nexus(message: str, history: Optional[list] = None, location: str = "", model_tier: Optional[str] = None):
    """
    history: list of {"role": "user"|"assistant", "content": str}, or None
    Yields text chunks. Caller still owns conversation-history
    persistence — save strip_unexecuted_action_markers(full_response)
    to history, not the raw model output, so dead markers never build
    up there either.

    Core chat + tiered models + safe web search only, this increment
    (Decision) — no memory, no bridges, no approval workflow, no tool
    loop yet.
    """
    context_blocks = []

    search_query = _build_search_query(message, location)
    search_result = web_search(search_query)
    if search_result.startswith(WEB_SEARCH_FAILED_PREFIX):
        # A genuine failure is a direct instruction, not optional
        # background to weigh or ignore (Lesson #2) — never let the
        # model answer as if a real (empty) search had quietly succeeded.
        context_blocks.append(search_result)
    else:
        context_blocks.append(format_memory_context([search_result], label="web search results"))

    # "Joey says:" is the exact literal phrase NEXUS's own (unchanged)
    # prompt looks for to treat this as a real, trusted instruction —
    # not a stylistic choice, a contract with the prompt text above.
    full_message = "\n\n".join(context_blocks + [f"Joey says: {message}"])

    messages = list(history) if history else []
    messages.append({"role": "user", "content": full_message})

    full_response = ""
    for chunk in stream_by_tier("nexus", model_tier, NEXUS_PROMPT, messages, location):
        full_response += chunk
        yield chunk

    # (caller is still responsible for saving
    # strip_unexecuted_action_markers(full_response) to its own
    # conversation history — this function doesn't persist the turn)