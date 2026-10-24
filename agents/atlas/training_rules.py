"""
TRAINING RULES (ATLAS, Phase 1 item 1.1) - the rules Joey sets up WITH ATLAS, stored as data.

WHY THIS EXISTS
Joey does not want safety rules hardcoded in ATLAS's code: he wants to create them by talking to ATLAS
(for example "no explosive moves, doctor's orders"). So the CONTENT of every rule (which words, which numbers)
lives in one locked data file he controls, and this module is the small, fixed ENGINE that enforces them. The
engine has to be code, because a model must never be the thing that enforces a safety rule.

FIVE KINDS OF RULE (the only things the engine understands)
- forbid       never plan an exercise whose name contains any of these words (unless it also has an exception word)
- note         exercises containing these words get a note line
- effort_cap   target effort (RPE) no higher than N, for all upper-body exercises or named muscles, optionally
               only during the ease-in
- ladder       a number that steps toward a target each workout (an arm angle 45 -> 0, say); pain steps it back;
               at the end the exercise becomes a normal exercise
- drop_muscle  leave these muscles out of a day's muscle list

RULES FOR THIS MODULE
- NO model and NO network code here. Later increments let a LOCAL model translate Joey's words into one of these
  five forms; he always sees the exact form as a proposal and approves it. Nothing a model says is stored unseen.
- Every write is one locked read-modify-write (Lesson #4). A damaged or wrong-shaped file fails loudly and is never
  overwritten (Lesson #5). Entries this version does not understand are skipped when reading and KEPT when writing.
- Word matching is whole-word (Lesson #6), through shared.keyword_gate.
- The file lives in the data folder (kept out of git): it contains health details.
"""
import json
import os
import re
import time
import uuid
from datetime import datetime
from functools import lru_cache
from typing import Any, Optional

from shared.file_store import load_json, update_json
from shared.keyword_gate import contains_keyword

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_RULES_PATH = os.path.join(_REPO_ROOT, "data", "training_rules.json")

RULES_VERSION = 1
KINDS = ("forbid", "note", "effort_cap", "ladder", "drop_muscle")
MUSCLES = ("chest", "shoulders", "triceps", "back", "biceps", "rear delts", "forearms",
           "quads", "hamstrings", "glutes", "calves", "core")
UPPER_BODY_MUSCLES = ("chest", "shoulders", "triceps", "back", "biceps", "rear delts", "forearms")
MAX_RULES = 50
MAX_WORDS = 20
MIN_WORD_CHARS = 3
MAX_WORD_CHARS = 30
MAX_WORD_TOKENS = 3
MAX_TEXT = 300
MAX_REASON = 150
MAX_NOTE = 200
MAX_LABEL = 60
MAX_UNIT = 12
MAX_NUMBER = 1000
MAX_EXAMPLES = 8
MAX_EXAMPLE_CHARS = 60
ID_MIN_PREFIX = 4


class RuleError(ValueError):
    """A rule (or a request about rules) that cannot be accepted; the message is plain English and safe to show Joey."""


def get_rules_path() -> str:
    return os.path.abspath(os.getenv("TRAINING_RULES_PATH") or DEFAULT_RULES_PATH)


# --------------------------------------------------------------
# CLEANING (nothing is trusted: Lesson #5)
# --------------------------------------------------------------

