"""
DRIVE EXTRACT — turns what Joey SAYS into log PROPOSALS (increment (b), Part 3b).

For one message Joey sent:
  1. detect_report_kinds(): a cheap whole-word pre-filter — does this even look
     like a mileage statement / fill-up / service / problem / "it's fixed"?
     (Lesson #6.) Questions and advice requests never count as reports.
  2. For each kind, ONE call to the LOCAL model (shared complete_ollama_json)
     with a prompt that spells out the exact JSON shape (Lesson #5). The model
     sees ONLY Joey's own message plus the numbered list of his open problems —
     never DRIVE's replies or history — so a wrong DRIVE statement can never be
     "extracted" back into data (Lesson #3).
  3. The answer is parsed and handed to drive_actions.propose_*, which
     re-validates it and queues a proposal. NOTHING is saved here: Joey approves
     or denies each proposal separately.

The real local model ignores some prompt rules, so Python ENFORCES them
(issue_match.py): a problem already on the open list is not proposed again;
"my light is fixed" with two light problems asks which one instead of guessing;
a service only "fixes" an open issue if the words actually overlap.

Every failure (model down, timeout, junk JSON, data the validators reject) becomes
ONE plain sentence for Joey. Nothing is guessed and nothing is silently dropped
(Lesson #12): a 4th thing in one message, or a 2nd job in a service report, gets
an explicit note.

Open problems are shown to the model as "1 — description", and it answers with
NUMBERS; Python maps them back to real ids (a garbled 36-character id can't
mislead it), and only a real JSON true counts for resolved_all / ambiguous.
"""
import json
import re
from datetime import datetime
from typing import Optional

from shared.keyword_gate import contains_keyword
from shared.agent_topics import (
    DRIVE_ADVICE_SIGNALS, DRIVE_MILEAGE_WORDS, DRIVE_FILLUP_WORDS, DRIVE_SERVICE_WORDS,
    DRIVE_SERVICE_DONE_SIGNALS, DRIVE_ISSUE_SYMPTOM_WORDS, DRIVE_ISSUE_RESOLVED_PHRASES,
    DRIVE_BRAKE_REMINDER_PHRASES, DRIVE_CARFAX_WORDS,
)
from shared.model_client import complete_ollama_json
from agents.drive import drive_actions
from agents.drive import issue_match
from agents.drive.drive_tools import SERVICE_DISPLAY_NAMES

MAX_INPUT_CHARS = 4000      # only the first part of a huge message goes to the model
MAX_KINDS = 3               # things handled per message
MAX_ISSUES_SHOWN = 50       # most recent open problems shown to the model
MAX_NAMES_IN_NOTE = 5       # how many problem names a "which one?" note spells out

KIND_MILEAGE = "mileage"
KIND_FILLUP = "fillup"
KIND_MAINTENANCE = "maintenance"
KIND_ISSUE = "issue"
KIND_ISSUE_UPDATE = "issue_update"
KIND_BRAKE_REMINDER = "brake_reminder"
KIND_CARFAX = "carfax"
_LABELS = {
    KIND_MILEAGE: "a mileage update", KIND_FILLUP: "a fill-up", KIND_MAINTENANCE: "a service entry",
    KIND_ISSUE: "an issue", KIND_ISSUE_UPDATE: "an issue update", KIND_BRAKE_REMINDER: "a brake reminder",
    KIND_CARFAX: "a Carfax entry",
}
_ALL_FIXED_RE = re.compile(r"\b100\s*(?:%|percent)", re.I)


class ExtractionError(Exception):
    """The local model call failed or its answer wasn't usable JSON."""


# ─────────────────────────────────────────────
# SECTION 1 — DETECTION (does it even look like a report?)
# ─────────────────────────────────────────────

