"""
DRIVE increment (b), Part 2 — L1, L2, L4, L5 tests for drive_actions.py
(the approval gate in front of every vehicle-data write). No model, no keys,
no cost. TEMP files only: your real vehicle.json and pending_actions.json
are never touched.

Run from the repo root:  python -m agents.drive.test_drive_actions
"""
import json
import os
import re
import shutil
import tempfile
import threading

# Point the approval queue at a throwaway file BEFORE importing anything that
# reads it (the queue path is read once, at import time).
_QUEUE_DIR = tempfile.mkdtemp(prefix="drive_actions_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from agents.drive import drive_actions as A
from agents.drive import drive_logging as Lg
from agents.drive import drive_tools as t
from shared import pending_actions as pa

SRC = os.path.join(t._REPO_ROOT, "agents", "drive", "drive_actions.py")
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
    """Brand-new vehicle file path (NOT created) AND an empty queue."""
    d = tempfile.mkdtemp(prefix="drive_actions_test_")
    os.environ["VEHICLE_DATA_PATH"] = os.path.join(d, "vehicle.json")
    if os.path.exists(QUEUE):
        os.remove(QUEUE)
    return os.environ["VEHICLE_DATA_PATH"], d


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
    a = pa.get_pending_action(action_id)
    return a["status"] if a else "missing"


def queue_actions():
    return read(QUEUE)["actions"] if os.path.exists(QUEUE) else []


def base_entry(**kw):
    d = {"agent": "drive", "status": "pending", "result": None, "created_at": "x", "resolved_at": None}
    d.update(kw)
    return d


def put_queue(*entries):
    os.makedirs(os.path.dirname(QUEUE), exist_ok=True)
    write_raw(QUEUE, {"actions": list(entries)})


def seed(path, **fields):
    v = {"id": "vehicle_001", "active": True, "make": "Honda", "model": "Civic", "year": 2016,
         "vin": "TESTVIN", "current_mileage": 55500, "mileage_last_updated": None,
         "maintenance_log": [], "upcoming_maintenance": [], "gas_log": [], "issues": [], "recalls": []}
    v.update(fields)
    write_raw(path, {"vehicles": [v]})


def vehicle(path):
    return read(path)["vehicles"][0]


def fill(**kw):
    d = {"gallons": 10, "price_per_gallon": 3.0, "mileage": 50300}
    d.update(kw)
    return d


# ───────────────────────── L1 — STATIC ─────────────────────────

with open(SRC, encoding="utf-8") as _f:
    _src = _f.read()


def _function_source(name):
    m = re.search(rf"^def {name}\(.*?(?=^def |\Z)", _src, re.S | re.M)
    assert m, name
    return m.group(0)


@check("L1 proposing (and the read-only helpers) never write: none of them touches a writer")
def _():
    for fn in ("_propose", "propose_mileage", "propose_maintenance", "propose_fillup", "propose_issue",
               "propose_issue_update", "_current_mileage", "_mileage_warnings", "_issues_readonly"):
        body = _function_source(fn)
        assert "log.log_" not in body and "update_issue_status" not in body, fn


@check("L1 only the _run_* handlers call the real writers (and only the shared gate ever calls them)")
def _():
    callers = [fn for fn in re.findall(r"^def (\w+)\(", _src, re.M)
               if "log.log_" in _function_source(fn) or "log.update_issue_status" in _function_source(fn)]
    assert callers and all(fn.startswith("_run_") for fn in callers), callers
    assert "log.log_" not in _function_source("approve_and_execute")


@check("L1 approval uses the atomic claim/finalize pair; no bare 'except:'; no secrets, old paths or raw open()")
def _():
    body = _function_source("approve_and_execute")
    assert "_gate.approve_and_execute" in body   # the atomic claim/finalize now lives in shared/action_gate.py (own L1-L5)
    assert not re.search(r"except\s*:", _src)
    assert "NEXUS SYSTEM" not in _src and "API_KEY" not in _src
    assert not re.search(r"\bopen\(", _src)


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 propose changes NOTHING in the vehicle file (not even creating it); the proposal is queued with clean data")
def _():
    path, d = fresh()
    a1, m1 = A.propose_mileage({"mileage": "55,500"})
    a2, m2 = A.propose_maintenance({"service_type": "Oil Change", "mileage": 55500})
    a3, m3 = A.propose_fillup(fill(gallons="10"))
    a4, m4 = A.propose_issue({"description": "Squeak", "severity": "mild"})
    assert not os.path.exists(path)
    q = {a["id"]: a for a in queue_actions()}
    assert len(q) == 4 and all(a["status"] == "pending" and a["agent"] == "drive" for a in q.values())
    assert q[a1]["details"] == {"mileage": 55500}
    assert q[a2]["details"]["service_type"] == "oil_change"
    assert q[a3]["details"]["gallons"] == 10
    assert q[a4]["details"]["severity"] == "low"
    for aid, msg in ((a1, m1), (a2, m2), (a3, m3), (a4, m4)):
        assert aid in msg and "Nothing is saved until you approve" in msg and "⚠" not in msg
    shutil.rmtree(d)


@check("L2 approve saves exactly one record per action, marks it executed, and the readers see it")
def _():
    path, d = fresh()
    seed(path, current_mileage=50000)
    a1, _ = A.propose_maintenance({"service_type": "oil_change", "mileage": 50000, "date": "2026-01-10"})
    out = A.approve_and_execute(a1)
    assert out.startswith("Maintenance logged") and "55,000" in out and status_of(a1) == "executed"
    a2, _ = A.propose_fillup(fill(mileage=50400))
    assert A.approve_and_execute(a2).startswith("Fill-up logged")
    a3, _ = A.propose_issue({"description": "Squeak"})
    assert A.approve_and_execute(a3).startswith("Issue logged")
    a4, _ = A.propose_mileage({"mileage": 51000})
    assert A.approve_and_execute(a4).startswith("Mileage updated")
    v = vehicle(path)
    assert len(v["maintenance_log"]) == 1 and len(v["gas_log"]) == 1 and len(v["issues"]) == 1
    assert v["current_mileage"] == 51000
    assert "Squeak" in t.get_open_issues() and "Oil Change" in t.get_recent_maintenance()
    shutil.rmtree(d)


@check("L2 deny saves nothing, marks it denied, and a denied action can never be approved later")
def _():
    path, d = fresh()
    aid, _ = A.propose_issue({"description": "Squeak"})
    out = A.deny_action(aid)
    assert out.startswith("Denied:") and status_of(aid) == "denied"
    assert not os.path.exists(path)
    assert "already denied" in A.approve_and_execute(aid)
    assert not os.path.exists(path)
    shutil.rmtree(d)


@check("L2 approving twice saves only once; the second try is told it's already executed")
def _():
    path, d = fresh()
    aid, _ = A.propose_issue({"description": "Squeak"})
    assert A.approve_and_execute(aid).startswith("Issue logged")
    assert "already executed" in A.approve_and_execute(aid)
    assert len(vehicle(path)["issues"]) == 1
    shutil.rmtree(d)


@check("L2 a short unique start of the id works (6+ chars); too short or unknown does not")
def _():
    path, d = fresh()
    aid, _ = A.propose_issue({"description": "one"})
    assert "Issue logged" in A.approve_and_execute(aid[:8])
    aid2, _ = A.propose_issue({"description": "two"})
    for bad in (aid2[:5], "zzzzzz", "000000"):
        assert "No pending action" in A.approve_and_execute(bad), bad
    assert status_of(aid2) == "pending"
    shutil.rmtree(d)


@check("L2 an ambiguous id start never guesses")
def _():
    path, d = fresh()
    put_queue(base_entry(id="abcdef-1", type="log_issue", details={"description": "x"}),
              base_entry(id="abcdef-2", type="log_issue", details={"description": "y"}))
    assert "more than one" in A.approve_and_execute("abcdef")
    assert "more than one" in A.deny_action("abcdef")
    assert all(a["status"] == "pending" for a in queue_actions()) and not os.path.exists(path)
    shutil.rmtree(d)


@check("L2 DRIVE can't approve or deny another agent's action")
def _():
    path, d = fresh()
    put_queue(base_entry(id="atlas-1", agent="atlas", type="log_swim", details={}))
    for fn in (A.approve_and_execute, A.deny_action):
        assert "doesn't belong" in fn("atlas-1")
    assert queue_actions()[0]["status"] == "pending" and not os.path.exists(path)
    shutil.rmtree(d)


@check("L2 bad data is rejected at PROPOSAL time and never enters the queue")
def _():
    path, d = fresh()
    for fn, bad in ((A.propose_mileage, {}), (A.propose_maintenance, {"service_type": "gas"}),
                    (A.propose_fillup, {}), (A.propose_issue, None), (A.propose_issue_update, {"issue_id": "a"})):
        assert raises(lambda f=fn, b=bad: f(b), ValueError), (fn.__name__, bad)
    assert queue_actions() == [] and not os.path.exists(path)
    shutil.rmtree(d)


@check("L2 'my check engine light is fixed now': log an issue, propose resolving it by id, approve — and the proposal itself changes nothing")
def _():
    path, d = fresh()
    seed(path)
    a1, _ = A.propose_issue({"description": "Check engine light on", "severity": "high"})
    A.approve_and_execute(a1)
    iid = vehicle(path)["issues"][0]["id"]
    aid, msg = A.propose_issue_update({"issue_id": iid, "new_status": "resolved", "resolution_notes": "new gas cap"})
    assert aid and "Check engine light on" in msg
    assert vehicle(path)["issues"][0]["status"] == "open"
    assert "Issue marked resolved" in A.approve_and_execute(aid)
    iss = vehicle(path)["issues"][0]
    assert iss["status"] == "resolved" and iss["resolution_notes"] == "new gas cap"
    shutil.rmtree(d)


@check("L2 an update that can't work is never queued: unknown id, or already resolved")
def _():
    path, d = fresh()
    seed(path)
    a1, _ = A.propose_issue({"description": "Squeak"})
    A.approve_and_execute(a1)
    iid = vehicle(path)["issues"][0]["id"]
    a2, _ = A.propose_issue_update({"issue_id": iid, "new_status": "resolved"})
    A.approve_and_execute(a2)
    aid, msg = A.propose_issue_update({"issue_id": iid, "new_status": "resolved"})
    assert aid is None and "already resolved" in msg
    aid, msg = A.propose_issue_update({"issue_id": "nope", "new_status": "resolved"})
    assert aid is None and "No issue" in msg
    assert A.list_pending() == "Nothing waiting for approval."
    shutil.rmtree(d)


@check("L2 an update whose issue got resolved before approval fails cleanly and is recorded as failed")
def _():
    path, d = fresh()
    seed(path)
    a1, _ = A.propose_issue({"description": "Squeak"})
    A.approve_and_execute(a1)
    iid = vehicle(path)["issues"][0]["id"]
    aid, _ = A.propose_issue_update({"issue_id": iid, "new_status": "resolved"})
    Lg.update_issue_status({"issue_id": iid, "new_status": "resolved"})      # resolved behind its back
    out = A.approve_and_execute(aid)
    assert "already resolved" in out and status_of(aid) == "failed"
    shutil.rmtree(d)


@check("L2 list_pending shows only DRIVE's pending items and drops approved/denied ones")
def _():
    path, d = fresh()
    a1, _ = A.propose_issue({"description": "one"})
    a2, _ = A.propose_issue({"description": "two"})
    a3, _ = A.propose_issue({"description": "three"})
    A.approve_and_execute(a1)
    A.deny_action(a2)
    q = read(QUEUE)
    q["actions"].append(base_entry(id="atlas-1", agent="atlas", type="log_swim", details={}))
    write_raw(QUEUE, q)
    out = A.list_pending()
    assert a3 in out and a1 not in out and a2 not in out and "atlas-1" not in out
    assert len(out.splitlines()) == 1
    shutil.rmtree(d)


@check("L2 proposals say 'not stated' for anything Joey didn't give (never a made-up 0 or $0)")
def _():
    path, d = fresh()
    _, m = A.propose_maintenance({"service_type": "oil_change"})
    assert "mileage not stated" in m and "cost not stated" in m
    _, m = A.propose_fillup({"gallons": 9})
    assert "mileage not stated" in m and "total cost not stated" in m and "price not stated" in m
    _, m = A.propose_issue({"description": "Squeak"})
    assert "severity: not stated" in m
    for text in (A.list_pending(),):
        assert "$0" not in text and "at 0 miles" not in text and "0 gal" not in text
    shutil.rmtree(d)


@check("L2 describe never crashes on junk details")
def _():
    for kind, details in (("log_fillup", {}), ("log_mileage", "x"), ("log_issue", None), ("weird", {"a": 1}),
                          ("log_maintenance", {"mileage": "abc", "display_name": "x", "date": "d", "cost": "lots"}),
                          ("update_issue", "oops"), ("log_mileage", {"mileage": "abc"})):
        assert isinstance(A.describe(kind, details), str), (kind, details)  # type: ignore


@check("L2 a mileage update LOWER than current warns, is still queued, changes nothing until approved, and still saves when approved")
def _():
    path, d = fresh()
    seed(path, current_mileage=55500)
    aid, msg = A.propose_mileage({"mileage": 54000})
    assert aid and "LOWER" in msg and "55,500" in msg
    assert vehicle(path)["current_mileage"] == 55500
    out = A.approve_and_execute(aid)
    assert "LOWER" in out and vehicle(path)["current_mileage"] == 54000
    shutil.rmtree(d)


@check("L2 big jumps warn about a typo; ordinary and backdated entries do NOT warn")
def _():
    path, d = fresh()
    seed(path, current_mileage=55500)
    for text in (A.propose_mileage({"mileage": 55500})[1], A.propose_mileage({"mileage": 56000})[1],
                 A.propose_maintenance({"service_type": "oil_change", "mileage": 40000, "date": "2025-01-01"})[1],
                 A.propose_maintenance({"service_type": "wiper_fluid"})[1]):
        assert "⚠" not in text, text
    assert "typo" in A.propose_mileage({"mileage": 555000})[1]
    assert "typo" in A.propose_maintenance({"service_type": "oil_change", "mileage": 80000})[1]
    assert "typo" in A.propose_fillup(fill(mileage=90000))[1]
    shutil.rmtree(d)


@check("L2 an unreadable vehicle file at proposal time: still queued, with a visible warning, file untouched; a missing file just means no warning")
def _():
    path, d = fresh()
    aid, msg = A.propose_mileage({"mileage": 50000})
    assert aid and "⚠" not in msg and not os.path.exists(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"vehicles": [ {"broken"')
    before = raw_bytes(path)
    aid, msg = A.propose_mileage({"mileage": 50000})
    assert aid and "Couldn't read" in msg
    assert raw_bytes(path) == before
    shutil.rmtree(d)


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 threads approving the SAME action: exactly one record is saved, 19 are turned away")
def _():
    path, d = fresh()
    aid, _ = A.propose_fillup(fill())
    results, lock = [], threading.Lock()

    def go():
        r = A.approve_and_execute(aid)
        with lock:
            results.append(r)

    threads = [threading.Thread(target=go) for _ in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    saved = [r for r in results if r.startswith("Fill-up logged")]
    assert len(saved) == 1, results
    assert len(vehicle(path)["gas_log"]) == 1
    assert status_of(aid) == "executed"
    shutil.rmtree(d)


@check("L4 20 simultaneous proposals: 20 distinct pending actions, none lost, vehicle file untouched")
def _():
    path, d = fresh()
    ids, errors, lock = [], [], threading.Lock()

    def go(n):
        try:
            if n % 2:
                aid, _ = A.propose_fillup(fill(mileage=50000 + n))
            else:
                aid, _ = A.propose_issue({"description": f"issue {n}"})
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
    ids = []
    for n in range(20):
        if n % 2:
            ids.append(A.propose_fillup(fill(mileage=50000 + n * 300))[0])
        else:
            ids.append(A.propose_issue({"description": f"issue {n}"})[0])
    results, lock = [], threading.Lock()

    def go(aid):
        r = A.approve_and_execute(aid)
        with lock:
            results.append(r)

    threads = [threading.Thread(target=go, args=(i,)) for i in ids]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert all(r.startswith(("Fill-up logged", "Issue logged")) for r in results), results
    v = vehicle(path)
    assert len(v["gas_log"]) == 10 and len(v["issues"]) == 10
    assert len({e["id"] for e in v["gas_log"] + v["issues"]}) == 20
    assert all(a["status"] == "executed" for a in queue_actions())
    shutil.rmtree(d)


@check("L4 100 propose-and-approve cycles in a row stay correct (and every MPG is right)")
def _():
    path, d = fresh()
    for n in range(100):
        aid, _ = A.propose_fillup(fill(mileage=50000 + n * 300))
        assert "Fill-up logged" in A.approve_and_execute(aid)
    g = vehicle(path)["gas_log"]
    assert len(g) == 100 and g[0]["mpg"] is None and all(e["mpg"] == 30.0 for e in g[1:])
    shutil.rmtree(d)


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 vehicle file corrupt at approval time: action is marked failed, file left exactly as it was")
def _():
    path, d = fresh()
    aid, _ = A.propose_fillup(fill())
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"vehicles": [ {"broken"')
    before = raw_bytes(path)
    out = A.approve_and_execute(aid)
    assert out.startswith("Execution failed"), out
    assert status_of(aid) == "failed"
    assert raw_bytes(path) == before
    shutil.rmtree(d)


@check("L5 wrong-shape vehicle file at approval time (a list field that isn't a list): fails cleanly, nothing partly saved")
def _():
    path, d = fresh()
    seed(path, maintenance_log="oops")
    before = raw_bytes(path)
    aid, _ = A.propose_maintenance({"service_type": "oil_change", "mileage": 55500})
    out = A.approve_and_execute(aid)
    assert out.startswith("Execution failed") and status_of(aid) == "failed"
    assert raw_bytes(path) == before
    shutil.rmtree(d)


@check("L5 hand-damaged queue entries (junk details, unknown type) fail cleanly, never crash or write")
def _():
    path, d = fresh()
    put_queue(base_entry(id="junk-1", type="log_mileage", details="not a dict"),
              base_entry(id="junk-2", type="log_fillup", details={}),
              base_entry(id="junk-3", type="delete_everything", details={}),
              base_entry(id="junk-4", type="log_issue", details=None))
    for aid in ("junk-1", "junk-2", "junk-3", "junk-4"):
        out = A.approve_and_execute(aid)
        assert out.startswith("Execution failed") or out.startswith("Unknown action type"), (aid, out)
    assert all(a["status"] == "failed" for a in queue_actions())
    assert not os.path.exists(path)
    shutil.rmtree(d)


@check("L5 corrupt queue file: proposing fails LOUDLY and writes nothing to the vehicle file")
def _():
    path, d = fresh()
    os.makedirs(os.path.dirname(QUEUE), exist_ok=True)
    with open(QUEUE, "w", encoding="utf-8") as f:
        f.write("{not json")
    assert raises(lambda: A.propose_mileage({"mileage": 50000}), Exception)
    assert not os.path.exists(path)
    os.remove(QUEUE)
    shutil.rmtree(d)


@check("L5 empty / None / number / whitespace / regex-special ids never crash or approve anything")
def _():
    path, d = fresh()
    A.propose_issue({"description": "x"})
    for bad in ("", "   ", None, 123, [], "a.*b", "[", "\\", "x" * 10000):
        for fn in (A.approve_and_execute, A.deny_action):
            out = fn(bad)  # type: ignore
            assert isinstance(out, str) and "No " in out, (fn.__name__, bad, out)
    assert not os.path.exists(path)
    assert all(a["status"] == "pending" for a in queue_actions())
    shutil.rmtree(d)


@check("L5 50,000-character text and unicode/emoji survive propose -> approve intact (cut to 1,000)")
def _():
    path, d = fresh()
    a1, _ = A.propose_issue({"description": "y" * 50000, "notes": "Schwimmen 泳ぐ 🏊 résumé"})
    A.approve_and_execute(a1)
    a2, _ = A.propose_maintenance({"service_type": "Brake job 🔧 épaule", "notes": "x" * 50000})
    A.approve_and_execute(a2)
    v = vehicle(path)
    assert len(v["issues"][0]["description"]) == 1000 and v["issues"][0]["notes"] == "Schwimmen 泳ぐ 🏊 résumé"
    assert len(v["maintenance_log"][0]["notes"]) == 1000
    assert v["maintenance_log"][0]["service_type"] == "Brake job 🔧 épaule"
    shutil.rmtree(d)


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)