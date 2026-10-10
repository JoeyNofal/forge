"""
ATLAS workout template, increment 1b - L1, L2, L4, L5 tests: turning a parsed
workout block into a proposal, and saving it only after approval.
No model, no keys, no cost. TEMP files only: your real fitness.json and
pending_actions.json are never touched. (L3, the real-model pass, does not
apply: nothing here talks to a model.)

Run from the repo root:  python -m agents.atlas.test_workout_log
"""
import copy
import json
import os
import random
import re
import shutil
import tempfile
import threading
from typing import Any, Optional

# Point the approval queue at a throwaway file BEFORE importing anything that reads it.
_QUEUE_DIR = tempfile.mkdtemp(prefix="workout_log_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from agents.atlas import atlas_actions as A
from agents.atlas import atlas_logging as log
from agents.atlas import atlas_tools as t
from agents.atlas import workout_block as W
from shared import pending_actions as pa

_ROOT = t._REPO_ROOT
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
    """Brand-new fitness file path AND an empty queue."""
    d = tempfile.mkdtemp(prefix="workout_log_test_")
    os.environ["FITNESS_DATA_PATH"] = os.path.join(d, "fitness.json")
    if os.path.exists(QUEUE):
        os.remove(QUEUE)
    return os.environ["FITNESS_DATA_PATH"], d


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_raw(path, obj):
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


def source(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def make_block(title="Chest workout", header_unit: Optional[str] = "Unit: lbs",
               main_sets=("Set 1: 10 reps | 10 lbs", "Set 2: 8 reps | 10 lbs"),
               warm_sets=("Set 1: 20 reps | bodyweight",),
               presc="2x10 | weight: 10 lbs | rest: 2 min | target RPE: 7"):
    lines = ["FORGE WORKOUT LOG v1", f"Title: {title}", "Date: 2026-10-01"]
    if header_unit:
        lines.append(header_unit)
    lines += ["", "## Warmup", "Exercise: Windmill arms",
              "Prescribed: 1x20 per arm | weight: bodyweight | rest: 30 sec | target RPE: 5",
              *warm_sets, "RPE: 5", "Notes: my shoulders click", "",
              "## Upper chest", "Exercise: Incline DB press", "Prescribed: " + presc,
              *main_sets, "RPE: 8", "Notes:"]
    return "\n".join(lines)


def norm(text):
    return log.normalize_workout_block(W.parse_workout_block(text))


# ---------------- L1 static ----------------
ACTIONS_SRC = source("agents", "atlas", "atlas_actions.py")
LOGGING_SRC = source("agents", "atlas", "atlas_logging.py")


@check("L1 static: only the gate's handler calls the writer; propose never saves")
def _():
    assert ACTIONS_SRC.count("log.log_workout_block(") == 1
    assert ACTIONS_SRC.index("log.log_workout_block(") > ACTIONS_SRC.index("def _run_workout_block")
    start = ACTIONS_SRC.index("def propose_workout_block")
    end = ACTIONS_SRC.index("def propose_injury_update")
    body = ACTIONS_SRC[start:end]
    assert "log_workout_block" not in body and "approve_and_execute" not in body


@check("L1 static: the writer module does not import the block reader; no secrets or old paths")
def _():
    assert "import workout_block" not in LOGGING_SRC and "agents.atlas.workout_block" not in LOGGING_SRC
    for src in (ACTIONS_SRC, LOGGING_SRC):
        assert not re.search(r"(api[_-]?key|sk-[A-Za-z0-9]|AIza|NEXUS SYSTEM)", src, re.I)


# ---------------- L2 smoke ----------------
@check("L2 your scenario becomes the exact saved shape")
def _():
    c = norm(make_block())
    assert c["type"] == "gym" and c["source"] == "workout_block" and c["title"] == "Chest workout"
    assert c["date"] == "2026-10-01" and len(c["block_hash"]) == 16
    assert c["duration_minutes"] is None and c["difficulty_1_to_10"] is None
    assert "warnings" not in c and "units_assumed" not in c
    assert c["cooldown"] == [] and c["skipped"] == []
    wm = c["warmup"][0]
    assert (wm["name"], wm["section"], wm["sets"], wm["reps"], wm["weight_lbs"], wm["rpe"]) == ("Windmill arms", "Warmup", 1, 20, None, 5)
    assert wm["notes"] == "my shoulders click" and wm["set_details"][0]["bodyweight"] is True
    inc = c["exercises"][0]
    assert (inc["name"], inc["section"], inc["sets"], inc["reps"], inc["weight_lbs"], inc["rpe"]) == ("Incline DB press", "Upper chest", 2, 10, 10, 8)
    assert [(d["set"], d["reps"], d["weight_lbs"]) for d in inc["set_details"]] == [(1, 10, 10), (2, 8, 10)]
    p = inc["prescribed"]
    assert (p["sets"], p["reps"], p["weight_lbs"], p["rest_seconds"], p["target_rpe"]) == (2, 10, 10, 120, 7)


@check("L2 kg is converted to pounds in Python (sets and prescribed), explicit kg beats a lbs header")
def _():
    c = norm(make_block(header_unit="Unit: kg", main_sets=("Set 1: 5 reps | 100",), presc="2x10 | weight: 50 kg"))
    inc = c["exercises"][0]
    assert inc["weight_lbs"] == 220.46 and inc["set_details"][0]["weight_lbs"] == 220.46
    assert inc["prescribed"]["weight_lbs"] == 110.23
    c = norm(make_block(main_sets=("Set 1: 5 reps | 60 kg",)))
    assert c["exercises"][0]["weight_lbs"] == 132.28


@check("L2 old fields: heaviest set wins, bodyweight uses most reps, timed sets leave reps empty")
def _():
    c = norm(make_block(main_sets=("Set 1: 10 reps | 100 lbs", "Set 2: 5 reps | 120 lbs", "Set 3: 8 reps | 120 lbs")))
    e = c["exercises"][0]
    assert (e["sets"], e["weight_lbs"], e["reps"]) == (3, 120, 8)
    c = norm(make_block(main_sets=("Set 1: 12 reps | bodyweight", "Set 2: 15 reps | bodyweight", "Set 3: 10 reps | bodyweight")))
    e = c["exercises"][0]
    assert (e["sets"], e["weight_lbs"], e["reps"]) == (3, None, 15)
    c = norm(make_block(main_sets=("Set 1: 30 sec | bodyweight", "Set 2: 45 sec |")))
    e = c["exercises"][0]
    assert (e["sets"], e["weight_lbs"], e["reps"]) == (2, None, None)
    assert [d["seconds"] for d in e["set_details"]] == [30, 45]


@check("L2 skipped exercises are listed, not saved as done; everything skipped is refused")
def _():
    c = norm(make_block(main_sets=("Set 1: |", "Set 2:")))
    assert c["exercises"] == [] and c["skipped"] == ["Incline DB press"] and len(c["warmup"]) == 1
    assert raises(lambda: norm(make_block(main_sets=("Set 1: |",), warm_sets=("Set 1: |",))), ValueError)


@check("L2 proposal-only notes: units_assumed and warnings appear on the clean record")
def _():
    c = norm(make_block(header_unit=None, main_sets=("Set 1: 8 reps | 25", "Set 2: lots | 5 lbs")))
    assert c["units_assumed"] == ["Incline DB press"] and c["warnings"]
    c = norm(make_block(header_unit="Unit: kg", main_sets=("Set 1: 5 reps | 3000",)))
    e = c["exercises"][0]
    assert e["weight_lbs"] is None and e["reps"] == 5 and any("too large" in w for w in c["warnings"])


@check("L2 the duplicate fingerprint: same workout same hash (even with Windows line ends), any change differs")
def _():
    a = norm(make_block())["block_hash"]
    assert a == norm(make_block().replace("\n", "\r\n"))["block_hash"]
    assert a != norm(make_block(title="Other"))["block_hash"]
    assert a != norm(make_block(main_sets=("Set 1: 10 reps | 10 lbs", "Set 2: 9 reps | 10 lbs")))["block_hash"]


@check("L2 describe: readable line with title, date, names, top-set weights, skipped, assumed units")
def _():
    s = A.describe("log_workout_block", norm(make_block()))
    for part in ("Chest workout", "2026-10-01", "Incline DB press", "1 warmup", "0 cooldown", "weights: Incline DB press 10 lbs"):
        assert part in s, (part, s)
    s = A.describe("log_workout_block", norm(make_block(main_sets=("Set 1: |",))))
    assert "skipped: Incline DB press" in s
    s = A.describe("log_workout_block", norm(make_block(header_unit=None, main_sets=("Set 1: 8 reps | 25",))))
    assert "(unit assumed)" in s
    assert A.describe("log_workout_block", {"bad": 1}).startswith("log_workout_block:")


@check("L2 propose: queued with zero effect on the fitness file, tells you nothing is saved")
def _():
    path, _d = fresh()
    aid, msg = A.propose_workout_block(make_block())
    assert "Nothing is saved until you approve" in msg and aid in msg and "Incline DB press" in msg
    assert t.load_fitness_data()["workouts"] == []
    assert len(pa.list_pending_actions("atlas")) == 1


@check("L2 propose shows a short 'heads up' for lines it could not read")
def _():
    fresh()
    aid, msg = A.propose_workout_block(make_block(main_sets=("Set 1: 10 reps | 10 lbs", "Set 2: lots | 5 lbs")))
    assert "Heads up" in msg and "lots" in msg


@check("L2 approve saves exactly one workout with all the new fields, and no proposal-only notes")
def _():
    path, _d = fresh()
    aid, _msg = A.propose_workout_block(make_block(header_unit=None, main_sets=("Set 1: 8 reps | 25", "Set 2: lots | 5 lbs")))
    res = A.approve_and_execute(aid)
    assert res.startswith("Workout logged"), res
    data = read(path)
    assert len(data["workouts"]) == 1 and len(data["injuries"]) == 1
    w = data["workouts"][0]
    assert w["type"] == "gym" and w["id"] and w["logged_at"] and w["block_hash"]
    assert "warnings" not in w and "units_assumed" not in w
    assert w["exercises"][0]["set_details"][0]["reps"] == 8 and w["warmup"][0]["name"] == "Windmill arms"


@check("L2 the existing readers still work, and warmups do not appear as lifts")
def _():
    path, _d = fresh()
    A.approve_and_execute(A.propose_workout_block(make_block())[0])
    gym = t.get_gym_history()
    assert "Incline DB press" in gym and "Windmill arms" not in gym
    assert "Incline DB press" in t.get_recent_workouts(5)
    assert "Gym sessions: 1" in t.get_data_summary_for_llm()


@check("L2 duplicates: proposing again is refused; two proposals made first -> only the first saves")
def _():
    path, _d = fresh()
    A.approve_and_execute(A.propose_workout_block(make_block())[0])
    aid, msg = A.propose_workout_block(make_block())
    assert aid is None and "already logged" in msg
    path, _d = fresh()
    id1 = A.propose_workout_block(make_block())[0]
    id2 = A.propose_workout_block(make_block())[0]
    assert A.approve_and_execute(id1).startswith("Workout logged")
    assert "already logged" in A.approve_and_execute(id2)
    assert len(read(path)["workouts"]) == 1


@check("L2 bad input fails loudly and queues nothing")
def _():
    fresh()
    assert raises(lambda: A.propose_workout_block("I did chest today"), W.BlockError)
    assert raises(lambda: A.propose_workout_block(None), TypeError)
    assert raises(lambda: log.normalize_workout_block("x"), (ValueError, TypeError))
    assert raises(lambda: log.normalize_workout_block({"sections": "no"}), ValueError)
    assert raises(lambda: log.normalize_workout_block({"sections": [None, "x", {"exercises": "y"}]}), ValueError)
    assert raises(lambda: log.log_workout_block("x"), (ValueError, TypeError))
    assert raises(lambda: log.log_workout_block({"source": "other", "block_hash": "x"}), ValueError)
    assert raises(lambda: log.log_workout_block({"source": "workout_block", "block_hash": "x", "exercises": "no"}), ValueError)
    assert pa.list_pending_actions("atlas") == []


@check("L2 normalizing never changes the parsed data it was given")
def _():
    parsed = W.parse_workout_block(make_block())
    before = copy.deepcopy(parsed)
    log.normalize_workout_block(parsed)
    assert parsed == before


# ---------------- L4 sustained / concurrency ----------------
@check("L4 100 normalizations of the same block are identical")
def _():
    first = norm(make_block())
    for _i in range(100):
        assert norm(make_block()) == first


@check("L4 20 different workouts approved at the same moment: exactly 20 saved, none lost")
def _():
    path, _d = fresh()
    ids = [A.propose_workout_block(make_block(title=f"W{i}"))[0] for i in range(20)]
    out, errors = [], []

    def go(i):
        try:
            out.append(A.approve_and_execute(ids[i]))
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go, args=(i,)) for i in range(20)]
    [th.start() for th in threads]
    [th.join() for th in threads]
    data = read(path)
    assert not errors, errors[:2]
    assert len(data["workouts"]) == 20 and len({w["id"] for w in data["workouts"]}) == 20
    assert all(r.startswith("Workout logged") for r in out)