def detect_report_kinds(message: str) -> list:
    """
    Which extractions to TRY, in the order they are handled. Empty = nothing to log.
    Raises TypeError for a non-string (fails loudly rather than guessing).
    """
    if not isinstance(message, str):
        raise TypeError(f"message must be a string, got {type(message).__name__}")
    text = message.replace("\u2019", "'").strip()      # phone keyboards type curly apostrophes
    if not text:
        return []
    if contains_keyword(text, DRIVE_BRAKE_REMINDER_PHRASES):
        return [KIND_BRAKE_REMINDER]       # a direct command: nothing else in the message is a "report"
    if contains_keyword(text, DRIVE_CARFAX_WORDS) and not contains_keyword(text, DRIVE_ADVICE_SIGNALS):
        return [KIND_CARFAX]               # a Carfax record is history: never also a service/mileage report
    advice = contains_keyword(text, DRIVE_ADVICE_SIGNALS)
    has_digit = any(c.isdigit() for c in text)
    kinds = []
    if contains_keyword(text, DRIVE_ISSUE_RESOLVED_PHRASES) or _ALL_FIXED_RE.search(text):
        kinds.append(KIND_ISSUE_UPDATE)
    fillup = has_digit and not advice and contains_keyword(text, DRIVE_FILLUP_WORDS)
    if fillup:
        kinds.append(KIND_FILLUP)
    service = (not advice and contains_keyword(text, DRIVE_SERVICE_WORDS)
               and contains_keyword(text, DRIVE_SERVICE_DONE_SIGNALS))
    if service:
        kinds.append(KIND_MAINTENANCE)
    # A mileage that rides along with a service or fill-up belongs to THAT record.
    if has_digit and not advice and not fillup and not service and contains_keyword(text, DRIVE_MILEAGE_WORDS):
        kinds.append(KIND_MILEAGE)
    # Problems are reported even alongside a question ("light is on, what do I do?").
    if contains_keyword(text, DRIVE_ISSUE_SYMPTOM_WORDS):
        kinds.append(KIND_ISSUE)
    return kinds


# ─────────────────────────────────────────────
# SECTION 2 — PROMPTS (exact output shapes, Lesson #5)
# ─────────────────────────────────────────────

_SERVICE_KEYS = ", ".join(k for k in SERVICE_DISPLAY_NAMES if k != "gas")

_COMMON_RULES = """You extract data from ONE message Joey wrote about his car. Reply with ONLY a JSON object — no other text.
Today's date is {{TODAY}}.
Rules:
- Use ONLY what the message explicitly says. Never invent a number, date, service or problem.
- The numbers inside the example JSON below are only examples. Never copy them.
- If a number is not stated, use null. If a date is not stated, use an empty string. If Joey says "yesterday" or "last Friday", work out the date from today's date.
- Convert units: liters to US gallons (1 L = 0.264 gal), kilometers to miles (1 km = 0.621 mi).
- If the message is a question, a plan, a request for advice, a hypothetical, or something that did not really happen, reply exactly {"kind": "none"}.
"""

MILEAGE_PROMPT = _COMMON_RULES + """
Task: Joey may be telling you how many miles his car has RIGHT NOW (what the odometer reads).

Reply in exactly this shape:
{"kind": "mileage", "mileage": 52000}
- mileage is a whole number, only if he said what the car's odometer currently reads.
- A mileage that is only part of a plan, a question, a past event, or a service interval (for example "oil change due at 60,000 miles") is NOT his current mileage: {"kind": "none"}
"""

FILLUP_PROMPT = _COMMON_RULES + """
Task: Joey may be reporting a fuel fill-up he ALREADY did.

Reply in exactly this shape:
{"kind": "fillup", "date": "", "gallons": 10, "price_per_gallon": null, "total_cost": 30, "mileage": null}
- gallons: how much fuel he put in. price_per_gallon: only if he said the per-gallon price. total_cost: only if he said what it cost in total (dollars).
- mileage: the odometer reading at the fill-up, only if he said it.
- Never work out a missing number yourself.
- If it is not a completed fill-up: {"kind": "none"}
"""

MAINTENANCE_PROMPT = _COMMON_RULES + """
Task: Joey may be reporting car maintenance or a repair he ALREADY had done.

Reply in exactly this shape:
{"kind": "maintenance", "service_type": "oil_change", "date": "", "mileage": null, "shop": "", "cost": null, "performed_by": "", "notes": "", "parts_used": [], "fixes_issue_numbers": [], "more_jobs": false}
- service_type: use one of these exact keys if the work matches: {{SERVICES}}. Otherwise write a short plain description of the work with spaces, like "brake pad replacement".
- If he reports TWO OR MORE different jobs, describe only the first one and set more_jobs to true.
- performed_by: "shop" if a shop or dealership did it, "diy" if he did it himself, otherwise an empty string.
- shop: the business name only if he named one (like "Honda of South Bend"); otherwise an empty string. Never write just "dealership" or "shop".
- mileage: the odometer reading when it was done, only if he said it. cost: dollars, only if he said it.
- parts_used: a list of strings, only parts he named.
- notes: extra details about the WORK itself, in his words; an empty string if none. Never put percentages or feelings in notes.
- fixes_issue_numbers: the numbers of any OPEN PROBLEMS below that this work clearly fixes (for example new brakes fix "squeaky brakes"). An empty list if none or if you are not sure.
OPEN PROBLEMS (number — description):
{{ISSUES}}
- If it is not completed work: {"kind": "none"}
"""