def _plain(v) -> str:
    """Lower-case letters and digits separated by single spaces ('Chin-Ups' -> 'chin ups'), for matching."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", v.lower()).split()) if isinstance(v, str) else ""


def _line(v, limit: int) -> str:
    """One clean line: every kind of whitespace becomes one space, other control characters are dropped."""
    if not isinstance(v, str):
        return ""
    return " ".join("".join(c if (c.isprintable() or c.isspace()) else " " for c in v).split())[:limit]


def _int(v, name: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or abs(v) > MAX_NUMBER:
        raise RuleError(f"{name} must be a whole number between -{MAX_NUMBER} and {MAX_NUMBER}")
    return v


def _words(v, name: str, required: bool) -> list:
    """A list of plain words or short phrases (letters only, 3-30 characters, at most 3 words each), no repeats."""
    if v is None and not required:
        return []
    if not isinstance(v, list):
        raise RuleError(f"{name} must be a list of words")
    out: list = []
    for item in v:
        word = _plain(item)
        if not word:
            continue
        if any(c.isdigit() for c in word):
            raise RuleError(f"'{word}' has a number in it; {name} are plain words")
        if len(word) < MIN_WORD_CHARS or len(word) > MAX_WORD_CHARS or len(word.split()) > MAX_WORD_TOKENS:
            raise RuleError(f"'{word}' is not a usable word (3 to {MAX_WORD_CHARS} letters, at most {MAX_WORD_TOKENS} words)")
        if word not in out:
            out.append(word)
    if len(out) > MAX_WORDS:
        raise RuleError(f"too many {name} (at most {MAX_WORDS})")
    if required and not out:
        raise RuleError(f"a rule needs at least one of {name}")
    return out


def _muscles(v, required: bool) -> list:
    if v is None and not required:
        return []
    if not isinstance(v, list):
        raise RuleError("muscles must be a list")
    out = []
    for m in v:
        key = _plain(m)
        if key not in MUSCLES:
            raise RuleError(f"'{_line(m, 30)}' is not a muscle I know (use: {', '.join(MUSCLES)})")
        if key not in out:
            out.append(key)
    if required and not out:
        raise RuleError("a rule needs at least one muscle")
    return out


def _examples(v, label: str) -> list:
    """Exercise names given as examples (kept as written, no repeats, at most 8)."""
    if v is None:
        return []
    if not isinstance(v, list):
        raise RuleError(f"{label} must be a list of exercise names")
    out: list = []
    seen: set = set()
    for item in v:
        text = _line(item, MAX_EXAMPLE_CHARS)
        key = _plain(text)
        if key and key not in seen:
            seen.add(key)
            out.append(text)
    return out[:MAX_EXAMPLES]


def _ladder_ok(start: int, step: int, end: int, current: int) -> None:
    if step == 0:
        raise RuleError("the step cannot be zero")
    if (end - start) * step <= 0:
        raise RuleError("the step must move from the start toward the end")
    low, high = (start, end) if step > 0 else (end, start)
    if not low <= current <= high:
        raise RuleError("the current value must lie between the start and the end")


def normalize_rule(raw, keep_id: bool = True) -> dict:
    """A clean rule from a dict, or RuleError. Unknown keys are dropped; every field is checked."""
    if not isinstance(raw, dict):
        raise RuleError("a rule must be an object")
    kind = raw.get("kind")
    if kind not in KINDS:
        raise RuleError(f"unknown kind of rule (use one of: {', '.join(KINDS)})")
    text = _line(raw.get("text"), MAX_TEXT)
    if not text:
        raise RuleError("a rule needs the words you used to describe it")
    rule_id = _line(raw.get("id"), 20) if keep_id else ""
    rule: dict[str, Any] = {"id": rule_id or uuid.uuid4().hex[:8], "kind": kind, "text": text,
                            "created_at": _line(raw.get("created_at"), 40)}
    if kind == "forbid":
        rule["words"] = _words(raw.get("words"), "words to block", True)
        rule["except_words"] = _words(raw.get("except_words"), "exception words", False)
        if set(rule["words"]) & set(rule["except_words"]):
            raise RuleError("a word cannot be both blocked and an exception")
        rule["examples"] = _examples(raw.get("examples"), "examples")
        rule["allowed_examples"] = _examples(raw.get("allowed_examples"), "allowed_examples")
        for ex in rule["examples"]:                 # a rule is CHECKED against its own examples
            if not _blocked(ex, rule["words"], rule["except_words"]):
                raise RuleError(f"the words would not block '{ex}', which is listed as an example of what the rule blocks")
        for ex in rule["allowed_examples"]:
            if _blocked(ex, rule["words"], rule["except_words"]):
                raise RuleError(f"the words would block '{ex}', which should stay allowed")
        rule["reason"] = _line(raw.get("reason"), MAX_REASON) or "blocked by one of your rules"
    elif kind == "note":
        rule["words"] = _words(raw.get("words"), "words to match", True)
        rule["note"] = _line(raw.get("note"), MAX_NOTE)
        if not rule["note"]:
            raise RuleError("a note rule needs the note to show")
    elif kind == "effort_cap":
        scope = raw.get("scope")
        if scope not in ("upper_body", "muscles"):
            raise RuleError("scope must be 'upper_body' or 'muscles'")
        rule["scope"] = scope
        rule["muscles"] = _muscles(raw.get("muscles"), scope == "muscles") if scope == "muscles" else []
        rpe = _int(raw.get("rpe_max"), "rpe_max")
        if not 1 <= rpe <= 10:
            raise RuleError("rpe_max must be from 1 to 10")
        rule["rpe_max"] = rpe
        only = raw.get("only_ease_in", False)
        if not isinstance(only, bool):
            raise RuleError("only_ease_in must be true or false")
        rule["only_ease_in"] = only
    elif kind == "ladder":
        rule["words"] = _words(raw.get("words"), "words to match", True)
        rule["label"] = _line(raw.get("label"), MAX_LABEL)
        rule["unit"] = _line(raw.get("unit"), MAX_UNIT)
        if not rule["label"]:
            raise RuleError("a ladder needs a label (for example 'arm angle from the wall')")
        start, step, end = _int(raw.get("start"), "start"), _int(raw.get("step"), "step"), _int(raw.get("end"), "end")
        current = _int(raw["current"], "current") if raw.get("current") is not None else start
        _ladder_ok(start, step, end, current)
        done = raw.get("done", False)
        if not isinstance(done, bool):
            raise RuleError("done must be true or false")
        rule.update({"start": start, "step": step, "end": end, "current": current, "done": done})
    else:   # drop_muscle
        rule["muscles"] = _muscles(raw.get("muscles"), True)
        rule["reason"] = _line(raw.get("reason"), MAX_REASON) or "left out by one of your rules"
    active = raw.get("active", True)
    rule["active"] = active if isinstance(active, bool) else True
    return rule


def _fingerprint(rule: dict) -> tuple:
    keys = ("kind", "words", "except_words", "scope", "muscles", "rpe_max", "only_ease_in", "start", "step", "end", "note")
    return tuple((k, tuple(sorted(rule[k])) if isinstance(rule.get(k), list) else rule.get(k)) for k in keys if k in rule)


# --------------------------------------------------------------
# READING (never writes, never creates the file)
# --------------------------------------------------------------

def _load_data() -> dict:
    path = get_rules_path()
    data = None
    for attempt in (1, 2):                            # a reader can catch a write in progress: one quick retry
        try:
            data = load_json(path, {})
            break
        except json.JSONDecodeError as e:
            if attempt == 2:
                raise RuntimeError(f"training rules file is damaged ({e.msg}): {path}") from e
            time.sleep(0.05)
    if not isinstance(data, dict) or ("rules" in data and not isinstance(data["rules"], list)):
        raise RuntimeError("training rules file has the wrong shape (expected an object with a 'rules' list)")
    return data


def load_rules_report() -> tuple:
    """(clean rules, number of entries skipped because this version could not understand them)."""
    rules, skipped = [], 0
    for entry in _load_data().get("rules", []):
        try:
            rules.append(normalize_rule(entry))
        except RuleError:
            skipped += 1
    return rules, skipped


def load_rules() -> list:
    """Every rule that can be understood (active or not). A missing file is simply no rules yet."""
    return load_rules_report()[0]


# --------------------------------------------------------------
# WRITING (each one locked read-modify-write; an error writes nothing)
# --------------------------------------------------------------

def _update(modify) -> None:
    """update_json on the rules file; a damaged file is a loud RuntimeError and is never overwritten."""
    try:
        update_json(get_rules_path(), modify, {})
    except json.JSONDecodeError as e:
        raise RuntimeError(f"training rules file is damaged ({e.msg}): {get_rules_path()}") from e


def _entries(data: Any) -> list:
    if not isinstance(data, dict) or ("rules" in data and not isinstance(data["rules"], list)):
        raise RuleError("the rules file has the wrong shape, so nothing was changed")
    data.setdefault("version", RULES_VERSION)
    data.setdefault("rules", [])
    return data["rules"]


def add_rule(raw) -> dict:
    """Saves ONE new rule and returns it. Refuses a duplicate, a bad rule, or a 51st rule."""
    rule = normalize_rule(raw, keep_id=False)
    rule["created_at"] = datetime.now().isoformat()
    result: dict[str, Any] = {}

    def _modify(data):
        entries = _entries(data)
        if len(entries) >= MAX_RULES:
            raise RuleError(f"you already have {MAX_RULES} rules; remove one first")
        taken = {e.get("id") for e in entries if isinstance(e, dict)}
        while rule["id"] in taken:
            rule["id"] = uuid.uuid4().hex[:8]
        for e in entries:
            try:
                other = normalize_rule(e)
            except RuleError:
                continue
            if other["active"] and _fingerprint(other) == _fingerprint(rule):
                raise RuleError(f"you already have this rule ({other['id']})")
        entries.append(rule)
        result["rule"] = rule
        return data

    _update(_modify)
    return result["rule"]


def _find(entries: list, ident) -> int:
    """The index of the entry with this id (the full id, or a unique start of at least 4 characters)."""
    key = _line(ident, 20).lower()
    if not key:
        raise RuleError("tell me which rule (its id)")
    ids = [(i, e["id"]) for i, e in enumerate(entries) if isinstance(e, dict) and isinstance(e.get("id"), str)]
    exact = [i for i, rid in ids if rid.lower() == key]
    if exact:
        return exact[0]
    if len(key) >= ID_MIN_PREFIX:
        part = [i for i, rid in ids if rid.lower().startswith(key)]
        if len(part) == 1:
            return part[0]
        if len(part) > 1:
            raise RuleError(f"'{key}' matches more than one rule; type more of the id")
    raise RuleError(f"no rule found with the id '{key}'")


def get_rule(ident) -> dict:
    """The clean rule with this id (the full id or a unique start of 4+ characters). READS only; RuleError when none/ambiguous."""
    entries = _load_data().get("rules", [])
    return normalize_rule(entries[_find(entries, ident)])


def check_ladder_value(rule: dict, value) -> int:
    """The value, if it is a whole number lying between this ladder's start and end; else RuleError. Pure."""
    number = _int(value, "value")
    _ladder_ok(rule["start"], rule["step"], rule["end"], number)
    return number


