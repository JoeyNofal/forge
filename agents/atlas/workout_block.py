"""
WORKOUT BLOCK - reads the text block the phone page copies back
(ATLAS workout template, increment 1a).

Pure reading: text in, clean dict out. It never talks to a model, never
touches a file, never saves anything. Saving is increment 1b.

BLOCK FORMAT (version 1) - the page builds it, nobody types it:

    FORGE WORKOUT LOG v1
    Title: Chest workout
    Date: 2026-10-01
    Unit: lbs

    ## Warmup
    Exercise: Windmill arms
    Prescribed: 1x20 per arm | weight: bodyweight | rest: 30 sec | target RPE: 5
    Set 1: 20 reps | bodyweight
    RPE: 5
    Notes: my shoulders click

RULES (Lessons #5 and #6):
- A line only counts as a keyword line when the keyword starts the line and is
  followed by a colon. No loose substring matching.
- Nothing is invented. An empty set row is "skipped", never saved as 0. A weight
  that is not stated stays None.
- A line it cannot read becomes a plain-English warning and is skipped. A block
  that is unusable as a whole raises BlockError.
- Weights stay in the unit Joey wrote. Converting kg to pounds happens later,
  in atlas_logging (increment 1b), not here.
"""
import re

from shared.normalizers import date_or_today

BLOCK_VERSION = 1
MAX_BLOCK_CHARS = 20000
MAX_SECTIONS = 10
MAX_EXERCISES = 30      # per section
MAX_SETS = 30           # per exercise
MAX_NAME = 100
MAX_NOTES = 500
MAX_REPS = 10000
MAX_SECONDS = 36000
MAX_WEIGHT = 5000       # in whatever unit was written (lbs or kg)
MAX_WARNINGS = 50


class BlockError(ValueError):
    """The block cannot be used as a whole (wrong header, nothing in it, too big...)."""


_NUM = r"\d+(?:\.\d+)?"
_HEADER_START_RE = re.compile(r"^forge workout log\b", re.IGNORECASE)
_HEADER_RE = re.compile(r"^forge workout log\s+v(\d+)\s*$", re.IGNORECASE)
_SECTION_RE = re.compile(r"^#{1,3}\s*(.+)$")
_SET_RE = re.compile(r"^set\s*(\d+)\s*:\s*(.*)$", re.IGNORECASE)
_KEY_RE = re.compile(r"^(title|date|unit|exercise|prescribed|rpe|notes)\s*:\s*(.*)$", re.IGNORECASE)
_AMOUNT_RE = re.compile(rf"^({_NUM})\s*(reps?|secs?|seconds?|s|mins?|minutes?)?$", re.IGNORECASE)
_WEIGHT_RE = re.compile(rf"^({_NUM})\s*(lbs?|pounds?|kgs?|kilos?|kilograms?)?$", re.IGNORECASE)
_UNIT_RE = re.compile(r"^(?:lbs?|pounds?|kgs?|kilos?|kilograms?)$", re.IGNORECASE)
_PRESCRIBED_SETS_RE = re.compile(
    rf"^({_NUM})\s*x\s*({_NUM})\s*(reps?|secs?|seconds?|s|mins?|minutes?)?\b", re.IGNORECASE)
_REST_RE = re.compile(rf"^rest\s*:\s*({_NUM})\s*(secs?|seconds?|s|mins?|minutes?|m)?$", re.IGNORECASE)
_TARGET_RPE_RE = re.compile(rf"^target\s*rpe\s*:\s*({_NUM})$", re.IGNORECASE)
_PRESCRIBED_WEIGHT_RE = re.compile(r"^weight\s*:\s*(.*)$", re.IGNORECASE)
_RPE_RE = re.compile(rf"^({_NUM})\s*(?:/\s*10)?$")
_WARMUP_RE = re.compile(r"\bwarm[\s-]?up\b", re.IGNORECASE)
_COOLDOWN_RE = re.compile(r"\bcool[\s-]?down\b", re.IGNORECASE)
_BODYWEIGHT_WORDS = ("bodyweight", "body weight", "bw")


