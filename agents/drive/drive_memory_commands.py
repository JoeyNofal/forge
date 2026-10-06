"""
DRIVE MEMORY COMMANDS — "what do you remember?" and "forget ..." (increment (c), Part 3).

Handled FIRST in chat, with NO model call (so they also work when Ollama is off, except forgetting by meaning,
which needs the embeddings; forgetting by id never does). They never save or recall anything.

- LIST: a numbered list of what DRIVE has saved, newest first, with category, date and a 6-character id.
- FORGET: ALWAYS a proposal Joey approves (the same approval gate as every other change), showing the exact
  memory. Nothing is deleted before approval. Forms: "forget <description>", "forget <id>", "forget that" (the
  newest memory), "forget everything" / "wipe your memory" (exactly the memories that exist NOW).
  If two memories match about equally, DRIVE lists them and asks which one — it never guesses.
- Everyday phrases are NOT commands ("forget it", "forget about it", "I forgot ...", "don't forget ..."): only a
  message that STARTS with "forget" (or "wipe/clear/erase/delete your memory") counts.
"""
import re
from typing import Optional

from shared import drive_memory
from shared.keyword_gate import contains_keyword
from shared.agent_topics import DRIVE_MEMORY_LIST_PHRASES
from agents.drive import drive_actions
from agents.drive import issue_match

MAX_LIST = 20
SHORT_ID = 6
FORGET_MAX_DISTANCE = 0.52       # real data: best UNRELATED target 0.554, worst legitimate target 0.493
AMBIGUITY_MARGIN = 0.03          # two memories this close are a tie: ask, never guess

_LEAD = r"(?:\W*(?:hey|ok|okay|please|can you|could you|would you|you can|go ahead and|just)\s+)*"
_FORGET_RE = re.compile(rf"^{_LEAD}forget\b[\s,:\-]*(.*)$", re.I | re.S)
_WIPE_RE = re.compile(
    rf"^{_LEAD}(?:wipe|clear|erase|delete|reset)\s+(?:out\s+)?(?:all\s+)?(?:of\s+)?(?:your|my|the|drive's)\s+(?:memory|memories)\b", re.I)
_ALL_RE = re.compile(
    r"^(?:everything|all|all of it|it all|all (?:of )?(?:your |my |the )?(?:memory|memories|that)|"
    r"everything you (?:know|remember)(?: about me)?)\W*$", re.I)
_NEVERMIND_RE = re.compile(r"^(?:about\s+)?it\b", re.I)                         # "forget it", "forget about it"
_LAST_RE = re.compile(r"^(?:that|this|that one|this one|the last (?:thing|one|memory)|what i (?:just )?(?:said|told you))\W*$", re.I)
_ID_RE = re.compile(r"^(?:memory\s+|id\s+|#)?([0-9a-f]{6,36}(?:-[0-9a-f\-]*)?)\W*$", re.I)
_FILLER_RE = re.compile(r"^(?:about|that|the fact that|what i said about|what i told you about|what i said|what i told you)\s+", re.I)


# ─────────────────────────────────────────────
# SECTION 1 — RECOGNIZING A COMMAND (no model, no files)
# ─────────────────────────────────────────────

def detect_memory_command(message) -> Optional[dict]:
    """
    None for anything that isn't a memory command (including every non-text input). Otherwise one of:
    {"kind": "list"} | {"kind": "forget_all"} | {"kind": "forget_last"} | {"kind": "forget", "target": text}
    """
    if not isinstance(message, str):
        return None
    text = " ".join(message.replace("\u2019", "'").split())
    if not text:
        return None
    if _WIPE_RE.match(text):
        return {"kind": "forget_all"}
    m = _FORGET_RE.match(text)
    if m:
        rest = m.group(1).strip().rstrip("?!. ").strip()
        if not rest:
            return None                                   # a bare "forget" is ambiguous: ignore it
        if _ALL_RE.match(rest):
            return {"kind": "forget_all"}
        if _NEVERMIND_RE.match(rest):
            return None                                   # "forget it" is everyday speech, not a command
        if _LAST_RE.match(rest):
            return {"kind": "forget_last"}
        if _ID_RE.match(rest):
            return {"kind": "forget", "target": rest}
        for _n in range(3):                               # "that I always use 0W-20" -> "I always use 0W-20"
            stripped = _FILLER_RE.sub("", rest, count=1).strip()
            if stripped == rest:
                break
            rest = stripped
        return {"kind": "forget", "target": rest} if rest else None
    if contains_keyword(text, DRIVE_MEMORY_LIST_PHRASES):
        return {"kind": "list"}
    return None