def duplicate_of(rule, rules) -> Optional[dict]:
    """The ACTIVE rule in `rules` that means exactly the same as `rule`, or None."""
    if not isinstance(rule, dict) or not isinstance(rules, list):
        return None
    mine = _fingerprint(rule)
    for other in rules:
        if isinstance(other, dict) and other.get("active") is True and _fingerprint(other) == mine:
            return other
    return None


def remove_rule(ident) -> dict:
    """Deletes ONE rule and returns what was removed."""
    result: dict[str, Any] = {}

    def _modify(data):
        entries = _entries(data)
        removed = entries.pop(_find(entries, ident))
        try:
            result["rule"] = normalize_rule(removed)
        except RuleError:                       # an entry this version cannot read can still be removed by its id
            result["rule"] = {"id": removed.get("id") if isinstance(removed, dict) else "", "kind": "unreadable"}
        return data

    _update(_modify)
    return result["rule"]


def set_ladder_value(ident, value) -> dict:
    """Sets a ladder's current value by hand (it must lie between its start and end); the ladder is not 'done' any more."""
    result: dict[str, Any] = {}

    def _modify(data):
        entries = _entries(data)
        i = _find(entries, ident)
        rule = normalize_rule(entries[i])
        if rule["kind"] != "ladder":
            raise RuleError("that rule is not a ladder")
        _ladder_ok(rule["start"], rule["step"], rule["end"], _int(value, "value"))
        rule["current"], rule["done"] = value, False
        entries[i] = rule
        result["rule"] = rule
        return data

    _update(_modify)
    return result["rule"]