# --------------------------------------------------------------
# SMALL HELPERS
# --------------------------------------------------------------

def _clean(text: str) -> str:
    """Phone keyboards and copy-paste bring smart punctuation, odd spaces, Windows line ends."""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\u00a0", " ").replace("\t", " ")
    t = t.replace("\u2019", "'").replace("\u2018", "'")
    t = t.replace("\u201c", '"').replace("\u201d", '"')
    t = t.replace("\u00d7", "x").replace("\u2013", "-").replace("\u2014", "-")
    return t


def _tidy(n):
    if n != n or n in (float("inf"), float("-inf")):
        return n          # infinity / NaN pass through; the range checks reject them
    return int(n) if n == int(n) else n


def _num(s: str):
    return _tidy(float(s))


def _warn(warnings: list, message: str) -> None:
    if len(warnings) < MAX_WARNINGS:
        warnings.append(message)
    elif len(warnings) == MAX_WARNINGS:
        warnings.append("more problems were found but are not listed")


def _unit_family(unit):
    """'lbs' / 'kg' from a unit word, or None when no unit was written."""
    if not unit:
        return None
    return "kg" if unit.lower().startswith("k") else "lbs"


def _section_kind(name: str) -> str:
    if _WARMUP_RE.search(name):
        return "warmup"
    if _COOLDOWN_RE.search(name):
        return "cooldown"
    return "main"


def _amount(text: str):
    """'10' or '10 reps' -> ('reps', 10); '30 sec' / '1 min' -> ('seconds', 30 / 60). Else None."""
    m = _AMOUNT_RE.match(text.strip())
    if not m:
        return None
    n = _num(m.group(1))
    unit = (m.group(2) or "reps").lower()
    if unit.startswith("rep"):
        return "reps", n
    if unit.startswith("m"):
        return "seconds", _tidy(n * 60)
    return "seconds", n


def _weight(text: str):
    """(kind, number, unit). kind is none / bodyweight / number / bad."""
    t = text.strip().lower()
    if not t:
        return "none", None, None
    if t in _BODYWEIGHT_WORDS:
        return "bodyweight", None, None
    m = _WEIGHT_RE.match(t)
    if not m:
        return "bad", None, None
    return "number", _num(m.group(1)), _unit_family(m.group(2))


def _parse_rpe(text: str, name: str, warnings: list):
    t = text.strip()
    if not t:
        return None
    m = _RPE_RE.match(t)
    if not m:
        _warn(warnings, f"{name}: could not read RPE '{t[:20]}' - left blank")
        return None
    n = _num(m.group(1))
    if not 1 <= n <= 10:
        _warn(warnings, f"{name}: RPE {n} is outside 1 to 10 - left blank")
        return None
    return n


def _parse_set(number: int, body: str, default_unit, name: str, warnings: list):
    """
    Returns None (set skipped) or (set_dict, unit_was_assumed).
    An empty row is simply "not done". Nothing is invented.
    """
    parts = [p.strip() for p in body.split("|")]
    amount_text = parts[0]
    weight_text = parts[1] if len(parts) > 1 else ""
    if not amount_text and not weight_text:
        return None
    if not amount_text:
        _warn(warnings, f"{name} set {number}: has a weight but no reps or time - skipped")
        return None
    a = _amount(amount_text)
    if a is None:
        _warn(warnings, f"{name} set {number}: could not read '{amount_text[:30]}' - skipped")
        return None
    kind, value = a
    if value <= 0:
        return None                                   # 0 reps = not done
    if value > (MAX_REPS if kind == "reps" else MAX_SECONDS):
        _warn(warnings, f"{name} set {number}: the number of {kind} is too large - skipped")
        return None

    wkind, weight, unit = _weight(weight_text)
    bodyweight = wkind == "bodyweight"
    assumed = False
    if wkind == "bad":
        _warn(warnings, f"{name} set {number}: could not read weight '{weight_text[:30]}' - weight left blank")
    if wkind == "number" and weight is not None:
        if weight > MAX_WEIGHT:
            _warn(warnings, f"{name} set {number}: that weight is too large - weight left blank")
            weight, unit = None, None
        elif weight == 0:
            weight, unit = None, None
        else:
            unit = unit or default_unit
            if not unit:
                unit, assumed = "lbs", True
    else:
        weight, unit = None, None
    return {
        "set": number,
        "reps": value if kind == "reps" else None,
        "seconds": value if kind == "seconds" else None,
        "weight": weight,
        "weight_unit": unit,
        "bodyweight": bodyweight,
    }, assumed


