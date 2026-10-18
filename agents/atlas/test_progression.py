"""
ATLAS progression, increment 3c - L1, L2, L4, L5 tests for agents/atlas/progression.py:
what weight to try next, worked out from your logged workouts with the agreed rules.
Pure Python: no model, no files, no keys.

Run from the repo root:  python -m agents.atlas.test_progression
"""
import ast
import json
import os
import random
import re
import threading
import time
from typing import Any

from agents.atlas import progression as G

_HERE = os.path.dirname(os.path.abspath(__file__))
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


def raises(fn, exc: Any = Exception):
    try:
        fn()
    except exc:
        return True
    return False


def ex(name, weight, sets: Any = 4, reps: Any = 8, rpe: Any = 7, target: Any = 7, done_sets: Any = None, done_reps: Any = None, planned_sets: Any = None):
    """One logged exercise: `sets` sets prescribed (4x8 by default), `done_sets` actually done at `done_reps` reps."""
    n_done = sets if done_sets is None else done_sets
    r_done = reps if done_reps is None else done_reps
    return {"name": name, "weight_lbs": weight, "rpe": rpe,
            "set_details": [{"set": i + 1, "reps": r_done, "weight_lbs": weight} for i in range(n_done)],
            "prescribed": {"sets": planned_sets or sets, "reps": reps, "target_rpe": target, "weight_lbs": weight}}


def day(date, *exercises, logged=None):
    return {"date": date, "logged_at": logged or date + "T10:00:00", "exercises": list(exercises)}


def suggest(name, workouts, **kw):
    return G.suggest_weight(name, workouts, **kw)


with open(os.path.join(_HERE, "progression.py"), encoding="utf-8") as f:
    SRC = f.read()


# ---------------- L1 static ----------------
@check("L1 static: pure Python (no model, file, network or approval code), no secrets")
def _():
    tree = ast.parse(SRC)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported <= {"math", "re", "typing", "agents.atlas"}, imported
    for banned in ("open(", "update_json", "stream_by_tier", "atlas_actions", "requests", "random"):
        assert banned not in SRC, banned
    assert not re.search(r"(api[_-]?key|sk-[A-Za-z0-9]|AIza|NEXUS SYSTEM)", SRC, re.I)


# ---------------- L2 smoke: rounding ----------------
@check("L2 rounding: nearest step, halves round up")
def _():
    r = G.round_to_unit
    assert r(127.5, 2.5) == 127.5 and r(126, 2.5) == 125 and r(127, 2.5) == 127.5 and r(2.5, 5) == 5 and r(7.5, 5) == 10 and r(142, 5) == 140


@check("L2 next weight up: +5 or +2.5 then rounded to the equipment, and ALWAYS above the last weight")
def _():
    n = G.next_up
    assert n(135, 5, 2.5) == 140 and n(100, 2.5, 5) == 105 and n(47, 2.5, 5) == 50 and n(22, 5, 5) == 25 and n(25, 2.5, 5) == 30
    for last in (2.5, 5, 7.5, 10, 22, 33.3, 47, 100, 135, 225, 315.5):
        for step in (2.5, 5):
            for unit in (2.5, 5):
                assert n(last, step, unit) > last, (last, step, unit)


@check("L2 deload: about 10% lighter, rounded DOWN to the equipment, always lighter; too light to drop gives nothing")
def _():
    d = G.deload_weight
    assert d(135, 2.5) == 120 and d(100, 5) == 90 and d(10, 2.5) == 7.5 and d(20, 5) == 15 and d(5, 2.5) == 2.5
    assert d(2.5, 2.5) is None and d(0, 2.5) is None
    for last in (7.5, 10, 12.5, 22, 45, 135, 225, 405.5):
        for unit in (2.5, 5):
            got = d(last, unit)
            assert got is None or got < last, (last, unit, got)