def next_ladder_value(rule: dict, discomfort: bool) -> tuple:
    """(next current value, done) after a workout done at rule['current']. Pure.
    Comfortable: step toward the end (a comfortable workout AT the end finishes the ladder).
    Discomfort: go back one step, never past the start."""
    cur, step, start, end = rule["current"], rule["step"], rule["start"], rule["end"]
    if discomfort:
        back = cur - step
        return (max(start, back) if step > 0 else min(start, back)), False
    ahead = cur + step
    return (min(end, ahead) if step > 0 else max(end, ahead)), cur == end


def apply_ladder_result(ident, discomfort: bool) -> dict:
    """Moves a ladder after a workout (locked) and returns {'before', 'after', 'done', 'rule'}. A finished ladder does not move."""
    result: dict[str, Any] = {}

    def _modify(data):
        entries = _entries(data)
        i = _find(entries, ident)
        rule = normalize_rule(entries[i])
        if rule["kind"] != "ladder":
            raise RuleError("that rule is not a ladder")
        before = rule["current"]
        if not rule["done"]:
            rule["current"], rule["done"] = next_ladder_value(rule, bool(discomfort))
        entries[i] = rule
        result.update({"before": before, "after": rule["current"], "done": rule["done"], "rule": rule})
        return data

    _update(_modify)
    return result


