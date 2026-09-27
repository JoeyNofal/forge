"""
NEXUS — Phase 2, core chat + memory.

No bridges, no approval workflow, no multi-step tool loop yet
(Decision: core chat first, same phased approach as CIPHER — those are
separate later increments, not built in one shot).
NEXUS is fully unrestricted (Core Reference: "Restriction: None") — no
keyword refusal gate, unlike CIPHER/ASSET/ATLAS/DRIVE/CASE.

Web search AND memory retrieval (Decision) both fire on nearly every
message — not gated behind a trigger-keyword list like CIPHER's — but
made SAFE: web search goes through shared/web_search.py's
WEB_SEARCH_FAILED_PREFIX marker (Lesson #2's direct fix, a real failure
is never silently swallowed), and memory only ever saves through
shared/nexus_memory.py's is_memory_worthy() filter (Lesson #3's fix).

Memory saving is inline: NEXUS's own response carries a MEMORY_SAVE
marker when something is genuinely worth remembering (same mechanism
as CIPHER — no extra classification API call per turn). NEXUS accepts
7 of the 8 shared categories — everything except financial_fact, which
stays ASSET's exclusive domain (Decision).

NEXUS's carried-over prompt (Decision: kept unchanged) still instructs
the model to write tool/bridge/record-keeping commands for systems that
don't exist yet in FORGE this increment — reminders, app launching,
folder/file reading, 7 of the 8 ASK_* bridges, backup/record/task-
tracking. strip_unexecuted_action_markers() below replaces any of
those with one clear placeholder — never left as dead syntax, and
never silently dropped either.

ASK_CIPHER is now REAL (Decision, this session) — the only bridge that
exists, since CIPHER is the only other agent built so far. Two
independent trigger paths, matching the old system's real design
(Lesson #6's word-boundary fix applied to the first one):
  1. Python-side keyword pre-check on Joey's raw message
     (NEXUS_CIPHER_BRIDGE_KEYWORDS) — when it fires, NEXUS's own model
     call is told to write ONE brief acknowledgment only, not attempt
     the technical answer itself.
  2. A fallback scan of NEXUS's own response for a real ASK_CIPHER:
     line the model wrote itself.
Either way, the actual bridge call goes straight to CIPHER's own
stream_cipher() — Lesson #1, no separate implementation — so reaching
CIPHER through NEXUS gets the exact same real, approval-gated
SAVE_FILE/RUN_COMMAND behavior CIPHER's direct chat already has.
CIPHER's answer is shown as its own distinct block, never re-
synthesized through NEXUS a second time.
"""
import re
from typing import Optional
from shared.keyword_gate import contains_keyword
from shared.agent_topics import NEXUS_CIPHER_BRIDGE_KEYWORDS
from shared.web_search import web_search, WEB_SEARCH_FAILED_PREFIX
from shared.model_client import stream_by_tier
from shared.memory_context import format_memory_context
from shared.nexus_memory import save_memory, search_memory
from agents.cipher.chat import stream_cipher
from agents.nexus.prompt import NEXUS_PROMPT

# Every marker NEXUS's carried-over prompt describes that FORGE hasn't
# built a real processor for yet, this increment. ASK_CIPHER is
# deliberately NOT in this list anymore — it's real now, handled by
# detect_cipher_bridge()/extract_cipher_bridge_task() below instead.
_LINE_MARKERS = [
    "OPEN_APP:", "SET_REMINDER:", "SEARCH_WEB:", "LIST_FOLDER:", "READ_FILE:",
    "ASK_ASSET:", "ASK_ATLAS:", "ASK_DRIVE:", "ASK_STOCK:",
    "ASK_FLAME:", "ASK_CASE:", "ASK_PULSE:",
    "CREATE_BACKUP:", "WRITE_RECORD:", "TRACK_TASK:",
]
_PLACEHOLDER = "(That capability isn't built yet in FORGE.)"

# Backtick-guarded so a MENTION of the marker ("the `ASK_CIPHER:`
# format") is never mistaken for actually issuing it — matches NEXUS's
# own prompt instruction about never wrapping a real command in
# backticks when just talking about it.
ASK_CIPHER_PATTERN = re.compile(r"(?<!`)ASK_CIPHER:\s*(.+)")


def detect_cipher_bridge(message: str) -> bool:
    """Python-side pre-check on Joey's raw message, word-boundary-safe (Lesson #6)."""
    return contains_keyword(message, NEXUS_CIPHER_BRIDGE_KEYWORDS)


def extract_cipher_bridge_task(text: str) -> Optional[str]:
    """Fallback: a real ASK_CIPHER: line NEXUS's own model wrote itself."""
    match = ASK_CIPHER_PATTERN.search(text)
    if match:
        task = match.group(1).strip()
        if task:
            return task
    return None