ISSUE_PROMPT = _COMMON_RULES + """
Task: Joey may be reporting a problem with his car that EXISTS RIGHT NOW.

Reply in exactly this shape:
{"kind": "issue", "description": "tire pressure light is on", "severity": "", "notes": "", "date": ""}
- description: the problem in Joey's own words, kept short. Two symptoms of the same problem go in ONE description.
- severity is "low", "medium" or "high" ONLY if his words say so (for example "dangerous" means high); otherwise an empty string.
- notes: other symptoms or details he mentioned about the problem, in his own words (for example "buzzing while driving"); an empty string if none. Never write about his question or about Joey himself.
- If he also asks a question, still report the problem itself — but do NOT answer the question.
- A problem he says is fixed, gone, or only happened in the past is NOT a current problem: {"kind": "none"}
- If he is only asking in general ("why would a car do X?"), or the problem is already in the list below: {"kind": "none"}
ALREADY LISTED (number — description):
{{ISSUES}}
"""

UPDATE_PROMPT = _COMMON_RULES + """
Task: Joey may be saying that a problem with his car is fixed or gone.

OPEN PROBLEMS (number — description):
{{ISSUES}}

Reply in exactly this shape:
{"kind": "issue_update", "issue_numbers": [1], "resolved_all": false, "ambiguous": false, "notes": "", "date": ""}
- issue_numbers: the numbers of the open problems he says are fixed. Only numbers from the list above.
- resolved_all: true ONLY if he says everything or all of them is fixed or fine ("everything is fixed", "all good now", "100%").
- ambiguous: true if he names ONE problem but more than one in the list could be what he means; then put every candidate number in issue_numbers.
- If he is not saying a listed problem is fixed: {"kind": "none"}
"""

CARFAX_PROMPT = _COMMON_RULES + """
Task: Joey may be telling you about ONE service record from a Carfax vehicle history report (work a PREVIOUS owner had done, before he owned the car).

Reply in exactly this shape:
{"kind": "carfax", "service_type": "oil_change", "date": "2024-03-15", "mileage": 40000, "shop": "", "cost": null, "notes": "", "parts_used": [], "more_jobs": false}
- date: the exact date on the record as YYYY-MM-DD, only if the message gives a full date. Otherwise an empty string. For this task, never use today's date and never work out a relative date like "last year".
- service_type: use one of these exact keys if the work matches: {{SERVICES}}. Otherwise write a short plain description of the work with spaces, like "timing belt replacement".
- mileage: the odometer reading on the record, only if stated. cost: dollars, only if stated.
- shop: the business name only if one is named; otherwise an empty string. Never write just "dealership" or "shop".
- notes: extra details about the work in his words; an empty string if none.
- parts_used: a list of strings, only parts named.
- If he lists TWO OR MORE records, describe only the first one and set more_jobs to true.
- If he is only asking a question, or this is not a service record: {"kind": "none"}
"""

_PROMPTS = {
    KIND_MILEAGE: MILEAGE_PROMPT, KIND_FILLUP: FILLUP_PROMPT, KIND_MAINTENANCE: MAINTENANCE_PROMPT,
    KIND_ISSUE: ISSUE_PROMPT, KIND_ISSUE_UPDATE: UPDATE_PROMPT, KIND_CARFAX: CARFAX_PROMPT,
}


def _shown(open_issues: list) -> list:
    return open_issues[-MAX_ISSUES_SHOWN:]


def _format_issues(open_issues: list) -> str:
    shown = _shown(open_issues)
    if not shown:
        return "(none)"
    return "\n".join(f"{n} — {desc}" for n, (_iid, desc) in enumerate(shown, 1))


