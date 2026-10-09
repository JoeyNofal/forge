"""
DRIVE increment (b), Part 3a — L1, L2, L4, L5 tests for "resolve several issues
at once" (drive_logging.update_issues_status + drive_actions.propose_issues_update).
TEMP files only. Run from the repo root:  python -m agents.drive.test_drive_resolve_all
"""
import json
import os
import re
import shutil
import tempfile
import threading
import time

_QUEUE_DIR = tempfile.mkdtemp(prefix="drive_resolveall_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from agents.drive import drive_actions as A
from agents.drive import drive_logging as L
from agents.drive import drive_tools as t
from shared import pending_actions as pa

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
    d = tempfile.mkdtemp(prefix="drive_resolveall_test_")
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


def seed_issues(path, n=3, closed=()):
    issues = [{"id": f"i{k}", "description": f"problem {k}", "status": "resolved" if f"i{k}" in closed else "open",
               "severity": "low", "reported_date": "2026-01-01"} for k in range(1, n + 1)]
    write_raw(path, {"vehicles": [{"id": "v", "active": True, "make": "Honda", "model": "Civic",
                                   "year": 2016, "current_mileage": 55500, "issues": issues}]})


def issues(path):
    return read(path)["vehicles"][0]["issues"]


with open(A.__file__, encoding="utf-8") as _f:
    _act_src = _f.read()


def _function_source(src, name):
    m = re.search(rf"^def {name}\(.*?(?=^def |\Z)", src, re.S | re.M)
    assert m, name
    return m.group(0)


# ───────────────────────── L1 — STATIC ─────────────────────────

@check("L1 proposing a bulk resolve never writes; only the _run_issues_update handler (called only by the shared gate) calls the bulk writer")
def _():
    assert "update_issues_status" not in _function_source(_act_src, "propose_issues_update")
    callers = [fn for fn in re.findall(r"^def (\w+)\(", _act_src, re.M)
               if "log.update_issues_status" in _function_source(_act_src, fn)]
    assert callers == ["_run_issues_update"], callers
    assert "update_issues_status" not in _function_source(_act_src, "approve_and_execute")


@check("L1 the bulk writer is built on the locked helper")
def _():
    with open(L.__file__, encoding="utf-8") as f:
        src = f.read()
    body = _function_source(src, "update_issues_status")
    assert "_modify_vehicle" in body and not re.search(r"\bopen\(", body)


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 bulk input: ids cleaned and de-duplicated; non-list, empty, too many, wrong status all rejected")
def _():
    u = L.normalize_issues_update({"issue_ids": [" a ", "b", "a", "", None, {"x": 1}, 7],
                                   "new_status": "Resolved", "resolution_notes": "all good", "date": "2026-02-02"})
    assert u["issue_ids"] == ["a", "b", "7"] and u["new_status"] == "resolved"
    assert u["resolution_notes"] == "all good" and u["date"] == "2026-02-02"
    assert len(L.normalize_issues_update({"issue_ids": [f"i{k}" for k in range(50)], "new_status": "resolved"})["issue_ids"]) == 50
    for bad in (None, {}, "x", {"issue_ids": "a", "new_status": "resolved"}, {"issue_ids": [], "new_status": "resolved"},
                {"issue_ids": ["a"], "new_status": "open"}, {"issue_ids": ["a"]},
                {"issue_ids": [None, ""], "new_status": "resolved"},
                {"issue_ids": [f"i{k}" for k in range(51)], "new_status": "resolved"}):
        assert raises(lambda b=bad: L.normalize_issues_update(b), ValueError), bad


@check("L2 bulk writer resolves exactly the listed issues, with notes and date; others stay open")
def _():
    path, d = fresh()
    seed_issues(path, 3)
    ok, msg = L.update_issues_status({"issue_ids": ["i1", "i3"], "new_status": "resolved",
                                      "resolution_notes": "all fixed", "date": "2026-02-02"})
    assert ok and "2 issue(s)" in msg and "problem 1" in msg and "problem 3" in msg
    a, b, c = issues(path)
    assert a["status"] == "resolved" and a["resolved_date"] == "2026-02-02" and a["resolution_notes"] == "all fixed"
    assert b["status"] == "open" and "resolved_date" not in b
    assert c["status"] == "resolved"
    assert read(path)["last_updated"]
    shutil.rmtree(d)


@check("L2 unknown / already-resolved ids are skipped and reported; if NOTHING qualifies, nothing changes")
def _():
    path, d = fresh()
    seed_issues(path, 3, closed=("i2",))
    ok, msg = L.update_issues_status({"issue_ids": ["i1", "i2", "nope"], "new_status": "resolved"})
    assert ok and "1 issue(s)" in msg and "2 skipped" in msg
    before = read(path)
    ok, msg = L.update_issues_status({"issue_ids": ["i2", "nope"], "new_status": "resolved"})
    assert not ok and "None of those" in msg and read(path) == before
    shutil.rmtree(d)


@check("L2 no issues list at all (missing or not a list): (False, ...) and nothing changed")
def _():
    path, d = fresh()
    for content in ({"vehicles": [{"active": True}]}, {"vehicles": [{"active": True, "issues": "oops"}]}):
        write_raw(path, content)
        before = read(path)
        ok, msg = L.update_issues_status({"issue_ids": ["a"], "new_status": "resolved"})
        assert not ok and read(path) == before
    shutil.rmtree(d)


@check("L2 everything else in the file is preserved (junk entries, extra keys, other vehicles)")
def _():
    path, d = fresh()
    seed_issues(path, 2)
    data = read(path)
    data["vehicles"][0]["issues"] = [5, None] + data["vehicles"][0]["issues"]
    data["vehicles"][0]["recalls"] = [{"x": 1}]
    data["vehicles"].append({"id": "v2", "active": False, "issues": [{"id": "i1", "status": "open"}]})
    data["top"] = [1]
    write_raw(path, data)
    other = read(path)["vehicles"][1]
    L.update_issues_status({"issue_ids": ["i1", "i2"], "new_status": "resolved"})
    after = read(path)
    v = after["vehicles"][0]
    assert v["issues"][:2] == [5, None] and v["recalls"] == [{"x": 1}]
    assert all(i["status"] == "resolved" for i in v["issues"][2:])
    assert after["vehicles"][1] == other and after["top"] == [1]
    shutil.rmtree(d)


@check("L2 proposal lists exactly the issues that are open, changes nothing, and is queued with clean data")
def _():
    path, d = fresh()
    seed_issues(path, 4, closed=("i4",))
    before = raw_bytes(path)
    aid, msg = A.propose_issues_update({"issue_ids": ["i1", "i2", "i4", "nope"], "new_status": "resolved"})
    assert aid and "problem 1" in msg and "problem 2" in msg and "problem 4" not in msg and "2 issue" in msg
    assert "Nothing is saved until you approve" in msg
    assert raw_bytes(path) == before
    q = [a for a in queue_actions() if a["id"] == aid][0]
    assert q["type"] == "update_issues" and q["status"] == "pending" and q["details"]["issue_ids"] == ["i1", "i2"]
    shutil.rmtree(d)


@check("L2 a proposal with nothing to resolve is never queued; bad data is rejected; a missing file is not created")
def _():
    path, d = fresh()
    seed_issues(path, 2, closed=("i1", "i2"))
    aid, msg = A.propose_issues_update({"issue_ids": ["i1", "i2"], "new_status": "resolved"})
    assert aid is None and "nothing to update" in msg
    assert raises(lambda: A.propose_issues_update({"issue_ids": "a", "new_status": "resolved"}), ValueError)
    assert queue_actions() == []
    os.remove(path)
    aid, msg = A.propose_issues_update({"issue_ids": ["i1"], "new_status": "resolved"})
    assert aid is None and not os.path.exists(path)
    shutil.rmtree(d)


@check("L2 approving resolves them all in ONE action, marks it executed, and a second approval does nothing")
def _():
    path, d = fresh()
    seed_issues(path, 3)
    aid, _ = A.propose_issues_update({"issue_ids": ["i1", "i2", "i3"], "new_status": "resolved",
                                      "resolution_notes": "everything fixed"})
    out = A.approve_and_execute(aid)
    assert out.startswith("Marked 3 issue(s) resolved") and status_of(aid) == "executed"
    assert all(i["status"] == "resolved" and i["resolution_notes"] == "everything fixed" for i in issues(path))
    assert "already executed" in A.approve_and_execute(aid)
    assert "problem 1" not in t.get_open_issues()
    shutil.rmtree(d)


@check("L2 issues resolved between proposal and approval: the rest still resolve and the skip is reported; if all are gone it fails cleanly")
def _():
    path, d = fresh()
    seed_issues(path, 3)
    aid, _ = A.propose_issues_update({"issue_ids": ["i1", "i2", "i3"], "new_status": "resolved"})
    L.update_issue_status({"issue_id": "i2", "new_status": "resolved"})
    out = A.approve_and_execute(aid)
    assert out.startswith("Marked 2 issue(s) resolved") and "1 skipped" in out and status_of(aid) == "executed"
    seed_issues(path, 2)
    aid2, _ = A.propose_issues_update({"issue_ids": ["i1", "i2"], "new_status": "resolved"})
    L.update_issues_status({"issue_ids": ["i1", "i2"], "new_status": "resolved"})
    out = A.approve_and_execute(aid2)
    assert "None of those" in out and status_of(aid2) == "failed"
    shutil.rmtree(d)


@check("L2 deny saves nothing and a denied bulk action can't be approved later")
def _():
    path, d = fresh()
    seed_issues(path, 2)
    before = raw_bytes(path)
    aid, _ = A.propose_issues_update({"issue_ids": ["i1", "i2"], "new_status": "resolved"})
    assert A.deny_action(aid).startswith("Denied: mark 2 issue(s) resolved")
    assert "already denied" in A.approve_and_execute(aid)
    assert raw_bytes(path) == before
    shutil.rmtree(d)


@check("L2 list_pending shows a waiting bulk action in plain English")
def _():
    path, d = fresh()
    seed_issues(path, 2)
    aid, _ = A.propose_issues_update({"issue_ids": ["i1", "i2"], "new_status": "resolved"})
    out = A.list_pending()
    assert aid in out and "issue(s) resolved" in out and "problem 1" in out
    shutil.rmtree(d)


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 threads approving the SAME bulk action: exactly one succeeds")
def _():
    path, d = fresh()
    seed_issues(path, 3)
    aid, _ = A.propose_issues_update({"issue_ids": ["i1", "i2", "i3"], "new_status": "resolved"})
    results, lock = [], threading.Lock()

    def go():
        r = A.approve_and_execute(aid)
        with lock:
            results.append(r)

    threads = [threading.Thread(target=go) for _ in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert len([r for r in results if r.startswith("Marked 3")]) == 1, results
    assert all(i["status"] == "resolved" for i in issues(path))
    shutil.rmtree(d)


@check("L4 20 threads resolving overlapping sets of 10 issues: no errors, valid file, all end resolved")
def _():
    path, d = fresh()
    seed_issues(path, 10)
    errors = []

    def go(n):
        try:
            L.update_issues_status({"issue_ids": [f"i{(n % 10) + 1}", f"i{((n + 3) % 10) + 1}"], "new_status": "resolved"})
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go, args=(n,)) for n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert not errors, errors
    assert len(issues(path)) == 10 and all(i["status"] == "resolved" for i in issues(path))
    shutil.rmtree(d)


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 hostile issue entries (list/number ids, junk items, unhashable ids) never crash; the valid ones resolve")
def _():
    path, d = fresh()
    write_raw(path, {"vehicles": [{"active": True, "issues": [
        5, None, "junk", {"id": ["x"], "status": "open"}, {"id": 7, "description": "numeric id", "status": "open"},
        {"id": "ok1", "description": "real one", "status": "open"}]}]})
    ok, msg = L.update_issues_status({"issue_ids": ["ok1", "7", "x"], "new_status": "resolved"})
    assert ok and "1 issue(s)" in msg and "real one" in msg
    iss = issues(path)
    assert iss[:3] == [5, None, "junk"] and iss[4]["status"] == "open" and iss[5]["status"] == "resolved"
    shutil.rmtree(d)


@check("L5 corrupt vehicle file: fails LOUDLY and the file is left exactly as it was")
def _():
    path, d = fresh()
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"vehicles": [ {"broken"')
    before = raw_bytes(path)
    assert raises(lambda: L.update_issues_status({"issue_ids": ["a"], "new_status": "resolved"}), Exception)
    assert raw_bytes(path) == before
    shutil.rmtree(d)


@check("L5 resolving 50 issues at once works and stays fast")
def _():
    path, d = fresh()
    seed_issues(path, 50)
    start = time.time()
    aid, _ = A.propose_issues_update({"issue_ids": [f"i{k}" for k in range(1, 51)], "new_status": "resolved"})
    out = A.approve_and_execute(aid)
    assert out.startswith("Marked 50 issue(s) resolved"), out
    assert all(i["status"] == "resolved" for i in issues(path))
    assert time.time() - start < 10
    shutil.rmtree(d)


@check("L5 50,000-character notes are cut to 1,000; unicode survives")
def _():
    path, d = fresh()
    seed_issues(path, 1)
    L.update_issues_status({"issue_ids": ["i1"], "new_status": "resolved", "resolution_notes": "x" * 50000})
    assert len(issues(path)[0]["resolution_notes"]) == 1000
    seed_issues(path, 1)
    L.update_issues_status({"issue_ids": ["i1"], "new_status": "resolved", "resolution_notes": "Bremsen 泳ぐ 🔧 épaule"})
    assert issues(path)[0]["resolution_notes"] == "Bremsen 泳ぐ 🔧 épaule"
    shutil.rmtree(d)


@check("L5 invalid input is rejected BEFORE the file is touched (a missing file is not created)")
def _():
    path, d = fresh()
    for bad in (None, {}, {"issue_ids": "a", "new_status": "resolved"}, {"issue_ids": ["a"], "new_status": "open"}):
        assert raises(lambda b=bad: L.update_issues_status(b), ValueError), bad
    assert not os.path.exists(path)
    shutil.rmtree(d)


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)