def _parse_prescribed(text: str) -> dict:
    """What ATLAS asked for. Advisory only: unreadable parts are simply left None."""
    out = {"text": text[:200], "sets": None, "reps": None, "seconds": None,
           "weight": None, "weight_unit": None, "bodyweight": False,
           "rest_seconds": None, "target_rpe": None}
    for part in (p.strip() for p in text.split("|")):
        m = _PRESCRIBED_WEIGHT_RE.match(part)
        if m:
            kind, value, unit = _weight(m.group(1))
            if kind == "bodyweight":
                out["bodyweight"] = True
            elif kind == "number" and value is not None and 0 < value <= MAX_WEIGHT:
                out["weight"], out["weight_unit"] = value, unit
            continue
        m = _REST_RE.match(part)
        if m:
            n = _num(m.group(1))
            unit = (m.group(2) or "s").lower()
            seconds = _tidy(n * 60) if unit.startswith("m") else n
            if 0 <= seconds <= MAX_SECONDS:
                out["rest_seconds"] = seconds
            continue
        m = _TARGET_RPE_RE.match(part)
        if m:
            n = _num(m.group(1))
            if 1 <= n <= 10:
                out["target_rpe"] = n
            continue
        m = _PRESCRIBED_SETS_RE.match(part)
        if m and out["sets"] is None:
            sets = _num(m.group(1))
            amount = _num(m.group(2))
            unit = (m.group(3) or "reps").lower()
            if 1 <= sets <= MAX_SETS and sets == int(sets):
                out["sets"] = int(sets)
                if unit.startswith("rep"):
                    out["reps"] = amount if amount <= MAX_REPS else None
                else:
                    seconds = _tidy(amount * 60) if unit.startswith("m") else amount
                    out["seconds"] = seconds if seconds <= MAX_SECONDS else None
    return out


# --------------------------------------------------------------
# PUBLIC FUNCTIONS
# --------------------------------------------------------------

def looks_like_workout_block(text) -> bool:
    """Cheap check used before parsing: does the first non-empty line start the block header?"""
    if not isinstance(text, str):
        return False
    for line in _clean(text[:2000]).split("\n"):
        if line.strip():
            return bool(_HEADER_START_RE.match(line.strip()))
    return False


