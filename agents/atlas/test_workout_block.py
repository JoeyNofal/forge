"""
WORKOUT BLOCK - L1, L2, L4, L5 tests for agents/atlas/workout_block.py.
No model, no files, no keys. (L3, the real-model pass, does not apply: this
module never talks to a model.)

Run from the repo root:  python -m agents.atlas.test_workout_block
"""
import ast
import json
import os
import random
import re
import threading
import time
from datetime import datetime

from agents.atlas import workout_block as W

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
_results = []


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


def raises(fn, exc=Exception):
    try:
        fn()
    except exc:
        return True
    return False


def read(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


SAMPLE = """FORGE WORKOUT LOG v1
Title: Chest workout
Date: 2026-10-01
Unit: lbs

## Warmup
Exercise: Windmill arms
Prescribed: 1x20 per arm | weight: bodyweight | rest: 30 sec | target RPE: 5
Set 1: 20 reps | bodyweight
RPE: 5
Notes: my shoulders click

## Upper chest
Exercise: Incline DB press
Prescribed: 2x10 | weight: 10 lbs | rest: 2 min | target RPE: 7
Set 1: 10 reps | 10 lbs
Set 2: 8 reps | 10 lbs
RPE: 8
Notes:
"""


def parse(body, header=()):
    text = "\n".join(["FORGE WORKOUT LOG v1", *header, "## Main", "Exercise: Squat", *body])
    r = W.parse_workout_block(text)
    return r, r["sections"][0]["exercises"][0]


def presc(text):
    return parse(["Prescribed: " + text])[1]["prescribed"]


# ---------------- L1 static ----------------
SRC = read("agents", "atlas", "workout_block.py")


@check("L1 static: imports only re and shared.normalizers (no model, file, network or logging code)")
def _():
    tree = ast.parse(SRC)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported <= {"re", "shared.normalizers"}, imported
    assert "open(" not in SRC and "requests" not in SRC


@check("L1 static: no secrets and no hardcoded old-project path")
def _():
    assert not re.search(r"(api[_-]?key|sk-[A-Za-z0-9]|AIza|NEXUS SYSTEM)", SRC, re.I)


# ---------------- L2 smoke: your own scenario ----------------
@check("L2 your scenario parses exactly (warmup + main, prescribed, sets, RPE, notes)")
def _():
    r = W.parse_workout_block(SAMPLE)
    assert r["title"] == "Chest workout" and r["date"] == "2026-10-01" and r["unit"] == "lbs"
    assert r["warnings"] == [] and r["units_assumed"] == []
    assert [s["kind"] for s in r["sections"]] == ["warmup", "main"]
    assert [s["name"] for s in r["sections"]] == ["Warmup", "Upper chest"]
    wm = r["sections"][0]["exercises"][0]
    assert wm["name"] == "Windmill arms" and wm["rpe"] == 5 and wm["notes"] == "my shoulders click"
    p = wm["prescribed"]
    assert (p["sets"], p["reps"], p["bodyweight"], p["rest_seconds"], p["target_rpe"]) == (1, 20, True, 30, 5)
    assert wm["sets"] == [{"set": 1, "reps": 20, "seconds": None, "weight": None,
                           "weight_unit": None, "bodyweight": True}]
    inc = r["sections"][1]["exercises"][0]
    p = inc["prescribed"]
    assert (p["sets"], p["reps"], p["weight"], p["weight_unit"], p["rest_seconds"], p["target_rpe"]) == (2, 10, 10, "lbs", 120, 7)
    assert [(s["reps"], s["weight"], s["weight_unit"]) for s in inc["sets"]] == [(10, 10, "lbs"), (8, 10, "lbs")]
    assert inc["rpe"] == 8 and inc["notes"] == "" and inc["sets_skipped"] == 0


@check("L2 section kinds: warmup / cooldown variants, whole-word only")
def _():
    k = W._section_kind
    assert k("Warmup") == "warmup" and k("Warm-up") == "warmup" and k("warm up") == "warmup"
    assert k("Cooldown") == "cooldown" and k("Cool down stretches") == "cooldown" and k("COOL-DOWN") == "cooldown"
    assert k("Upper chest") == "main" and k("Swarmup") == "main" and k("Warmups") == "main"


@check("L2 timed sets: seconds and minutes become seconds, reps stay None")
def _():
    r, ex = parse(["Set 1: 30 sec | bodyweight", "Set 2: 1 min |", "Set 3: 45 s"])
    assert [(s["seconds"], s["reps"]) for s in ex["sets"]] == [(30, None), (60, None), (45, None)]


@check("L2 empty / zero rows are skipped and counted, never saved as zero")
def _():
    r, ex = parse(["Set 1: 10 reps | 50 lbs", "Set 2: |", "Set 3:", "Set 4: 0 reps | 50 lbs"])
    assert len(ex["sets"]) == 1 and ex["sets_skipped"] == 3


@check("L2 units: header unit used, explicit unit wins, no unit at all -> lbs and flagged")
def _():
    r, ex = parse(["Set 1: 5 reps | 100"], header=["Unit: kg"])
    assert ex["sets"][0]["weight_unit"] == "kg" and r["units_assumed"] == []
    r, ex = parse(["Set 1: 5 reps | 60 kg"], header=["Unit: lbs"])
    assert ex["sets"][0]["weight_unit"] == "kg"
    r, ex = parse(["Set 1: 5 reps | 100"])
    assert ex["sets"][0]["weight_unit"] == "lbs" and r["units_assumed"] == ["Squat"]


@check("L2 bodyweight / blank weight / zero weight are never flagged and never invented")
def _():
    r, ex = parse(["Set 1: 12 reps | bodyweight", "Set 2: 12 reps |", "Set 3: 12 reps | 0 lbs"])
    assert r["units_assumed"] == []
    assert ex["sets"][0]["bodyweight"] is True and ex["sets"][0]["weight"] is None
    assert ex["sets"][1]["bodyweight"] is False and ex["sets"][1]["weight"] is None
    assert ex["sets"][2]["weight"] is None and ex["sets"][2]["weight_unit"] is None


@check("L2 unreadable sets become warnings; readable parts survive")
def _():
    r, ex = parse(["Set 1: lots | 50 lbs", "Set 2: 10 reps | heavy", "Set 3: | 50 lbs", "Set 5: 99999 reps | 10 lbs"])
    assert len(ex["sets"]) == 1 and ex["sets"][0]["reps"] == 10 and ex["sets"][0]["weight"] is None
    assert ex["sets_skipped"] == 3 and len(r["warnings"]) == 4


@check("L2 RPE: 8/10 and 7.5 ok; 11, 0, words and blank all become None")
def _():
    def rpe(v):
        r, ex = parse(["Set 1: 5 reps | 100 lbs", "RPE: " + v])
        return ex["rpe"], len(r["warnings"])
    assert rpe("8/10") == (8, 0) and rpe("7.5") == (7.5, 0) and rpe("") == (None, 0)
    assert rpe("11") == (None, 1) and rpe("0") == (None, 1) and rpe("easy") == (None, 1)


@check("L2 notes: run onto more lines, stop at a blank line or the next key")
def _():
    r, ex = parse(["Set 1: 5 reps | 100 lbs", "Notes: left shoulder clicked", "on the last rep", "", "stray line"])
    assert ex["notes"] == "left shoulder clicked on the last rep" and len(r["warnings"]) == 1
    r, ex = parse(["Set 1: 5 reps | 100 lbs", "Notes:", "RPE: 6"])
    assert ex["notes"] == "" and ex["rpe"] == 6
    r, ex = parse(["Notes: felt good", "set up was slow"])
    assert ex["notes"] == "felt good set up was slow"


@check("L2 phone paste: Windows line ends, odd spaces, smart punctuation, the x sign")
def _():
    text = ("FORGE WORKOUT LOG v1\r\nDate: 2026-10-01\r\n## Main\r\nExercise:\u00a0Curl\r\n"
            "Prescribed: 3 \u00d7 8 | weight: 25 kg\r\nSet 1: 8 reps | 25 kg\r\nNotes: didn\u2019t lock out")
    ex = W.parse_workout_block(text)["sections"][0]["exercises"][0]
    assert ex["name"] == "Curl" and ex["prescribed"]["sets"] == 3 and ex["prescribed"]["reps"] == 8
    assert ex["notes"] == "didn't lock out"


@check("L2 header rules: wrong or missing header, wrong version, no exercises, non-string")
def _():
    assert raises(lambda: W.parse_workout_block("I did chest today"), W.BlockError)
    assert raises(lambda: W.parse_workout_block(""), W.BlockError)
    assert raises(lambda: W.parse_workout_block("FORGE WORKOUT LOG"), W.BlockError)
    assert raises(lambda: W.parse_workout_block("FORGE WORKOUT LOG v2\n## A\nExercise: X"), W.BlockError)
    assert raises(lambda: W.parse_workout_block("FORGE WORKOUT LOG v1\nTitle: empty"), W.BlockError)
    assert raises(lambda: W.parse_workout_block("FORGE WORKOUT LOG v1\n## Warmup"), W.BlockError)
    for bad in (None, 5, b"bytes", ["x"], {"a": 1}):
        assert raises(lambda b=bad: W.parse_workout_block(b), TypeError)


@check("L2 header tolerance: leading blank lines and lower case are fine")
def _():
    r = W.parse_workout_block("\n\n  forge workout log v1\n## A\nExercise: X\nSet 1: 5 reps | 5 lbs")
    assert r["sections"][0]["exercises"][0]["name"] == "X"


@check("L2 date: valid kept; future, words and blank become today (warned except blank)")
def _():
    today = datetime.now().strftime("%Y-%m-%d")
    def d(v):
        r = W.parse_workout_block(f"FORGE WORKOUT LOG v1\nDate: {v}\n## A\nExercise: X")
        return r["date"], len(r["warnings"])
    assert d("2026-10-01") == ("2026-10-01", 0)
    assert d("2999-01-01") == (today, 1) and d("yesterday") == (today, 1) and d("") == (today, 0)


@check("L2 prescribed variants and junk")
def _():
    p = presc("3 x 8 | weight: 25 kg | rest: 90 | target RPE: 8.5")
    assert (p["sets"], p["reps"], p["weight"], p["weight_unit"], p["rest_seconds"], p["target_rpe"]) == (3, 8, 25, "kg", 90, 8.5)
    assert presc("4x10 per side")["sets"] == 4 and presc("4x10 per side")["reps"] == 10
    p = presc("3x30 sec | rest: 1.5 min")
    assert (p["sets"], p["seconds"], p["reps"], p["rest_seconds"]) == (3, 30, None, 90)
    assert presc("2x10 | weight: bodyweight")["bodyweight"] is True
    assert presc("2x10 | weight: 10lb")["weight_unit"] == "lbs"
    p = presc("whatever | nonsense: 4")
    assert p["sets"] is None and p["text"] == "whatever | nonsense: 4"
    assert presc("0x10")["sets"] is None and presc("99x10")["sets"] is None


@check("L2 / Lesson #6: keywords need the colon and the whole word at the start of the line")
def _():
    r, ex = parse(["Set 1: 5 reps | 100 lbs", "Exercises: 3", "Notes about my shoulder", "Settings: x", "Titles: y"])
    assert len(r["sections"][0]["exercises"]) == 1 and ex["notes"] == "" and len(r["warnings"]) == 4


@check("L2 an exercise with no filled sets is kept with zero sets (so 1b can call it skipped)")
def _():
    r, ex = parse(["Set 1: |", "RPE:"])
    assert ex["sets"] == [] and ex["sets_skipped"] == 1


@check("L2 looks_like_workout_block: yes for the header, no for ordinary chat and non-strings")
def _():
    assert W.looks_like_workout_block(SAMPLE) and W.looks_like_workout_block("\n  Forge Workout Log v1\nx")
    assert not W.looks_like_workout_block("I did chest today, bench 3x8 at 135 lbs")
    assert not W.looks_like_workout_block("") and not W.looks_like_workout_block(None)
    assert not W.looks_like_workout_block("hello\nFORGE WORKOUT LOG v1")


@check("L2 result is plain data: JSON-serializable, parsing twice gives the same answer")
def _():
    a = W.parse_workout_block(SAMPLE)
    assert json.loads(json.dumps(a)) == a and W.parse_workout_block(SAMPLE) == a


@check("L2 limits: names and notes cut, extra sets ignored, too many sections/exercises/characters refused")
def _():
    r, ex = parse(["Set %d: 5 reps | 5 lbs" % i for i in range(1, 40)])
    assert len(ex["sets"]) == W.MAX_SETS and any("extra sets" in w for w in r["warnings"])
    text = "FORGE WORKOUT LOG v1\n## A\nExercise: " + "n" * 500 + "\nNotes: " + "z" * 2000
    ex = W.parse_workout_block(text)["sections"][0]["exercises"][0]
    assert len(ex["name"]) == W.MAX_NAME and len(ex["notes"]) == W.MAX_NOTES
    many_sections = "FORGE WORKOUT LOG v1\n" + "".join(f"## S{i}\nExercise: X\n" for i in range(W.MAX_SECTIONS + 1))
    assert raises(lambda: W.parse_workout_block(many_sections), W.BlockError)
    many_ex = "FORGE WORKOUT LOG v1\n## A\n" + "Exercise: X\n" * (W.MAX_EXERCISES + 1)
    assert raises(lambda: W.parse_workout_block(many_ex), W.BlockError)
    assert raises(lambda: W.parse_workout_block("FORGE WORKOUT LOG v1\n" + "x" * W.MAX_BLOCK_CHARS), W.BlockError)


# ---------------- L4 sustained / concurrency ----------------
@check("L4 200 sequential parses all identical")
def _():
    first = W.parse_workout_block(SAMPLE)
    for _i in range(200):
        assert W.parse_workout_block(SAMPLE) == first


@check("L4 20 threads parse different blocks at once, zero cross-talk")
def _():
    errors, out = [], {}

    def work(n):
        try:
            t = f"FORGE WORKOUT LOG v1\nTitle: T{n}\n## A\nExercise: E{n}\nSet 1: {n + 1} reps | {n + 5} lbs\nNotes: n{n}"
            for _i in range(50):
                r = W.parse_workout_block(t)
                ex = r["sections"][0]["exercises"][0]
                assert r["title"] == f"T{n}" and ex["name"] == f"E{n}"
                assert ex["sets"][0]["reps"] == n + 1 and ex["notes"] == f"n{n}"
            out[n] = True
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=work, args=(n,)) for n in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors[:2]
    assert len(out) == 20


