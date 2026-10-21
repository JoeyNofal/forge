"""
ATLAS — Phase 4, increment (a): core chat.

Deliberately NOT here yet (each is its own tested increment):
  (c) permanent memory
  (d) workout photo scan
  (e) fillable workout templates

Increment (b), logging: when Joey REPORTS a workout or an injury, the reply
ends with a proposal note (atlas_extract.extract_and_propose). Nothing is
ever saved by chat.py — Joey approves or denies each proposal separately.

What this does:
- Refuses non-fitness questions with the word-boundary gate (Lesson #6),
  in Goggins' voice.
- "Show me my logged data" questions are answered directly from the
  fitness file with NO model call — the old system's own design, kept
  because a model can't invent a workout count it never gets to write.
  The trigger is tighter than the old one (see agent_topics.py).
- Everything else: the live fitness summary goes into the prompt, the
  model answers in voice. A real data-load failure becomes an explicit
  "unavailable" note (Lesson #12) instead of a crash or a silent skip.
- Web search only when the message looks like a research question, using
  shared/web_search.py; a failed search is passed through as a failure,
  never hidden (Lesson #2).
- Goes through stream_by_tier — the same shared model path as every other
  agent (Lesson #1/#11). model_tier=None means "ATLAS's live default"
  (free_cloud). The caller owns conversation history.
"""
import re
from typing import Optional

from shared.keyword_gate import should_refuse, contains_keyword
from shared.agent_topics import (
    ATLAS_NON_TOPIC, ATLAS_INTENT, ATLAS_SEARCH_TRIGGERS,
    ATLAS_HISTORY_PHRASES, ATLAS_HISTORY_QUANTITY, ATLAS_HISTORY_SUBJECTS,
    ATLAS_ADVICE_SIGNALS, ATLAS_REPORT_PHRASES,
    ATLAS_SWIM_WORDS, ATLAS_GYM_WORDS, ATLAS_INJURY_WORDS,
)
from shared.web_search import web_search, WEB_SEARCH_FAILED_PREFIX
from shared.model_client import stream_by_tier
from shared.memory_context import format_memory_context
from agents.atlas.prompt import ATLAS_SYSTEM_PROMPT
from agents.atlas import atlas_tools
from agents.atlas import atlas_actions
from agents.atlas.atlas_extract import extract_and_propose
from agents.atlas import atlas_program
from agents.atlas import atlas_rules
from agents.atlas import atlas_setup
from agents.atlas import exercise_draft
from agents.atlas import exercise_library as library
from agents.atlas import workout_coach
from agents.atlas.note_reader import apply_note_readings
from agents.atlas.workout_block import looks_like_workout_block

# Same line ATLAS's own prompt already uses for off-topic questions.
REFUSAL_MESSAGE = "That's not my lane — hit up NEXUS."


# A message counts as a command ONLY when the whole message is the command
# (Lesson #6): "I approve of this plan" must never approve anything.
_APPROVAL_RE = re.compile(r"^\s*(?:(approve)|(deny))\s+([0-9a-f][0-9a-f-]{5,35})\s*[.!]?\s*$", re.IGNORECASE)
_PENDING_RE = re.compile(r"^\s*(?:show\s+|list\s+)?pending(?:\s+(?:actions|proposals))?\s*[?.!]?\s*$", re.IGNORECASE)


def parse_approval_command(message):
    """('approve' | 'deny', id start) when the WHOLE message is that command, else None. A non-string fails loudly."""
    m = _APPROVAL_RE.match(message)
    if not m:
        return None
    return ("approve" if m.group(1) else "deny", m.group(3))


def is_pending_command(message) -> bool:
    return bool(_PENDING_RE.match(message))


def workout_block_reply(message: str, history: Optional[list] = None, location: str = "",
                        model_tier: Optional[str] = None):
    """
    A pasted FORGE WORKOUT LOG. The order matters:
      1. read it with plain rules (no model) and queue ONE proposal - nothing is saved
         until Joey approves it;
      2. tell him how to approve or deny;
      3. only THEN ask the model to coach, using facts and flags Python already worked
         out. If the model fails, the proposal and the approve line are already delivered.
    """
    try:
        action_id, text = atlas_actions.propose_workout_block(message, note_reader=apply_note_readings)
    except RuntimeError as e:
        yield f"I can't read or write your fitness data right now: {e}"
        return
    except ValueError as e:                       # includes BlockError
        yield f"I couldn't use that workout log: {e}. Nothing was saved."
        return
    yield text
    if not action_id:
        return                                    # already logged: nothing to coach on
    short = action_id[:8]
    yield f"\n\nReply 'approve {short}' to save it, or 'deny {short}' to throw it away."

    clean = atlas_actions.get_pending_workout(action_id)
    if clean is None:
        return
    try:
        live = atlas_tools.get_data_summary_for_llm()
    except RuntimeError as e:
        live = f"FITNESS DATA UNAVAILABLE: {e}"
    messages = list(history) if history else []
    messages.append({"role": "user", "content": workout_coach.coach_context(clean, live)})
    # The reply is collected whole and cleaned in Python before Joey sees it: the real models
    # asked too many questions, asked questions when nothing was flagged, and quoted numbers
    # that were not in the facts. If the model fails, nothing from it is shown (the proposal
    # and the approve line were already delivered above).
    reply = "".join(stream_by_tier("atlas", model_tier, ATLAS_SYSTEM_PROMPT, messages, location))
    coaching = workout_coach.filter_coach_reply(reply, clean, live)
    if coaching:
        yield "\n\n" + coaching