def parse_workout_block(text) -> dict:
    """
    Block text -> {"title", "date", "unit", "sections", "units_assumed", "warnings"}.
    Each section: {"name", "kind" (warmup/main/cooldown), "exercises": [...]}.
    Each exercise: {"name", "prescribed", "sets", "sets_skipped", "rpe", "notes"}.
    Raises TypeError for a non-string, BlockError when the block is unusable.
    """
    if not isinstance(text, str):
        raise TypeError(f"workout block must be a string, got {type(text).__name__}")
    if len(text) > MAX_BLOCK_CHARS:
        raise BlockError(f"workout block is too long ({len(text)} characters, the limit is {MAX_BLOCK_CHARS})")

    lines = [ln.strip() for ln in _clean(text).split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    if not lines or not _HEADER_START_RE.match(lines[0]):
        raise BlockError("this is not a FORGE workout log (the first line must be 'FORGE WORKOUT LOG v1')")
    m = _HEADER_RE.match(lines[0])
    if not m:
        raise BlockError("the header line must be exactly 'FORGE WORKOUT LOG v1'")
    if int(m.group(1)[:6]) != BLOCK_VERSION:
        raise BlockError(f"unsupported workout log version v{m.group(1)[:6]}")

    title, date_raw, default_unit = "", "", None
    sections, section, ex = [], None, None
    notes_open = False
    units_assumed, warnings = [], []
    total_exercises = 0

    for line in lines[1:]:
        if not line:
            notes_open = False
            continue

        m = _SECTION_RE.match(line)
        if m:
            if len(sections) >= MAX_SECTIONS:
                raise BlockError(f"too many sections (the limit is {MAX_SECTIONS})")
            name = m.group(1).strip()[:MAX_NAME]
            section = {"name": name, "kind": _section_kind(name), "exercises": []}
            sections.append(section)
            ex, notes_open = None, False
            continue

        m = _SET_RE.match(line)
        if m:
            notes_open = False
            if ex is None:
                _warn(warnings, f"a set line outside any exercise was ignored: '{line[:40]}'")
                continue
            if len(ex["sets"]) + ex["sets_skipped"] >= MAX_SETS:
                _warn(warnings, f"{ex['name']}: more than {MAX_SETS} sets - extra sets ignored")
                continue
            if len(m.group(1)) > 4:
                _warn(warnings, f"{ex['name']}: set number '{m.group(1)[:10]}' is not sensible - skipped")
                ex["sets_skipped"] += 1
                continue
            result = _parse_set(int(m.group(1)), m.group(2), default_unit, ex["name"], warnings)
            if result is None:
                ex["sets_skipped"] += 1
            else:
                set_dict, was_assumed = result
                ex["sets"].append(set_dict)
                if was_assumed and ex["name"] not in units_assumed:
                    units_assumed.append(ex["name"])
            continue

        m = _KEY_RE.match(line)
        if m:
            key, value = m.group(1).lower(), m.group(2).strip()
            notes_open = False
            if key in ("title", "date", "unit"):
                if section is not None:
                    _warn(warnings, f"'{key}' line after the first section was ignored")
                elif key == "title":
                    title = value[:MAX_NAME]
                elif key == "date":
                    date_raw = value
                elif _UNIT_RE.match(value):
                    default_unit = _unit_family(value)
                elif value:
                    _warn(warnings, f"unit '{value[:20]}' not understood (use lbs or kg)")
                continue
            if key == "exercise":
                if not value:
                    _warn(warnings, "an Exercise line with no name was ignored")
                    ex = None
                    continue
                if section is None:
                    section = {"name": "Workout", "kind": "main", "exercises": []}
                    sections.append(section)
                if len(section["exercises"]) >= MAX_EXERCISES:
                    raise BlockError(f"too many exercises in one section (the limit is {MAX_EXERCISES})")
                ex = {"name": value[:MAX_NAME], "prescribed": None, "sets": [],
                      "sets_skipped": 0, "rpe": None, "notes": ""}
                section["exercises"].append(ex)
                total_exercises += 1
                continue
            if ex is None:
                _warn(warnings, f"a '{key}' line outside any exercise was ignored")
                continue
            if key == "prescribed":
                ex["prescribed"] = _parse_prescribed(value)
            elif key == "rpe":
                ex["rpe"] = _parse_rpe(value, ex["name"], warnings)
            elif key == "notes":
                ex["notes"] = value[:MAX_NOTES]
                notes_open = True
            continue

        if notes_open and ex is not None:           # a note that ran onto more lines
            ex["notes"] = (ex["notes"] + " " + line).strip()[:MAX_NOTES]
            continue
        _warn(warnings, f"line not understood, skipped: '{line[:40]}'")

    sections = [s for s in sections if s["exercises"]]
    if total_exercises == 0 or not sections:
        raise BlockError("the workout log contains no exercises")

    date = date_or_today(date_raw)
    if date_raw and date != date_raw.strip()[:10]:
        _warn(warnings, f"date '{date_raw[:20]}' is not a valid past or present date - today's date was used")

    return {
        "title": title or "Workout",
        "date": date,
        "unit": default_unit,
        "sections": sections,
        "units_assumed": units_assumed,
        "warnings": warnings,
    }