# --------------------------------------------------------------
# ENFORCING (pure: they take the rules list, so they are easy to test and cannot write)
# --------------------------------------------------------------

def _active(rules, kind: str) -> list:
    return [r for r in rules if isinstance(r, dict) and r.get("kind") == kind and r.get("active") is True] if isinstance(rules, list) else []


@lru_cache(maxsize=1024)
def _variants(words: tuple) -> tuple:
    """Each word with its plural, singular and -ing forms (curl -> curls, jumps -> jump, jump <-> jumping, raise -> raising,
    run -> running, chin up -> chin ups), so a rule written with one form still matches the others. Words ending in 'ss'
    (press) are not shortened. A form that is not a real word is harmless: it simply never matches an exercise name."""
    out: list = []
    for w in words:
        options = [w]
        if w.endswith(("ss", "x", "ch", "sh")):
            options.append(w + "es")                      # press -> presses, box -> boxes
        elif w.endswith("s"):
            if len(w) > 3:
                options.append(w[:-1])                    # curls -> curl
        else:
            options.append(w + "s")                       # curl -> curls
        base = w[:-1] if (w.endswith("s") and not w.endswith("ss") and len(w) > 3) else w
        if base.endswith("ing") and len(base) > 5:
            stem = base[:-3]                              # jumping -> jump, raising -> raise, running -> run
            options += [stem, stem + "s", stem + "e"]
            if len(stem) > 2 and stem[-1] == stem[-2]:
                options.append(stem[:-1])
        else:
            options.append(base + "ing")                  # jump -> jumping, row -> rowing
            if base.endswith("e"):
                options.append(base[:-1] + "ing")         # raise -> raising
            if len(base) >= 3 and base[-1] not in "aeiouwxy" and base[-2] in "aeiou" and base[-3] not in "aeiou":
                options.append(base + base[-1] + "ing")   # run -> running, slam -> slamming
        for v in options:
            if v and v not in out:
                out.append(v)
    return tuple(out)


def _matches(name, words) -> bool:
    if not isinstance(words, list) or not words or not all(isinstance(w, str) for w in words):
        return False
    return contains_keyword(_plain(name), list(_variants(tuple(words))))


def _blocked(name, words, except_words) -> bool:
    return _matches(name, words) and not _matches(name, except_words)


def forbid_reason(name, rules) -> str:
    """'' when no rule blocks this exercise, else the reason of the first rule that does."""
    for r in _active(rules, "forbid"):
        if _blocked(name, r.get("words"), r.get("except_words")):
            return str(r.get("reason") or "blocked by one of your rules")
    return ""


def notes_for(name, rules) -> list:
    """The note lines (no repeats) of every note rule that matches this exercise."""
    out: list = []
    for r in _active(rules, "note"):
        note = r.get("note")
        if isinstance(note, str) and note and _matches(name, r.get("words")) and note not in out:
            out.append(note)
    return out


def effort_cap_for(muscle, rules, ease_in_active: bool) -> Optional[int]:
    """The lowest RPE cap that applies to an exercise working this muscle, or None. Caps marked 'only during the ease-in' count only then."""
    key = _plain(muscle)
    caps = []
    for r in _active(rules, "effort_cap"):
        rpe, scope, muscles = r.get("rpe_max"), r.get("scope"), r.get("muscles")
        if isinstance(rpe, bool) or not isinstance(rpe, int):
            continue
        if r.get("only_ease_in") is True and not ease_in_active:
            continue
        if (scope == "upper_body" and key in UPPER_BODY_MUSCLES) or (scope == "muscles" and isinstance(muscles, list) and key in muscles):
            caps.append(rpe)
    return min(caps) if caps else None