@check("L4 a big valid block (90 exercises, 270 sets) parses fast")
def _():
    parts = ["FORGE WORKOUT LOG v1", "Date: 2026-10-01", "Unit: lbs"]
    for s in range(3):
        parts.append(f"## Section {s}")
        for e in range(30):
            parts += [f"Exercise: Exercise {s}-{e}", "Prescribed: 3x10 | weight: 20 lbs | rest: 60 sec | target RPE: 7"]
            parts += [f"Set {i}: 10 reps | 20 lbs" for i in (1, 2, 3)]
            parts += ["RPE: 7", "Notes: ok"]
    text = "\n".join(parts)
    assert len(text) < W.MAX_BLOCK_CHARS, len(text)
    t0 = time.time()
    r = W.parse_workout_block(text)
    assert time.time() - t0 < 1.0
    assert sum(len(s["exercises"]) for s in r["sections"]) == 90 and r["warnings"] == []


# ---------------- L5 extreme / breaking ----------------
@check("L5 junk text only ever gives BlockError or TypeError, never another crash")
def _():
    for junk in ["", " ", "\n\n", "\x00\x01\x02", "x" * 20000, "FORGE WORKOUT LOG v1",
                 "FORGE WORKOUT LOG v1\n" + "Set 1: 10\n" * 3000, "\U0001F4AA" * 500, "FORGE WORKOUT LOG v99999999999999"]:
        assert raises(lambda j=junk: W.parse_workout_block(j), W.BlockError), repr(junk[:20])


