"""
ATLAS rules, Phase 1 item 1.2c - L1, L2, L4, L5 tests for agents/atlas/exercise_vocab.py (the reference list of
words that appear inside real exercise names). Pure Python: no model, no network, no files.

Run from the repo root:  python -m agents.atlas.test_exercise_vocab
"""
import os
import threading
import time
from typing import Any

from agents.atlas import exercise_vocab as V

_HERE = os.path.dirname(os.path.abspath(__file__))
_results: list = []


def check(name):
    def deco(fn):
        try:
            fn()
            _results.append((name, True, ""))
            print(f"PASS  {name}")
        except Exception as e:
            _results.append((name, False, repr(e)))
            print(f"FAIL  {name}  -> {e!r}")
        return fn
    return deco


with open(os.path.join(_HERE, "exercise_vocab.py"), encoding="utf-8") as f:
    SRC = f.read()

REAL_NAMES = [
    "Barbell back squat", "Bench press", "Incline dumbbell press", "Seated cable row", "Lat pulldown", "Overhead press",
    "Military press", "Romanian deadlift", "Hip thrust", "Leg press", "Leg curl", "Hamstring curl", "Calf raise", "Face pull",
    "Triceps pushdown", "Skullcrusher", "Hammer curl", "Preacher curl", "Chin-ups", "Pull-ups", "Push-ups", "Dips", "Goblet squat",
    "Bulgarian split squat", "Walking lunges", "Kettlebell swing", "Box jump", "Jump squat", "Power clean", "Burpee",
    "Medicine ball slam", "Plank", "Side plank", "Dead bug", "Bird dog", "Glute bridge march", "Crunches", "Cable crossover",
    "Dumbbell fly", "Machine chest press", "Leg extension", "Seated calf raise", "Hanging leg raise", "Farmer's carry", "Sled push",
    "Battle ropes", "Landmine press", "Arnold press", "Pendlay row", "Good morning", "Zercher squat", "Turkish get-up",
    "Back extension", "Reverse fly", "Lateral raise", "Front raise", "Rear delt fly", "Shrugs", "Cable woodchop", "Pallof press",
    "Mountain climbers", "Jumping jacks", "Running", "Rowing machine", "Stationary bike", "Step-ups", "Nordic hamstring curl",
    "Wall sit", "Hollow hold", "Superman", "Close-grip bench press", "Pause squat", "Tempo deadlift", "Single-leg Romanian deadlift",
    "Trap bar deadlift", "Sumo deadlift", "Smith machine squat", "Resistance band pull apart", "Stability ball curl",
    "Bosu ball squat", "TRX row", "Ring dips", "Muscle-up", "Handstand push-up", "Plyometric push-up", "Snatch", "Clean and jerk",
    "Thrusters", "Wall ball", "Pec deck", "Hack squat", "Cyclist squat", "Banded pull apart", "Chest-supported row", "Elevated push-up",
]
CATEGORY_WORDS = ["explosive", "exercise", "workout", "move", "heavy", "light", "hard", "easy", "careful", "fast", "intense"]


@check("L1 pure reference data: no model, network, file or secret code in the module")
def _():
    for banned in ("model_client", "requests", "anthropic", "ollama", "genai", "urllib", "socket", "open(", "json", "sk-", "AIza", "D:\\", "C:\\"):
        assert banned not in SRC, banned


@check("L1 category words are deliberately NOT in the list (a rule built on them blocks nothing)")
def _():
    for w in CATEGORY_WORDS:
        assert w not in V.KNOWN, w
    assert len(V.KNOWN) > 350 and all(w == w.lower() for w in V.KNOWN)


@check("L2 about 90 real exercise names contain no unknown word")
def _():
    unknown = [(n, V.unknown_words([n])) for n in REAL_NAMES if V.unknown_words([n])]
    assert unknown == [], unknown


@check("L2 category words and nonsense are unknown, in the order they appear, without repeats")
def _():
    assert V.unknown_words(CATEGORY_WORDS) == CATEGORY_WORDS
    assert V.unknown_words(["explosive jump", "explosive curl", "explosive push-up"]) == ["explosive"]
    assert V.unknown_words(["zzz squat", "qqq row", "zzz curl"]) == ["zzz", "qqq"]
    assert V.unknown_words(["Heavy squat and careful row"]) == ["heavy", "careful"]


@check("L2 plural, singular and -ing forms of known words are known")
def _():
    for t in ("curls", "rows", "raises", "squats", "lunges", "jumping lunges", "running", "squatting", "swinging", "climbers", "dips", "burpees"):
        assert V.unknown_words([t]) == [], t
    assert V.unknown_words(["cats and dogs"]) == []                      # cat (cat-cow), dog (bird dog) and 'and' are in the list


@check("L2 digits and single letters are ignored; case and punctuation do not matter")
def _():
    assert V.unknown_words(["Y raise", "T raise", "90/90 stretch", "Farmer's carry", "SQUAT!!", "  Bench-Press  "]) == []
    assert V.unknown_words(["21s curl"]) == ["21s"]


@check("L2 words from Joey's OWN library names count as known when passed in")
def _():
    extra = V.tokens_of(["Zebra squat", "Quagga squat"])
    assert extra == frozenset({"zebra", "quagga", "squat"})
    assert V.unknown_words(["zebra squat", "quagga row"]) == ["zebra", "quagga"]
    assert V.unknown_words(["zebra squat", "quagga row"], extra) == []


@check("L5 junk input never crashes: non-lists, non-strings, nested lists, None, numbers, empty")
def _():
    for junk in (None, "squat", 5, {}, (), [], [None], [5], [["squat"]], [{}], [b"x"], ["", "   ", "\x00"], [1.5, True]):
        assert V.unknown_words(junk) == [], junk                           # nothing usable in it = nothing unknown, never a crash
    assert V.tokens_of(None) == frozenset() and V.tokens_of("x") == frozenset() and V.tokens_of([None, 5, ["a"]]) == frozenset()


@check("L5 huge input stays fast: 100,000 words, a 1 MB name, and emoji/unicode")
def _():
    t = time.time()
    many = ["barbell squat zzz"] * 50000
    assert V.unknown_words(many) == ["zzz"] and time.time() - t < 10
    t = time.time()
    assert V.unknown_words(["squat " * 200000]) == [] and time.time() - t < 10
    assert V.unknown_words(["\U0001F4AA squat \u00e9\u00e8 \u0441\u043f\u0440\u044b\u0436\u043e\u043a"]) == []        # non-ASCII is ignored, not unknown


@check("L4 20 threads at once: the same answers, no cross-talk")
def _():
    out: list = []
    errs: list = []

    def work(i):
        try:
            out.append((i, V.unknown_words(["squat", "explosive", "curl" if i % 2 else "exercise"])))
        except Exception as e:
            errs.append(repr(e))
    ts = [threading.Thread(target=work, args=(i,)) for i in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs and len(out) == 20
    assert all(r == (["explosive"] if i % 2 else ["explosive", "exercise"]) for i, r in out)


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)