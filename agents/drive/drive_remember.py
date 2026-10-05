"""
DRIVE REMEMBER — what DRIVE LEARNS from Joey and what it RECALLS for him (increment (c), Part 2).
The store itself is shared/drive_memory.py (Part 1).

SAVING (after DRIVE's reply; automatic, and always visible):
  - Joey's OWN message only, never DRIVE's reply (Lesson #3): a wrong DRIVE statement can never become a memory.
  - A cheap whole-word pre-filter ("I always", "I prefer", "I decided", "remember that", "actually"...) decides whether
    the local model is even asked. Advice requests ("should I always ...?") never count.
  - The local model returns standalone third-person facts; PYTHON enforces what the model is only asked to do: the six
    categories, one short fact each, no money (ASSET's), no workouts (ATLAS's), no logged events (mileage, services,
    fill-ups, problems, recalls and Carfax live in the vehicle file), at most MAX_MEMORIES_PER_MESSAGE.
  - Every saved fact is announced ("Remembered: ..."), and so is every failure. The only silent case is a fact that
    was already remembered.
RECALLING (before DRIVE's reply; chat.py skips this for refusals and "show me my logged data"):
  - the closest memories within the relevance cutoff, labeled "background, may be outdated" (Lesson #2);
  - if memory can't be consulted, the model is told so and not to guess (Lesson #12).
Nothing here touches the vehicle file or the approval queue.
"""
from typing import Optional

from shared import drive_memory
from shared.keyword_gate import contains_keyword
from shared.agent_topics import (
    DRIVE_ADVICE_SIGNALS, DRIVE_MEMORY_SIGNALS, DRIVE_MEMORY_BLOCK_WORDS,
    DRIVE_PAST_EVENT_WORDS, DRIVE_HABIT_WORDS,
)
from shared.memory_context import format_memory_context
from shared.model_client import complete_ollama_json
from agents.drive import drive_extract

MAX_MEMORIES_PER_MESSAGE = 3
MAX_INPUT_CHARS = 4000

MEMORY_PROMPT = """You pick out lasting facts from ONE message Joey wrote about his car. Reply with ONLY a JSON object — no other text.
Rules:
- Use ONLY what Joey explicitly says in this message. Never invent, guess or add anything.
- Write each fact as ONE short standalone sentence about Joey in the third person, so it still makes sense months later (for example "Joey always uses full synthetic 0W-20 oil in his Civic.").
- Remember only these kinds of things, and give each fact exactly one category:
  "preference": how Joey likes things done, or what he always or never does with his car
  "decision": a choice Joey has made
  "plan": something Joey is going to do, usually with a time (a trip, a purchase, work on the car: anything he is planning, even if it is not maintenance)
  "goal": something Joey wants to achieve with the car
  "correction": Joey correcting or updating something that was said or assumed before. State the corrected fact directly and keep every detail he gave (for example "Joey's dealer is Honda of South Bend, not the one on Main Street.")
  "project_fact": a lasting fact about his car or situation that a service log would not hold (a quirk, or which shop he uses)
- NEVER remember: mileage readings, fill-ups, services or repairs that were done, new problems, problems that got fixed, recalls, Carfax history, anything about money or prices or budgets, or workouts. Those are tracked elsewhere.
- If the message is a question, a request for advice, a hypothetical, or has nothing lasting in it, reply exactly {"kind": "none"}.
- At most 3 facts.
- The value of "kind" is always "memory" or "none" — never a category name. The category goes inside each memory.

Reply in exactly this shape:
{"kind": "memory", "memories": [{"category": "preference", "fact": "Joey always uses full synthetic 0W-20 oil in his Civic."}]}
"""


# ─────────────────────────────────────────────
# SECTION 1 — SAVING
# ─────────────────────────────────────────────

def looks_memorable(message) -> bool:
    """Cheap pre-filter: is there anything lasting worth asking the model about? Never raises."""
    if not isinstance(message, str) or not message.strip():
        return False
    text = message.replace("\u2019", "'")                 # phone keyboards type curly apostrophes
    if contains_keyword(text, DRIVE_ADVICE_SIGNALS):
        return False
    return contains_keyword(text, DRIVE_MEMORY_SIGNALS)


def _fact_allowed(fact: str) -> bool:
    """Python's guards on a fact the model produced (the prompt asks for the same; this ENFORCES it)."""
    if "$" in fact or contains_keyword(fact, DRIVE_MEMORY_BLOCK_WORDS):
        return False                                       # money is ASSET's, workouts are ATLAS's
    if contains_keyword(fact, DRIVE_PAST_EVENT_WORDS) and not contains_keyword(fact, DRIVE_HABIT_WORDS):
        return False                                       # reads like a logged event: the vehicle file holds it
    return True