# ─────────────────────────────────────────────
# SECTION 2 — ANSWERING IT
# ─────────────────────────────────────────────

def _short(memory_id) -> str:
    return str(memory_id)[:SHORT_ID]


def _describe(m: dict) -> str:
    parts = [p for p in (str(m.get("category") or ""), str(m.get("saved_at") or "")[:10]) if p]
    parts.append(f"id {_short(m.get('id'))}")
    return f"{m.get('text')} [{', '.join(parts)}]"


def _list_reply() -> str:
    items = drive_memory.list_memories()
    if not items:
        return ('I haven\'t been told anything to remember yet. Tell me things like "I always use full synthetic '
                '0W-20 oil" or "remember that the left rear window sticks" and I\'ll keep them.')
    lines = [f"Here's what I remember ({len(items)}):"]
    for n, m in enumerate(items[:MAX_LIST], 1):
        lines.append(f"{n}. {_describe(m)}")
    if len(items) > MAX_LIST:
        lines.append(f"...and {len(items) - MAX_LIST} more.")
    lines.append('To remove one, say "forget" and describe it, or "forget <id>". "forget everything" clears all (you approve first).')
    return "\n".join(lines)


def _ask_which(hits: list) -> str:
    lines = ["That could mean more than one memory:"]
    for n, m in enumerate(hits, 1):
        lines.append(f"{n}. {_describe(m)}")
    lines.append('Tell me which one, for example "forget <id>". Nothing was changed.')
    return "\n".join(lines)


def _propose_one(memory: dict) -> str:
    return drive_actions.propose_forget_memory(memory)[1]


def _forget_last_reply() -> str:
    newest = drive_memory.list_memories(limit=1)
    if not newest:
        return "I haven't saved any memories, so there is nothing to forget."
    return _propose_one(newest[0])


def _forget_all_reply() -> str:
    items = drive_memory.list_memories()
    if not items:
        return "I haven't saved any memories, so there is nothing to forget."
    return drive_actions.propose_forget_all_memories(items)[1]


def _forget_reply(target) -> str:
    target = " ".join(str(target or "").split())
    if not target:
        return 'Tell me what to forget, for example "forget the Colorado trip", or use an id from "what do you remember?".'
    memories = drive_memory.list_memories()
    if not memories:
        return "I haven't saved any memories, so there is nothing to forget."

    id_match = _ID_RE.match(target)                          # 1) an id from the list (works even with Ollama off)
    if id_match and len(id_match.group(1)) >= SHORT_ID:
        prefix = id_match.group(1).lower()
        hits = [m for m in memories if str(m["id"]).lower().startswith(prefix)]
        if len(hits) == 1:
            return _propose_one(hits[0])
        if len(hits) > 1:
            return _ask_which(hits[:5])

    words = issue_match.content_words(target)                # 2) his exact WORDS: a vague word that fits several
    by_words = [m for m in memories if words and words <= issue_match.content_words(m["text"])]   # memories is a question
    if len(by_words) >= 2:
        return _ask_which(by_words[:5])

    try:                                                     # 3) a description: found by MEANING
        found = drive_memory.search_memories(target, n_results=3, max_distance=FORGET_MAX_DISTANCE)
    except Exception as e:
        if len(by_words) == 1:                               # embeddings down, but his words fit exactly one memory
            return _propose_one(by_words[0])
        return (f"I couldn't search my memory right now ({type(e).__name__}: {e}). "
                'Say "forget <id>" using an id from "what do you remember?".')
    if not found:
        if len(by_words) == 1:                               # too far in meaning, but his words fit exactly one memory
            return _propose_one(by_words[0])
        return (f'I couldn\'t find a memory matching "{target[:80]}". Say "what do you remember?" to see them all. '
                "(Logged mileage, services, fill-ups and issues aren't memories: they live in your vehicle file, "
                "and you remove those in the DRIVE Tracker.)")
    ties = [f for f in found if f["distance"] - found[0]["distance"] < AMBIGUITY_MARGIN]
    if len(ties) >= 2:
        return _ask_which(ties)
    return _propose_one(found[0])


def handle_memory_command(command) -> str:
    """The reply for a detected command. Never raises: a problem becomes a plain sentence and nothing is changed."""
    try:
        kind = command.get("kind") if isinstance(command, dict) else None
        if kind == "list":
            return _list_reply()
        if kind == "forget_all":
            return _forget_all_reply()
        if kind == "forget_last":
            return _forget_last_reply()
        if kind == "forget":
            return _forget_reply(command.get("target"))
        return "I didn't understand that memory command. Nothing was changed."
    except Exception as e:
        return f"I couldn't do that with my memory ({type(e).__name__}: {e}). Nothing was changed."