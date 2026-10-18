"""
ATLAS - L1, L2, L4, L5 tests for the 'power' goal type, the shoulder/biceps limitation rule
(programs.limit_flags / focus_for / describe_program) and the progression wording fix.
Pure Python: no model, no files, no keys. (No L3: nothing here calls a real model.)

Run from the repo root:  python -m agents.atlas.test_atlas_limits_power
"""
import ast
import os
import random
import threading
import time
from typing import Optional

from agents.atlas import programs as G
from agents.atlas import progression as R
from agents.atlas import training_profile as P

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
            print(f"FAIL  {name}\n      {e!r}")
        return fn
    return deco


def read(name):
    with open(os.path.join(_HERE, name), encoding="utf-8") as f:
        return f.read()


SHOULDER = "tear in the labrum of the right shoulder under the biceps tendon"


def prof(**kw):
    base = {"goal": "get fit", "goal_type": "general", "program_style": "full_body", "session_minutes": 60, "limitations": []}
    base.update(kw)
    return P.normalize_profile(base)


# ---------------- L1 static ----------------
@check("L1 programs.py stays pure: no model, file, network or env access")
def _():
    tree = ast.parse(read("programs.py"))
    mods = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)}
    mods |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not mods & {"os", "requests", "urllib", "socket", "subprocess", "anthropic", "ollama", "google"}, mods
    assert "open(" not in read("programs.py") and "getenv" not in read("programs.py")


@check("L1 no secrets or hardcoded old paths in the changed files")
def _():
    for f in ("programs.py", "progression.py", "training_profile.py"):
        t = read(f)
        assert "sk-" not in t and "NEXUS SYSTEM" not in t and "AIza" not in t, f


# ---------------- L2 power goal ----------------
@check("L2 power is a goal type with its own numbers; the other numbers are unchanged")
def _():
    assert "power" in P.GOAL_TYPES and P.GOAL_TYPE_LABELS["power"] == "power"
    assert G.goal_params("power") == {"sets": (3, 5), "reps": (3, 5), "rest_seconds": (120, 180), "rpe_main": 7, "rpe_accessory": 6}
    assert G.goal_params("strength")["reps"] == (3, 6) and G.goal_params("muscle")["reps"] == (8, 12)
    assert set(G.GOAL_PARAMS) == set(P.GOAL_TYPES)


@check("L2 goal words: power / explosive find power; powerlifting stays strength; earliest word still wins")
def _():
    g = P.derive_goal_type
    assert g("I want more power") == "power" and g("explosive jumps") == "power" and g("plyometrics") == "power"
    assert g("powerlifting") == "strength" and g("I want to be stronger and powerful") == "strength"
    assert g("power then strength") == "power" and g("strength then power") == "strength"
    assert g("muscles showing, then power") == "muscle"
    assert P.parse_goal_type("power") == "power" and P.parse_goal_type(" POWER ") == "power"
    assert P.normalize_profile({"goal": "x", "goal_type": "power"})["goal_type"] == "power"


@check("L2 a power profile is described with the power numbers")
def _():
    text = G.describe_program(prof(goal_type="power"), [])
    assert "For your goal (power): 3-5 sets of 3-5 reps, rest 120-180 sec, target RPE 7 on main lifts and 6 on accessories" in text


# ---------------- L2 limitation rule ----------------
@check("L2 biceps/shoulder/labrum/rotator in a limitation switch the rule on; unrelated limits do not")
def _():
    on = G.limit_flags(prof(limitations=[SHOULDER]))
    assert on["drop_muscles"] == ["biceps"] and "windmill arms" in on["avoid_warmups"] and on["pt_note"] == G.PT_CHECK_NOTE and on["reason"]
    for t in ("sore bicep", "left shoulders ache", "labrum", "rotator cuff", "SHOULDER"):
        assert G.limit_flags(prof(limitations=[t]))["drop_muscles"] == ["biceps"], t
    for t in ("bad knee", "lower back", "shouldered the blame", "tricep strain"):
        assert G.limit_flags(prof(limitations=[t]))["drop_muscles"] == [], t
    assert G.limit_flags(prof())["drop_muscles"] == [] and G.limit_flags(prof())["pt_note"] == ""


@check("L2 focus_for removes biceps only; the program tables themselves are never changed")
def _():
    p = prof(limitations=[SHOULDER])
    assert G.focus_for(["hamstrings", "biceps", "triceps"], p) == ["hamstrings", "triceps"]
    assert G.focus_for(["hamstrings", "biceps"], prof()) == ["hamstrings", "biceps"]
    assert "biceps" in G.PROGRAMS["full_body"]["days"][1]["focus"]


@check("L2 my program with the shoulder note drops biceps, explains why, and keeps the rest")
def _():
    text = G.describe_program(prof(limitations=[SHOULDER]), [])
    assert "Full body B: hamstrings, glutes, back, chest, triceps, forearms, plus a core (abs) finisher" in text
    assert "biceps is left out of your plans" in text and "windmill arms" in text and G.PT_CHECK_NOTE in text
    plain = G.describe_program(prof(), [])
    assert "biceps" in plain and "left out" not in plain
    arms = G.describe_program(prof(program_style="bro_split", limitations=[SHOULDER]), [])
    assert "Arms: triceps, forearms" in arms


