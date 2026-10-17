"""
ATLAS programs, increment 3b - L1, L2, L4, L5 tests for the program commands ('my program',
'set next day <label>') and how the rotation follows your logged, tagged workouts end to end.
No real model, no keys, no cost (the chat model is a fake). TEMP files only: your real profile,
fitness data and approval queue are never touched.

Run from the repo root:  python -m agents.atlas.test_atlas_program
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

_QUEUE_DIR = tempfile.mkdtemp(prefix="program_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from agents.atlas import atlas_actions as A
from agents.atlas import atlas_program as AP
from agents.atlas import chat as C
from agents.atlas import training_profile as P
from shared import pending_actions as pa

_HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE = pa.PENDING_ACTIONS_PATH
CHAT_CALLS: list = []
_results: list = []


def fake_chat_model(agent, tier, system, messages, location=""):
    CHAT_CALLS.append(messages)
    yield "CHAT TEXT"


C.stream_by_tier = fake_chat_model
C.extract_and_propose = lambda message: []
C.web_search = lambda q: "stub search result"


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
    d = tempfile.mkdtemp(prefix="program_test_")
    os.environ["TRAINING_PROFILE_PATH"] = os.path.join(d, "training_profile.json")
    os.environ["ATLAS_SETUP_STATE_PATH"] = os.path.join(d, "atlas_setup_state.json")
    os.environ["FITNESS_DATA_PATH"] = os.path.join(d, "fitness.json")
    os.environ["EXERCISE_LIBRARY_PATH"] = os.path.join(d, "exercise_library.json")
    if os.path.exists(QUEUE):
        os.remove(QUEUE)
    CHAT_CALLS.clear()
    return d


def raises(fn, exc: Any = Exception):
    try:
        fn()
    except exc:
        return True
    return False


def pending():
    return pa.list_pending_actions("atlas")


def run(msg):
    return "".join(C.stream_atlas(msg))


def approve_id(text) -> str:
    m = re.search(r"approve ([0-9a-f]{8})", text)
    assert m is not None, text
    return m.group(1)


def tagged_block(program, day, date, title=None):
    lines = ["FORGE WORKOUT LOG v1", f"Title: {title or day + ' ' + date}", f"Date: {date}", "Unit: lbs"]
    if program:
        lines.append(f"Program: {program}")
    if day:
        lines.append(f"Day: {day}")
    lines += ["## Main", "Exercise: Squat", "Prescribed: 1x5 | weight: 100 lbs", "Set 1: 5 reps | 100 lbs", "RPE: 7", "Notes:"]
    return "\n".join(lines)


def log_workout(program, day, date, title=None) -> str:
    """Pastes a finished workout through the real proposal and approval path; returns the approval message."""
    aid, _msg = A.propose_workout_block(tagged_block(program, day, date, title))
    assert aid is not None
    return A.approve_and_execute(aid)


def set_profile(**over):
    base = {"goal": "Build muscle", "days_per_week": 4, "session_minutes": 60, "program_style": "ppl", "setup_complete": True}
    base.update(over)
    P.save_profile(base)


with open(os.path.join(_HERE, "atlas_program.py"), encoding="utf-8") as f:
    SRC = f.read()
with open(os.path.join(_HERE, "chat.py"), encoding="utf-8") as f:
    CHAT_SRC = f.read()


# ---------------- L1 static ----------------
@check("L1 static: the command module reads and proposes only; it never writes a file or calls a model")
def _():
    tree = ast.parse(SRC)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported <= {"re", "typing", "agents.atlas", "agents.atlas.atlas_tools"}, imported
    for banned in ("open(", "update_json", "stream_by_tier", "update_field(", "save_profile(", "approve_and_execute", "json.dump"):
        assert banned not in SRC, banned
    assert not re.search(r"(api[_-]?key|sk-[A-Za-z0-9]|AIza|NEXUS SYSTEM)", SRC, re.I)


@check("L1 static: in chat, program commands run BEFORE the setup interview and BEFORE the refusal gate")
def _():
    assert CHAT_SRC.count("atlas_program.handle_message(message)") == 1
    i = CHAT_SRC.index("atlas_program.handle_message(message)")
    assert CHAT_SRC.index("parse_library_command(message)") < i < CHAT_SRC.index("atlas_setup.handle_message(message)") < CHAT_SRC.index("if should_refuse(message, ATLAS_NON_TOPIC")
    assert ".lower()" not in CHAT_SRC


# ---------------- L2 smoke ----------------
@check("L2 commands: only a message that is JUST the command counts")
def _():
    m = AP.match_command
    for text in ("my program", "My Program?", "show program", "show my program", "view my program.", "see program"):
        assert m(text) == ("show", None), text
    assert m("set next day Pull") == ("next_day", "Pull") and m(" Set Next Day full body b. ") == ("next_day", "full body b")
    for no in ("program", "my programming question", "please set next day Pull", "set next day", "set next day Pull\nset next day Push",
               "what is my program for tomorrow", "show program please", "", "x" * 300, "set next day " + "d" * 41):
        assert m(no) is None, no[:40]
    assert raises(lambda: AP.match_command(None), TypeError)          # pyright: ignore[reportArgumentType]
    assert AP.handle_message("what should I bench") is None


@check("L2 with no profile yet, both commands point you to setup and change nothing")
def _():
    fresh()
    for cmd in ("my program", "set next day Pull"):
        out = AP.handle_message(cmd)
        assert out is not None and "don't have a training profile yet" in out and "atlas setup" in out
    assert pending() == []


@check("L2 'my program' for a fresh profile: the days in order and Next is day 1")
def _():
    fresh()
    set_profile()
    out = AP.handle_message("my program")
    assert out is not None
    assert out.startswith("Your program: push / pull / legs (your choice)")
    assert "Next: Push (no tagged workout yet in this program, so it starts at day 1)." in out
    assert "  2. Pull: back, biceps, rear delts, forearms, plus a core (abs) finisher" in out


@check("L2 the whole loop: each approved TAGGED workout says what is next, and 'my program' follows; untagged workouts never move it")
def _():
    fresh()
    set_profile()
    res = log_workout("ppl", "Push", "2026-10-01")
    assert res.startswith("Workout logged") and res.endswith("\nNext in your push / pull / legs program: Pull.")
    assert "Next: Pull (the day after your last tagged workout: Push on 2026-10-01)." in (AP.handle_message("my program") or "")
    res = log_workout(None, None, "2026-10-02", title="Off program")
    assert res.startswith("Workout logged") and "Next in your" not in res
    assert "Next: Pull" in (AP.handle_message("my program") or "")
    assert log_workout("ppl", "Pull", "2026-10-03").endswith("Next in your push / pull / legs program: Legs.")
    assert log_workout("ppl", "Legs", "2026-10-05").endswith("Next in your push / pull / legs program: Push.")
    out = AP.handle_message("my program") or ""
    assert "Next: Push (the day after your last tagged workout: Legs on 2026-10-05)." in out


@check("L2 a workout tagged with an unknown program or day is logged normally, with no hint and no effect on the rotation")
def _():
    fresh()
    set_profile()
    for program, day in (("banana", "Push"), ("ppl", "Chest"), ("ppl", None), (None, "Push"), ("auto", "Push")):
        res = log_workout(program, day, "2026-10-0" + str(1 + len(program or "") % 8), title=f"odd {program} {day}")
        assert res.startswith("Workout logged") and "Next in your" not in res, (program, day, res)
    assert "starts at day 1" in (AP.handle_message("my program") or "")


@check("L2 set next day: a proposal that saves nothing until approved; once approved it wins until your next tagged workout")
def _():
    fresh()
    set_profile()
    log_workout("ppl", "Push", "2026-10-01")
    out = AP.handle_message("set next day legs")
    assert out is not None and "set your next program day to: Legs" in out and "Nothing is saved until you approve" in out
    assert "Next: Pull" in (AP.handle_message("my program") or "")                       # not approved yet
    assert A.approve_and_execute(approve_id(out)).startswith("Profile updated")
    shown = AP.handle_message("my program") or ""
    assert "Next: Legs (you set it by hand; your last tagged workout was Push on 2026-10-01)." in shown
    assert log_workout("ppl", "Legs", "2026-10-03").endswith("Next in your push / pull / legs program: Push.")
    assert "Next: Push (the day after your last tagged workout: Legs on 2026-10-03)." in (AP.handle_message("my program") or "")


@check("L2 set next day with a day your program does not have: the days are listed and nothing is queued")
def _():
    fresh()
    set_profile()
    out = AP.handle_message("set next day Chest")
    assert out is not None and "I don't know a day called 'Chest'" in out and "Your days are: Push, Pull, Legs" in out
    assert "Nothing was saved" in out and pending() == []


@check("L2 changing program style restarts the rotation at day 1; 'you decide' is settled from your days a week")
def _():
    fresh()
    set_profile()
    log_workout("ppl", "Push", "2026-10-01")
    log_workout("ppl", "Pull", "2026-10-02")
    P.update_field("program_style", "upper/lower")
    out = AP.handle_message("my program") or ""
    assert out.startswith("Your program: upper / lower (your choice)") and "Next: Upper (no tagged workout yet" in out
    P.update_field("program_style", "you decide")
    out = AP.handle_message("my program") or ""
    assert "upper / lower (you said 'you decide', so I chose it from your 4 days a week)" in out
    P.update_field("days_per_week", 6)
    assert "push / pull / legs (you said 'you decide', so I chose it from your 6 days a week)" in (AP.handle_message("my program") or "")
    assert "Next: Legs (the day after your last tagged workout: Pull on 2026-10-02)." in (AP.handle_message("my program") or "")


@check("L2 full body: the day names have spaces; case and spacing do not matter in the command, and the saved name is the proper one")
def _():
    fresh()
    set_profile(program_style="full body")
    out = AP.handle_message("set next day full   BODY b") or ""
    assert "set your next program day to: Full body B" in out
    A.approve_and_execute(approve_id(out))
    assert "Next: Full body B (you set it by hand)." in (AP.handle_message("my program") or "")
    assert log_workout("full body", "Full body B", "2026-10-04").endswith("Next in your full body A/B program: Full body A.")


@check("L2 chat: both commands work in chat with no model call; ordinary messages are unaffected")
def _():
    fresh()
    set_profile()
    out = run("my program")
    assert out.startswith("Your program: push / pull / legs") and CHAT_CALLS == []
    out = run("set next day pull")
    assert "set your next program day to: Pull" in out and CHAT_CALLS == []
    assert run("approve " + approve_id(out)).startswith("Profile updated")
    assert "Next: Pull (you set it by hand)." in run("show my program")
    for msg in ("program", "please set next day Pull", "what should I bench next week"):
        assert run(msg) == "CHAT TEXT", msg


@check("L2 chat: 'my program' still works in the middle of the setup interview and does not move it")
def _():
    fresh()
    set_profile()
    assert "Setup question 1 of 12" in run("atlas setup")
    assert run("my program").startswith("Your program: push / pull / legs")
    assert run("I want to build muscle").startswith("Got it.\n\nSetup question 2 of 12")


@check("L2 a damaged profile or fitness file is reported plainly; odd values inside a profile never crash it")
def _():
    d = fresh()
    path = os.path.join(d, "training_profile.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json")
    out = AP.handle_message("my program") or ""
    assert "can't read or write your profile or workout files" in out
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"profile": {"program_style": ["x"], "days_per_week": [4], "goal": 5, "next_day": "Pull", "session_minutes": {"a": 1}}}, f)
    out = AP.handle_message("my program") or ""
    assert "full body A/B" in out and "Next: Full body A" in out


# ---------------- L4 sustained / concurrency ----------------
@check("L4 20 'my program' reads while 6 tagged workouts are approved at the same moment: no crash, and the rotation ends in the right place")
def _():
    fresh()
    set_profile()
    days = ["Push", "Pull", "Legs", "Push", "Pull", "Legs"]
    ids = [A.propose_workout_block(tagged_block("ppl", days[i], f"2026-10-0{i + 1}"))[0] for i in range(6)]
    outs, results, errors = [], [], []

    def read_it():
        try:
            for _i in range(5):
                outs.append(AP.handle_message("my program"))
        except Exception as e:
            errors.append(repr(e))

    def approve(aid):
        try:
            results.append(A.approve_and_execute(aid))
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=read_it) for _i in range(20)] + [threading.Thread(target=approve, args=(a,)) for a in ids]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors[:2]
    assert all(o is not None and o.startswith("Your program: push / pull / legs") for o in outs)
    assert len(results) == 6 and all(r.startswith("Workout logged") for r in results)
    assert "Next: Push (the day after your last tagged workout: Legs on 2026-10-06)." in (AP.handle_message("my program") or "")


@check("L4 20 'set next day' proposals approved at once: the profile stays valid with one of the days set")
def _():
    fresh()
    set_profile()
    texts = [AP.handle_message(f"set next day {['Push', 'Pull', 'Legs'][i % 3]}") for i in range(20)]
    assert all(t is not None and "Proposed:" in t for t in texts) and len(pending()) == 20
    results = []
    ids = [approve_id(t) for t in texts if t is not None]
    threads = [threading.Thread(target=lambda s=s: results.append(A.approve_and_execute(s))) for s in ids]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert all(r.startswith("Profile updated") for r in results), results[:3]
    p = P.load_profile()
    assert p is not None and p["next_day"] is not None and p["next_day"]["day"] in ("Push", "Pull", "Legs")


@check("L4 a 5,000-workout history is read and worked out fast")
def _():
    d = fresh()
    set_profile()
    workouts = [{"type": "gym", "date": f"2025-{1 + i % 12:02d}-{1 + i % 28:02d}", "logged_at": f"2025-01-01T00:{i % 60:02d}:{i % 60:02d}",
                 "program": "ppl", "program_day": ["Push", "Pull", "Legs"][i % 3]} for i in range(5000)]
    with open(os.path.join(d, "fitness.json"), "w", encoding="utf-8") as f:
        json.dump({"workouts": workouts, "injuries": []}, f)
    t0 = time.time()
    out = AP.handle_message("my program") or ""
    assert time.time() - t0 < 5.0 and "Next:" in out


# ---------------- L5 extreme / breaking ----------------
@check("L5 junk inside the fitness file (non-dict workouts, bad tags) never breaks 'my program'")
def _():
    d = fresh()
    set_profile()
    junk = ["x", None, 5, [], {"program": ["ppl"], "program_day": {"a": 1}}, {"program": "ppl", "program_day": "Pull", "date": 5, "logged_at": None},
            {"program": "ppl", "program_day": "Push", "date": "2026-10-01"}]
    with open(os.path.join(d, "fitness.json"), "w", encoding="utf-8") as f:
        json.dump({"workouts": junk, "injuries": []}, f)
    out = AP.handle_message("my program") or ""
    assert "Next:" in out and "Your program: push / pull / legs" in out


@check("L5 500 random command-like messages: always text or nothing back, never a crash")
def _():
    d = fresh()
    set_profile()
    rng = random.Random(33)
    pieces = ["my program", "show program", "set next day", "Pull", "Legs", "Push", "full body", "x", "\n", "  ", "!!!", "\U0001F4AA", "a" * 60,
              "approve", "?", "program", "set", "next", "day"]
    for _i in range(500):
        msg = " ".join(rng.choice(pieces) for _j in range(rng.randint(1, 4)))
        out = AP.handle_message(msg)
        assert out is None or (isinstance(out, str) and out != ""), repr(msg)
    assert os.path.exists(os.path.join(d, "training_profile.json"))


@check("L5 a command with emoji or control characters never crashes and never saves anything by itself")
def _():
    fresh()
    set_profile()
    before = len(pending())
    for msg in ("set next day \U0001F4AA", "set next day Pull\x00", "set next day \u00a0Pull\u00a0"):
        assert AP.handle_message(msg) is not None
    assert len([p for p in pending() if "next program day" in str(p)]) <= 1 and len(pending()) >= before


@check("L5 a non-text message fails loudly")
def _():
    fresh()
    for bad in (None, 5, ["x"], b"x"):
        assert raises(lambda b=bad: AP.handle_message(b), TypeError)       # pyright: ignore[reportArgumentType]

# ---------------- 3c: 'next weight <exercise>' ----------------
def bench_block(date, reps, rpe, sets=4):
    lines = ["FORGE WORKOUT LOG v1", f"Title: Bench {date}", f"Date: {date}", "Unit: lbs", "## Main", "Exercise: Bench press",
             f"Prescribed: {sets}x8 | weight: 135 lbs | target RPE: 7"]
    lines += [f"Set {i + 1}: {reps} reps | 135 lbs" for i in range(sets)]
    lines += [f"RPE: {rpe}", "Notes:"]
    return "\n".join(lines)


def log_bench(date, reps=8, rpe=7, sets=4) -> str:
    aid, _msg = A.propose_workout_block(bench_block(date, reps, rpe, sets))
    assert aid is not None
    return A.approve_and_execute(aid)


@check("L2 3c command: 'next weight <exercise>' (also 'for', and a trailing question mark) is a command only as a whole message")
def _():
    m = AP.match_command
    assert m("next weight bench press") == ("next_weight", "bench press")
    assert m("Next weight for Incline DB press?") == ("next_weight", "Incline DB press")
    for no in ("next weight", "what is my next weight for bench", "please next weight bench", "next weights bench", "next weight " + "x" * 101,
               "next weight a\nnext weight b"):
        assert m(no) is None, no[:40]


@check("L2 3c: no history gives no invented weight; it works without a profile")
def _():
    fresh()
    out = AP.handle_message("next weight bench press") or ""
    assert out.startswith("bench press: no weight yet.") and "feels like RPE 6" in out and pending() == []


@check("L2 3c: after logged sessions it follows the rules - a success adds 5, a struggle repeats, two in a row drops about 10%")
def _():
    fresh()
    log_bench("2026-10-01")
    out = AP.handle_message("next weight bench press") or ""
    assert out.startswith("bench press: Try 140 lbs.") and "a success, so +5 lbs to 140 lbs" in out
    log_bench("2026-10-03", reps=6)
    out = AP.handle_message("next weight bench press") or ""
    assert out.startswith("bench press: Repeat 135 lbs.") and "a struggle, so repeat 135 lbs" in out
    log_bench("2026-10-05", reps=5)
    out = AP.handle_message("next weight bench press") or ""
    assert out.startswith("bench press: Drop to 120 lbs.") and "about 10% lighter" in out
    log_bench("2026-10-07", reps=8, rpe=7)
    assert (AP.handle_message("next weight bench press") or "").startswith("bench press: Try 140 lbs.")


@check("L2 3c: the library's other names are used, so a different spelling finds the same history")
def _():
    fresh()
    from agents.atlas import exercise_library as library
    ok, msg = library.add_entry({"name": "Bench press", "aliases": ["flat barbell press"], "steps": ["Lie down.", "Press up.", "Lower slowly."],
                                 "primary_muscles": ["chest"]})
    assert ok, msg
    log_bench("2026-10-01")
    out = AP.handle_message("next weight flat barbell press") or ""
    assert "Try 140 lbs." in out


@check("L2 3c: it works in chat with no model call, and a damaged fitness file is reported plainly")
def _():
    d = fresh()
    log_bench("2026-10-01")
    out = run("next weight bench press")
    assert out.startswith("bench press: Try 140 lbs.") and CHAT_CALLS == []
    assert run("what is my next weight for bench press") == "CHAT TEXT"
    with open(os.path.join(d, "fitness.json"), "w", encoding="utf-8") as f:
        f.write("{not json")
    assert "can't read or write your profile or workout files" in run("next weight bench press")


@check("L4 3c: 20 'next weight' reads while 4 logged workouts are approved at the same moment: no crash, final answer correct")
def _():
    fresh()
    ids = [A.propose_workout_block(bench_block(f"2026-10-0{i + 1}", 8, 7))[0] for i in range(4)]
    outs, errors = [], []

    def read_it():
        try:
            for _i in range(5):
                outs.append(AP.handle_message("next weight bench press"))
        except Exception as e:
            errors.append(repr(e))

    def approve(aid):
        try:
            A.approve_and_execute(aid)
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=read_it) for _i in range(20)] + [threading.Thread(target=approve, args=(a,)) for a in ids]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors[:2]
    assert all(o is not None and o.startswith("bench press:") for o in outs)
    assert (AP.handle_message("next weight bench press") or "").startswith("bench press: Try 140 lbs.")

passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
shutil.rmtree(_QUEUE_DIR, ignore_errors=True)
raise SystemExit(0 if passed == len(_results) else 1)