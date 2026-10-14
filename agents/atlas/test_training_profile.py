"""
ATLAS setup, increment 3a-i - L1, L2, L4, L5 tests for the training profile store
(agents/atlas/training_profile.py) and its two approval actions (save the whole
profile, change one thing). No model, no keys, no cost. TEMP files only: your real
profile and approval queue are never touched.

Run from the repo root:  python -m agents.atlas.test_training_profile
"""
import ast
import json
import os
import random
import re
import shutil
import tempfile
import threading
import time
from typing import Any

_QUEUE_DIR = tempfile.mkdtemp(prefix="profile_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from agents.atlas import atlas_actions as A
from agents.atlas import training_profile as P
from shared import pending_actions as pa

_HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE = pa.PENDING_ACTIONS_PATH
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


def fresh():
    d = tempfile.mkdtemp(prefix="profile_test_")
    os.environ["TRAINING_PROFILE_PATH"] = os.path.join(d, "training_profile.json")
    if os.path.exists(QUEUE):
        os.remove(QUEUE)
    return os.environ["TRAINING_PROFILE_PATH"]


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_raw(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def raw_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def raises(fn, exc: Any = Exception):
    try:
        fn()
    except exc:
        return True
    return False


def pending():
    return pa.list_pending_actions("atlas")


FULL = {
    "goal": "Build muscle and get stronger, back in shape for swimming",
    "experience": "Lifted on and off for 3 years, comfortable with squat, bench and deadlift",
    "consistency": "Trained twice a week for the last 3 months",
    "days_per_week": 4,
    "session_minutes": 60,
    "equipment": "Full gym",
    "limitations": ["Left shoulder clicks overhead"],
    "activity": "Swim twice a week",
    "preferences": "Love pull-ups, hate burpees",
    "program_style": "ppl",
    "body": "",
    "notes": "Prefers mornings",
    "setup_complete": True,
}

with open(os.path.join(_HERE, "training_profile.py"), encoding="utf-8") as f:
    SRC = f.read()
with open(os.path.join(_HERE, "atlas_actions.py"), encoding="utf-8") as f:
    ACTIONS_SRC = f.read()


# ---------------- L1 static ----------------
@check("L1 static: the store imports only the standard library and two shared helpers; no model, network or raw file writes")
def _():
    tree = ast.parse(SRC)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported <= {"json", "os", "re", "time", "datetime", "typing", "shared.file_store", "shared.normalizers"}, imported
    assert "open(" not in SRC and "json.dump(" not in SRC and "stream_by_tier" not in SRC
    assert not re.search(r"(api[_-]?key|sk-[A-Za-z0-9]|AIza|NEXUS SYSTEM)", SRC, re.I)


@check("L1 static: only the approval handlers write the profile; the propose functions never do")
def _():
    assert ACTIONS_SRC.count("profiles.save_profile(") == 1 and ACTIONS_SRC.count("profiles.update_field(") == 1
    assert ACTIONS_SRC.index("profiles.save_profile(") > ACTIONS_SRC.index("def _run_save_profile")
    assert ACTIONS_SRC.index("profiles.update_field(") > ACTIONS_SRC.index("def _run_update_profile")
    body = ACTIONS_SRC[ACTIONS_SRC.index("def propose_save_profile"):ACTIONS_SRC.index("def propose_injury_update")]
    assert "save_profile(" not in body.replace("def propose_save_profile(", "") and "update_field(" not in body
    assert "approve_and_execute" not in body


# ---------------- L2 smoke: words to values ----------------
@check("L2 goal type: the EARLIEST goal word wins, whole words only")
def _():
    g = P.derive_goal_type
    assert g("I want to get stronger and build muscle") == "strength"
    assert g("build muscle then get strong") == "muscle"
    assert g("lose fat") == "fat_loss" and g("swim faster and run a marathon") == "endurance"
    assert g("be healthy") == "general" and g("") == "general"
    assert g("I'm into strongman and muscular") == "general"
    for bad in (None, 5, ["muscle"]):
        assert g(bad) == "general"


@check("L2 goal type words typed by hand: 'fat loss', 'Fat-Loss', 'muscle'; junk is refused")
def _():
    assert P.parse_goal_type("fat loss") == "fat_loss" and P.parse_goal_type(" Fat-Loss ") == "fat_loss"
    assert P.parse_goal_type("muscle") == "muscle" and P.parse_goal_type("general") == "general"
    for bad in ("gain", "", None, 5, "muscle building"):
        assert P.parse_goal_type(bad) is None, bad


@check("L2 program style: many ways to say it, earliest wins, 'pull-ups' is not a program")
def _():
    s = P.parse_program_style
    for text, want in (("push/pull/legs", "ppl"), ("PPL", "ppl"), ("push, pull, legs", "ppl"), ("Push Pull Leg", "ppl"),
                       ("Upper and lower", "upper_lower"), ("upper/lower", "upper_lower"), ("full-body", "full_body"),
                       ("full body", "full_body"), ("bro split", "bro_split"), ("bro", "bro_split"),
                       ("you decide", "auto"), ("whatever", "auto"), ("I don't know", "auto"),
                       ("ppl or upper lower", "ppl"), ("upper_lower", "upper_lower"), ("bro_split", "bro_split")):
        assert s(text) == want, (text, s(text))
    for bad in ("pull-ups", "legs", "", None, 5, "banana"):
        assert s(bad) is None, bad


# ---------------- L2 smoke: the profile shape ----------------
@check("L2 an empty profile is all 'not given', never invented")
def _():
    p = P.normalize_profile({})
    assert p["goal"] == "" and p["goal_type"] == "general" and p["days_per_week"] is None and p["session_minutes"] is None
    assert p["limitations"] == [] and p["program_style"] == "auto" and p["setup_complete"] is False
    assert p["created_at"] is None and p["version"] == 1


@check("L2 a full profile keeps Joey's words exactly; unknown keys are dropped; goal type comes from his goal words")
def _():
    p = P.normalize_profile(dict(FULL, junk="x", other={"a": 1}))
    assert p["goal"] == FULL["goal"] and p["experience"] == FULL["experience"] and p["limitations"] == FULL["limitations"]
    assert p["goal_type"] == "muscle" and p["days_per_week"] == 4 and p["session_minutes"] == 60
    assert p["program_style"] == "ppl" and p["setup_complete"] is True and "junk" not in p and "other" not in p


@check("L2 messy values: text on one line, numbers from strings, out-of-range numbers become 'not given', yes is not True")
def _():
    p = P.normalize_profile({"goal": "  build\n\tmuscle \x00 now ", "days_per_week": "4", "session_minutes": 14,
                             "limitations": "left knee; right wrist\nleft knee", "setup_complete": "yes",
                             "goal_type": "fat loss", "program_style": "push pull legs"})
    assert p["goal"] == "build muscle now" and p["days_per_week"] == 4 and p["session_minutes"] is None
    assert p["limitations"] == ["left knee", "right wrist"] and p["setup_complete"] is False
    assert p["goal_type"] == "fat_loss" and p["program_style"] == "ppl"
    assert P.normalize_profile({"goal": "lift", "goal_type": "nonsense"})["goal_type"] == "general"
    for bad_days in (0, 8, True, 3.5, "abc", None, [4], -1):
        assert P.normalize_profile({"days_per_week": bad_days})["days_per_week"] is None, bad_days
    assert P.normalize_profile({"days_per_week": 3.0})["days_per_week"] == 3


@check("L2 limits: giant text is cut, limitations capped at 20, a non-dict is refused")
def _():
    p = P.normalize_profile({"goal": "g" * 5000, "body": "b" * 5000, "limitations": [f"limit {i}" for i in range(500)]})
    assert len(p["goal"]) == 500 and len(p["body"]) == 200 and len(p["limitations"]) == 20
    for bad in (None, "x", 5, [FULL]):
        assert raises(lambda b=bad: P.normalize_profile(b), ValueError)


@check("L2 single changes: good values are cleaned; unusable ones are refused with a plain reason")
def _():
    c = P.clean_update
    assert c("goal", "  lose   fat ") == {"field": "goal", "value": "lose fat"}
    assert c("goal_type", "Fat Loss") == {"field": "goal_type", "value": "fat_loss"}
    assert c("days_per_week", "4") == {"field": "days_per_week", "value": 4}
    assert c("session_minutes", 45) == {"field": "session_minutes", "value": 45}
    assert c("program_style", "upper/lower") == {"field": "program_style", "value": "upper_lower"}
    assert c("program_style", "ppl") == {"field": "program_style", "value": "ppl"}
    assert c("add_limitation", " left knee ") == {"field": "add_limitation", "value": "left knee"}
    assert c("clear_limitations", "ignored") == {"field": "clear_limitations", "value": None}
    for field, bad in (("nope", "x"), (None, "x"), ("goal", ""), ("goal", None), ("goal_type", "gain"), ("days_per_week", 0),
                       ("days_per_week", "abc"), ("days_per_week", True), ("session_minutes", 14), ("session_minutes", 181),
                       ("program_style", "banana"), ("add_limitation", "   "), ("notes", 5)):
        assert raises(lambda f=field, b=bad: P.clean_update(f, b), ValueError), (field, bad)


@check("L2 format_profile: readable, numbered limitations, 'not given' for gaps, and the setup state")
def _():
    text = P.format_profile(dict(FULL))
    for part in ("Training profile (setup complete):", "Goal: Build muscle and get stronger", "(type: build muscle)",
                 "Days per week: 4   Minutes per session: 60", "Limitations:", "  1. Left shoulder clicks overhead",
                 "Program style: push / pull / legs", "Body numbers: (not given)"):
        assert part in text, part
    empty = P.format_profile({})
    assert "setup not finished" in empty and "Limitations: none noted" in empty and "Goal: (not given)" in empty
    assert raises(lambda: P.format_profile("x"), ValueError)


# ---------------- L2 smoke: the file ----------------
@check("L2 save then load: round trip, timestamps set, created_at kept on a second save, reading never creates the file")
def _():
    path = fresh()
    assert P.load_profile() is None and not os.path.exists(path)
    ok, msg = P.save_profile(FULL)
    assert ok and msg == "Training profile saved."
    first = P.load_profile()
    assert first is not None and first["goal"] == FULL["goal"] and first["created_at"] and first["updated_at"]
    time.sleep(0.01)
    P.save_profile(dict(FULL, goal="Lose fat"))
    second = P.load_profile()
    assert second is not None and second["goal"] == "Lose fat" and second["goal_type"] == "fat_loss"
    assert second["created_at"] == first["created_at"] and second["updated_at"] >= first["updated_at"]


@check("L2 changing one thing: creates an unfinished profile if there is none, keeps everything else, re-derives goal type")
def _():
    path = fresh()
    ok, msg = P.update_field("days_per_week", 3)
    assert ok and "days per week -> 3" in msg
    p = P.load_profile()
    assert p is not None and p["days_per_week"] == 3 and p["setup_complete"] is False and p["created_at"]
    P.save_profile(FULL)
    ok, msg = P.update_field("goal", "Lose fat before summer")
    assert ok and "goal type: fat loss" in msg
    p = P.load_profile()
    assert p is not None and p["goal_type"] == "fat_loss" and p["experience"] == FULL["experience"] and p["setup_complete"] is True
    ok, msg = P.update_field("goal_type", "strength")
    assert ok and (P.load_profile() or {})["goal_type"] == "strength"
    ok, msg = P.update_field("program_style", "bro split")
    assert ok and "bro split" in msg


@check("L2 limitations: add, a repeat says so, cap at 20, clear")
def _():
    fresh()
    assert P.update_field("add_limitation", "left knee")[0]
    ok, msg = P.update_field("add_limitation", "LEFT KNEE")
    assert not ok and "already in your profile" in msg
    for i in range(25):
        P.update_field("add_limitation", f"limit {i}")
    p = P.load_profile()
    assert p is not None and len(p["limitations"]) == 20
    ok, msg = P.update_field("add_limitation", "one more")
    assert not ok and "already has 20" in msg
    assert P.update_field("clear_limitations", None)[0] and (P.load_profile() or {})["limitations"] == []


@check("L2 a refused change touches nothing: no file is created")
def _():
    path = fresh()
    assert raises(lambda: P.update_field("days_per_week", 12), ValueError)
    assert raises(lambda: P.update_field("nope", "x"), ValueError)
    assert not os.path.exists(path)


# ---------------- L2 smoke: approval actions ----------------
@check("L2 propose save: shows the whole profile, saves nothing, creates no file; approve saves; deny throws away")
def _():
    path = fresh()
    aid, msg = A.propose_save_profile(FULL)
    assert aid and "Nothing is saved until you approve" in msg and "Training profile (setup complete):" in msg
    assert "Left shoulder clicks overhead" in msg and not os.path.exists(path) and len(pending()) == 1
    assert A.approve_and_execute(aid) == "Training profile saved."
    p = P.load_profile()
    assert p is not None and p["goal"] == FULL["goal"]
    aid2, _m = A.propose_save_profile(dict(FULL, goal="Different"))
    assert A.deny_action(aid2).startswith("Denied")
    p = P.load_profile()
    assert p is not None and p["goal"] == FULL["goal"] and pending() == []


@check("L2 propose a change: one clear line, saves nothing; approve applies it; bad values raise and queue nothing")
def _():
    path = fresh()
    P.save_profile(FULL)
    aid, msg = A.propose_profile_update("days_per_week", "5")
    assert aid and "set your days per week to: 5" in msg and (P.load_profile() or {})["days_per_week"] == 4
    assert A.approve_and_execute(aid).startswith("Profile updated")
    assert (P.load_profile() or {})["days_per_week"] == 5
    aid, msg = A.propose_profile_update("add_limitation", "right wrist")
    assert "add a limitation to your training profile: right wrist" in msg
    aid2, msg2 = A.propose_profile_update("clear_limitations", None)
    assert "clear all limitations" in msg2
    before = len(pending())
    for field, bad in (("days_per_week", 9), ("nope", "x"), ("goal", "")):
        assert raises(lambda f=field, b=bad: A.propose_profile_update(f, b), ValueError)
    assert len(pending()) == before


@check("L2 describe: readable one-liners, odd data falls back instead of crashing")
def _():
    assert "goal: Build muscle" in A.describe("save_profile", P.normalize_profile(FULL))
    assert A.describe("update_profile", {"field": "goal", "value": "Lose fat"}) == "set your goal to: Lose fat"
    assert A.describe("update_profile", {"field": "nope", "value": 1}).startswith("update_profile:")
    assert A.describe("save_profile", {"bad": 1}).startswith("save_profile:")


# ---------------- L4 sustained / concurrency ----------------
@check("L4 20 limitations added at the same moment: all 20 are in the profile, none lost")
def _():
    path = fresh()
    errors = []

    def go(i):
        try:
            P.update_field("add_limitation", f"limitation {chr(65 + i)}")
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go, args=(i,)) for i in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    p = P.load_profile()
    assert not errors, errors[:2]
    assert p is not None and len(p["limitations"]) == 20 and len(set(p["limitations"])) == 20


@check("L4 mixed changes at once (days, goal, limitations): the file stays valid and every kind of change lands")
def _():
    path = fresh()
    P.save_profile(FULL)
    errors = []

    def go(i):
        try:
            if i % 3 == 0:
                P.update_field("days_per_week", 1 + i % 7)
            elif i % 3 == 1:
                P.update_field("goal", f"goal number {i}")
            else:
                P.update_field("add_limitation", f"limitation {chr(65 + i)}")
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go, args=(i,)) for i in range(30)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    p = P.load_profile()
    assert not errors, errors[:2]
    assert p is not None and p["goal"].startswith("goal number") and p["days_per_week"] in range(1, 8)
    assert len(p["limitations"]) == 1 + 10 and p["experience"] == FULL["experience"]
    json.loads(raw_bytes(path))


