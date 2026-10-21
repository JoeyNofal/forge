"""
ATLAS RULES COMMANDS (Phase 1 item 1.2) - you talk to ATLAS to set up your own training rules.

    rules                      show your rules (reads only)
    add rule <your words>      a LOCAL model drafts the rule; you see exactly what it means, then approve it
    remove rule <id>           a proposal to delete one rule
    set angle <id> <number>    a proposal to set a ladder by hand (for example the lateral raise angle)
    rules setup                the starter set from what your doctor said, one proposal per rule

HOW THE DRAFTING IS KEPT SAFE (the lessons from the real-model runs, enforced in Python)
- The model reads ONLY the one sentence you typed. It never sees your profile, your health notes or your logs,
  and it is the LOCAL model (never the cloud).
- Its answer is untrusted DATA: it must be one of the five rule kinds and passes the same checks as any rule
  (training_rules.normalize_rule). The "words you used" stored with the rule are YOURS, never the model's.
- Every number in the drafted rule must appear as digits in your sentence (the local model copies numbers from
  its own examples). A zero is allowed (for example a ladder that ends at 0).
- Nothing is saved by drafting. You see the exact rule (and, for a "never plan" rule, which of your library
  exercises it would block), and it is saved only when you approve it.
- A message counts as a command ONLY when the WHOLE message is the command (Lesson #6).
"""
import re
from typing import Any, Optional

from agents.atlas import atlas_actions, exercise_library
from agents.atlas import training_rules as rules_mod
from shared.model_client import complete_ollama_json
from shared.model_json import ExtractionError, model_call_failed, parse_model_json

_I = re.IGNORECASE
_SHOW_RE = re.compile(r"^\s*(?:(?:show|view|see|list)\s+(?:my\s+)?(?:training\s+)?rules|my\s+rules|rules)\s*[?.!]?\s*$", _I)
_SETUP_RE = re.compile(r"^\s*(?:rules\s+setup|setup\s+rules|atlas\s+rules\s+setup)\s*[.!]?\s*$", _I)
_ADD_RE = re.compile(r"^\s*add\s+rule\s+(\S[\s\S]*?)\s*[.!]?\s*$", _I)          # any length: a too-long one gets an answer, not silence
_REMOVE_RE = re.compile(r"^\s*remove\s+rule\s+(\S{1,40})\s*[.!]?\s*$", _I)
_ANGLE_RE = re.compile(r"^\s*set\s+angle\s+(\S{1,40})\s+(-?\d{1,4})\s*[.!]?\s*$", _I)

MAX_SENTENCE = 300
MAX_LIBRARY_HITS_SHOWN = 8
MAX_QUESTION = 200
_NUMBER_KEYS = ("rpe_max", "start", "step", "end")

# The starter set (what Joey's doctor said). These are SUGGESTIONS: each becomes a proposal he can approve or
# deny, and once approved it is DATA in his rules file, not code. Nothing here is enforced until he approves it.
STARTER_RULES = [
    {"kind": "forbid", "text": "no explosive moves (doctor's orders)",
     "words": ["jump", "jumps", "jumping", "clean", "cleans", "snatch", "snatches", "throw", "throws", "slam", "slams",
               "burpee", "burpees", "plyo", "plyometric", "plyometrics", "kettlebell swing", "kettlebell swings"],
     "reason": "doctor's orders: no explosive moves"},
    {"kind": "ladder", "text": "lateral raises only with the arm angle progression: back to a wall, arms up at 45 degrees from the wall, "
                              "5 degrees closer to the wall each workout",
     "words": ["lateral raise", "lateral raises", "side raise", "side raises"], "label": "arm angle from the wall",
     "unit": "degrees", "start": 45, "step": -5, "end": 0},
    {"kind": "effort_cap", "text": "RPE 5 for anything upper body while easing in", "scope": "upper_body", "rpe_max": 5,
     "only_ease_in": True},
    {"kind": "forbid", "text": "no curls or chin-ups for now, except leg and hamstring curls",
     "words": ["curl", "curls", "chin up", "chin ups", "chinup", "chinups"], "except_words": ["leg", "hamstring"],
     "reason": "curls and chin-ups are off for now (caution)"},
    {"kind": "drop_muscle", "text": "leave biceps out of the workouts for now", "muscles": ["biceps"],
     "reason": "biceps are left out for now (caution)"},
]