# ---------------- L2 smoke: what kind of lift ----------------
@check("L2 dumbbell lifts are recognised from the name (DB spelled any way) or the library's equipment")
def _():
    assert G.is_dumbbell("Incline DB press") and G.is_dumbbell("dumbbell curl") and G.is_dumbbell("Dumbbells row")
    assert G.is_dumbbell("Row", equipment=["Dumbbells", "bench"]) and not G.is_dumbbell("Bench press") and not G.is_dumbbell("Barbell row")
    for odd in (None, 5, ["x"], ""):
        assert G.is_dumbbell(odd) is False
    assert G.weight_unit("Incline DB press", 50) == 5 and G.weight_unit("Hammer DB curl", 15) == 2.5 and G.weight_unit("Bench press", 135) == 2.5


@check("L2 small or big lift: words in the name first, then the library's muscles; presses stay big")
def _():
    small = ("Bicep curl", "Lateral raise", "Tricep pushdown", "Triceps extension", "Calf raise", "Face pull", "Hammer curl", "Cable fly",
             "Shrugs", "Plank", "Wrist curl", "Cable crunch", "Leg curl")
    big = ("Bench press", "Overhead press", "Shoulder press", "Squat", "Deadlift", "Barbell row", "Arnold press", "Leg press", "Pull-ups", "Lunge")
    for n in small:
        assert G.is_small_lift(n) is True, n
    for n in big:
        assert G.is_small_lift(n) is False, n
    assert G.is_small_lift("Cable thing", ["biceps"]) and G.is_small_lift("Cable thing", ["Triceps", "forearms"])
    assert not G.is_small_lift("Row", ["back", "biceps"]) and not G.is_small_lift("Weird", []) and not G.is_small_lift("Weird", None)
    assert not G.is_small_lift("Arnold press", ["shoulders"])
    for odd in (None, 5, ["x"]):
        assert G.is_small_lift(odd) is False


# ---------------- L2 smoke: judging one session ----------------
@check("L2 one session: success, neutral, struggle (reps missed at target RPE, RPE 2+ over), skipped sets neutral, unknown without a prescription")
def _():
    e = G.evaluate_session
    assert e(ex("Squat", 100, rpe=7, target=7))["status"] == "success"
    assert e(ex("Squat", 100, rpe=6, target=7))["status"] == "success"
    assert e(ex("Squat", 100, rpe=8, target=7))["status"] == "neutral"
    assert e(ex("Squat", 100, rpe=9, target=7))["status"] == "struggle"
    assert e(ex("Squat", 100, rpe=7, target=7, done_reps=6))["status"] == "struggle"
    assert e(ex("Squat", 100, rpe=7, target=7, done_sets=3))["status"] == "neutral"             # a skipped set is never a struggle, and never a success
    assert e(ex("Squat", 100, rpe=None, target=7))["status"] == "success"
    assert e(ex("Squat", 100, rpe=7, target=7, done_reps=10))["status"] == "success"           # extra reps are fine
    bare = ex("Squat", 100)
    bare["prescribed"] = None
    assert e(bare)["status"] == "unknown"
    bw = ex("Pull-ups", None)
    assert e(bw)["top_weight"] is None
    timed = {"name": "Plank", "weight_lbs": None, "rpe": 6, "set_details": [{"seconds": 30}, {"seconds": 35}],
             "prescribed": {"sets": 2, "seconds": 30, "target_rpe": 6}}
    assert e(timed)["status"] == "success"
    timed["set_details"][1]["seconds"] = 20
    assert e(timed)["status"] == "struggle"