@check("L4 one 'save profile' proposal approved by 20 threads: saved exactly once")
def _():
    path = fresh()
    aid = A.propose_save_profile(FULL)[0]
    outs = []
    threads = [threading.Thread(target=lambda: outs.append(A.approve_and_execute(aid))) for _i in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(1 for o in outs if o == "Training profile saved.") == 1
    assert (P.load_profile() or {})["goal"] == FULL["goal"]


@check("L4 100 loads in a row stay fast and identical")
def _():
    fresh()
    P.save_profile(FULL)
    first = P.load_profile()
    t0 = time.time()
    for _i in range(100):
        assert P.load_profile() == first
    assert time.time() - t0 < 5.0


# ---------------- L5 extreme / breaking ----------------
@check("L5 damaged JSON: reading and changing fail loudly and the file is byte-for-byte untouched")
def _():
    path = fresh()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json")
    before = raw_bytes(path)
    assert raises(lambda: P.load_profile(), RuntimeError)
    assert raises(lambda: P.update_field("days_per_week", 3), Exception)
    assert raises(lambda: P.save_profile(FULL), Exception)
    assert raw_bytes(path) == before


@check("L5 wrong shapes (top-level list, 'profile' not an object): fails loudly and never overwrites")
def _():
    for content in ([1, 2, 3], {"profile": [1, 2]}, {"profile": "oops"}):
        path = fresh()
        write_raw(path, content)
        before = raw_bytes(path)
        assert raises(lambda: P.load_profile(), RuntimeError)
        assert raises(lambda: P.update_field("days_per_week", 3), RuntimeError)
        assert raises(lambda: P.save_profile(FULL), RuntimeError)
        assert raw_bytes(path) == before


@check("L5 other keys in the file survive a save and an update")
def _():
    path = fresh()
    write_raw(path, {"profile": {"goal": "old"}, "future_feature": {"keep": "me"}})
    P.update_field("days_per_week", 2)
    P.save_profile(FULL)
    data = read(path)
    assert data["future_feature"] == {"keep": "me"} and data["profile"]["days_per_week"] == 4


@check("L5 unicode and emoji survive the whole trip through the file")
def _():
    path = fresh()
    P.save_profile(dict(FULL, goal="Br\u00fcst \U0001F4AA \u4e2d\u6587", limitations=["\u00e9paule \U0001F525"]))
    p = P.load_profile()
    assert p is not None and p["goal"] == "Br\u00fcst \U0001F4AA \u4e2d\u6587" and p["limitations"] == ["\u00e9paule \U0001F525"]


@check("L5 400 random hostile profiles and changes: a clean result or a ValueError, never any other crash")
def _():
    rng = random.Random(6)
    values = [None, 5, True, "", " ", "x", "a" * 800, "4", 0, 99, 3.5, float("nan"), float("inf"), [], ["a", None, 5],
              {"a": 1}, "\x00\x01", "push pull legs", "muscle", "left knee; right wrist", -3, [[1]]]
    keys = list(P.TEXT_FIELDS) + ["goal_type", "days_per_week", "session_minutes", "limitations", "program_style", "setup_complete"]
    for _i in range(400):
        raw = {k: rng.choice(values) for k in keys if rng.random() < 0.8}
        p = P.normalize_profile(raw)
        json.dumps(p)
        assert p["goal_type"] in P.GOAL_TYPES and p["program_style"] in P.PROGRAM_STYLES
        assert p["days_per_week"] is None or 1 <= p["days_per_week"] <= 7
        assert len(p["limitations"]) <= 20 and isinstance(p["setup_complete"], bool)
        P.format_profile(p)
        try:
            P.clean_update(rng.choice(list(P.UPDATABLE_FIELDS) + ["nope", None]), rng.choice(values))
        except ValueError:
            pass

# ---------------- 3b: the manual 'next program day' ----------------
@check("L2 3b next day: kept as {day, set_at} when usable, None for anything else; a hand-set day shows in the profile text")
def _():
    p = P.normalize_profile({"next_day": {"day": " Pull ", "set_at": "2026-10-01T10:00:00"}})
    assert p["next_day"] == {"day": "Pull", "set_at": "2026-10-01T10:00:00"}
    for bad in ("Pull", 5, {}, {"day": ""}, {"day": 5}, None, ["Pull"], {"set_at": "x"}):
        assert P.normalize_profile({"next_day": bad})["next_day"] is None, bad
    assert "next day set by hand: Pull" in P.format_profile({"next_day": {"day": "Pull", "set_at": "x"}})
    assert "next day set by hand" not in P.format_profile({})


@check("L2 3b next day: a change is cleaned or refused, applied with a timestamp, and described in one clear line")
def _():
    assert P.clean_update("next_day", "  Full   body B ") == {"field": "next_day", "value": "Full body B"}
    for bad in ("", None, "   ", 5, ["Pull"]):
        assert raises(lambda b=bad: P.clean_update("next_day", b), ValueError), bad
    path = fresh()
    ok, msg = P.update_field("next_day", "Pull")
    p = P.load_profile()
    assert ok and msg == "Profile updated: next program day -> Pull." and p is not None
    assert p["next_day"] is not None and p["next_day"]["day"] == "Pull" and p["next_day"]["set_at"]
    aid, text = A.propose_profile_update("next_day", "Legs")
    assert "set your next program day to: Legs" in text and "Nothing is saved until you approve" in text

passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
shutil.rmtree(_QUEUE_DIR, ignore_errors=True)
raise SystemExit(0 if passed == len(_results) else 1)