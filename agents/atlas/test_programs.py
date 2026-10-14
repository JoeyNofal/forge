"""
ATLAS programs, increment 3b - L1, L2, L4, L5 tests for agents/atlas/programs.py: the program
templates, the numbers per goal, session sizing and the rotation ("which day is next").
Pure Python: no model, no files, no keys.

Run from the repo root:  python -m agents.atlas.test_programs
"""
import ast
import json
import os
import random
import re
import threading
import time
from typing import Any

from agents.atlas import programs as G

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


def w(program, day, date, logged=None):
    return {"program": program, "program_day": day, "date": date, "logged_at": logged or date + "T10:00:00"}


with open(os.path.join(_HERE, "programs.py"), encoding="utf-8") as f:
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
    assert imported <= {"typing", "agents.atlas"}, imported
    for banned in ("open(", "update_json", "stream_by_tier", "atlas_actions", "requests"):
        assert banned not in SRC, banned
    assert not re.search(r"(api[_-]?key|sk-[A-Za-z0-9]|AIza|NEXUS SYSTEM)", SRC, re.I)


# ---------------- L2 smoke: the tables ----------------
@check("L2 templates: four styles, unique day names, every day has focus muscles, every day carries a core finisher")
def _():
    assert set(G.PROGRAMS) == {"ppl", "upper_lower", "full_body", "bro_split"}
    for key, prog in G.PROGRAMS.items():
        labels = [d["label"] for d in prog["days"]]
        assert len(labels) == len(set(x.lower() for x in labels)) and len(labels) >= 2, key
        for i, d in enumerate(prog["days"]):
            assert d["focus"] and all(isinstance(m, str) and m for m in d["focus"])
            info = G.day_info(key, i)
            assert info["core_finisher"] is True and info["label"] == d["label"] and info["focus"] == d["focus"]
    assert G.CORE_FINISHER == ["abs", "core"]


@check("L2 templates: what you asked for - Pull has back, biceps, rear delts and forearms; Push has chest, shoulders, triceps; Legs has the leg muscles")
def _():
    days = {d["label"]: d["focus"] for d in G.PROGRAMS["ppl"]["days"]}
    assert days["Pull"] == ["back", "biceps", "rear delts", "forearms"]
    assert days["Push"] == ["chest", "shoulders", "triceps"]
    assert days["Legs"] == ["quads", "hamstrings", "glutes", "calves"]
    assert [d["label"] for d in G.PROGRAMS["bro_split"]["days"]] == ["Chest", "Back", "Shoulders", "Arms", "Legs"]
    assert [d["label"] for d in G.PROGRAMS["upper_lower"]["days"]] == ["Upper", "Lower"]
    assert [d["label"] for d in G.PROGRAMS["full_body"]["days"]] == ["Full body A", "Full body B"]
    assert "forearms" in G.PROGRAMS["upper_lower"]["days"][0]["focus"] and "forearms" in G.PROGRAMS["bro_split"]["days"][3]["focus"]


@check("L2 day info is a copy: changing it never changes the template")
def _():
    info = G.day_info("ppl", 0)
    info["focus"].append("legs")
    assert G.PROGRAMS["ppl"]["days"][0]["focus"] == ["chest", "shoulders", "triceps"]


@check("L2 goal numbers: the agreed table; unknown goals get the general numbers")
def _():
    g = G.goal_params
    assert g("strength") == {"sets": (4, 4), "reps": (3, 6), "rest_seconds": (180, 180), "rpe_main": 8, "rpe_accessory": 7}
    assert g("muscle")["reps"] == (8, 12) and g("muscle")["sets"] == (3, 4) and g("muscle")["rest_seconds"] == (90, 90)
    assert g("fat_loss") == g("endurance") and g("fat_loss")["reps"] == (12, 20) and g("fat_loss")["rest_seconds"] == (45, 60)
    assert g("general")["rpe_main"] == 7 and g("general")["rest_seconds"] == (75, 75) and G.WARMUP_RPE == 5
    for odd in ("banana", None, 5, ["muscle"], ""):
        assert g(odd) == G.GOAL_PARAMS["general"]


