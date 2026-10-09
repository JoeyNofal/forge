"""
SHARED NORMALIZER HELPERS — the small "untrusted in, clean out" functions that
atlas_logging.py and drive_logging.py each used to carry their own copy of.

WHY ONE COPY (Lesson #9): the two copies had already drifted apart. DRIVE's number
reader understood "1,500" and "$30"; ATLAS's silently read both as "not stated". DRIVE's
text reader turned a dict into ""; ATLAS saved the dict's Python repr as a note. One
tested copy cannot drift. STOCK, FLAME and the rest reuse this instead of copy number three.

RULES (Lesson #5: never trust the shape):
- Nothing is invented: "not stated" is 0 / "" / [] and the caller decides what that means.
- A number that IS stated but out of range raises ValueError (it is never clamped or guessed).
- Bad shapes degrade to "not stated"; they never crash.
"""
from datetime import datetime

MAX_TEXT = 1000
MAX_LIST = 30


def num(v, low, high, what):
    """Number in [low, high]; None/''/non-numeric -> 0 (= not stated); out of range -> ValueError.
    Strings may carry thousands commas or a dollar sign ("1,500", "$30")."""
    if v is None or v == "" or isinstance(v, bool):
        return 0
    if isinstance(v, str):
        v = v.replace(",", "").replace("$", "").strip()
    try:
        n = float(v)
    except (TypeError, ValueError):
        return 0
    if n != n or n < low or n > high:   # n != n catches NaN
        raise ValueError(f"{what} out of range: {v!r}")
    return int(n) if n == int(n) else n


def text(v) -> str:
    """Plain text, trimmed and capped. None and dicts are 'not stated' (""); a list is joined."""
    if v is None or isinstance(v, dict):
        return ""
    if isinstance(v, list):
        v = ", ".join(str(x) for x in v if x not in (None, ""))
    return str(v).strip()[:MAX_TEXT]


def str_list(v) -> list:
    """List of short strings from a list OR a comma-separated string."""
    if v is None or v == "":
        return []
    if isinstance(v, str):
        v = v.split(",")
    if not isinstance(v, list):
        return []
    out = []
    for x in v:
        if isinstance(x, dict):
            x = x.get("description") or x.get("name") or ""
        s = str(x).strip()
        if s:
            out.append(s[:200])
    return out[:MAX_LIST]


def date_or_today(v) -> str:
    """A real, non-future YYYY-MM-DD, else today."""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        d = datetime.strptime(str(v).strip()[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return today
    return d if d <= today else today


def require_dict(raw, kind):
    if not isinstance(raw, dict):
        raise ValueError(f"{kind}: expected an object, got {type(raw).__name__}")