def ladder_for(name, rules) -> Optional[dict]:
    """The ladder this exercise is on right now, or None (no ladder, or it is finished: a normal exercise again)."""
    for r in _active(rules, "ladder"):
        nums = [r.get(k) for k in ("current", "start", "step", "end")]
        if not _matches(name, r.get("words")) or r.get("done") is True or any(isinstance(n, bool) or not isinstance(n, int) for n in nums):
            continue
        return {"id": r.get("id"), "label": r.get("label"), "unit": r.get("unit"), "value": r["current"], "start": r["start"],
                "step": r["step"], "end": r["end"]}
    return None


def has_ladder(name, rules) -> bool:
    """True when ANY active ladder rule (finished or not) names this exercise."""
    return any(_matches(name, r.get("words")) for r in _active(rules, "ladder"))


def dropped_muscles(rules) -> list:
    out: list = []
    for r in _active(rules, "drop_muscle"):
        muscles = r.get("muscles")
        out += [m for m in (muscles if isinstance(muscles, list) else []) if isinstance(m, str) and m not in out]
    return out


# --------------------------------------------------------------
# SHOWING A RULE (used by the proposals Joey approves)
# --------------------------------------------------------------

def describe_rule(rule) -> str:
    """The exact meaning of a rule in plain words, so Joey sees what he is approving."""
    if not isinstance(rule, dict) or rule.get("kind") not in KINDS:
        return "(a rule I cannot read)"
    k = rule["kind"]
    head = f"Your words: \"{_line(rule.get('text'), MAX_TEXT)}\""
    if k == "forbid":
        body = "Never plan an exercise whose name contains: " + ", ".join(rule.get("words", []))
        if rule.get("except_words"):
            body += f" (unless it also contains: {', '.join(rule['except_words'])})"
        body += f". Reason shown: {rule.get('reason', '')}"
        shown = [str(x) for x in rule.get("examples", []) if isinstance(x, str)] if isinstance(rule.get("examples"), list) else []
        allowed = [str(x) for x in rule.get("allowed_examples", []) if isinstance(x, str)] if isinstance(rule.get("allowed_examples"), list) else []
        if shown:
            body += f"\nBlocks, for example: {', '.join(shown)}"
        if allowed:
            body += f"\nStill allowed: {', '.join(allowed)}"
    elif k == "note":
        body = f"Add this note to exercises containing: {', '.join(rule.get('words', []))}. Note: {rule.get('note', '')}"
    elif k == "effort_cap":
        who = "all upper-body exercises" if rule.get("scope") == "upper_body" else f"exercises for: {', '.join(rule.get('muscles', []))}"
        body = f"Target effort no higher than RPE {rule.get('rpe_max')} for {who}" + (", only during the ease-in" if rule.get("only_ease_in") else "")
    elif k == "ladder":
        unit = f" {rule.get('unit')}" if rule.get("unit") else ""
        step = rule.get("step")
        step_text = f"{step:+d}" if isinstance(step, int) and not isinstance(step, bool) else str(step)
        body = (f"For exercises containing: {', '.join(rule.get('words', []))}. {rule.get('label')}: start {rule.get('start')}{unit}, "
                f"step {step_text}{unit} each workout, until {rule.get('end')}{unit}; discomfort goes back one step; "
                f"at the end it becomes a normal exercise. Now at {rule.get('current')}{unit}" + (" (finished)" if rule.get("done") else ""))
    else:
        body = f"Leave out of the muscle list: {', '.join(rule.get('muscles', []))}. Reason shown: {rule.get('reason', '')}"
    return head + "\n" + body


def list_rules_text(rules) -> str:
    """A numbered list for the `rules` command."""
    items = [r for r in rules if isinstance(r, dict)] if isinstance(rules, list) else []
    if not items:
        return "You have no rules yet."
    return "\n".join(f"{i}. [{r.get('id')}] {'' if r.get('active') else '(paused) '}{describe_rule(r)}" for i, r in enumerate(items, 1))