@check("L2 session sizing: 30 -> 3 main, 45 -> 4, 60 -> 5, 90 -> 6; warmup 3-4, cooldown 2-3; core finisher only from 40 minutes")
def _():
    s = G.session_shape
    for minutes, main, warm, cool, core in ((30, 3, 3, 2, False), (45, 4, 3, 2, True), (60, 5, 4, 3, True), (90, 6, 4, 3, True),
                                            (15, 2, 3, 2, False), (24, 2, 3, 2, False), (25, 3, 3, 2, False), (37, 3, 3, 2, False),
                                            (38, 4, 3, 2, False), (40, 4, 3, 2, True), (52, 4, 4, 3, True), (53, 5, 4, 3, True),
                                            (75, 5, 4, 3, True), (76, 6, 4, 3, True), (180, 6, 4, 3, True)):
        got = s(minutes)
        assert (got["main"], got["warmup"], got["cooldown"], got["core_finisher"]) == (main, warm, cool, core), minutes
    for odd in (None, 0, 10, 181, True, "60", 45.5, [60]):
        assert s(odd)["minutes"] == 60 and s(odd)["main"] == 5, odd


@check("L2 'you decide': 1-3 days full body, 4 upper/lower, 5+ push/pull/legs, no days set -> full body; a chosen style wins")
def _():
    r = G.resolve_style
    for days, want in ((1, "full_body"), (2, "full_body"), (3, "full_body"), (4, "upper_lower"), (5, "ppl"), (6, "ppl"), (7, "ppl"), (None, "full_body")):
        style, reason = r({"program_style": "auto", "days_per_week": days})
        assert style == want and "you decide" in reason or "you said 'you decide'" in reason, (days, style, reason)
    assert r({"program_style": "bro_split", "days_per_week": 3}) == ("bro_split", "your choice")
    assert r({"program_style": "ppl"})[0] == "ppl"
    for odd in (None, "x", 5, {}, {"program_style": "nonsense", "days_per_week": True}):
        assert r(odd)[0] == "full_body"


# ---------------- L2 smoke: the rotation ----------------
@check("L2 days are found by name, ignoring case and spacing; unknown names and styles give nothing")
def _():
    f = G.find_day
    assert f("ppl", "pull") == 1 and f("ppl", "  PUSH ") == 0 and f("full_body", "full   body b") == 1
    for bad in ("Chest", "", None, 5, "pu"):
        assert f("ppl", bad) is None, bad
    assert f("nope", "Pull") is None and f(None, "Pull") is None


@check("L2 rotation: starts at day 1, then one day per tagged workout, wrapping round")
def _():
    st = G.rotation_state("ppl", [])
    assert st["next"]["label"] == "Push" and st["last"] is None and "starts at day 1" in st["reason"]
    st = G.rotation_state("ppl", [w("ppl", "Push", "2026-10-01")])
    assert st["next"]["label"] == "Pull" and st["last"] == {"label": "Push", "date": "2026-10-01"}
    st = G.rotation_state("ppl", [w("ppl", "Push", "2026-10-01"), w("ppl", "Pull", "2026-10-03")])
    assert st["next"]["label"] == "Legs"
    st = G.rotation_state("ppl", [w("ppl", "Push", "2026-10-01"), w("ppl", "Pull", "2026-10-03"), w("ppl", "Legs", "2026-10-05")])
    assert st["next"]["label"] == "Push" and st["last"]["label"] == "Legs"


@check("L2 rotation: the most recent tagged workout counts (by date, then by when it was logged), whatever the order in the file")
def _():
    ws = [w("ppl", "Legs", "2026-10-05"), w("ppl", "Push", "2026-10-01"), w("ppl", "Pull", "2026-10-03")]
    assert G.rotation_state("ppl", ws)["next"]["label"] == "Push"
    same_day = [w("ppl", "Push", "2026-10-05", "2026-10-05T09:00:00"), w("ppl", "Pull", "2026-10-05", "2026-10-05T18:00:00")]
    assert G.rotation_state("ppl", same_day)["next"]["label"] == "Legs"


