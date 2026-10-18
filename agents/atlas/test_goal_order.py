"""
ATLAS goal order - L1, L2, L4, L5 tests (pure Python, temp files only, no model).
Covers: the `set goal order ...` command, the goal order and goal-history fields of the training profile,
`set goal type X` moving X to the front, goal start dates, and what a redone setup keeps.

Run from the repo root:  python -m agents.atlas.test_goal_order
"""
import json
import os
import random
import tempfile
import threading
from typing import Any

_DIR = tempfile.mkdtemp(prefix="atlas_goal_order_")
os.environ["TRAINING_PROFILE_PATH"] = os.path.join(_DIR, "training_profile.json")
os.environ["ATLAS_SETUP_STATE_PATH"] = os.path.join(_DIR, "setup_state.json")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_DIR, "pending_actions.json")

from agents.atlas import atlas_actions as A
from agents.atlas import atlas_setup as S
from agents.atlas import programs as G
from agents.atlas import training_profile as P

_HERE = os.path.dirname(os.path.abspath(__file__))
_results = []
FULL = ["power", "strength", "muscle", "endurance", "fat_loss"]


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


def fresh():
    path = os.path.join(tempfile.mkdtemp(prefix="goal_order_t_"), "profile.json")
    os.environ["TRAINING_PROFILE_PATH"] = path
    q = os.environ["PENDING_ACTIONS_PATH"]
    if os.path.exists(q):
        os.remove(q)
    return path