# Exercise-library commands (increment 2b-ii). Like approve/deny, a message counts ONLY when the
# WHOLE message is the command (Lesson #6).
_LIBRARY_RE = re.compile(
    r"^\s*(?:(show)\s+exercise|(draft)\s+exercise|(reviewed))\s+(\S.{0,99}?)\s*[.!]?\s*$", re.IGNORECASE)
_LIBRARY_LIST_RE = re.compile(
    r"^\s*(?:exercise\s+library|list\s+exercises|show\s+exercises)\s*[?.!]?\s*$", re.IGNORECASE)
MAX_LISTED_EXERCISES = 50


def parse_library_command(message):
    """('show' | 'draft' | 'reviewed' | 'list', name) when the WHOLE message is that command, else None."""
    m = _LIBRARY_RE.match(message)
    if m:
        kind = "show" if m.group(1) else "draft" if m.group(2) else "reviewed"
        return kind, m.group(4)
    if _LIBRARY_LIST_RE.match(message):
        return "list", ""
    return None


def library_command_applies(command) -> bool:
    """
    'reviewed <name>' only counts when that name is really in the library; any other message
    that merely starts with the word 'reviewed' is ordinary chat.
    """
    kind, name = command
    if kind != "reviewed":
        return True
    try:
        return library.find_exercise(name) is not None
    except (ValueError, RuntimeError):
        return True                              # an ambiguous or damaged library is reported, not hidden


def _approve_hint(action_id: str) -> str:
    short = action_id[:8]
    return f"\n\nReply 'approve {short}' to save it, or 'deny {short}' to throw it away."


def library_command_reply(command):
    """
    show / draft / reviewed / list. Everything here is read-only or a PROPOSAL: nothing is
    written to the library until Joey approves. Only 'draft' calls a model (the free cloud
    drafter, which is sent the exercise NAME and nothing else).
    """
    kind, name = command
    try:
        if kind == "list":
            entries = library.list_entries()
            if not entries:
                yield "The exercise library is empty. Type 'draft exercise <name>' to add one."
                return
            lines = []
            for e in entries[:MAX_LISTED_EXERCISES]:
                status = "reviewed" if e.get("status") == library.STATUS_REVIEWED else "AI-drafted"
                lines.append(f"- {str(e.get('name', '?'))[:60]} ({status})")
            more = len(entries) - MAX_LISTED_EXERCISES
            tail = f"\n...and {more} more." if more > 0 else ""
            yield f"Exercise library ({len(entries)}):\n" + "\n".join(lines) + tail
            return
        if kind == "show":
            entry = library.find_exercise(name)
            if entry is None:
                yield (f"'{name}' is not in the exercise library. "
                       f"Type 'draft exercise {name}' and I will draft a how-to for you to approve.")
            else:
                yield library.format_entry(entry)
            return
        if kind == "reviewed":
            action_id, text = atlas_actions.propose_mark_reviewed(name)
            yield text
            if action_id:
                yield _approve_hint(action_id)
            return
        existing = library.find_exercise(name)     # kind == "draft"
        if existing is not None:
            yield "That exercise is already in the library:\n\n" + library.format_entry(existing)
            return
        yield f"Drafting a how-to for '{name}' (only the exercise name is sent to the model)...\n\n"
        raw = exercise_draft.draft_exercise(name)
        action_id, text = atlas_actions.propose_add_exercise(raw)
        yield text
        if action_id:
            yield _approve_hint(action_id)
    except exercise_draft.DraftError as e:
        yield f"I couldn't draft that: {e}. Nothing was saved."
    except RuntimeError as e:
        yield f"I can't read or write the exercise library right now: {e}"
    except ValueError as e:
        yield f"I couldn't use that: {e}. Nothing was saved."


def is_history_question(message: str) -> bool:
    """True when the message is asking to SEE logged data (answered with no model call)."""
    if contains_keyword(message, ATLAS_REPORT_PHRASES):
        return False  # reporting a new workout, not asking for history
    if contains_keyword(message, ATLAS_ADVICE_SIGNALS):
        return False  # asking for coaching, not a data dump
    if contains_keyword(message, ATLAS_HISTORY_PHRASES):
        return True
    return (
        contains_keyword(message, ATLAS_HISTORY_QUANTITY)
        and contains_keyword(message, ATLAS_HISTORY_SUBJECTS)
    )