@check("L2 rotation: workouts without a tag, with unknown days, or tagged with another style never move it (changing style restarts at day 1)")
def _():
    ws = [{"date": "2026-10-09", "type": "gym"}, w("ppl", "Chest", "2026-10-08"), w("upper_lower", "Upper", "2026-10-07"),
          w("ppl", "Push", "2026-10-02"), w("nonsense", "Pull", "2026-10-09"), {"program": "ppl"}, "junk", None, 5]
    assert G.rotation_state("ppl", ws)["next"]["label"] == "Pull"
    assert G.rotation_state("upper_lower", ws)["next"]["label"] == "Lower"
    assert G.rotation_state("bro_split", ws)["next"]["label"] == "Chest" and G.rotation_state("bro_split", ws)["last"] is None
    assert G.rotation_state("full_body", None)["next"]["label"] == "Full body A"


@check("L2 rotation: a tag can be written the way the page echoes it ('push pull legs', 'PPL', 'Push / Pull / Legs')")
def _():
    for tag in ("ppl", "PPL", "push pull legs", "Push / Pull / Legs", "push-pull-legs"):
        assert G.rotation_state("ppl", [w(tag, "Pull", "2026-10-03")])["next"]["label"] == "Legs", tag


@check("L2 rotation: 'set next day' overrides until the next tagged workout is logged; an unknown day is ignored")
def _():
    ws = [w("ppl", "Push", "2026-10-01", "2026-10-01T10:00:00")]
    ov = {"day": "Legs", "set_at": "2026-10-02T09:00:00"}
    st = G.rotation_state("ppl", ws, ov)
    assert st["next"]["label"] == "Legs" and st["reason"] == "you set it by hand"
    ws.append(w("ppl", "Legs", "2026-10-03", "2026-10-03T10:00:00"))
    assert G.rotation_state("ppl", ws, ov)["next"]["label"] == "Push"               # the override is used up
    assert G.rotation_state("ppl", [], {"day": "Pull", "set_at": "2026-10-02T09:00:00"})["next"]["label"] == "Pull"
    for bad in ({"day": "Chest", "set_at": "2026-10-02T09:00:00"}, {"day": "Legs"}, {"set_at": "x"}, "Legs", 5, None, {}):
        assert G.rotation_state("ppl", ws[:1], bad)["next"]["label"] == "Pull", bad
    assert raises(lambda: G.rotation_state("nope", []), ValueError)


@check("L2 the day after: wraps round, and unknown things give nothing")
def _():
    def after(style, label):
        d = G.next_day_after(style, label)
        return d["label"] if d else None

    assert after("ppl", "Push") == "Pull" and after("ppl", "legs") == "Push"
    assert after("full_body", "Full body B") == "Full body A"
    assert G.next_day_after("ppl", "Chest") is None and G.next_day_after("nope", "Push") is None


@check("L2 the 'next in your program' line: only for a real tag, and it reads nothing")
def _():
    assert G.next_day_hint("ppl", "Push") == "\nNext in your push / pull / legs program: Pull."
    assert G.next_day_hint("push pull legs", "Legs") == "\nNext in your push / pull / legs program: Push."
    for bad in ((None, None), ("ppl", None), ("ppl", "Chest"), ("banana", "Push"), (5, 5), ("auto", "Push"), ("ppl", "")):
        assert G.next_day_hint(*bad) == "", bad