def saved(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["profile"]


# ---------------- L1 static ----------------
@check("L1 static: the profile module still imports only the standard library and shared helpers; the order command is matched BEFORE the generic 'set goal ...'")
def _():
    import ast
    src = open(os.path.join(_HERE, "training_profile.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not mods & {"requests", "anthropic", "google", "ollama", "subprocess"}, mods
    names = [k for k, _ in S._COMMANDS]
    assert names.index("goal_order") < names.index("text")


# ---------------- L2 parsing ----------------
@check("L2 parse_goal_order: commas, 'then', 'and', '>', arrows, case, 'fat loss' and 'fat_loss'")
def _():
    p = P.parse_goal_order
    assert p("power, strength, muscle, endurance, fat loss") == FULL
    assert p("Power THEN Strength > Muscle -> Endurance; Fat-Loss") == FULL
    assert p("power \u2192 strength") == ["power", "strength"]
    assert p("strength and power") == ["strength", "power"]
    assert p("general") == ["general"] and p("fat_loss, power") == ["fat_loss", "power"]


@check("L2 parse_goal_order: unknown goals, repeats and empty input are refused with a plain reason, never guessed")
def _():
    for bad, why in (("power, banana", "banana"), ("power, strength, power", "twice"), ("", "needs goals"), ("   ", "needs goals"),
                     (",,,", "needs goals"), ("explosive", "not a goal")):
        try:
            P.parse_goal_order(bad)
        except ValueError as e:
            assert why in str(e), (bad, str(e))
        else:
            raise AssertionError(bad)
    assert raises(lambda: P.parse_goal_order(None), ValueError) and raises(lambda: P.parse_goal_order(5), ValueError)


@check("L2 the command: 'set goal order ...' becomes a goal_order command (never the free-text 'set goal'), 'set goal type' unchanged")
def _():
    assert S.match_command("set goal order power, strength") == ("goal_order", "power, strength")
    assert S.match_command("Set Goal Order power then strength.") == ("goal_order", "power then strength")
    assert S.match_command("set goal type power") == ("goal_type", "power")
    kind, value = S.match_command("set goal get bigger") or (None, None)
    assert kind == "text" and value == ("goal", "get bigger")
    assert S.match_command("please set goal order") is None


# ---------------- L2 the record ----------------
@check("L2 normalize: an order makes its first goal the goal type; junk in the order or history is dropped")
def _():
    p = P.normalize_profile({"goal": "x", "goal_type": "muscle", "goal_order": ["power", "banana", "power", 5, "Strength"]})
    assert p["goal_order"] == ["power", "strength"] and p["goal_type"] == "power"
    p = P.normalize_profile({"goal_order": "power", "goal_history": [None, 5, {"goal_type": "x", "started": "2026-01-01"},
                                                                   {"goal_type": "power", "started": "2026-10-18"}]})
    assert p["goal_order"] == [] and p["goal_history"] == [{"goal_type": "power", "started": "2026-10-18", "ended": None}]
    assert P.goal_priority({"goal": "x", "goal_type": "endurance"}) == ["endurance"]
    assert P.goal_priority({"goal_order": ["power", "strength"]}) == ["power", "strength"]


@check("L2 track_goal: first goal opens an entry, the same goal changes nothing, a new goal closes the old and opens a new one")
def _():
    p = P.normalize_profile({"goal_type": "power"})
    P.track_goal(p, "2026-10-18")
    P.track_goal(p, "2026-10-19")
    assert p["goal_history"] == [{"goal_type": "power", "started": "2026-10-18", "ended": None}]
    p["goal_type"] = "strength"
    P.track_goal(p, "2026-12-01")
    assert p["goal_history"] == [{"goal_type": "power", "started": "2026-10-18", "ended": "2026-12-01"},
                                 {"goal_type": "strength", "started": "2026-12-01", "ended": None}]
    for i in range(80):
        p["goal_type"] = "muscle" if i % 2 else "endurance"
        P.track_goal(p, f"2027-01-{i % 28 + 1:02d}")
    assert len(p["goal_history"]) <= P.MAX_GOAL_HISTORY and sum(1 for h in p["goal_history"] if h["ended"] is None) == 1


@check("L2 profile text shows the order and when the current goal started")
def _():
    p = P.normalize_profile({"goal": "get fit", "goal_order": FULL})
    P.track_goal(p, "2026-10-18")
    text = P.format_profile(p)
    assert "Goal order: power > strength > build muscle > endurance > fat loss" in text
    assert "Current goal (power) since 2026-10-18" in text and "(type: power)" in text
    assert "Goal order" not in P.format_profile(P.normalize_profile({"goal": "x"}))


@check("L2 training numbers follow the FIRST goal in the order")
def _():
    p = P.normalize_profile({"goal": "x", "goal_type": "muscle", "goal_order": ["power", "strength"], "program_style": "full_body"})
    assert "For your goal (power): 3-5 sets of 3-5 reps" in G.describe_program(p, [])


# ---------------- L2 saving ----------------
@check("L2 set goal order: saved, goal type = first, start date recorded, readable message; a bad order saves nothing")
def _():
    path = fresh()
    ok, msg = P.update_field("goal_order", ["power", "strength", "muscle", "endurance", "fat_loss"])
    assert ok and "goal order -> power > strength > build muscle > endurance > fat loss" in msg, msg
    p = saved(path)
    assert p["goal_order"] == FULL and p["goal_type"] == "power"
    assert len(p["goal_history"]) == 1 and p["goal_history"][0]["goal_type"] == "power" and p["goal_history"][0]["ended"] is None
    before = open(path, encoding="utf-8").read()
    assert raises(lambda: P.update_field("goal_order", "power, banana"), ValueError)
    assert open(path, encoding="utf-8").read() == before


@check("L2 set goal type X with an order: X moves to the front, the rest keep their sequence, the history records the change")
def _():
    path = fresh()
    P.update_field("goal_order", FULL)
    ok, msg = P.update_field("goal_type", "strength")
    assert ok and "goal order now: strength > power > build muscle > endurance > fat loss" in msg, msg
    p = saved(path)
    assert p["goal_order"] == ["strength", "power", "muscle", "endurance", "fat_loss"] and p["goal_type"] == "strength"
    assert [h["goal_type"] for h in p["goal_history"]] == ["power", "strength"] and p["goal_history"][0]["ended"] is not None
    P.update_field("goal_type", "general")                          # not in the order: inserted at the front
    assert saved(path)["goal_order"][0] == "general" and len(saved(path)["goal_order"]) == 6


@check("L2 set goal type with NO order works as before and now records the start; 'set goal ...' text re-derives only without an order")
def _():
    path = fresh()
    P.update_field("goal_type", "endurance")
    p = saved(path)
    assert p["goal_type"] == "endurance" and p["goal_order"] == [] and p["goal_history"][0]["goal_type"] == "endurance"
    P.update_field("goal", "I want more power")
    assert saved(path)["goal_type"] == "power"
    P.update_field("goal_order", ["strength", "power"])
    P.update_field("goal", "I want to swim faster")                  # endurance words, but his order wins
    p = saved(path)
    assert p["goal_type"] == "strength" and p["goal"] == "I want to swim faster"


@check("L2 redoing setup keeps his goal order and history (the order is his choice, not an interview answer)")
def _():
    path = fresh()
    P.update_field("goal_order", FULL)
    new = P.normalize_profile({"goal": "build muscle", "setup_complete": True})
    assert new["goal_type"] == "muscle" and new["goal_order"] == []
    ok, msg = P.save_profile(new)
    p = saved(path)
    assert ok and p["goal_order"] == FULL and p["goal_type"] == "power" and "goal order was kept" in msg
    assert len(p["goal_history"]) == 1
    path = fresh()
    P.save_profile(P.normalize_profile({"goal": "build muscle", "setup_complete": True}))
    assert saved(path)["goal_history"][0]["goal_type"] == "muscle"          # first ever save opens the history too


@check("L2 through chat: the command becomes a proposal that reads 'goal order', approving applies it")
def _():
    path = fresh()
    text = S.handle_message("set goal order power, strength, muscle, endurance, fat loss")
    assert text and "set your goal order to: power > strength > build muscle > endurance > fat loss" in text, text
    assert not os.path.exists(path)                                  # nothing saved yet
    import re
    found = re.search(r"approve ([0-9a-f]{8})", text)
    assert found is not None
    sid = found.group(1)
    out = A.approve_and_execute(sid)
    assert "goal order" in out and saved(path)["goal_order"] == FULL
    assert "banana" in (S.handle_message("set goal order power, banana") or "")
    shown = S.handle_message("show profile") or ""
    assert "Goal order: power > strength" in shown


# ---------------- L4 sustained ----------------
@check("L4 20 order changes at once: the file stays valid, the order is one of the requested ones, exactly one open history entry")
def _():
    path = fresh()
    orders = [random.Random(i).sample(P.GOAL_TYPES, random.Random(i).randint(1, 6)) for i in range(20)]

    def work(o):
        P.update_field("goal_order", o)
    ts = [threading.Thread(target=work, args=(o,)) for o in orders]
    [t.start() for t in ts]
    [t.join() for t in ts]
    p = saved(path)
    assert p["goal_order"] in orders and p["goal_type"] == p["goal_order"][0]
    assert sum(1 for h in p["goal_history"] if h["ended"] is None) == 1 and p["goal_history"][-1]["goal_type"] == p["goal_type"]


@check("L4 20 'set goal type' changes at once with an order: still a permutation of the same goals, front = goal type")
def _():
    path = fresh()
    P.update_field("goal_order", FULL)
    goals = list(P.GOAL_TYPES)

    def work(i):
        P.update_field("goal_type", goals[i % len(goals)])
    ts = [threading.Thread(target=work, args=(i,)) for i in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    p = saved(path)
    assert p["goal_order"][0] == p["goal_type"] and len(set(p["goal_order"])) == len(p["goal_order"]) and set(FULL) <= set(p["goal_order"])
    assert sum(1 for h in p["goal_history"] if h["ended"] is None) == 1


@check("L4 1,000 saves in a row never grow the history past its cap")
def _():
    path = fresh()
    for i in range(1000):
        P.update_field("goal_type", P.GOAL_TYPES[i % len(P.GOAL_TYPES)])
    assert len(saved(path)["goal_history"]) <= P.MAX_GOAL_HISTORY


# ---------------- L5 extreme ----------------
@check("L5 3,000 hostile order strings: a clean list of known goals or a ValueError, never any other crash")
def _():
    rng = random.Random(9)
    bits = ["power", "strength", "fat loss", "x", "", ",", ">", "then", "and", "\u2192", "\U0001F4AA", "muscle ", "  ", "endurance", "general", "\x00", "a" * 400]
    for _ in range(3000):
        text = rng.choice(["", " "]).join(rng.choice(bits) for _ in range(rng.randint(0, 9)))
        try:
            out = P.parse_goal_order(text)
        except ValueError:
            continue
        assert out and len(out) == len(set(out)) and all(g in P.GOAL_TYPES for g in out), (text, out)


@check("L5 damaged profile files: wrong shapes in goal_order / goal_history are cleaned or fail loudly, never overwrite his data")
def _():
    path = fresh()
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"profile": {"goal": "x", "goal_order": {"a": 1}, "goal_history": "junk", "goal_type": "muscle"}}, f)
    ok, _msg = P.update_field("goal_order", ["power"])
    p = saved(path)
    assert ok and p["goal_order"] == ["power"] and len(p["goal_history"]) == 1
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json")
    before = open(path, encoding="utf-8").read()
    assert raises(lambda: P.update_field("goal_order", ["power"]))
    assert open(path, encoding="utf-8").read() == before
    assert P.normalize_profile({"goal_order": [["power"], None, {"x": 1}]})["goal_order"] == []
    assert P.normalize_profile({"goal_order": ["power"] * 1000})["goal_order"] == ["power"]


@check("L5 a 5,000-character 'set goal order' message and odd spacing never crash")
def _():
    fresh()
    big = S.handle_message("set goal order " + "power, " * 1000)
    assert big is None or isinstance(big, str)
    assert isinstance(S.handle_message("set   goal   order   power ,  strength   ."), str)
    assert isinstance(S.handle_message("SET GOAL ORDER \U0001F4AA"), str)


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)