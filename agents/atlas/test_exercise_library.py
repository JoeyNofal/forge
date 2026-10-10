"""
ATLAS workout template, increment 2a - L1, L2, L4, L5 tests for the exercise
library store (agents/atlas/exercise_library.py) and its two approval actions.
No model, no keys, no cost. TEMP files only: your real library and approval
queue are never touched. (L3, the real-model pass, comes with 2b, when a model
actually drafts entries.)

Run from the repo root:  python -m agents.atlas.test_exercise_library
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

_QUEUE_DIR = tempfile.mkdtemp(prefix="exlib_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from agents.atlas import atlas_actions as A
from agents.atlas import exercise_library as L
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
    d = tempfile.mkdtemp(prefix="exlib_test_")
    os.environ["EXERCISE_LIBRARY_PATH"] = os.path.join(d, "exercise_library.json")
    if os.path.exists(QUEUE):
        os.remove(QUEUE)
    return os.environ["EXERCISE_LIBRARY_PATH"]


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


def draft(**over):
    d = {
        "name": "Incline DB press",
        "aliases": ["incline dumbbell bench press", "incline chest press"],
        "steps": ["Set the bench to 30 degrees.", "Press the dumbbells up over your upper chest.", "Lower them slowly."],
        "primary_muscles": ["upper chest"],
        "secondary_muscles": ["front delts", "triceps"],
        "common_mistakes": ["Flaring the elbows wide", "Bouncing the weights off the chest"],
        "equipment": ["dumbbells", "incline bench"],
    }
    d.update(over)
    return d


def add(**over):
    return L.add_entry(draft(**over))


def must_find(name):
    e = L.find_exercise(name)
    assert e is not None, name
    return e


with open(os.path.join(_HERE, "exercise_library.py"), encoding="utf-8") as f:
    SRC = f.read()
with open(os.path.join(_HERE, "atlas_actions.py"), encoding="utf-8") as f:
    ACTIONS_SRC = f.read()


# ---------------- L1 static ----------------
@check("L1 static: the store imports only the standard library and the two shared helpers (no model, network or web code)")
def _():
    tree = ast.parse(SRC)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    allowed = {"json", "os", "re", "time", "uuid", "datetime", "shared.file_store", "shared.normalizers"}
    assert imported <= allowed, imported
    assert "open(" not in SRC and "json.dump(" not in SRC     # every write goes through the locked helper
    assert not re.search(r"(api[_-]?key|sk-[A-Za-z0-9]|AIza|NEXUS SYSTEM)", SRC, re.I)


@check("L1 static: only the approval handlers write the library; the propose functions never do")
def _():
    assert ACTIONS_SRC.count("library.add_entry(") == 1 and ACTIONS_SRC.count("library.mark_reviewed(") == 1
    assert ACTIONS_SRC.index("library.add_entry(") > ACTIONS_SRC.index("def _run_add_exercise")
    assert ACTIONS_SRC.index("library.mark_reviewed(") > ACTIONS_SRC.index("def _run_mark_exercise_reviewed")
    body = ACTIONS_SRC[ACTIONS_SRC.index("def propose_add_exercise"):ACTIONS_SRC.index("def propose_injury_update")]
    assert "library.add_entry(" not in body and "library.mark_reviewed(" not in body and "approve_and_execute" not in body


# ---------------- L2 smoke: cleaning ----------------
@check("L2 names: DB/dumbbell, hyphens, case and spacing match; look-alikes do not; non-text gives ''")
def _():
    n = L.normalize_name
    assert n("Incline DB press") == n("incline dumbbell press") == "incline dumbbell press"
    assert n("Pull-ups") == n("pull ups") == "pull ups"
    assert n("  BENCH   press!! ") == "bench press"
    assert n("KB swing") == "kettlebell swing" and n("Dumbbells curl") == "dumbbell curl"
    assert n("pullups") != n("pull ups") and n("bench press") != n("benchpress")
    assert n("D\u00e9velop\u00e9") == "d\u00e9velop\u00e9"
    for bad in (None, 5, ["x"], b"x", "", "!!!"):
        assert n(bad) == ""
    assert len(n("x" * 100000)) == 200


@check("L2 a good draft becomes the exact clean entry, always AI-drafted")
def _():
    e = L.normalize_entry(draft(status="reviewed", id="evil", extra="ignored"))
    assert e == {
        "name": "Incline DB press",
        "aliases": ["incline dumbbell bench press", "incline chest press"],
        "steps": ["Set the bench to 30 degrees.", "Press the dumbbells up over your upper chest.", "Lower them slowly."],
        "primary_muscles": ["upper chest"],
        "secondary_muscles": ["front delts", "triceps"],
        "common_mistakes": ["Flaring the elbows wide", "Bouncing the weights off the chest"],
        "equipment": ["dumbbells", "incline bench"],
        "status": "ai_drafted",
    }


@check("L2 messy drafts: numbering stripped, strings and dicts accepted, duplicates and the name itself removed from other names")
def _():
    e = L.normalize_entry(draft(steps=["1. Do this", "Step 2: Do that", "- bullet", "10) Last", "2-3 deep breaths", "2.5 second pause"]))
    assert e["steps"] == ["Do this", "Do that", "bullet", "Last", "2-3 deep breaths", "2.5 second pause"]
    e = L.normalize_entry(draft(steps="1. First\n2. Second\n\n3. Third", primary_muscles="chest, triceps; core",
                                secondary_muscles=None, common_mistakes="Rushing\nArching"))
    assert e["steps"] == ["First", "Second", "Third"] and e["primary_muscles"] == ["chest", "triceps", "core"]
    assert e["secondary_muscles"] == [] and e["common_mistakes"] == ["Rushing", "Arching"]
    e = L.normalize_entry(draft(steps=[{"step": 1, "text": "Do this"}, {"step": "Then that"}, {"step": 3}, 5, None, True]))
    assert e["steps"] == ["Do this", "Then that"]
    e = L.normalize_entry(draft(aliases=["Incline DB Press", "incline dumbbell press", "Incline Dumbbell Press!", "x"]))
    assert e["aliases"] == ["x"]


@check("L2 drafts that are not usable are refused: no name, no steps, no primary muscle, not a dict")
def _():
    for bad in (draft(name=""), draft(name="!!!"), draft(name=None), draft(steps=[]), draft(steps="   "),
                draft(primary_muscles=[]), draft(primary_muscles=[None, 5])):
        assert raises(lambda b=bad: L.normalize_entry(b), ValueError)
    for bad in (None, "x", 5, [draft()]):
        assert raises(lambda b=bad: L.normalize_entry(b), (ValueError, TypeError))


# ---------------- L2 smoke: store ----------------
@check("L2 add then find: by name, by another name, with DB/dumbbell, case and spacing differences")
def _():
    path = fresh()
    ok, msg = add()
    assert ok and msg.startswith("Exercise added"), msg
    first = L.find_exercise("Incline DB press")
    assert first is not None and first["status"] == "ai_drafted" and first["reviewed_at"] is None
    assert first["id"] and first["created_at"]
    for q in ("incline dumbbell press", "  INCLINE   DB  PRESS ", "incline chest press", "Incline Dumbbell Bench Press"):
        found = L.find_exercise(q)
        assert found is not None and found["id"] == first["id"], q
    for q in ("decline press", "", None, 5, "!!!", "incline"):
        assert L.find_exercise(q) is None, q
    assert len(read(path)["exercises"]) == 1


@check("L2 duplicates are refused: same name, a name variant, a new name colliding with an old other name (and the reverse)")
def _():
    path = fresh()
    add()
    for over in (dict(), dict(name="Incline Dumbbell Press"), dict(name="Incline Chest Press", aliases=[]),
                 dict(name="Something else", aliases=["incline DB press"])):
        ok, msg = add(**over)
        assert not ok and "already in the library" in msg, (over, msg)
    assert len(read(path)["exercises"]) == 1


@check("L2 mark reviewed: sets status and time once; repeats, unknown ids and non-text ids change nothing")
def _():
    path = fresh()
    add()
    eid = must_find("incline db press")["id"]
    ok, msg = L.mark_reviewed(eid)
    assert ok and msg.startswith("Marked as reviewed"), msg
    e = must_find("Incline DB press")
    assert e["status"] == "reviewed" and e["reviewed_at"] and e["steps"][0].startswith("Set the bench")
    ok, msg = L.mark_reviewed(eid)
    assert not ok and "already marked as reviewed" in msg
    ok, msg = L.mark_reviewed("no-such-id")
    assert not ok and "no longer in the library" in msg
    for bad in (None, 5, ["x"], ""):
        ok, msg = L.mark_reviewed(bad)
        assert not ok and "could not be identified" in msg


@check("L2 format_entry: readable how-to with the right status label; junk fields never crash")
def _():
    text = L.format_entry(L.normalize_entry(draft()))
    for part in ("Incline DB press (AI-drafted, NOT yet reviewed)", "Targets: upper chest (also: front delts, triceps)",
                 "Equipment: dumbbells, incline bench", "1. Set the bench to 30 degrees.", "3. Lower them slowly.",
                 "Common mistakes:", "- Flaring the elbows wide"):
        assert part in text, part
    assert "reviewed by you" in L.format_entry({"name": "Squat", "status": "reviewed"})
    assert L.format_entry({"name": 5, "steps": "no", "primary_muscles": [None, 5]}).startswith("Unnamed exercise (AI-drafted")
    assert raises(lambda: L.format_entry("x"), ValueError)


@check("L2 reading never writes: a missing file means an empty library and no file is created")
def _():
    path = fresh()
    assert L.list_entries() == [] and L.find_exercise("squat") is None and L.find_conflict(draft()) is None
    assert not os.path.exists(path)


@check("L2 a hand-edited file with two entries answering to one name: lookup refuses to guess, adding is refused")
def _():
    path = fresh()
    write_raw(path, {"exercises": [{"id": "1", "name": "Squat"}, {"id": "2", "name": "squat", "aliases": ["back squat"]}]})
    assert raises(lambda: L.find_exercise("SQUAT"), ValueError)
    assert L.find_exercise("back squat") is not None
    ok, msg = add(name="Squat")
    assert not ok and "already in the library" in msg


# ---------------- L2 smoke: approval actions ----------------
@check("L2 propose add: shows you the whole how-to, saves nothing, creates no file")
def _():
    path = fresh()
    aid, msg = A.propose_add_exercise(draft())
    assert aid and "Nothing is saved until you approve" in msg
    for part in ("Targets: upper chest (also: front delts, triceps)", "1. Set the bench to 30 degrees.", "NOT yet reviewed"):
        assert part in msg, part
    assert not os.path.exists(path) and len(pending()) == 1


@check("L2 approving saves it; proposing it again, or one of its other names, says it is already there")
def _():
    path = fresh()
    aid, _m = A.propose_add_exercise(draft())
    assert A.approve_and_execute(aid).startswith("Exercise added")
    assert len(read(path)["exercises"]) == 1 and pending() == []
    for over in (dict(), dict(name="incline chest press", aliases=[])):
        new_id, msg = A.propose_add_exercise(draft(**over))
        assert new_id is None and "already in the library" in msg
    assert pending() == []


@check("L2 bad drafts raise and queue nothing")
def _():
    fresh()
    assert raises(lambda: A.propose_add_exercise(draft(steps=[])), ValueError)
    assert raises(lambda: A.propose_add_exercise("x"), (ValueError, TypeError))
    assert pending() == []


@check("L2 propose reviewed: needs an entry that exists and is not reviewed yet; approving marks it")
def _():
    path = fresh()
    aid, msg = A.propose_mark_reviewed("Deadlift")
    assert aid is None and "not in the exercise library" in msg
    assert A.propose_mark_reviewed(None)[0] is None
    A.approve_and_execute(A.propose_add_exercise(draft())[0])
    aid, msg = A.propose_mark_reviewed("incline dumbbell press")
    assert aid and "Nothing is saved until you approve" in msg and "Incline DB press" in msg
    assert must_find("incline db press")["status"] == "ai_drafted"          # a proposal changes nothing
    assert A.approve_and_execute(aid).startswith("Marked as reviewed")
    assert must_find("incline db press")["status"] == "reviewed"
    aid2, msg2 = A.propose_mark_reviewed("Incline DB press")
    assert aid2 is None and "already marked as reviewed" in msg2


@check("L2 reviewing an entry that was removed before you approved fails cleanly")
def _():
    path = fresh()
    A.approve_and_execute(A.propose_add_exercise(draft())[0])
    aid, _m = A.propose_mark_reviewed("Incline DB press")
    write_raw(path, {"exercises": []})
    assert "no longer in the library" in A.approve_and_execute(aid)


@check("L2 describe: readable one-liners, and odd data falls back instead of crashing")
def _():
    assert "Incline DB press" in A.describe("add_exercise", L.normalize_entry(draft()))
    assert "Squat" in A.describe("mark_exercise_reviewed", {"id": "x", "name": "Squat"})
    assert A.describe("add_exercise", {"bad": 1}).startswith("add_exercise:")


# ---------------- L4 sustained / concurrency ----------------
@check("L4 20 different exercises added at the same moment: exactly 20 saved, none lost, unique ids")
def _():
    path = fresh()
    outs, errors = [], []

    def go(i):
        try:
            outs.append(add(name=f"Exercise {chr(65 + i)}", aliases=[]))
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go, args=(i,)) for i in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    entries = read(path)["exercises"]
    assert not errors, errors[:2]
    assert len(entries) == 20 and len({e["id"] for e in entries}) == 20 and all(ok for ok, _m in outs)


@check("L4 20 threads adding the SAME exercise under different spellings: exactly one is saved")
def _():
    path = fresh()
    names = ["Incline DB press", "incline dumbbell press", "INCLINE  DB  PRESS"]
    outs = []
    threads = [threading.Thread(target=lambda i=i: outs.append(add(name=names[i % 3], aliases=[]))) for i in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(1 for ok, _m in outs if ok) == 1 and len(read(path)["exercises"]) == 1


@check("L4 one 'add' proposal approved by 20 threads: saved exactly once")
def _():
    path = fresh()
    aid = A.propose_add_exercise(draft())[0]
    outs = []
    threads = [threading.Thread(target=lambda: outs.append(A.approve_and_execute(aid))) for _i in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(1 for o in outs if o.startswith("Exercise added")) == 1 and len(read(path)["exercises"]) == 1


@check("L4 20 threads marking the same entry reviewed: exactly one succeeds")
def _():
    fresh()
    add()
    eid = must_find("incline db press")["id"]
    outs = []
    threads = [threading.Thread(target=lambda: outs.append(L.mark_reviewed(eid))) for _i in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(1 for ok, _m in outs if ok) == 1 and sum(1 for ok, m in outs if "already marked" in m) == 19


@check("L4 a 500-entry library: 50 lookups stay fast and correct")
def _():
    path = fresh()
    write_raw(path, {"exercises": [{"id": str(i), "name": f"Exercise {i}", "aliases": [f"alt {i}"], "status": "ai_drafted"} for i in range(500)]})
    t0 = time.time()
    for i in range(0, 500, 10):
        e = L.find_exercise(f"alt {i}")
        assert e is not None and e["id"] == str(i)
    assert time.time() - t0 < 3.0


# ---------------- L5 extreme / breaking ----------------
@check("L5 damaged JSON: reading fails loudly, adding fails, and the file is byte-for-byte untouched")
def _():
    path = fresh()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json")
    before = raw_bytes(path)
    assert raises(lambda: L.find_exercise("squat"), RuntimeError)
    assert raises(lambda: add(), Exception) and raw_bytes(path) == before


@check("L5 wrong shapes (a top-level list, 'exercises' not a list): fails loudly and never overwrites")
def _():
    for content in ([1, 2, 3], {"exercises": "oops"}):
        path = fresh()
        write_raw(path, content)
        before = raw_bytes(path)
        assert raises(lambda: L.list_entries(), RuntimeError)
        assert raises(lambda: add(), RuntimeError) and raw_bytes(path) == before


@check("L5 junk already in the list is preserved and ignored by lookups; the new entry is still added")
def _():
    path = fresh()
    junk = ["junk", None, 5, {"note": "no name"}]
    write_raw(path, {"exercises": junk, "other_key": 1})
    ok, msg = add()
    assert ok, msg
    data = read(path)
    assert data["exercises"][:4] == junk and len(data["exercises"]) == 5 and data["other_key"] == 1
    assert L.find_exercise("incline db press") is not None


@check("L5 a full library refuses new entries politely")
def _():
    path = fresh()
    write_raw(path, {"exercises": [{"id": str(i), "name": f"E{i}"} for i in range(L.MAX_ENTRIES)]})
    ok, msg = add()
    assert not ok and "full" in msg and len(read(path)["exercises"]) == L.MAX_ENTRIES


@check("L5 hostile drafts: giant text cut, 10,000 steps capped, control characters removed, odd types skipped")
def _():
    e = L.normalize_entry(draft(name="n" * 5000, steps=[f"step {i}" for i in range(10000)],
                                primary_muscles=["m" * 5000], common_mistakes=["x" * 5000] * 50,
                                aliases=[f"a{i}" for i in range(500)]))
    assert len(e["name"]) == L.MAX_NAME and len(e["steps"]) == L.MAX_STEPS
    assert len(e["primary_muscles"][0]) == L.MAX_MUSCLE and len(e["common_mistakes"]) == 1
    assert len(e["aliases"]) == L.MAX_ALIASES
    e = L.normalize_entry(draft(name="Squat\x00\x01", steps=["Do\tthis\nnow\x07"]))
    assert e["name"] == "Squat" and e["steps"] == ["Do this now"]


@check("L5 unicode and emoji survive the whole trip through the file")
def _():
    path = fresh()
    ok, msg = add(name="D\u00e9velop\u00e9 \U0001F4AA", steps=["\u4e2d\u6587 step \U0001F525"], aliases=[])
    assert ok, msg
    assert read(path)["exercises"][0]["name"] == "D\u00e9velop\u00e9 \U0001F4AA"
    assert L.find_exercise("d\u00e9velop\u00e9 \U0001F4AA") is not None


@check("L5 300 random hostile drafts: a clean entry or a ValueError, never any other crash")
def _():
    rng = random.Random(9)
    values = [None, 5, True, "", " ", "x", "a" * 500, "1. a\n2. b", [], ["a", None, {"text": "b"}], {"a": 1}, [[1]],
              1e308, float("nan"), "\x00\x01", "Bench press", "chest, back"]
    keys = ["name", "aliases", "steps", "primary_muscles", "secondary_muscles", "common_mistakes", "equipment", "status"]
    for _i in range(300):
        raw = {k: rng.choice(values) for k in keys if rng.random() < 0.8}
        try:
            e = L.normalize_entry(raw)
        except ValueError:
            continue
        json.dumps(e)
        assert e["status"] == "ai_drafted" and e["steps"] and e["primary_muscles"] and L.normalize_name(e["name"])


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
shutil.rmtree(_QUEUE_DIR, ignore_errors=True)
raise SystemExit(0 if passed == len(_results) else 1)