@check("L2 'my program' text: style, days with the core finisher, what is next, session size and goal numbers")
def _():
    prof = {"goal": "Build muscle", "days_per_week": 4, "session_minutes": 60, "program_style": "ppl"}
    text = G.describe_program(prof, [w("ppl", "Push", "2026-10-09")])
    for part in ("Your program: push / pull / legs (your choice)", "  1. Push: chest, shoulders, triceps, plus a core (abs) finisher",
                 "  2. Pull: back, biceps, rear delts, forearms, plus a core (abs) finisher", "Next: Pull (the day after your last tagged workout: Push on 2026-10-09).",
                 "A 60-minute session: 4 warmup moves, 5 main exercises with a core finisher, 3 cooldown moves.",
                 "For your goal (build muscle): 3-4 sets of 8-12 reps, rest 90 sec, target RPE 8 on main lifts and 7 on accessories (warmups 5)."):
        assert part in text, part
    auto = G.describe_program({"program_style": "auto", "days_per_week": 4, "goal": "get stronger", "session_minutes": 30}, [])
    assert "Your program: upper / lower (you said 'you decide', so I chose it from your 4 days a week)" in auto
    assert "Next: Upper (no tagged workout yet in this program, so it starts at day 1)." in auto
    assert "without the core finisher (too short)" in auto and "4 sets of 3-6 reps, rest 180 sec" in auto
    assert raises(lambda: G.describe_program("x", []), ValueError)


# ---------------- L4 sustained / concurrency ----------------
@check("L4 100 identical calls give identical answers, and a 5,000-workout history is handled fast")
def _():
    ws = [w("ppl", ["Push", "Pull", "Legs"][i % 3], f"2026-{1 + i // 400:02d}-{1 + (i // 14) % 28:02d}", f"2026-01-01T{i % 24:02d}:{i % 60:02d}:00") for i in range(5000)]
    first = G.rotation_state("ppl", ws)
    t0 = time.time()
    for _i in range(100):
        assert G.rotation_state("ppl", ws) == first
    assert time.time() - t0 < 10.0


@check("L4 20 threads working out different rotations at once: no cross-talk")
def _():
    errors = []

    def work(n):
        try:
            style = ["ppl", "upper_lower", "full_body", "bro_split"][n % 4]
            days = G.PROGRAMS[style]["days"]
            for k in range(len(days)):
                st = G.rotation_state(style, [w(style, days[k]["label"], "2026-10-01")])
                assert st["next"]["label"] == days[(k + 1) % len(days)]["label"]
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=work, args=(n,)) for n in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors[:2]


# ---------------- L5 extreme / breaking ----------------
@check("L5 400 hostile histories and profiles: a clean answer or a ValueError, never any other crash")
def _():
    rng = random.Random(21)
    junk = [None, 5, True, "", "ppl", "Push", "x" * 500, ["a"], {"a": 1}, float("nan"), "2026-10-01", "\x00", {"day": "Push", "set_at": "2026-10-01"}]
    for _i in range(400):
        ws = [{k: rng.choice(junk) for k in ("program", "program_day", "date", "logged_at") if rng.random() < 0.8} if rng.random() < 0.8 else rng.choice(junk)
              for _j in range(rng.randint(0, 6))]
        style = rng.choice(list(G.PROGRAMS))
        st = G.rotation_state(style, ws if rng.random() < 0.9 else rng.choice(junk), rng.choice(junk))
        assert st["next"]["label"] in [d["label"] for d in G.PROGRAMS[style]["days"]]
        json.dumps(st)
        prof = {k: rng.choice(junk) for k in ("program_style", "days_per_week", "session_minutes", "goal_type", "next_day") if rng.random() < 0.8}
        G.describe_program(prof, ws)
        G.next_day_hint(rng.choice(junk), rng.choice(junk))
        G.session_shape(rng.choice(junk))


@check("L5 emoji and odd spacing in tags survive without crashing")
def _():
    assert G.rotation_state("ppl", [w("ppl", "\U0001F4AA Push", "2026-10-01")])["next"]["label"] == "Push"
    assert G.rotation_state("ppl", [w("ppl", "  pull\u00a0 ", "2026-10-01")])["next"]["label"] == "Legs"


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)