def extract_memories(message: str) -> list:
    """
    The facts worth remembering from Joey's message: [{"category", "fact"}], already guarded. [] when there is
    nothing (including when the pre-filter says the model need not be asked). Raises ExtractionError when the
    model call fails or its answer is unusable.
    """
    if not looks_memorable(message):
        return []
    try:
        raw = complete_ollama_json(MEMORY_PROMPT, message[:MAX_INPUT_CHARS])
    except Exception as e:                  # model down, timeout... surfaced as a note, never swallowed
        raise drive_extract.ExtractionError(f"the local model call failed ({type(e).__name__}: {e})") from e
    data = drive_extract._parse_model_json(raw)
    kind = data.get("kind")
    if kind == "none":
        return []
    if kind == "memory":
        items = data.get("memories")
        if not isinstance(items, list):
            raise drive_extract.ExtractionError("the answer had no list of memories")
    elif isinstance(kind, str) and kind in drive_memory.DRIVE_MEMORY_CATEGORIES:
        # The real local model sometimes writes the CATEGORY into "kind". Use ONLY what it actually provided.
        items = data.get("memories")
        if isinstance(items, list):
            items = [dict(i, category=i.get("category", kind)) if isinstance(i, dict) else i for i in items]
        elif "fact" in data:
            items = [{"category": kind, "fact": data.get("fact")}]
        else:
            raise drive_extract.ExtractionError(f"unexpected answer type {kind!r}")
    else:
        raise drive_extract.ExtractionError(f"unexpected answer type {kind!r}")
    kept = []
    for item in items:
        if not isinstance(item, dict):
            continue
        category, fact = item.get("category"), item.get("fact")
        if not isinstance(category, str) or category not in drive_memory.DRIVE_MEMORY_CATEGORIES:
            continue
        if not isinstance(fact, str):
            continue
        fact = " ".join(fact.split())
        if not fact or len(fact) > drive_memory.MAX_FACT_CHARS or not _fact_allowed(fact):
            continue
        kept.append({"category": category, "fact": fact})
    return kept


def remember_from_message(message) -> list:
    """
    Called AFTER DRIVE's reply. Saves what is worth remembering and returns plain notes for Joey
    ("Remembered: ...", or honest 'couldn't' sentences). Never raises.
    """
    try:
        facts = extract_memories(message)
    except (drive_extract.ExtractionError, ValueError, RuntimeError, OSError) as e:
        return [f"I couldn't check that message for anything to remember ({e}). Nothing was saved."]
    notes = []
    for item in facts[:MAX_MEMORIES_PER_MESSAGE]:
        try:
            result = drive_memory.save_memory(item["category"], item["fact"], {"source": "joey_message"})
        except Exception as e:              # Ollama off, ChromaDB trouble: reported, never hidden
            notes.append(f"I couldn't save that to memory ({type(e).__name__}: {e}).")
            continue
        if result["status"] == "saved":
            notes.append(f"Remembered: {item['fact']}")
        elif result["status"] == "filtered":
            notes.append(f"I couldn't save that to memory: {result['reason']}.")
        # "duplicate": already known, so there is nothing new to say
    if len(facts) > MAX_MEMORIES_PER_MESSAGE:
        notes.append(f"I only remembered the first {MAX_MEMORIES_PER_MESSAGE} things from that message — "
                     "tell me the rest again on their own.")
    return notes


# ─────────────────────────────────────────────
# SECTION 2 — RECALLING
# ─────────────────────────────────────────────

def _safe_text(text) -> str:
    """One clean line, with '---' broken up so a stored fact can never fake the end of the background block."""
    return " ".join(str(text).split()).replace("---", "-")


def memory_context_block(message) -> Optional[str]:
    """
    Called BEFORE DRIVE's reply. The labeled background block of the closest memories (None when there are none),
    or a 'memory unavailable, do not guess' note when memory could not be consulted. Never raises.
    """
    if not isinstance(message, str) or not message.strip():
        return None
    try:
        found = drive_memory.search_memories(message, n_results=3)
    except Exception as e:
        return (f"[DRIVE MEMORY UNAVAILABLE: could not consult what Joey told you before ({type(e).__name__}: {e}). "
                "Do not guess or invent anything he supposedly said earlier.]")
    if not found:
        return None
    items = [f"- {_safe_text(m['text'])} (told to you {str(m['saved_at'])[:10]})" for m in found]
    return format_memory_context(items, label="memory (things Joey told you earlier)")