@check("L2 finding sessions: DB/dumbbell and case ignored, other names via aliases, newest first, only the last 2, warmups and junk ignored")
def _():
    ws = [day("2026-10-01", ex("Incline DB press", 40)), day("2026-10-05", ex("incline dumbbell press", 45)),
          day("2026-10-03", ex("Bench press", 135)), day("2026-10-09", ex("INCLINE  DB  PRESS", 50)),
          {"date": "2026-10-10", "warmup": [ex("Incline DB press", 5)], "exercises": []}, "junk", None, 5, {"exercises": "no"}]
    found = G.find_sessions("Incline DB press", ws)
    assert [d for d, _e in found] == ["2026-10-09", "2026-10-05"]
    assert len(G.find_sessions("Incline DB press", ws, limit=5)) == 3
    assert [d for d, _e in G.find_sessions("Chest press", ws, aliases=["Incline dumbbell press"])] == ["2026-10-09", "2026-10-05"]
    same = [day("2026-10-05", ex("Squat", 100), logged="2026-10-05T09:00:00"), day("2026-10-05", ex("Squat", 105), logged="2026-10-05T18:00:00")]
    assert [e["weight_lbs"] for _d, e in G.find_sessions("Squat", same)] == [105, 100]
    assert G.find_sessions("", ws) == [] and G.find_sessions("Squat", None) == [] and G.find_sessions(None, ws) == []


# ---------------- L2 smoke: the decisions ----------------
@check("L2 no history: no weight is invented, only the RPE 6 advice")
def _():
    s = suggest("Bench press", [])
    assert s["action"] == "new" and s["weight_lbs"] is None and s["sessions_used"] == 0 and "feels like RPE 6" in s["reason"]
    assert suggest("Bench press", [day("2026-10-01", ex("Squat", 100))])["weight_lbs"] is None


@check("L2 success: +5 on a big lift, +2.5 on a small lift, dumbbells of 20 lbs or more in 5s; an easy session gets the same normal step")
def _():
    s = suggest("Bench press", [day("2026-10-01", ex("Bench press", 135))])
    assert (s["action"], s["weight_lbs"], s["last_weight_lbs"], s["step"], s["unit"]) == ("increase", 140, 135, 5.0, 2.5)
    assert "a success, so +5 lbs to 140 lbs" in s["reason"] and "4 of 4 sets at 135 lbs" in s["reason"]
    s = suggest("Triceps pushdown", [day("2026-10-01", ex("Triceps pushdown", 40))])
    assert s["action"] == "increase" and s["weight_lbs"] == 42.5 and s["small_lift"] is True
    s = suggest("Hammer curl", [day("2026-10-01", ex("Hammer curl", 25))], equipment=["dumbbells"], primary_muscles=["biceps"])
    assert s["weight_lbs"] == 30 and s["unit"] == 5
    s = suggest("Incline DB press", [day("2026-10-01", ex("Incline DB press", 50))])
    assert s["weight_lbs"] == 55
    easy = suggest("Bench press", [day("2026-10-01", ex("Bench press", 135, rpe=4, target=7))])
    assert easy["action"] == "increase" and easy["weight_lbs"] == 140


@check("L2 reps hit but harder than planned (RPE 1 over): repeat the same weight")
def _():
    s = suggest("Bench press", [day("2026-10-01", ex("Bench press", 135, rpe=8, target=7))])
    assert s["action"] == "hold" and s["weight_lbs"] == 135 and "repeat 135 lbs" in s["reason"]


@check("L2 one struggle repeats; two in a row drops about 10%; a success after that climbs again from the lighter weight")
def _():
    hard = ex("Bench press", 135, rpe=9, target=7)
    s = suggest("Bench press", [day("2026-10-01", ex("Bench press", 135)), day("2026-10-03", hard)])
    assert s["action"] == "hold" and s["weight_lbs"] == 135 and "a struggle, so repeat 135 lbs" in s["reason"]
    s = suggest("Bench press", [day("2026-10-01", ex("Bench press", 135, done_reps=5)), day("2026-10-03", hard)])
    assert s["action"] == "deload" and s["weight_lbs"] == 120 and "about 10% lighter" in s["reason"] and "2026-10-01" in s["reason"]
    s = suggest("Bench press", [day("2026-10-01", ex("Bench press", 135, done_reps=5)), day("2026-10-03", hard),
                                day("2026-10-05", ex("Bench press", 120))])
    assert s["action"] == "increase" and s["weight_lbs"] == 125
    s = suggest("Bench press", [day("2026-10-01", hard), day("2026-10-03", ex("Bench press", 135)), day("2026-10-05", hard)])
    assert s["action"] == "hold"                                                       # not two in a row