SYSTEM_PROMPT = """You turn ONE sentence about a person's training rules into ONE JSON object. Reply with only the JSON object, no commentary.
Choose "kind":
- "forbid": never plan exercises whose names contain certain words. Fields: words (single words or short phrases that appear in exercise names; include plural forms), except_words (words that make an exercise allowed again; may be empty), reason (short).
- "note": show a note on exercises whose names contain certain words. Fields: words, note (short).
- "effort_cap": limit how hard exercises may be, as RPE from 1 to 10. Fields: scope ("upper_body" or "muscles"), muscles (a list, only when scope is "muscles"), rpe_max, only_ease_in (true ONLY if the person says it applies just to the first workouts or the ease-in).
- "ladder": a number that changes step by step each workout for certain exercises. Fields: words, label, unit, start, step (negative when the number goes down), end.
- "drop_muscle": leave muscles out of workouts. Fields: muscles, reason.
Allowed muscles: chest, shoulders, triceps, back, biceps, rear delts, forearms, quads, hamstrings, glutes, calves, core.
Use ONLY numbers that appear in the sentence (use 0 for an end value of zero). Write words in lower case.
If you cannot tell what rule is meant, reply {"kind": "unclear", "question": "what you need to know"}.
Examples of the shape (the content is made up):
Sentence: no overhead pressing until my coach says so
{"kind": "forbid", "words": ["overhead", "military"], "except_words": [], "reason": "no overhead pressing until the coach agrees"}
Sentence: keep my leg exercises at RPE 6 at most while I ease in
{"kind": "effort_cap", "scope": "muscles", "muscles": ["quads", "hamstrings", "glutes", "calves"], "rpe_max": 6, "only_ease_in": true}
Sentence: wrist curls hold 10 seconds longer each workout, from 20 seconds up to 60
{"kind": "ladder", "words": ["wrist curl", "wrist curls"], "label": "hold time", "unit": "seconds", "start": 20, "step": 10, "end": 60}
Sentence: warn me on deadlifts to check my form first
{"kind": "note", "words": ["deadlift", "deadlifts"], "note": "Check your form first."}"""


# --------------------------------------------------------------
# COMMANDS (whole message only)
# --------------------------------------------------------------

def match_command(message) -> Optional[tuple[str, Any]]:
    """('show'|'setup', None) / ('add'|'remove', text) / ('angle', (id, number)) when the WHOLE message is that command, else None."""
    if _SHOW_RE.match(message):
        return "show", None
    if _SETUP_RE.match(message):
        return "setup", None
    m = _ADD_RE.match(message)
    if m:
        return "add", m.group(1)
    m = _REMOVE_RE.match(message)
    if m:
        return "remove", m.group(1)
    m = _ANGLE_RE.match(message)
    if m:
        return "angle", (m.group(1), int(m.group(2)))
    return None


# --------------------------------------------------------------
# DRAFTING A RULE FROM HIS WORDS
# --------------------------------------------------------------

def _clean_sentence(text) -> str:
    return " ".join("".join(c if (c.isprintable() or c.isspace()) else " " for c in text).split()) if isinstance(text, str) else ""


def _coerce_numbers(data: dict) -> dict:
    """A number the model wrote as text ('45') becomes a number; anything else is left for the checks to refuse."""
    out = dict(data)
    for key in _NUMBER_KEYS:
        v = out.get(key)
        if isinstance(v, str) and re.fullmatch(r"-?\d{1,4}", v.strip()):
            out[key] = int(v.strip())
    return out


def _numbers_stated(rule: dict, sentence: str) -> None:
    """Every nonzero number in the rule must appear as digits in Joey's sentence (the model copies numbers from its examples)."""
    stated = {int(n) for n in re.findall(r"\d+", sentence)}
    for key in _NUMBER_KEYS:
        v = rule.get(key)
        if isinstance(v, int) and not isinstance(v, bool) and v != 0 and abs(v) not in stated:
            raise rules_mod.RuleError(f"the draft used the number {abs(v)}, but that number is not in what you wrote "
                                      f"(write numbers as digits, for example '5 degrees')")


def draft_rule(sentence: str) -> dict:
    """The clean rule drafted from ONE sentence of his, or RuleError / ExtractionError. Saves nothing."""
    text = _clean_sentence(sentence)
    if not text:
        raise rules_mod.RuleError("tell me the rule in a sentence, for example: add rule no overhead pressing for now")
    if len(text) > MAX_SENTENCE:
        raise rules_mod.RuleError(f"that is {len(text)} characters; a rule must be {MAX_SENTENCE} or fewer. Split it into shorter rules")
    try:
        raw = complete_ollama_json(SYSTEM_PROMPT, text)
    except Exception as e:                                     # Ollama down, timeout...: said plainly, never swallowed
        raise model_call_failed(e) from e
    data = parse_model_json(raw)
    if data.get("kind") == "unclear":
        q = _clean_sentence(data.get("question"))[:MAX_QUESTION]
        raise rules_mod.RuleError("I could not tell what rule you mean" + (f": {q}" if q else "") + ". Try saying it another way")
    data = _coerce_numbers(data)
    data["text"] = text                                        # his words are stored, never the model's
    data["active"] = True                                      # a drafted rule is never one that silently does nothing
    data.pop("id", None)
    data.pop("created_at", None)
    rule = rules_mod.normalize_rule(data, keep_id=False)
    _numbers_stated(rule, text)
    return rule


