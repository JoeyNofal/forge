"""
ATLAS increment (b), Part 2 — L1, L2, L4, L5 tests for atlas_actions.py
(the approval gate in front of every fitness-data write). No model, no keys,
no cost. TEMP files only: your real fitness.json and pending_actions.json
are never touched.

Run from the repo root:  python -m agents.atlas.test_atlas_actions
"""
import json
import os
import re
import shutil
import tempfile
import threading

# Point the approval queue at a throwaway file BEFORE importing anything that
# reads it (the queue path is read once, at import time).
_QUEUE_DIR = tempfile.mkdtemp(prefix="atlas_actions_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from agents.atlas import atlas_actions as A
from agents.atlas import atlas_tools as t
from shared import pending_actions as pa

SRC = os.path.join(t._REPO_ROOT, "agents", "atlas", "atlas_actions.py")
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
    d = tempfile.mkdtemp(prefix="atlas_actions_test_")
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


def raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    return False


def status_of(action_id):
    """Status of a queued action ('missing' if it isn't there)."""
    a = pa.get_pending_action(action_id)
    return a["status"] if a else "missing"


def queue_actions():
    return read(QUEUE)["actions"] if os.path.exists(QUEUE) else []


def swim(**kw):
    d = {"total_distance_yards": 2000, "duration_minutes": 45, "strokes": ["freestyle"]}
    d.update(kw)
    return d


GYM = {"exercises": [{"name": "bench press", "sets": 3, "reps": 8, "weight_lbs": 135}], "duration_minutes": 50}


# ───────────────────────── L1 — STATIC ─────────────────────────

with open(SRC, encoding="utf-8") as _f:
    _src = _f.read()


def _function_source(name):
    m = re.search(rf"^def {name}\(.*?(?=^def |\Z)", _src, re.S | re.M)
    assert m, name
    return m.group(0)


@check("L1 proposing never writes: no propose_* function touches a writer")
def _():
    for fn in ("_propose", "propose_swim", "propose_gym", "propose_injury", "propose_injury_update"):
        body = _function_source(fn)
        assert "log.log_" not in body and "update_injury_status" not in body, fn


@check("L1 only approve_and_execute calls the real writers")
def _():
    callers = [fn for fn in re.findall(r"^def (\w+)\(", _src, re.M)
               if "log.log_" in _function_source(fn) or "log.update_injury_status" in _function_source(fn)]
    assert callers == ["approve_and_execute"], callers


@check("L1 approval uses the atomic claim/finalize pair; no bare 'except:'; no secrets or old paths")
def _():
    body = _function_source("approve_and_execute")
    assert "claim_action" in body and "finalize_action" in body
    assert not re.search(r"except\s*:", _src)
    assert "NEXUS SYSTEM" not in _src and "API_KEY" not in _src
    assert not re.search(r"\bopen\(", _src)


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 propose changes NOTHING in the fitness file; the proposal is queued with clean data")
def _():
    path, d = fresh()
    aid, msg = A.propose_swim(swim(total_distance_yards="2000", strokes="Freestyle"))
    assert not os.path.exists(path)                       # not even created
    assert "Nothing is saved until you approve" in msg and aid in msg and "2000 yards" in msg
    q = queue_actions()
    assert len(q) == 1 and q[0]["agent"] == "atlas" and q[0]["status"] == "pending"
    assert q[0]["details"]["strokes"] == ["freestyle"] and q[0]["details"]["total_distance_yards"] == 2000
    shutil.rmtree(d)


@check("L2 approve saves exactly one record, marks the action executed, and the readers see it")
def _():
    path, d = fresh()
    aid, _ = A.propose_gym(GYM)
    out = A.approve_and_execute(aid)
    assert "Gym workout logged" in out, out
    assert len(read(path)["workouts"]) == 1
    assert status_of(aid) == "executed"
    assert "bench press" in t.get_gym_history()
    shutil.rmtree(d)


@check("L2 deny saves nothing, marks it denied, and a denied action can never be approved later")
def _():
    path, d = fresh()
    aid, _ = A.propose_swim(swim())
    out = A.deny_action(aid)
    assert out.startswith("Denied: log swim")
    assert not os.path.exists(path)
    assert status_of(aid) == "denied"
    assert "already denied" in A.approve_and_execute(aid)
    assert not os.path.exists(path)
    shutil.rmtree(d)


@check("L2 approving twice saves only once; the second try is told it's already executed")
def _():
    path, d = fresh()
    aid, _ = A.propose_swim(swim())
    A.approve_and_execute(aid)
    again = A.approve_and_execute(aid)
    assert "already executed" in again
    assert len(read(path)["workouts"]) == 1
    assert "already executed" in A.deny_action(aid)
    shutil.rmtree(d)


@check("L2 a short unique start of the id works (6+ chars); too short or unknown does not")
def _():
    path, d = fresh()
    aid, _ = A.propose_swim(swim())
    assert "No pending action" in A.approve_and_execute(aid[:5])
    assert "No pending action" in A.approve_and_execute("zzzzzzzz")
    assert not os.path.exists(path)                       # the failed attempts saved nothing
    out = A.approve_and_execute(aid[:8])
    assert "Swim logged" in out, out
    assert len(read(path)["workouts"]) == 1
    shutil.rmtree(d)


@check("L2 an ambiguous id start never guesses")
def _():
    path, d = fresh()
    os.makedirs(os.path.dirname(QUEUE), exist_ok=True)
    base = {"agent": "atlas", "type": "log_swim", "details": {}, "status": "pending", "result": None,
            "created_at": "x", "resolved_at": None}
    write_raw(QUEUE, {"actions": [dict(base, id="abcdef11-aaaa"), dict(base, id="abcdef22-bbbb")]})
    out = A.approve_and_execute("abcdef")
    assert "more than one" in out
    assert all(a["status"] == "pending" for a in queue_actions())
    shutil.rmtree(d)


@check("L2 ATLAS can't approve or deny another agent's action")
def _():
    path, d = fresh()
    other = pa.create_pending_action("cipher", "create_file", {"path": "x", "content": "y"})
    assert "doesn't belong to ATLAS" in A.approve_and_execute(other)
    assert "doesn't belong to ATLAS" in A.deny_action(other)
    assert status_of(other) == "pending"
    assert A.list_pending() == "Nothing waiting for approval."
    shutil.rmtree(d)


@check("L2 bad data is rejected at PROPOSAL time and never enters the queue")
def _():
    path, d = fresh()
    for fn, bad in ((A.propose_swim, {}), (A.propose_swim, None), (A.propose_gym, {"exercises": []}),
                    (A.propose_injury, {}), (A.propose_injury_update, {"body_part": "knee", "new_status": "healed"})):
        assert raises(lambda f=fn, b=bad: f(b), ValueError), (fn.__name__, bad)
    assert queue_actions() == []
    shutil.rmtree(d)


@check("L2 injury log + 'my shoulder is better now' update, both through approval")
def _():
    path, d = fresh()
    aid, _ = A.propose_injury({"body_part": "shoulder", "description": "left shoulder pinch", "severity": "moderate"})
    A.approve_and_execute(aid)
    uid, msg = A.propose_injury_update({"body_part": "shoulder", "new_status": "recovering", "notes": "better"})
    assert uid and "shoulder -> recovering" in msg
    assert [i for i in read(path)["injuries"] if i.get("body_part") == "shoulder"][0]["status"] == "active"   # not yet
    out = A.approve_and_execute(uid)
    assert "active → recovering" in out, out
    assert [i for i in read(path)["injuries"] if i.get("body_part") == "shoulder"][0]["status"] == "recovering"
    shutil.rmtree(d)


@check("L2 an update that can't work is never queued: no match / several matches")
def _():
    path, d = fresh()
    log_ids = [A.propose_injury({"body_part": "left shoulder", "description": "left shoulder pinch"})[0],
               A.propose_injury({"body_part": "right shoulder", "description": "right shoulder ache"})[0]]
    for i in log_ids:
        A.approve_and_execute(i)
    before = len(queue_actions())
    aid, msg = A.propose_injury_update({"body_part": "shoulder", "new_status": "resolved"})
    assert aid is None and "More than one" in msg
    aid, msg = A.propose_injury_update({"body_part": "wrist", "new_status": "resolved"})
    assert aid is None and "No open injury" in msg
    assert len(queue_actions()) == before
    shutil.rmtree(d)


@check("L2 an update whose injury got resolved before approval fails cleanly and is recorded as failed")
def _():
    path, d = fresh()
    A.approve_and_execute(A.propose_injury({"body_part": "knee", "description": "sore knee"})[0])
    u1, _ = A.propose_injury_update({"body_part": "knee", "new_status": "resolved"})
    u2, _ = A.propose_injury_update({"body_part": "knee", "new_status": "recovering"})
    assert u1 and u2
    assert "active → resolved" in A.approve_and_execute(u1)
    out = A.approve_and_execute(u2)
    assert "No open injury" in out
    assert status_of(u2) == "failed"
    shutil.rmtree(d)


@check("L2 list_pending shows only ATLAS's pending items and drops resolved ones")
def _():
    path, d = fresh()
    a, _ = A.propose_swim(swim())
    b, _ = A.propose_gym(GYM)
    text = A.list_pending()
    assert a in text and b in text and "log swim" in text and "log gym workout" in text
    A.deny_action(a)
    text = A.list_pending()
    assert a not in text and b in text
    shutil.rmtree(d)


@check("L2 proposals say 'not stated' for anything Joey didn't give (never a made-up 0 min or 5/10)")
def _():
    path, d = fresh()
    _, msg = A.propose_gym({"exercises": ["squat"]})
    assert "duration not stated" in msg and "difficulty not stated" in msg and "0 min" not in msg and "5/10" not in msg
    _, msg = A.propose_swim({"total_distance_yards": 1000})
    assert "1000 yards" in msg and "duration not stated" in msg and "difficulty not stated" in msg
    _, msg = A.propose_gym({"exercises": ["squat"], "duration_minutes": 45, "difficulty": 8})
    assert "45 min" in msg and "difficulty 8/10" in msg
    shutil.rmtree(d)


@check("L2 describe never crashes on junk details")
def _():
    for t_, d_ in (("log_swim", None), ("log_gym", {}), ("log_injury", "x"), ("update_injury", []), ("weird", 5)):
        assert isinstance(A.describe(t_, d_), str)  # type: ignore


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 threads approving the SAME action: exactly one record is saved, 19 are turned away")
def _():
    path, d = fresh()
    aid, _ = A.propose_swim(swim())
    results, lock = [], threading.Lock()

    def go():
        r = A.approve_and_execute(aid)
        with lock:
            results.append(r)

    threads = [threading.Thread(target=go) for _ in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    saved = [r for r in results if r.startswith("Swim logged")]
    assert len(saved) == 1, results
    assert len(read(path)["workouts"]) == 1
    assert status_of(aid) == "executed"
    shutil.rmtree(d)


@check("L4 20 simultaneous proposals: 20 distinct pending actions, none lost, fitness file untouched")
def _():
    path, d = fresh()
    ids, errors, lock = [], [], threading.Lock()

    def go(n):
        try:
            aid, _ = A.propose_swim(swim(total_distance_yards=100 + n))
            with lock:
                ids.append(aid)
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go, args=(n,)) for n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert not errors, errors
    assert len(set(ids)) == 20 and len(queue_actions()) == 20
    assert not os.path.exists(path)
    shutil.rmtree(d)


@check("L4 20 different actions approved at the same time: all 20 saved, none lost or doubled")
def _():
    path, d = fresh()
    ids = [A.propose_swim(swim(total_distance_yards=100 + n))[0] for n in range(20)]
    results, lock = [], threading.Lock()

    def go(aid):
        r = A.approve_and_execute(aid)
        with lock:
            results.append(r)

    threads = [threading.Thread(target=go, args=(i,)) for i in ids]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert all(r.startswith("Swim logged") for r in results), results
    w = read(path)["workouts"]
    assert len(w) == 20 and len({x["id"] for x in w}) == 20
    assert all(a["status"] == "executed" for a in queue_actions())
    shutil.rmtree(d)


@check("L4 100 propose-and-approve cycles in a row stay correct")
def _():
    path, d = fresh()
    for n in range(100):
        aid, _ = A.propose_gym({"exercises": [f"ex{n}"]})
        assert "Gym workout logged" in A.approve_and_execute(aid)
    assert len(read(path)["workouts"]) == 100
    shutil.rmtree(d)


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 fitness file corrupt at approval time: action is marked failed, file left exactly as it was")
def _():
    path, d = fresh()
    aid, _ = A.propose_swim(swim())
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"workouts": [ {"broken"')
    before = raw_bytes(path)
    out = A.approve_and_execute(aid)
    assert out.startswith("Execution failed"), out
    assert status_of(aid) == "failed"
    assert raw_bytes(path) == before
    shutil.rmtree(d)


@check("L5 hand-damaged queue entries (junk details, unknown type) fail cleanly, never crash or write")
def _():
    path, d = fresh()
    os.makedirs(os.path.dirname(QUEUE), exist_ok=True)
    base = {"agent": "atlas", "status": "pending", "result": None, "created_at": "x", "resolved_at": None}
    write_raw(QUEUE, {"actions": [dict(base, id="junk-1", type="log_swim", details="not a dict"),
                                  dict(base, id="junk-2", type="log_gym", details={"exercises": []}),
                                  dict(base, id="junk-3", type="delete_everything", details={})]})
    for aid in ("junk-1", "junk-2", "junk-3"):
        out = A.approve_and_execute(aid)
        assert out.startswith("Execution failed") or out.startswith("Unknown action type"), (aid, out)
    q = {a["id"]: a for a in queue_actions()}
    assert all(q[i]["status"] == "failed" for i in q), q
    assert not os.path.exists(path) or read(path)["workouts"] == []
    shutil.rmtree(d)


@check("L5 corrupt queue file: proposing fails LOUDLY and writes nothing to the fitness file")
def _():
    path, d = fresh()
    os.makedirs(os.path.dirname(QUEUE), exist_ok=True)
    with open(QUEUE, "w", encoding="utf-8") as f:
        f.write("{not json")
    assert raises(lambda: A.propose_swim(swim()), Exception)
    assert not os.path.exists(path)
    os.remove(QUEUE)
    shutil.rmtree(d)


@check("L5 empty / None / number / whitespace / regex-special ids never crash or approve anything")
def _():
    path, d = fresh()
    A.propose_swim(swim())
    for bad in ("", "   ", None, 123, [], "a.*b", "[", "\\", "x" * 10000):
        for fn in (A.approve_and_execute, A.deny_action):
            out = fn(bad)  # type: ignore
            assert isinstance(out, str) and ("No " in out), (fn.__name__, bad, out)
    assert not os.path.exists(path)
    assert all(a["status"] == "pending" for a in queue_actions())
    shutil.rmtree(d)


@check("L5 50,000-character text and unicode/emoji survive propose -> approve intact (cut to 1,000)")
def _():
    path, d = fresh()
    aid, _ = A.propose_swim(swim(coach_notes="Schwimmen 泳ぐ 🏊‍♂️ résumé", form_notes="x" * 50000))
    A.approve_and_execute(aid)
    w = read(path)["workouts"][0]
    assert w["coach_notes"] == "Schwimmen 泳ぐ 🏊‍♂️ résumé" and len(w["form_notes"]) == 1000
    shutil.rmtree(d)


passed = sum(1 for _, ok, _ in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
if passed != len(_results):
    raise SystemExit(1)