# ---------------- L2 progression wording ----------------
def _ex(done, planned_reps=8, planned_sets=3, rpe: Optional[int] = 8):
    return {"name": "Bench press", "weight_lbs": 135, "rpe": rpe, "prescribed": {"sets": planned_sets, "reps": planned_reps, "weight_lbs": 135, "target_rpe": 8},
            "set_details": [{"set": i + 1, "reps": r, "weight_lbs": 135} for i, r in enumerate(done)]}


def _day(date, ex):
    return {"date": date, "logged_at": date + "T10:00:00", "type": "gym", "exercises": [ex]}


@check("L2 wording: a missed rep says which sets hit the prescription; the status is unchanged")
def _():
    s = R.suggest_weight("Bench press", [_day("2026-10-18", _ex([8, 8, 7]))])
    assert s["action"] == "hold" and "135" in s["reason"]
    assert "2 of 3 sets hit the prescribed 8 reps" in s["reason"] and "reps missed" not in s["reason"], s["reason"]
    assert "3 of 3 sets at 135 lbs" in s["reason"]


@check("L2 wording: a skipped set shows fewer sets done; every-rep-hit text is unchanged")
def _():
    s = R.suggest_weight("Bench press", [_day("2026-10-18", _ex([8, 8]))])
    assert s["action"] == "hold" and "2 of 3 sets at 135 lbs" in s["reason"] and "every rep hit in the sets you did" in s["reason"], s["reason"]
    ok = R.suggest_weight("Bench press", [_day("2026-10-18", _ex([8, 8, 8], rpe=None))])
    assert "every rep hit" in ok["reason"]


@check("L2 wording: timed exercises say seconds")
def _():
    ex = {"name": "Plank", "weight_lbs": 25, "rpe": 7, "prescribed": {"sets": 2, "seconds": 30, "target_rpe": 7, "weight_lbs": 25},
          "set_details": [{"set": 1, "seconds": 30, "weight_lbs": 25}, {"set": 2, "seconds": 20, "weight_lbs": 25}]}
    text = R._session_text("2026-10-18", R.evaluate_session(ex))
    assert "1 of 2 sets hit the prescribed 30 sec" in text, text


# ---------------- L4 sustained ----------------
@check("L4 10,000 random limitation lists: never crashes, rule always matches a plain recomputation")
def _():
    rng = random.Random(7)
    words = ["shoulder", "bicep", "knee", "labrum", "back", "hip", "tricep", "rotator", "", "x" * 50]
    for _ in range(10000):
        lims = [" ".join(rng.choice(words) for _ in range(rng.randint(0, 5))) for _ in range(rng.randint(0, 4))]
        want = any(set(t.split()) & {"shoulder", "bicep", "labrum", "rotator"} for t in lims)
        got = G.limit_flags({"limitations": lims})["drop_muscles"] == ["biceps"]
        assert got == want, lims


@check("L4 20 threads x 200 calls see identical results")
def _():
    bad, p = [], prof(limitations=[SHOULDER])

    def work():
        for _ in range(200):
            if G.describe_program(p, []) != G.describe_program(p, []) or G.focus_for(["biceps", "chest"], p) != ["chest"]:
                bad.append(1)
    ts = [threading.Thread(target=work) for _ in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not bad


# ---------------- L5 extreme ----------------
@check("L5 damaged shapes never crash: None, wrong types, nested junk, huge text, unicode")
def _():
    for bad in (None, 5, "x", [], {"limitations": None}, {"limitations": "shoulder"}, {"limitations": [None, 5, ["shoulder"], {"a": 1}]},
                {"limitations": {"a": "shoulder"}}):
        assert G.limit_flags(bad)["drop_muscles"] == [], bad
    assert G.focus_for(None, prof()) == [] and G.focus_for("biceps", prof()) == [] and G.focus_for([None, 5, "chest"], prof()) == ["chest"]
    t0 = time.time()
    assert G.limit_flags({"limitations": ["a " * 400000 + "shoulder"]})["drop_muscles"] == []     # past the 20,000-char cap
    assert G.limit_flags({"limitations": ["\U0001F4AA shoulder \u00e9\u4e2d"]})["drop_muscles"] == ["biceps"]
    assert time.time() - t0 < 2


@check("L5 wording code never crashes on a damaged evaluation")
def _():
    for ev in ({"reps_hit": False, "sets_done": 1, "planned_sets": None, "rpe": None, "target_rpe": None, "top_weight": 100},
               {"reps_hit": None, "sets_done": 1, "planned_sets": 3, "rpe": None, "target_rpe": None, "top_weight": 100}):
        assert "on " in R._session_text("2026-10-18", ev)


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)