@check("L4 one proposal approved by 20 threads: saved exactly once")
def _():
    path, _d = fresh()
    aid = A.propose_workout_block(make_block())[0]
    out = []
    threads = [threading.Thread(target=lambda: out.append(A.approve_and_execute(aid))) for _i in range(20)]
    [th.start() for th in threads]
    [th.join() for th in threads]
    assert sum(1 for r in out if r.startswith("Workout logged")) == 1
    assert len(read(path)["workouts"]) == 1


@check("L4 20 separate proposals of the SAME workout approved at once: the duplicate guard saves exactly one")
def _():
    path, _d = fresh()
    ids = [A.propose_workout_block(make_block())[0] for _i in range(20)]
    out = []
    threads = [threading.Thread(target=lambda i=i: out.append(A.approve_and_execute(ids[i]))) for i in range(20)]
    [th.start() for th in threads]
    [th.join() for th in threads]
    assert sum(1 for r in out if r.startswith("Workout logged")) == 1
    assert sum(1 for r in out if "already logged" in r) == 19
    assert len(read(path)["workouts"]) == 1


# ---------------- L5 extreme / breaking ----------------
@check("L5 'workouts' that is not a list: fails loudly and the file is byte-for-byte unchanged")
def _():
    path, _d = fresh()
    write_raw(path, {"workouts": "oops", "injuries": []})
    before = raw_bytes(path)
    clean = norm(make_block())
    assert raises(lambda: log.log_workout_block(clean), RuntimeError)
    assert raw_bytes(path) == before


