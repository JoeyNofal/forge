"""
ATLAS plan builder, increment 3d-1 - L1, L2, L4, L5 tests for agents/atlas/plan_facts.py (the facts-gatherer).
Pure Python: no model, no network, no keys. Data files are TEMP files only.

Run from the repo root:  python -m agents.atlas.test_plan_facts
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

from agents.atlas import plan_facts as P
from agents.atlas import programs
from agents.atlas import training_profile as profiles

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


def raises(fn, exc: Any = Exception):
    try:
        fn()
    except exc:
        return True
    return False


with open(os.path.join(_HERE, "plan_facts.py"), encoding="utf-8") as f:
    SRC = f.read()

PROFILE: dict[str, Any] = {"goal": "get strong", "session_minutes": 60, "program_style": "ppl", "setup_complete": True,
                           "limitations": ["torn labrum, biceps tendon pain"], "equipment": "full gym"}
FLAGS = programs.limit_flags(PROFILE)
NO_FLAGS = programs.limit_flags({})


def tagged(day, date, names, program="ppl", logged=None):
    return {"program": program, "program_day": day, "date": date, "logged_at": logged or date + "T10:00:00",
            "exercises": [{"name": n, "section": "Chest"} if isinstance(n, str) else n for n in names]}


def facts(profile=None, workouts=None, injuries=None, entries=None, **kw):
    return P.build_facts(PROFILE if profile is None else profile, [] if workouts is None else workouts,
                         [] if injuries is None else injuries, [] if entries is None else entries, **kw)


# ---------------------------------------------------------------- L1 static
@check("L1 no model, network, or write code in plan_facts.py")
def _():
    for bad in ("model_client", "requests", "anthropic", "ollama", "genai", "urllib", "socket", "json.dump",
                "write(", "open(", "random", "sk-", "AIza", "update_json", "save_profile"):
        assert bad not in SRC, bad


@check("L1 no hardcoded user path and no old-folder path")
def _():
    assert "D:\\" not in SRC and "NEXUS SYSTEM" not in SRC and "C:\\" not in SRC


@check("L1 reuses the tested helpers instead of re-implementing them")
def _():
    for needle in ("programs.session_shape", "programs.rotation_state", "programs.limit_flags", "progression.suggest_for",
                   "contains_keyword", "profiles.goal_priority", "programs.focus_for"):
        assert needle in SRC, needle


@check("L1 approved lists contain nothing that loads the shoulder, and no listed shoulder warmup")
def _():
    avoid = {P._plain(a) for a in programs.SHOULDER_WARMUPS_TO_AVOID}
    assert not avoid & {P._plain(w) for w in P.WARMUP_CHOICES}
    assert len(P.WARMUP_CHOICES) == 6 and len(P.COOLDOWN_CHOICES) == 5 and len(P.CORE_CHOICES) == 6
    assert "plank" in P.CORE_CHOICES and "crunches" in P.CORE_CHOICES


# ---------------------------------------------------------------- L2 basics
@check("L2 no profile -> ok False with a clear next step, never a crash")
def _():
    for bad in (None, "x", 5, [], ()):
        r = P.build_facts(bad, [], [], [])
        assert r["ok"] is False and "atlas setup" in r["problem"]
    assert "atlas setup" in P.describe_facts(P.build_facts(None, [], [], []))


@check("L2 a normal profile gives the day, shape, goal numbers and the unit")
def _():
    r = facts()
    assert r["ok"] and r["day"]["label"] == "Push" and r["style"] == "ppl" and r["unit"] == "lbs"
    assert r["shape"]["main"] == 5 and r["shape"]["warmup"] == 4 and r["shape"]["cooldown"] == 3
    assert r["goal_type"] == "strength" and r["goal_params"]["sets"] == (4, 4)
    assert r["core_finisher"] is True and r["minutes_source"] == "your profile"


@check("L2 minutes: override beats profile; no minutes anywhere = the default 60 and says so")
def _():
    assert facts(minutes_override=90)["shape"]["main"] == 6 and facts(minutes_override=90)["minutes_source"] == "this request"
    p = dict(PROFILE)
    del p["session_minutes"]
    r = facts(profile=p)
    assert r["minutes"] == 60 and "default" in r["minutes_source"]
    assert facts(minutes_override=30)["core_finisher"] is False


@check("L2 a bad minutes override is refused loudly (bool, 14, 181, text, float)")
def _():
    for bad in (True, 14, 181, "60", 60.5, 0, -5):
        assert raises(lambda b=bad: facts(minutes_override=b), ValueError), bad


@check("L2 goal order: the first goal is the goal type")
def _():
    p = dict(PROFILE, goal_order=["power", "strength", "muscle"])
    r = facts(profile=p)
    assert r["goal_type"] == "power" and r["goal_order"][:2] == ["power", "strength"] and r["goal_params"]["reps"] == (3, 5)


@check("L2 rotation: a tagged workout advances the day; an override wins until the next tagged workout")
def _():
    assert facts(workouts=[tagged("Push", "2026-10-01", ["Bench press"])])["day"]["label"] == "Pull"
    p = dict(PROFILE, next_day={"day": "Legs", "set_at": "2026-10-05T09:00:00"})
    assert facts(profile=p, workouts=[tagged("Push", "2026-10-01", ["Bench press"])])["day"]["label"] == "Legs"
    assert facts(profile=p, workouts=[tagged("Pull", "2026-10-06", ["Row"])])["day"]["label"] == "Legs"
    assert facts(profile=p, workouts=[tagged("Legs", "2026-10-06", ["Squat"])])["day"]["label"] == "Push"


@check("L2 'you decide' style is settled from days per week; a wrong style falls back safely")
def _():
    assert facts(profile=dict(PROFILE, program_style="auto", days_per_week=4))["style"] == "upper_lower"
    assert facts(profile=dict(PROFILE, program_style="auto"))["style"] == "full_body"
    assert facts(profile=dict(PROFILE, program_style="nonsense"))["ok"]


@check("L2 shoulder/biceps limitation drops biceps from the focus and sets the PT note; none = nothing dropped")
def _():
    pull = facts(workouts=[tagged("Push", "2026-10-01", ["Bench press"])])
    assert "biceps" not in pull["day"]["focus"] and pull["limits"]["pt_note"] == programs.PT_CHECK_NOTE
    clean = facts(profile={"session_minutes": 60, "program_style": "ppl", "setup_complete": True}, workouts=[tagged("Push", "2026-10-01", ["x"])])
    assert "biceps" in clean["day"]["focus"] and clean["limits"]["drop_muscles"] == []


@check("L2 unfinished setup is noted; profile_text only has non-empty answers")
def _():
    r = facts(profile={"goal": "get strong", "session_minutes": 60})
    assert r["notes"] and "interview" in r["notes"][0]
    assert r["profile_text"] == {"goal": "get strong"}


@check("L2 open injuries only (active/recovering); placeholder, resolved and junk ignored; unstated severity named")
def _():
    inj = [{"status": "none", "description": "No injuries currently on file."},
           {"status": "resolved", "description": "old ankle"},
           {"status": "active", "body_part": "shoulder", "description": "labrum tear", "severity": "moderate"},
           {"status": "recovering", "body_part": "knee", "description": "tweak", "severity": "banana"},
           "junk", None, 5, {"status": ["active"]}]
    r = facts(injuries=inj)["open_injuries"]
    assert [i["body_part"] for i in r] == ["shoulder", "knee"]
    assert r[0]["severity"] == "moderate" and r[1]["severity"] == "unstated"


@check("L2 warmups never include a listed shoulder warmup")
def _():
    r = facts()
    assert r["warmups"] and not {P._plain(a) for a in r["limits"]["avoid_warmups"]} & {P._plain(w) for w in r["warmups"]}


# ---------------------------------------------------------------- exclusions
@check("L2 exclusions: curls and chin-ups out ONLY while a biceps limitation is on file")
def _():
    for n in ("Barbell curl", "Hammer Curls", "Chin-Ups", "chin ups", "Chinups", "Reverse-grip curl", "EZ bar curls"):
        assert P.exclusion_reason(n, FLAGS), n
        assert P.exclusion_reason(n, NO_FLAGS) == "", n
    for n in ("Leg curl", "Lying leg curls", "Seated hamstring curl", "Nordic hamstring curl"):     # leg work is allowed
        assert P.exclusion_reason(n, FLAGS) == "", n
    for n in ("Dumbbell curl", "Wrist curl", "Preacher curl", "Chin-up"):                           # still blocked
        assert P.exclusion_reason(n, FLAGS), n
    assert P.exclusion_reason("Leg curl", FLAGS, ["Biceps"])      # a library entry that says biceps is still out
    for n in ("Curling stone carry", "Bench press", "Dumbbell row", "Lat pulldown"):
        assert P.exclusion_reason(n, FLAGS) == "", n


@check("L2 exclusions: a library entry whose PRIMARY muscle is biceps is out; secondary biceps is fine")
def _():
    assert P.exclusion_reason("Zottman", FLAGS, ["Biceps brachii"])
    assert P.exclusion_reason("Barbell row", FLAGS, ["Lats", "Rhomboids"]) == ""
    assert P.exclusion_reason("Zottman", NO_FLAGS, ["Biceps"]) == ""


@check("L2 exclusions: explosive moves out by default, allowed when asked")
def _():
    for n in ("Jump squat", "Box jumps", "Power clean", "Clean and press", "Snatch", "Medicine ball slam", "Wall throws",
              "Burpees", "Kettlebell swing", "Kettlebell swings", "Plyometric push-up", "Jumping lunges"):
        assert P.exclusion_reason(n, NO_FLAGS), n
        assert P.exclusion_reason(n, NO_FLAGS, allow_explosive=True) == "", n
    for n in ("Goblet squat", "Cleaner stance deadlift", "Swing-free lunge", "Kettlebell goblet squat", "Dead bug"):
        assert P.exclusion_reason(n, NO_FLAGS) == "", n


@check("L2 exclusions: junk names and junk flags never crash")
def _():
    for bad in (None, "", "   ", 5, [], {}, "\x00"):
        assert P.exclusion_reason(bad, FLAGS)
    for bad_flags in (None, "x", 5, [], {"drop_muscles": "biceps"}, {"drop_muscles": None}):
        assert P.exclusion_reason("Bench press", bad_flags) == ""


@check("L2 PT note: rows, pulldowns, pull-ups, overhead/military, shoulder press - only while the limitation is on file")
def _():
    for n in ("Barbell row", "Dumbbell Rows", "Lat Pull-Down", "Pulldown", "Pull-Ups", "Overhead press", "Military press",
              "Seated shoulder press", "Face pull"):
        assert P.pt_note_for(n, FLAGS) == programs.PT_CHECK_NOTE, n
        assert P.pt_note_for(n, NO_FLAGS) == "", n
    for n in ("Bench press", "Squat", "Rowing machine", "Leg press", "Browser"):
        assert P.pt_note_for(n, FLAGS) == "", n
    assert P.pt_note_for(None, FLAGS) == "" and P.pt_note_for("Row", None) == ""


# ---------------------------------------------------------------- last session and variety
@check("L2 last session: latest tagged workout of the SAME style and day; other days, styles and untagged are ignored")
def _():
    ws = [tagged("Push", "2026-09-01", ["Old bench"]), tagged("Push", "2026-10-01", ["Bench press", "Incline press"]),
          tagged("Pull", "2026-10-03", ["Row"]), tagged("Push", "2026-10-04", ["Other style"], program="upper_lower"),
          {"date": "2026-10-05", "exercises": [{"name": "Untagged"}]}]
    r = P.last_session_for("ppl", 0, ws)
    assert r == {"date": "2026-10-01", "exercises": ["Bench press", "Incline press"],
                 "sections": {"Bench press": "Chest", "Incline press": "Chest"}}
    assert P.last_session_for("ppl", 2, ws) is None


@check("L2 last session: same date is settled by logged_at; core finisher, duplicates and junk entries are skipped")
def _():
    ws = [tagged("Push", "2026-10-01", ["A"], logged="2026-10-01T08:00:00"),
          tagged("Push", "2026-10-01", ["Bench press", "bench press", "Plank", {"name": "Crunch thing", "section": "Core"},
                                         "Dips", {"nope": 1}, None, 7, {"name": "  "}], logged="2026-10-01T18:00:00")]
    last = P.last_session_for("ppl", 0, ws)
    assert last is not None
    names = last["exercises"]
    assert names == ["Bench press", "Dips"], names      # "A" (earlier logged_at), the repeat "bench press", Plank and the Core-section move are gone


@check("L2 variety: 5 exercises = 2 main + 3 accessories; main kept, 60% of accessories kept, the rest open")
def _():
    last = tagged("Push", "2026-10-01", ["Bench", "Incline", "Fly", "Lateral", "Pushdown"])
    # a Pull day is next after this Push, so ask for Push again by override to see the Push session
    p = dict(PROFILE, next_day={"day": "Push", "set_at": "2026-10-02T09:00:00"})
    v = facts(profile=p, workouts=[last])["variety"]
    assert v["main_slots"] == 2 and v["accessory_slots"] == 3 and v["previous_date"] == "2026-10-01"
    assert v["keep_main"] == ["Bench", "Incline"] and v["keep_accessories"] == ["Fly", "Lateral"] and v["open_slots"] == 1


@check("L2 variety table: how many accessories stay for 2, 3, 4, 5, 6 exercises")
def _():
    names = ["a", "b", "c", "d", "e", "f"]
    expect = {2: (1, 1), 3: (1, 1), 4: (2, 1), 5: (2, 2), 6: (2, 2)}    # (main kept, accessories kept)
    for slots, (m, a) in expect.items():
        prev = {"date": "d", "exercises": names}
        v = P._variety(slots, prev, [], NO_FLAGS)
        assert (len(v["keep_main"]), len(v["keep_accessories"])) == (m, a), (slots, v)
        assert v["open_slots"] == slots - m - a


@check("L2 variety: no history = nothing kept and every slot open; fewer previous exercises than slots is handled")
def _():
    v = facts()["variety"]
    assert v["keep_main"] == [] and v["keep_accessories"] == [] and v["open_slots"] == 5 and v["previous_date"] is None
    v = P._variety(5, {"date": "d", "exercises": ["only one"]}, [], NO_FLAGS)
    assert v["keep_main"] == ["only one"] and v["open_slots"] == 4


@check("L2 variety: a kept exercise that is now excluded is dropped with a reason and never kept")
def _():
    prev = {"date": "d", "exercises": ["Bench", "Barbell curl", "Fly", "Lateral", "Pushdown"]}
    v = P._variety(5, prev, [], FLAGS)
    assert v["dropped"] and v["dropped"][0]["name"] == "Barbell curl"
    assert "Barbell curl" not in v["keep_main"] + v["keep_accessories"]


def _history(weight=100):
    return {"program": "ppl", "program_day": "Push", "date": "2026-10-01", "logged_at": "2026-10-01T10:00:00",
            "exercises": [{"name": "Bench press", "section": "Chest", "rpe": 7, "weight_lbs": weight,
                           "prescribed": {"sets": 2, "reps": 5, "weight_lbs": weight, "target_rpe": 8},
                           "set_details": [{"set": 1, "reps": 5, "weight_lbs": weight}, {"set": 2, "reps": 5, "weight_lbs": weight}]}]}


@check("L2 weights: only for the exercises that stay, worked out by progression.py; none without history")
def _():
    p = dict(PROFILE, next_day={"day": "Push", "set_at": "2026-10-02T09:00:00"})
    r = facts(profile=p, workouts=[_history()])
    assert list(r["weights"]) == ["Bench press"] and r["weights"]["Bench press"]["action"] == "increase"
    assert r["weights"]["Bench press"]["weight_lbs"] == 105
    assert facts()["weights"] == {}


@check("L2 library candidates: matching muscles only, biceps/curl/explosive entries removed, junk entries ignored")
def _():
    lib = [{"name": "Bench press", "primary_muscles": ["Pectoralis major"], "equipment": ["barbell"], "status": "ai_drafted"},
           {"name": "Barbell curl", "primary_muscles": ["Biceps"]},
           {"name": "Squat", "primary_muscles": ["Quadriceps"]},
           {"name": "Clap push-up", "primary_muscles": ["Chest"], "aliases": []},
           {"name": "Plyometric push-up", "primary_muscles": ["Chest"]},
           "junk", None, {"name": "No muscles"}, {"name": "Bad", "primary_muscles": "chest"}]
    r = facts(entries=lib)
    names = [c["name"] for c in r["library_candidates"]]
    assert names == ["Bench press", "Clap push-up"], names
    assert r["library_names"][:3] == ["Bench press", "Barbell curl", "Squat"]


# ---------------------------------------------------------------- real files
def _temp_env():
    d = tempfile.mkdtemp()
    paths = {"FITNESS_DATA_PATH": os.path.join(d, "fitness.json"), "TRAINING_PROFILE_PATH": os.path.join(d, "profile.json"),
             "EXERCISE_LIBRARY_PATH": os.path.join(d, "library.json")}
    return paths


@check("L2 gather_facts on temp files: no profile -> ok False; then a saved profile works; reading writes no profile or library")
def _():
    paths = _temp_env()
    old = {k: os.environ.get(k) for k in paths}
    os.environ.update(paths)
    try:
        assert P.gather_facts()["ok"] is False
        ok, _msg = profiles.save_profile(profiles.normalize_profile(PROFILE))
        assert ok
        r = P.gather_facts(minutes_override=45)
        assert r["ok"] and r["minutes"] == 45 and r["shape"]["main"] == 4
        assert not os.path.exists(paths["EXERCISE_LIBRARY_PATH"])
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@check("L5 a damaged fitness file or library file fails LOUDLY (never silently ignored)")
def _():
    paths = _temp_env()
    old = {k: os.environ.get(k) for k in paths}
    os.environ.update(paths)
    try:
        profiles.save_profile(profiles.normalize_profile(PROFILE))
        with open(paths["FITNESS_DATA_PATH"], "w", encoding="utf-8") as f:
            f.write("{not json")
        assert raises(P.gather_facts, RuntimeError)
        os.remove(paths["FITNESS_DATA_PATH"])
        with open(paths["EXERCISE_LIBRARY_PATH"], "w", encoding="utf-8") as f:
            f.write("[1,2")
        assert raises(P.gather_facts, RuntimeError)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@check("L2 the command-line check prints the facts; a bad minutes argument is refused with a plain message")
def _():
    paths = _temp_env()
    env = dict(os.environ, **paths)
    sub: Any = subprocess
    base = [sys.executable, "-m", "agents.atlas.plan_facts"]
    r = sub.run(base, cwd=_ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "no training profile" in r.stdout, (r.stdout, r.stderr[-200:])
    r = sub.run(base + ["abc"], cwd=_ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode != 0 and "whole number" in (r.stderr + r.stdout)


# ---------------------------------------------------------------- L4 sustained / concurrency
@check("L4 100 identical calls give identical facts, and the inputs are never changed")
def _():
    ws = [tagged("Push", "2026-10-01", ["Bench", "Incline", "Fly", "Lateral", "Pushdown"]), _history()]
    inj = [{"status": "active", "body_part": "shoulder", "description": "labrum"}]
    lib = [{"name": "Bench press", "primary_muscles": ["Chest"], "aliases": ["bp"]}]
    before = copy.deepcopy((PROFILE, ws, inj, lib))
    first = facts(workouts=ws, injuries=inj, entries=lib, today="2026-10-19")
    for _i in range(100):
        assert facts(workouts=ws, injuries=inj, entries=lib, today="2026-10-19") == first
    assert (PROFILE, ws, inj, lib) == before


@check("L4 20 threads at once: every result correct, no cross-talk")
def _():
    out, errs = [], []

    def work(i):
        try:
            minutes = 30 + i
            r = facts(minutes_override=minutes)
            out.append((minutes, r["minutes"], r["shape"]["main"]))
        except Exception as e:
            errs.append(repr(e))
    ts = [threading.Thread(target=work, args=(i,)) for i in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs and len(out) == 20 and all(a == b for a, b, _ in out)


# ---------------------------------------------------------------- L5 extreme
@check("L5 junk data of every kind never crashes (workouts, injuries, library, profile fields)")
def _():
    junk = [None, "x", 5, 3.5, True, [], {}, [None], [[]], ["a"], {"exercises": 5}, [{"exercises": "no"}], [{"program": []}],
            [{"program": "ppl", "program_day": ["Push"]}], [{"program": "ppl", "program_day": "Push", "exercises": [[], {}, None]}]]
    for j in junk:
        r = P.build_facts(PROFILE, j, j, j)
        assert r["ok"]
    for k in ("limitations", "goal_order", "next_day", "days_per_week", "program_style", "goal", "session_minutes"):
        for j in junk:
            assert P.build_facts(dict(PROFILE, **{k: j}), [], [], [])["ok"] is True, (k, j)


@check("L5 huge text, emoji and control characters are cleaned and bounded")
def _():
    big = "x" * 50000
    inj = [{"status": "active", "body_part": big, "description": big + "\x00\x07evil", "severity": "mild"}]
    r = facts(injuries=inj)["open_injuries"][0]
    assert len(r["body_part"]) <= 60 and len(r["description"]) <= 150 and "\x00" not in r["description"]
    ws = [tagged("Push", "2026-10-01", ["\U0001F4AA Bench press " + "y" * 5000, "Incline \u202e press"])]
    p = dict(PROFILE, next_day={"day": "Push", "set_at": "2026-10-02T09:00:00"})
    v = facts(profile=p, workouts=ws)["variety"]
    assert all(len(n) <= 100 for n in v["keep_main"] + v["keep_accessories"])


@check("L5 20,000 workouts and 5,000 library entries stay fast and the output stays bounded")
def _():
    ws = [tagged(["Push", "Pull", "Legs"][i % 3], f"2026-{1 + i % 12:02d}-{1 + i % 28:02d}", ["Bench", "Row", "Squat"]) for i in range(20000)]
    lib = [{"name": f"Exercise {i}", "primary_muscles": ["Chest"], "aliases": [f"alias {i}"]} for i in range(5000)]
    t = time.time()
    r = facts(workouts=ws, entries=lib)
    assert time.time() - t < 20, time.time() - t
    assert len(r["library_candidates"]) == P.MAX_CANDIDATES and len(r["library_names"]) == P.MAX_LIBRARY_NAMES
    inj = [{"status": "active", "description": f"i{i}"} for i in range(500)]
    assert len(facts(injuries=inj)["open_injuries"]) == P.MAX_INJURIES


@check("L5 describe_facts never crashes on junk or a half-empty facts dict")
def _():
    for j in (None, 5, "x", [], {}, {"ok": False}, {"ok": False, "problem": "p"}):
        assert isinstance(P.describe_facts(j), str)
    assert "Next:" in P.describe_facts(facts())


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)