@check("L5 thousands of bad lines still give a short, capped warning list")
def _():
    text = "FORGE WORKOUT LOG v1\n## A\nExercise: A\nSet 1: 5 reps | 5 lbs\n" + "garbage line\n" * 1500
    r = W.parse_workout_block(text)
    assert len(r["warnings"]) <= W.MAX_WARNINGS + 1 and len(r["sections"][0]["exercises"]) == 1


@check("L5 300 randomly damaged copies of your scenario: a clean answer or BlockError, nothing else")
def _():
    rng = random.Random(7)
    for _i in range(300):
        chars = list(SAMPLE)
        for _j in range(rng.randint(1, 15)):
            i = rng.randrange(len(chars))
            op = rng.choice(["del", "dup", "junk"])
            if op == "del" and len(chars) > 1:
                chars.pop(i)
            elif op == "dup":
                chars.insert(i, chars[i])
            else:
                chars.insert(i, rng.choice("|:#x9 \n/-.")) 
        try:
            r = W.parse_workout_block("".join(chars))
        except W.BlockError:
            continue
        json.dumps(r)
        assert r["sections"] and isinstance(r["warnings"], list)


@check("L5 5,000-digit numbers and 20,000-character lines cannot hang the reader")
def _():
    t0 = time.time()
    for line in ["Set 1: " + "9" * 5000 + " reps | 5 lbs", "Prescribed: " + "9" * 5000 + "x" + "9" * 5000,
                 "Set 1: 5 reps | " + "1" * 5000 + "x", "RPE: " + "7" * 5000]:
        r, ex = parse([line])
        assert isinstance(r["warnings"], list)
    assert time.time() - t0 < 2.0


@check("L5 unicode and emoji survive in names and notes")
def _():
    text = "FORGE WORKOUT LOG v1\n## A\nExercise: Pull-ups \U0001F4AA\nSet 1: 5 reps\nNotes: \u00e9\u00e0\u4e2d\u6587 felt great \U0001F525"
    ex = W.parse_workout_block(text)["sections"][0]["exercises"][0]
    assert "\U0001F4AA" in ex["name"] and "\U0001F525" in ex["notes"]


@check("L5 nothing is invented: a set with no weight text has weight None, never 0 or a default")
def _():
    r, ex = parse(["Set 1: 5 reps"])
    s = ex["sets"][0]
    assert s["weight"] is None and s["weight_unit"] is None and s["bodyweight"] is False and ex["rpe"] is None


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)