def _build_prompt(kind: str, today: str, open_issues: list) -> str:
    return (_PROMPTS[kind]
            .replace("{{TODAY}}", today)
            .replace("{{SERVICES}}", _SERVICE_KEYS)
            .replace("{{ISSUES}}", _format_issues(open_issues)))


# ─────────────────────────────────────────────
# SECTION 3 — CALLING THE LOCAL MODEL
# ─────────────────────────────────────────────

def _parse_model_json(text) -> dict:
    """Model text -> dict, or ExtractionError. Tolerates ```json fences; nothing else."""
    if not isinstance(text, str) or not text.strip():
        raise ExtractionError("the local model returned nothing")
    cleaned = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.S | re.I)
    if fenced:
        cleaned = fenced.group(1)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"the local model's answer wasn't valid JSON ({e.msg})") from e
    if not isinstance(data, dict):
        raise ExtractionError(f"expected a JSON object, got {type(data).__name__}")
    return data


def _extract(kind: str, message: str, today: str, open_issues: list) -> dict:
    prompt = _build_prompt(kind, today, open_issues)
    try:
        raw_text = complete_ollama_json(prompt, message[:MAX_INPUT_CHARS])
    except Exception as e:       # model down, timeout, bad response — surfaced, never swallowed
        raise ExtractionError(f"the local model call failed ({type(e).__name__}: {e})") from e
    return _parse_model_json(raw_text)


# ─────────────────────────────────────────────
# SECTION 4 — EXTRACT -> PROPOSE (with the Python guards)
# ─────────────────────────────────────────────

def _numbers_to_ids(numbers, open_issues: list) -> list:
    """The model's 1-based issue numbers -> real ids. Anything that isn't a valid number is ignored."""
    if not isinstance(numbers, list):
        return []
    shown = _shown(open_issues)
    ids = []
    for n in numbers:
        if isinstance(n, bool):
            continue
        if isinstance(n, str) and n.strip().isdigit():
            n = int(n.strip())
        if isinstance(n, float) and n.is_integer():
            n = int(n)
        if isinstance(n, int) and 1 <= n <= len(shown):
            iid = shown[n - 1][0]
            if iid not in ids:
                ids.append(iid)
    return ids


def _propose_resolution(ids: list, date, notes) -> str:
    raw = {"new_status": "resolved", "resolution_notes": notes, "date": date}
    if len(ids) == 1:
        return drive_actions.propose_issue_update(dict(raw, issue_id=ids[0]))[1]
    return drive_actions.propose_issues_update(dict(raw, issue_ids=ids))[1]


def _names_for_note(names: list) -> str:
    shown = "; ".join(str(n) for n in names[:MAX_NAMES_IN_NOTE])
    extra = len(names) - MAX_NAMES_IN_NOTE
    return shown + (f" (and {extra} more)" if extra > 0 else "")


def _ask_which(names: list) -> list:
    return [f"That could mean more than one open problem ({_names_for_note(names)}). "
            "Tell me which one(s) you mean. Nothing was proposed."]


def _doubtful_pick(chosen_id: str, open_issues: list, message: str):
    """
    Guard for ONE chosen issue. Returns the descriptions Joey should choose between if the
    pick looks doubtful (another open issue matches his words just as well, or better), else None.
    When his words match NO issue at all ("the second one"), the model's pick is trusted.
    """
    scores = issue_match.issue_scores(message, open_issues)
    top = max(scores, default=0)
    if top == 0:
        return None
    position = {iid: n for n, (iid, _desc) in enumerate(open_issues)}[chosen_id]
    best = [n for n, s in enumerate(scores) if s == top]
    if scores[position] < top or len(best) > 1:
        return [open_issues[n][1] for n in sorted(set(best + [position]))]
    return None


def _handle_issue_update(data: dict, open_issues: list, handled_ids: set, message: str) -> list:
    ids = _numbers_to_ids(data.get("issue_numbers"), open_issues)
    names = dict(open_issues)
    if data.get("resolved_all") is True:
        ids = [iid for iid, _desc in open_issues]          # Python decides "all", not the model
    elif data.get("ambiguous") is True and len(ids) >= 2:
        return _ask_which([names.get(i, i) for i in ids])
    elif not ids:
        return ["I couldn't tell which open problem you mean. Nothing was proposed."]
    elif len(ids) == 1:
        doubtful = _doubtful_pick(ids[0], open_issues, message)
        if doubtful:
            return _ask_which(doubtful)
    handled_ids.update(ids)
    return [_propose_resolution(ids, data.get("date"), data.get("notes"))]


