"""
ISSUE MATCH — plain-Python text matching between what Joey SAYS and the problems
already saved (increment (b), Part 3b-3).

Added after the first real-model run: the local model ignored prompt rules
("don't repeat a problem that's already listed", "ask when it's ambiguous",
"only claim a fix when it's clearly the same thing"). So Python enforces them.

Pure functions only: no files, no model, no network. Matching is by shared
CONTENT WORDS (not substrings): case-insensitive, plural 's' ignored, short and
filler words dropped. It is deliberately conservative — when unsure, callers ask
Joey or skip the proposal; they never guess.
"""
import re
from typing import Optional

_STOPWORDS = frozenset("""
a an and are as at be been but by car did do does for from get got had has have he her him
his i if in is it its just me my no not now of off on or our she so that the their them
then there they this to up us was we were what when which who will with you your all fixed
fix fine good ok okay again still really very vehicle
""".split())


def _normalize(word: str) -> str:
    """A lowercase word with a plural 's' removed (brakes -> brake, not glass -> glas)."""
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def content_words(text) -> set:
    """The meaningful words of `text`. A non-string is just 'no words'."""
    if not isinstance(text, str):
        return set()
    out = set()
    for raw in re.findall(r"[A-Za-z0-9]+", text):
        word = raw.lower()
        if len(word) < 3 or word in _STOPWORDS:
            continue
        out.add(_normalize(word))
    return out


def overlap(a, b) -> int:
    """How many content words two texts share."""
    return len(content_words(a) & content_words(b))


def is_duplicate(description, existing) -> bool:
    """
    The same problem described again: identical content words, or one description's
    words (at least two of them) entirely inside the other's.
    ("tire light on" ~ "tire pressure light is on"; but "noise" ~ "weird noise" is NOT.)
    """
    a, b = content_words(description), content_words(existing)
    if not a or not b:
        return False
    if a == b:
        return True
    small, large = (a, b) if len(a) <= len(b) else (b, a)
    return len(small) >= 2 and small <= large


def find_duplicate(description, open_issues) -> Optional[str]:
    """The saved description of an open issue that `description` repeats, or None."""
    if not isinstance(open_issues, list):
        return None
    for item in open_issues:
        existing = item[1] if isinstance(item, (tuple, list)) and len(item) >= 2 else None
        if existing is not None and is_duplicate(description, existing):
            return str(existing)
    return None


def issue_scores(message, open_issues) -> list:
    """For each open issue (in order), how many content words it shares with `message`."""
    if not isinstance(open_issues, list):
        return []
    words = content_words(message)
    scores = []
    for item in open_issues:
        desc = item[1] if isinstance(item, (tuple, list)) and len(item) >= 2 else ""
        scores.append(len(words & content_words(desc)))
    return scores