@check("L5 corrupt JSON file: fails loudly and the file is untouched")
def _():
    path, _d = fresh()
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json")
    before = raw_bytes(path)
    clean = norm(make_block())
    assert raises(lambda: log.log_workout_block(clean), Exception)
    assert raw_bytes(path) == before


@check("L5 junk already in the workouts list is preserved and the new workout is still added")
def _():
    path, _d = fresh()
    junk = ["junk", None, {"type": "swim"}, 5]
    write_raw(path, {"workouts": junk, "injuries": []})
    ok, msg = log.log_workout_block(norm(make_block()))
    assert ok, msg
    w = read(path)["workouts"]
    assert len(w) == 5 and w[:4] == junk


@check("L5 a big workout (90 exercises) is proposed, approved and read back")
def _():
    path, _d = fresh()
    lines = ["FORGE WORKOUT LOG v1", "Title: Big", "Date: 2026-10-01", "Unit: lbs"]
    for s in "ABC":
        lines.append(f"## Main {s}")
        for e in range(30):
            lines += [f"Exercise: E{s}{e}", "Set 1: 5 reps | 20 lbs"]
    aid, _msg = A.propose_workout_block("\n".join(lines))
    assert A.approve_and_execute(aid).startswith("Workout logged")
    assert len(read(path)["workouts"][0]["exercises"]) == 90