@check("L2 the weight you ACTUALLY lifted is the base, not the one prescribed (heavier or lighter)")
def _():
    heavier = ex("Bench press", 145)
    heavier["prescribed"]["weight_lbs"] = 135
    assert suggest("Bench press", [day("2026-10-01", heavier)])["weight_lbs"] == 150
    lighter = ex("Bench press", 125)
    lighter["prescribed"]["weight_lbs"] = 135
    assert suggest("Bench press", [day("2026-10-01", lighter)])["weight_lbs"] == 130


@check("L2 bodyweight, no prescription, missing RPE, and too-light-to-drop are each handled honestly")
def _():
    s = suggest("Pull-ups", [day("2026-10-01", ex("Pull-ups", None))])
    assert s["action"] == "bodyweight" and s["weight_lbs"] is None and "progress the reps" in s["reason"]
    bare = ex("Squat", 100)
    bare["prescribed"] = None
    s = suggest("Squat", [day("2026-10-01", bare)])
    assert s["action"] == "unknown" and s["weight_lbs"] == 100 and "no prescription was recorded" in s["reason"]
    s = suggest("Squat", [day("2026-10-01", ex("Squat", 100, rpe=None))])
    assert s["action"] == "increase" and any("no RPE was logged" in n for n in s["notes"])
    tiny_hard = ex("Face pull", 2.5, rpe=9, target=7, done_reps=5)
    s = suggest("Face pull", [day("2026-10-01", tiny_hard), day("2026-10-03", tiny_hard)])
    assert s["action"] == "hold" and s["weight_lbs"] == 2.5 and any("too light to drop" in n for n in s["notes"])


@check("L2 suggest_for: other names, muscles and equipment from the library entries are used")
def _():
    ws = [day("2026-10-01", ex("Hammer curl", 25))]
    entries = [{"name": "Hammer curl", "aliases": ["neutral grip curl"], "primary_muscles": ["biceps"], "equipment": ["dumbbells"]}]
    out = G.suggest_for(["Neutral grip curl", "Bench press", 5, None], ws, entries)
    assert set(out) == {"Neutral grip curl", "Bench press"}
    assert out["Neutral grip curl"]["weight_lbs"] == 30 and out["Neutral grip curl"]["unit"] == 5
    assert out["Bench press"]["weight_lbs"] is None
    assert G.suggest_for("x", ws) == {} and G.suggest_for(["Bench press"], None, "junk")["Bench press"]["action"] == "new"


@check("L2 the plain-English text: weight, reason, step and rounding, notes")
def _():
    text = G.describe_suggestion(suggest("Bench press", [day("2026-10-01", ex("Bench press", 135, rpe=None))]))
    for part in ("Bench press: Try 140 lbs.", "Why: on 2026-10-01 you did 4 of 4 sets at 135 lbs (every rep hit, no RPE to compare)",
                 "(big lift: steps of 5 lbs, rounded to 2.5 lbs.)", "Note: no RPE was logged, so I went by the reps alone."):
        assert part in text, part
    assert G.describe_suggestion(suggest("Squat", [])).startswith("Squat: no weight yet.")
    assert G.describe_suggestion(suggest("Pull-ups", [day("2026-10-01", ex("Pull-ups", None))])).startswith("Pull-ups: bodyweight, no weight to set.")
    assert "Drop to 120 lbs." in G.describe_suggestion(suggest("Bench press", [day("2026-10-01", ex("Bench press", 135, done_reps=5)),
                                                                              day("2026-10-03", ex("Bench press", 135, rpe=9))]))
    assert raises(lambda: G.describe_suggestion("x"), ValueError)       # pyright: ignore[reportArgumentType]