def _handle_maintenance(data: dict, open_issues: list, handled_ids: set, message: str) -> list:
    notes = [drive_actions.propose_maintenance(data)[1]]
    if data.get("more_jobs") is True:
        notes.append("You mentioned more than one job — I only proposed the first. Send the others on their own.")
    # The model's claim that this work fixes an open issue is only believed when the words overlap.
    names = dict(open_issues)
    claimed = [i for i in _numbers_to_ids(data.get("fixes_issue_numbers"), open_issues) if i not in handled_ids]
    text = f"{message} {data.get('service_type') or ''}"
    fix_ids = [i for i in claimed if issue_match.overlap(names.get(i, ""), text) >= 1]
    if fix_ids:
        handled_ids.update(fix_ids)
        notes.append(_propose_resolution(fix_ids, data.get("date"), ""))
    return notes


def _handle_issue(data: dict, open_issues: list) -> list:
    already = issue_match.find_duplicate(data.get("description"), open_issues)
    if already is not None:
        return [f"That problem is already on your open list ({already}) — I didn't propose it again."]
    return [drive_actions.propose_issue(data)[1]]


def _handle_carfax(data: dict) -> list:
    notes = [drive_actions.propose_carfax(data)[1]]
    if data.get("more_jobs") is True:
        notes.append("You listed more than one Carfax record — I only proposed the first. Send the others on their own.")
    return notes


def _handle(kind: str, message: str, today: str, open_issues: list, handled_ids: set) -> list:
    """One extraction. Returns a list of notes for Joey ([] when there's nothing to log)."""
    if kind == KIND_BRAKE_REMINDER:        # a fixed command: no local-model call at all
        return [drive_actions.propose_brake_reminder()[1]]
    data = _extract(kind, message, today, open_issues)
    found = data.get("kind")
    if found == "none":
        return []
    if found != kind:
        raise ExtractionError(f"unexpected answer type {found!r}")
    if kind == KIND_MILEAGE:
        return [drive_actions.propose_mileage(data)[1]]
    if kind == KIND_FILLUP:
        return [drive_actions.propose_fillup(data)[1]]
    if kind == KIND_ISSUE:
        return _handle_issue(data, open_issues)
    if kind == KIND_CARFAX:
        return _handle_carfax(data)
    if kind == KIND_MAINTENANCE:
        return _handle_maintenance(data, open_issues, handled_ids, message)
    return _handle_issue_update(data, open_issues, handled_ids, message)


def extract_and_propose(message: str, today: Optional[str] = None) -> list:
    """
    The one function chat.py calls. Returns a list of plain-English notes for
    Joey (proposals, or honest "couldn't" sentences) — [] when the message isn't
    a report. Never saves anything.
    """
    kinds = detect_report_kinds(message)
    if not kinds:
        return []
    today = today or datetime.now().strftime("%Y-%m-%d")

    open_issues, issues_problem = [], None
    if any(k in kinds for k in (KIND_ISSUE_UPDATE, KIND_MAINTENANCE, KIND_ISSUE)):
        try:
            open_issues = drive_actions.list_open_issues()
        except RuntimeError as e:
            issues_problem = str(e)

    notes, handled_ids = [], set()
    for kind in kinds[:MAX_KINDS]:
        if kind == KIND_ISSUE_UPDATE:
            if issues_problem:
                notes.append(f"I couldn't read your open issues to check that: {issues_problem}. Nothing was proposed.")
                continue
            if not open_issues:
                continue                      # nothing open, so nothing could be "fixed"
        try:
            notes.extend(_handle(kind, message, today, open_issues, handled_ids))
        except (ExtractionError, ValueError, RuntimeError, OSError) as e:
            notes.append(f"I couldn't turn that into {_LABELS[kind]}: {e}. Nothing was proposed.")
    if len(kinds) > MAX_KINDS:
        notes.append(f"I only handled the first {MAX_KINDS} things in that message — send the rest again on their own.")
    return notes