@check("L5 unicode and emoji survive the whole trip through the file")
def _():
    path, _d = fresh()
    text = ("FORGE WORKOUT LOG v1\nTitle: Br\u00fcst \U0001F4AA\n## A\nExercise: Pull-ups \U0001F525\n"
            "Set 1: 5 reps | bodyweight\nNotes: \u00e9cole \u4e2d\u6587")
    A.approve_and_execute(A.propose_workout_block(text)[0])
    w = read(path)["workouts"][0]
    assert w["title"] == "Br\u00fcst \U0001F4AA" and w["exercises"][0]["name"] == "Pull-ups \U0001F525"
    assert w["exercises"][0]["notes"] == "\u00e9cole \u4e2d\u6587"


@check("L5 200 randomly damaged blocks: a clean record or a ValueError, never any other crash")
def _():
    rng = random.Random(11)
    base = make_block()
    for _i in range(200):
        chars = list(base)
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
            c = norm("".join(chars))
        except ValueError:
            continue
        json.dumps(c)
        assert isinstance(c["exercises"], list) and isinstance(c["warmup"], list) and len(c["block_hash"]) == 16


@check("L5 a 20,000+ character paste is refused cleanly")
def _():
    fresh()
    assert raises(lambda: A.propose_workout_block("FORGE WORKOUT LOG v1\n" + "x" * 20500), W.BlockError)
    assert pa.list_pending_actions("atlas") == []


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
shutil.rmtree(_QUEUE_DIR, ignore_errors=True)
raise SystemExit(0 if passed == len(_results) else 1)