def history_answer(message: str) -> str:
    """Picks which slice of the data to show. May raise RuntimeError if the data can't be read."""
    if contains_keyword(message, ATLAS_INJURY_WORDS):
        return atlas_tools.get_injury_history()
    swim = contains_keyword(message, ATLAS_SWIM_WORDS)
    gym = contains_keyword(message, ATLAS_GYM_WORDS)
    if swim and not gym:
        return atlas_tools.get_swim_history()
    if gym and not swim:
        return atlas_tools.get_gym_history()
    return (
        atlas_tools.get_recent_workouts(10) + "\n\n"
        + atlas_tools.get_swim_history() + "\n\n"
        + atlas_tools.get_gym_history()
    )


# Context for the model: it cannot save, approve or log anything itself. A model that says "logged!" or
# "approved, it's in the system" without a real save is making a false record (Lesson #3). Found in real
# use: pasted log lines sent one by one made ATLAS announce workouts as logged when nothing was.
LOGGING_NOTE = (
    "[LOGGING: You cannot save, log, approve or change any record yourself, and you do not know whether the "
    "system will offer to log anything. Never say you have logged, saved, recorded, approved or remembered "
    "anything, and never say something is in the system or the log because of this message. Do not narrate "
    "approvals or proposals. If Joey wants something logged, tell him to describe it or paste his workout log; "
    "the system takes it from there. Just react to what Joey said.]"
)


def stream_atlas(message: str, history: Optional[list] = None, location: str = "",
                 model_tier: Optional[str] = None):
    """
    history: list of {"role": "user"|"assistant", "content": str}, or None
    Yields text chunks. The caller owns conversation-history persistence.
    """
    # Commands and pasted workout logs are handled with plain rules, BEFORE the
    # refusal gate (a note like "ate food" must never get a workout refused).
    command = parse_approval_command(message)
    if command:
        action, action_id = command
        try:
            if action == "approve":
                yield atlas_actions.approve_and_execute(action_id)
            else:
                yield atlas_actions.deny_action(action_id)
        except RuntimeError as e:
            yield f"I couldn't do that: {e}"
        return
    if is_pending_command(message):
        try:
            yield atlas_actions.list_pending()
        except RuntimeError as e:
            yield f"I couldn't read the waiting list: {e}"
        return
    if looks_like_workout_block(message):
        yield from workout_block_reply(message, history, location, model_tier)
        return
    library_command = parse_library_command(message)
    if library_command and library_command_applies(library_command):
        yield from library_command_reply(library_command)
        return
    program_text = atlas_program.handle_message(message)      # 'my program', 'set next day Pull' (increment 3b)
    if program_text is not None:
        yield program_text
        return
    rules_text = atlas_rules.handle_message(message)           # 'rules', 'add rule ...', 'set angle ...' (Phase 1 item 1.2)
    if rules_text is not None:
        yield rules_text
        return
    # First-time setup interview and profile commands (increment 3a-ii). None = not setup's business.
    setup_text = atlas_setup.handle_message(message)
    if setup_text is not None:
        yield setup_text
        return

    if should_refuse(message, ATLAS_NON_TOPIC, ATLAS_INTENT):
        yield REFUSAL_MESSAGE
        return

    if is_history_question(message):
        try:
            yield history_answer(message)
        except RuntimeError as e:
            yield f"I can't read your fitness data right now: {e}"
        return

    context_blocks = [LOGGING_NOTE]

    try:
        context_blocks.append(
            f"[Live fitness data from Joey's log:\n{atlas_tools.get_data_summary_for_llm()}]"
        )
    except RuntimeError as e:
        context_blocks.append(f"[FITNESS DATA UNAVAILABLE: {e}]")

    if contains_keyword(message, ATLAS_SEARCH_TRIGGERS):
        search_result = web_search(message)
        if search_result.startswith(WEB_SEARCH_FAILED_PREFIX):
            context_blocks.append(search_result)
        else:
            context_blocks.append(format_memory_context([search_result], label="web search results"))

    full_message = "\n\n".join(context_blocks + [f"Joey says: {message}"])

    messages = list(history) if history else []
    messages.append({"role": "user", "content": full_message})

    yield from stream_by_tier("atlas", model_tier, ATLAS_SYSTEM_PROMPT, messages, location)

    # Only reached if the reply streamed fully (an error above propagates).
    # Uses Joey's own message only — never ATLAS's reply (Lesson #3).
    notes = extract_and_propose(message)
    if notes:
        yield "\n\n" + "\n\n".join(notes)