# ---------------- L4 sustained / concurrency ----------------
@check("L4 100 identical calls give identical answers, and a 5,000-workout history is worked through fast")
def _():
    ws = [day(f"2026-{1 + i // 400:02d}-{1 + (i // 14) % 28:02d}", ex("Bench press", 100 + (i % 20) * 5), logged=f"2026-01-01T{i % 24:02d}:{i % 60:02d}:00") for i in range(5000)]
    first = suggest("Bench press", ws)
    t0 = time.time()
    for _i in range(100):
        assert suggest("Bench press", ws) == first
    assert time.time() - t0 < 10.0


@check("L4 20 threads working out different exercises at once: no cross-talk")
def _():
    errors = []

    def work(n):
        try:
            name = f"Lift {chr(65 + n)}"
            ws = [day("2026-10-01", ex(name, 100 + n * 5))]
            for _i in range(50):
                s = suggest(name, ws)
                assert s["exercise"] == name and s["weight_lbs"] == 105 + n * 5
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=work, args=(n,)) for n in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors[:2]


# ---------------- L5 extreme / breaking ----------------
@check("L5 500 hostile histories: a clean answer that never contradicts its own action, never any other crash")
def _():
    rng = random.Random(14)
    junk = [None, 5, -5, 0, True, "", "x", "a" * 400, [], ["a"], {"a": 1}, float("nan"), float("inf"), 1e308, 135, 2.5, "135", [{"reps": 8}], {"sets": 4, "reps": 8}]

    def rand_ex():
        return {k: rng.choice(junk) for k in ("name", "weight_lbs", "rpe", "set_details", "prescribed") if rng.random() < 0.85}

    for _i in range(500):
        ws = [{"date": rng.choice(junk), "logged_at": rng.choice(junk), "exercises": [rand_ex() for _j in range(rng.randint(0, 3))]}
              if rng.random() < 0.85 else rng.choice(junk) for _k in range(rng.randint(0, 6))]
        for name in ("Bench press", rng.choice(junk)):
            s = suggest(name, rng.choice([ws, ws, ws, rng.choice(junk)]), aliases=rng.choice(junk), primary_muscles=rng.choice(junk), equipment=rng.choice(junk))
            json.dumps(s)
            w, last = s["weight_lbs"], s["last_weight_lbs"]
            if s["action"] == "increase":
                assert w is not None and last is not None and w > last
            elif s["action"] == "deload":
                assert w is not None and last is not None and 0 < w < last
            elif s["action"] == "hold":
                assert w == last
            elif s["action"] == "new":
                assert w is None
            G.describe_suggestion(s)


@check("L5 absurd numbers: nonsense (negative, NaN, infinity, text) counts as no weight; a typo over 5,000 lbs is flagged, never worked from")
def _():
    for bad in (-5, 0, float("nan"), float("inf"), True, "135"):
        s = suggest("Bench press", [day("2026-10-01", ex("Bench press", bad))])
        assert s["action"] == "bodyweight" and s["weight_lbs"] is None, (bad, s)
    for typo in (1e308, 5001, 100000):
        s = suggest("Bench press", [day("2026-10-01", ex("Bench press", typo))])
        assert s["action"] == "unknown" and s["weight_lbs"] is None and "not believable" in s["reason"], (typo, s)
    assert suggest("Bench press", [day("2026-10-01", ex("Bench press", 5000))])["action"] == "increase"


@check("L5 emoji, accents and odd spacing in names still match; control characters do not crash")
def _():
    ws = [day("2026-10-01", ex("D\u00e9velop\u00e9 \U0001F4AA", 100))]
    assert suggest("d\u00e9velop\u00e9   \U0001F4AA", ws)["weight_lbs"] == 105
    suggest("Bench\x00 press", ws)
    suggest("x" * 100000, ws)


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)