def _library_hits(rule: dict) -> tuple:
    """(names of library exercises a 'never plan' rule would block, how many in all). Quietly (names, total) = ([], 0) if unreadable."""
    if rule.get("kind") != "forbid":
        return [], 0
    try:
        entries = exercise_library.list_entries()
    except RuntimeError:
        return [], 0
    names = [str(e.get("name")) for e in entries if isinstance(e, dict) and rules_mod.forbid_reason(e.get("name"), [dict(rule, active=True)])]
    return names[:MAX_LIBRARY_HITS_SHOWN], len(names)


def _approve_hint(action_id: str) -> str:
    short = action_id[:8]
    return f"\n\nReply 'approve {short}' to save it, or 'deny {short}' to throw it away."


# --------------------------------------------------------------
# WHAT EACH COMMAND DOES
# --------------------------------------------------------------

def show_rules() -> str:
    rules, skipped = rules_mod.load_rules_report()
    if not rules:
        text = "You have no rules yet. Type 'rules setup' for the starter set, or 'add rule <your words>' to make your own."
    else:
        text = f"Your rules ({len(rules)}):\n" + rules_mod.list_rules_text(rules)
    if skipped:
        text += f"\n\n({skipped} saved entr{'y' if skipped == 1 else 'ies'} could not be read and {'is' if skipped == 1 else 'are'} being ignored.)"
    return text


def add_rule_reply(sentence: str) -> str:
    try:
        rule = draft_rule(sentence)
        if rules_mod.duplicate_of(rule, rules_mod.load_rules()):
            return "You already have a rule that means the same thing. Type 'rules' to see it. Nothing was saved."
        names, total = _library_hits(rule)
        action_id, text = atlas_actions.propose_add_rule(rule, names, total)
    except ExtractionError as e:
        return (f"I couldn't turn that into a rule: {e}. Nothing was saved. "
                f"You can say it another way, or type 'rules setup' for the starter set.")
    except rules_mod.RuleError as e:
        return f"I couldn't turn that into a rule: {e}. Nothing was saved."
    return ("Here is what I understood. Read the words carefully, they are exactly what ATLAS will enforce:\n\n"
            + text + _approve_hint(action_id))


def remove_rule_reply(ident: str) -> str:
    try:
        action_id, text = atlas_actions.propose_remove_rule(ident)
    except rules_mod.RuleError as e:
        return f"I couldn't do that: {e}. Nothing was changed. Type 'rules' to see the ids."
    return text + _approve_hint(action_id)


def set_angle_reply(ident: str, number: int) -> str:
    try:
        action_id, text = atlas_actions.propose_set_ladder(ident, number)
    except rules_mod.RuleError as e:
        return f"I couldn't do that: {e}. Nothing was changed. Type 'rules' to see the ids."
    return text + _approve_hint(action_id)


def setup_reply() -> str:
    existing = rules_mod.load_rules()
    parts, skipped = [], 0
    for preset in STARTER_RULES:
        rule = rules_mod.normalize_rule(preset, keep_id=False)
        if rules_mod.duplicate_of(rule, existing):
            skipped += 1
            continue
        names, total = _library_hits(rule)
        action_id, text = atlas_actions.propose_add_rule(rule, names, total)
        parts.append(text + _approve_hint(action_id))
    if not parts:
        return "You already have every rule in the starter set. Type 'rules' to see them."
    head = ("Starter rules from what your doctor said. Each one is its own proposal: approve the ones you want and deny the rest. "
            "Nothing is saved until you approve it.")
    if skipped:
        head += f" ({skipped} you already have, so I left {'it' if skipped == 1 else 'them'} out.)"
    return head + "\n\n" + "\n\n".join(parts)


def handle_message(message) -> Optional[str]:
    """The text to show for a rules command, or None when the message is none of its business. A non-text message fails loudly."""
    command = match_command(message)
    if command is None:
        return None
    kind, value = command
    try:
        if kind == "show":
            return show_rules()
        if kind == "setup":
            return setup_reply()
        if kind == "add":
            return add_rule_reply(value)
        if kind == "remove":
            return remove_rule_reply(value)
        return set_angle_reply(*value)
    except RuntimeError as e:
        return f"I can't read or write your rules right now: {e}"