def strip_bridge_markers(text: str) -> str:
    """
    Replaces a real ASK_CIPHER: line with a short plain-English note in
    what gets saved to history, instead of leaving raw machine syntax
    there — mirrors CIPHER's own strip_action_markers().
    """
    return ASK_CIPHER_PATTERN.sub(lambda m: f"(Routed to CIPHER: {m.group(1).strip()})", text)

# Must match shared.memory_context.MEMORY_WORTHY_CATEGORIES — kept as
# its own set here (rather than imported) so an unrelated category
# added for another agent later can't silently start being accepted
# from NEXUS's own inline marker without a deliberate prompt.py update
# to match (same reasoning as CIPHER's own separate set).
# financial_fact deliberately excluded (Decision) — ASSET's domain only.
NEXUS_MEMORY_SAVE_CATEGORIES = {
    "decision", "preference", "correction", "goal",
    "workout_log", "plan", "project_fact",
}
MEMORY_SAVE_PATTERN = re.compile(r"MEMORY_SAVE:\s*(\w+)\s*\|\s*(.+)")


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


def extract_memory_saves(text: str) -> list[tuple[str, str]]:
    """
    Pulls out any MEMORY_SAVE: <category> | <content> line(s) NEXUS
    wrote inline. A category that isn't one of
    NEXUS_MEMORY_SAVE_CATEGORIES (e.g. a hallucinated word, or
    financial_fact) is silently skipped rather than saved — this is the
    validation step, not shared.nexus_memory's filter, which is a
    second independent check.
    """
    saves = []
    for match in MEMORY_SAVE_PATTERN.finditer(text):
        category = match.group(1).strip().lower()
        content = match.group(2).strip()
        if category in NEXUS_MEMORY_SAVE_CATEGORIES and content:
            saves.append((category, content))
    return saves


def strip_memory_markers(text: str) -> str:
    """
    Removes MEMORY_SAVE lines from text before it's kept as saved
    conversation history — unlike the action markers above, this
    marker IS fully functional (the save already happened), so it's
    removed outright rather than replaced with a "not yet built"
    placeholder.
    """
    return MEMORY_SAVE_PATTERN.sub("", text).rstrip()


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
    persistence — save
    strip_unexecuted_action_markers(strip_bridge_markers(strip_memory_markers(full_response)))
    to history, not the raw model output, so dead markers, MEMORY_SAVE
    lines, and raw bridge syntax never build up there.

    Permanent memory (the 7 categories above) is saved automatically
    inside this function when NEXUS's response carries a MEMORY_SAVE
    marker — the caller doesn't need to do anything extra for that part.

    If this message routes to CIPHER (either Python-side keyword
    pre-check, or NEXUS's own model writing a real ASK_CIPHER: line),
    CIPHER's real streamed answer is yielded right after NEXUS's own
    part of the response, separated clearly — CIPHER's own memory and
    approval-gated actions all work exactly as they do in direct chat
    (Lesson #1).

    Core chat + tiered models + safe, near-universal web search and
    memory retrieval, plus the one real bridge (CIPHER) this increment
    (Decision) — no approval workflow of NEXUS's own, no tool loop, no
    other bridges yet (nothing else exists to bridge to).
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

    memory_results = search_memory(message)
    if memory_results:
        context_blocks.append(format_memory_context(memory_results, label="memory"))

    # "Joey says:" is the exact literal phrase NEXUS's own (unchanged)
    # prompt looks for to treat this as a real, trusted instruction —
    # not a stylistic choice, a contract with the prompt text above.
    routed_to_cipher = detect_cipher_bridge(message)
    instruction_lines = [f"Joey says: {message}"]
    if routed_to_cipher:
        instruction_lines.append(
            "[SYSTEM NOTE: This has already been routed to CIPHER automatically. "
            "Write ONE brief sentence acknowledging that, in your own voice — do NOT "
            "attempt to answer the technical question yourself, and do NOT write an "
            "ASK_CIPHER line, the system is handling that for you.]"
        )
    full_message = "\n\n".join(context_blocks + instruction_lines)

    messages = list(history) if history else []
    messages.append({"role": "user", "content": full_message})

    full_response = ""
    for chunk in stream_by_tier("nexus", model_tier, NEXUS_PROMPT, messages, location):
        full_response += chunk
        yield chunk

    for category, content in extract_memory_saves(full_response):
        save_memory(category, content)

    bridge_task = message if routed_to_cipher else extract_cipher_bridge_task(full_response)
    if bridge_task:
        yield "\n\n---\nCIPHER:\n"
        yield from stream_cipher(bridge_task)

    # (caller is still responsible for saving
    # strip_unexecuted_action_markers(strip_bridge_markers(strip_memory_markers(full_response)))
    # to its own conversation history — this function persists MEMORY_SAVE
    # items but does not persist the turn itself, and never executes any
    # of CIPHER's own SAVE_FILE/RUN_COMMAND proposals — that's still
    # entirely CIPHER's own approval-gated territory)