"""
DRIVE increment (b), Part 3c — L1, L2, L4, L5 tests for the brake work:
"brake replacement" as a real service type (it restarts the brake-inspection schedule)
and the one-time "Brake Inspection, due today" reminder (proposed by a fixed command,
saved only when Joey approves). The local model is FAKED. TEMP files only.

Run from the repo root:  python -m agents.drive.test_drive_brakes
"""
import json
import os
import re
import shutil
import tempfile
import threading
import time
from datetime import datetime, timedelta

_QUEUE_DIR = tempfile.mkdtemp(prefix="drive_brakes_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from agents.drive import drive_actions as A
from agents.drive import drive_extract as X
from agents.drive import drive_logging as Lg
from agents.drive import drive_tools as t
from shared import agent_topics
from shared import pending_actions as pa

QUEUE = pa.PENDING_ACTIONS_PATH
_results = []
model_calls = []
answers = {}
_lock = threading.Lock()
today_str = time.strftime("%Y-%m-%d")
IV = t.MAINTENANCE_INTERVALS["brake_inspection"]


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


def fake_local(system_prompt, user_text, timeout=90.0):
    with _lock:
        model_calls.append(user_text)
    a = answers.get("maintenance")
    return '{"kind": "none"}' if a is None else json.dumps(a)


X.complete_ollama_json = fake_local


def fresh():
    d = tempfile.mkdtemp(prefix="drive_brakes_test_")
    os.environ["VEHICLE_DATA_PATH"] = os.path.join(d, "vehicle.json")
    if os.path.exists(QUEUE):
        os.remove(QUEUE)
    model_calls.clear()
    answers.clear()
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


def seed(path, **fields):
    v = {"id": "vehicle_001", "active": True, "make": "Honda", "model": "Civic", "year": 2016,
         "vin": "TESTVIN", "current_mileage": 55500, "mileage_last_updated": None,
         "maintenance_log": [], "upcoming_maintenance": [], "gas_log": [], "issues": [], "recalls": []}
    v.update(fields)
    write_raw(path, {"vehicles": [v]})


def vehicle(path):
    return read(path)["vehicles"][0]


def queue_actions():
    return read(QUEUE)["actions"] if os.path.exists(QUEUE) else []


def types():
    return [a["type"] for a in queue_actions()]


def status_of(action_id):
    a = pa.get_pending_action(action_id)
    return a["status"] if a else "missing"


def brake_rows(path):
    return [u for u in vehicle(path)["upcoming_maintenance"]
            if isinstance(u, dict) and u.get("service_type") == "brake_inspection"]


def _function_source(src, name):
    m = re.search(rf"^def {name}\(.*?(?=^def |\Z)", src, re.S | re.M)
    assert m, name
    return m.group(0)


with open(Lg.__file__, encoding="utf-8") as _f:
    LSRC = _f.read()
with open(A.__file__, encoding="utf-8") as _f:
    ASRC = _f.read()
with open(X.__file__, encoding="utf-8") as _f:
    XSRC = _f.read()

# ───────────────────────── L1 — STATIC ─────────────────────────


@check("L1 brake logic lives in drive_logging; the reminder writer uses the locked helper and no raw file access")
def _():
    assert "SCHEDULE_RESETS" in LSRC and "_BRAKE_WORK_WORDS" in LSRC and "_NOT_BRAKE_WORK" in LSRC
    body = _function_source(LSRC, "log_brake_reminder")
    assert "_modify_vehicle" in body and not re.search(r"\bopen\(", body) and "json.dump" not in body
    assert not re.search(r"\bopen\(", LSRC)


@check("L1 proposing the reminder never writes; only approve_and_execute calls the reminder writer")
def _():
    for fn in ("propose_brake_reminder", "_has_brake_schedule_readonly"):
        body = _function_source(ASRC, fn)
        assert "log.log_" not in body and "update_issue" not in body, fn
    callers = [fn for fn in re.findall(r"^def (\w+)\(", ASRC, re.M)
               if "log.log_brake_reminder" in _function_source(ASRC, fn)]
    assert callers == ["approve_and_execute"], callers


@check("L1 the reminder command is answered BEFORE any local-model call")
def _():
    body = _function_source(XSRC, "_handle")
    assert "KIND_BRAKE_REMINDER" in body and "_extract(" in body
    assert body.index("KIND_BRAKE_REMINDER") < body.index("_extract(")


@check("L1 the reminder phrases live in shared/agent_topics and include the three Joey chose")
def _():
    for p in ("add a brake reminder", "remind me about my brakes", "remind me to check my brakes"):
        assert p in agent_topics.DRIVE_BRAKE_REMINDER_PHRASES, p


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 brake wording: pad/rotor/caliper/replaced/repair variants become 'brake_replacement'; lights, bulbs, fluid, noises and other services do NOT")
def _():
    yes = ("brake pad replacement", "Brakes replaced", "brake repair", "new brake rotors", "brake caliper replaced",
           "Brake Replacement", "brake_replacement", "BRAKES REPLACED!!!", "replaced the brake pads",
           "brake pads and rotors replaced")
    for said in yes:
        n = Lg.normalize_maintenance({"service_type": said})
        assert n["service_type"] == "brake_replacement" and n["display_name"] == "Brake Replacement", (said, n)
    for said in ("brake light bulb replaced", "brake fluid flush", "Brake job 🔧 épaule", "brake squeak", "replace headlight"):
        n = Lg.normalize_maintenance({"service_type": said})
        assert n["service_type"] != "brake_replacement" and n["service_type"] == said, (said, n)
    assert Lg.normalize_maintenance({"service_type": "brake inspection"})["service_type"] == "brake_inspection"
    assert Lg.normalize_maintenance({"service_type": "tire replacement"})["service_type"] == "tire_replacement"


@check("L2 logging a brake replacement restarts the BRAKE INSPECTION schedule (one row, right numbers); no 'brake_replacement' schedule row")
def _():
    path, d = fresh()
    seed(path, current_mileage=56000, upcoming_maintenance=[
        {"service_type": "oil_change", "display_name": "Oil Change", "last_done_mileage": 52000,
         "last_done_date": "2026-06-16", "due_mileage": 57000, "due_date": "2026-12-13"}])
    msg = Lg.log_maintenance({"service_type": "brake pad replacement", "mileage": 56000, "date": "2026-01-10"})
    v = vehicle(path)
    assert v["maintenance_log"][0]["service_type"] == "brake_replacement"
    assert v["maintenance_log"][0]["display_name"] == "Brake Replacement"
    up = v["upcoming_maintenance"]
    assert [u["service_type"] for u in up] == ["oil_change", "brake_inspection"]
    b = up[1]
    assert b["display_name"] == "Brake Inspection" and b["last_done_mileage"] == 56000 and b["last_done_date"] == "2026-01-10"
    assert b["due_mileage"] == 56000 + IV["miles"]
    assert b["due_date"] == (datetime(2026, 1, 10) + timedelta(days=IV["days"])).strftime("%Y-%m-%d")
    assert "for Brake Inspection" in msg and "Brake Replacement" in msg
    shutil.rmtree(d)


@check("L2 a normal brake inspection still works; later brake work replaces the row (never duplicates)")
def _():
    path, d = fresh()
    seed(path)
    msg = Lg.log_maintenance({"service_type": "brake_inspection", "mileage": 50000, "date": "2026-01-10"})
    assert "for Brake Inspection" not in msg and "Next due:" in msg
    Lg.log_maintenance({"service_type": "brake replacement", "mileage": 54000, "date": "2026-06-01"})
    rows = brake_rows(path)
    assert len(rows) == 1 and rows[0]["last_done_mileage"] == 54000
    assert len(vehicle(path)["maintenance_log"]) == 2
    assert not [u for u in vehicle(path)["upcoming_maintenance"] if u.get("service_type") == "brake_replacement"]
    shutil.rmtree(d)


@check("L2 the 'due today' reminder is replaced by the first real brake work — even a backdated one")
def _():
    path, d = fresh()
    seed(path)
    assert Lg.log_brake_reminder()[0] is True
    Lg.log_maintenance({"service_type": "brake replacement", "mileage": 40000, "date": "2025-01-01"})
    rows = brake_rows(path)
    assert len(rows) == 1 and rows[0]["last_done_date"] == "2025-01-01"
    shutil.rmtree(d)


@check("L2 reminder writer: exact entry, other rows untouched, a second one is refused, a normal brake row also blocks it, a missing list or file is fine")
def _():
    path, d = fresh()
    oil = {"service_type": "oil_change", "display_name": "Oil Change", "due_date": "2999-01-01"}
    seed(path, upcoming_maintenance=[oil])
    ok, msg = Lg.log_brake_reminder()
    assert ok and today_str in msg
    up = vehicle(path)["upcoming_maintenance"]
    assert up[0] == oil and up[1] == {"service_type": "brake_inspection", "display_name": "Brake Inspection",
                                      "last_done_mileage": None, "last_done_date": None,
                                      "due_mileage": None, "due_date": today_str}
    assert read(path)["last_updated"]
    before = read(path)
    ok, msg = Lg.log_brake_reminder()
    assert not ok and "already" in msg and read(path) == before
    seed(path)
    Lg.log_maintenance({"service_type": "brake_inspection", "date": "2026-01-10"})
    before = read(path)
    assert Lg.log_brake_reminder()[0] is False and read(path) == before
    seed(path, upcoming_maintenance=None)
    assert Lg.log_brake_reminder()[0] is True and len(brake_rows(path)) == 1
    os.remove(path)
    assert Lg.log_brake_reminder()[0] is True and len(brake_rows(path)) == 1
    shutil.rmtree(d)


@check("L2 an upcoming list that is not a list is never overwritten (RuntimeError, file untouched)")
def _():
    path, d = fresh()
    for bad in ({"a": 1}, "oops", 5):
        seed(path, upcoming_maintenance=bad)
        before = raw_bytes(path)
        assert raises(Lg.log_brake_reminder, RuntimeError), bad
        assert raw_bytes(path) == before
    shutil.rmtree(d)


@check("L2 DRIVE's own reader shows the reminder as coming due today (so the DRIVE model sees it too)")
def _():
    path, d = fresh()
    seed(path)
    Lg.log_brake_reminder()
    out = t.get_upcoming_maintenance()
    assert "COMING DUE SOON" in out and "Brake Inspection" in out and "0 days away" in out
    shutil.rmtree(d)


@check("L2 proposing the reminder: clean proposal, queued as pending, vehicle file untouched (not even created)")
def _():
    path, d = fresh()
    seed(path)
    before = raw_bytes(path)
    aid, msg = A.propose_brake_reminder()
    assert aid and msg.startswith("Proposed: add a brake reminder") and "Nothing is saved until you approve" in msg
    q = queue_actions()
    assert len(q) == 1 and q[0]["type"] == "add_brake_reminder" and q[0]["status"] == "pending"
    assert q[0]["details"] == {"service_type": "brake_inspection"}
    assert raw_bytes(path) == before
    path2, d2 = fresh()
    aid, msg = A.propose_brake_reminder()
    assert aid and not os.path.exists(path2)
    shutil.rmtree(d); shutil.rmtree(d2)


@check("L2 approving adds the reminder once; approving again does nothing; a second proposal is not even queued")
def _():
    path, d = fresh()
    seed(path)
    aid, _m = A.propose_brake_reminder()
    out = A.approve_and_execute(aid)
    assert out.startswith("Brake reminder added") and status_of(aid) == "executed"
    assert len(brake_rows(path)) == 1 and brake_rows(path)[0]["due_date"] == today_str
    assert "already executed" in A.approve_and_execute(aid)
    aid2, msg2 = A.propose_brake_reminder()
    assert aid2 is None and "already on your schedule" in msg2 and len(queue_actions()) == 1
    shutil.rmtree(d)


@check("L2 denying saves nothing, and a denied reminder can't be approved later")
def _():
    path, d = fresh()
    seed(path)
    before = raw_bytes(path)
    aid, _m = A.propose_brake_reminder()
    assert A.deny_action(aid).startswith("Denied: add a brake reminder")
    assert "already denied" in A.approve_and_execute(aid)
    assert raw_bytes(path) == before and A.list_pending() == "Nothing waiting for approval."
    aid, _m = A.propose_brake_reminder()
    assert aid[:8] in A.list_pending() and "add a brake reminder" in A.list_pending()
    shutil.rmtree(d)


@check("L2 a brake inspection logged between proposal and approval: approval fails cleanly, nothing doubled")
def _():
    path, d = fresh()
    seed(path)
    aid, _m = A.propose_brake_reminder()
    Lg.log_maintenance({"service_type": "brake_inspection", "date": "2026-01-10"})
    out = A.approve_and_execute(aid)
    assert "already on your schedule" in out and status_of(aid) == "failed"
    rows = brake_rows(path)
    assert len(rows) == 1 and rows[0]["last_done_date"] == "2026-01-10"
    shutil.rmtree(d)


@check("L2 detection: Joey's three phrases (and variants) are the reminder command; look-alikes are not")
def _():
    for msg in ("add a brake reminder", "Remind me about my brakes", "remind me to check my brakes",
                "set a brake reminder", "Please add a brake reminder.", "REMIND ME ABOUT MY BRAKES!"):
        assert X.detect_report_kinds(msg) == ["brake_reminder"], msg
    assert X.detect_report_kinds("my brakes are squeaking") == ["issue"]
    assert X.detect_report_kinds("remind me to buy milk") == []
    assert X.detect_report_kinds("got the brakes replaced") == ["maintenance"]


@check("L2 through extraction: the command makes NO model call and queues a proposal; once approved, asking again says it's already there")
def _():
    path, d = fresh()
    seed(path)
    notes = X.extract_and_propose("remind me about my brakes")
    assert len(notes) == 1 and "Proposed: add a brake reminder" in notes[0]
    assert model_calls == [] and types() == ["add_brake_reminder"]
    A.approve_and_execute(queue_actions()[0]["id"])
    notes = X.extract_and_propose("remind me about my brakes")
    assert len(notes) == 1 and "already on your schedule" in notes[0]
    assert len(queue_actions()) == 1 and model_calls == []
    shutil.rmtree(d)


@check("L2 end to end: reminder approved -> 'got the brakes replaced' (real-model wording) approved -> the reminder is replaced by the normal interval")
def _():
    path, d = fresh()
    seed(path, current_mileage=56000)
    X.extract_and_propose("add a brake reminder")
    A.approve_and_execute(queue_actions()[0]["id"])
    assert "0 days away" in t.get_upcoming_maintenance()
    answers["maintenance"] = {"kind": "maintenance", "service_type": "brake pad replacement", "date": "",
                              "mileage": 56000, "shop": "", "cost": None, "performed_by": "", "notes": "",
                              "parts_used": [], "fixes_issue_numbers": [], "more_jobs": False}
    notes = X.extract_and_propose("got the brakes replaced")
    assert len(notes) == 1 and "Brake Replacement" in notes[0]
    mid = [a["id"] for a in queue_actions() if a["type"] == "log_maintenance"][0]
    out = A.approve_and_execute(mid)
    assert out.startswith("Maintenance logged: Brake Replacement") and "for Brake Inspection" in out
    rows = brake_rows(path)
    assert len(rows) == 1 and rows[0]["last_done_date"] == today_str and rows[0]["last_done_mileage"] == 56000
    assert rows[0]["due_date"] == (datetime.now() + timedelta(days=IV["days"])).strftime("%Y-%m-%d")
    assert "0 days away" not in t.get_upcoming_maintenance()
    shutil.rmtree(d)


@check("L2 the model's service list now offers 'brake_replacement'")
def _():
    assert "brake_replacement" in X._SERVICE_KEYS and "brake_replacement" in X.MAINTENANCE_PROMPT.replace("{{SERVICES}}", X._SERVICE_KEYS)


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 simultaneous reminder proposals, then 20 simultaneous approvals: exactly ONE reminder is saved")
def _():
    path, d = fresh()
    seed(path)
    ids, errors = [], []

    def prop():
        try:
            aid, _m = A.propose_brake_reminder()
            with _lock:
                ids.append(aid)
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=prop) for _n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert not errors, errors
    assert None not in ids and len(set(ids)) == 20
    results = []

    def appr(aid):
        r = A.approve_and_execute(aid)
        with _lock:
            results.append(r)

    threads = [threading.Thread(target=appr, args=(i,)) for i in ids]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert len([r for r in results if r.startswith("Brake reminder added")]) == 1, results
    assert len([r for r in results if "already on your schedule" in r]) == 19, results
    assert len(brake_rows(path)) == 1
    assert [a["status"] for a in queue_actions()].count("executed") == 1
    shutil.rmtree(d)


@check("L4 20 simultaneous brake replacements: 20 log entries, exactly ONE Brake Inspection row")
def _():
    path, d = fresh()
    seed(path)
    errors = []

    def go(n):
        try:
            Lg.log_maintenance({"service_type": "brake pad replacement", "mileage": 50000 + n, "date": "2026-01-10"})
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go, args=(n,)) for n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert not errors, errors
    assert len(vehicle(path)["maintenance_log"]) == 20 and len(brake_rows(path)) == 1
    shutil.rmtree(d)


@check("L4 once the reminder exists, 100 more attempts are all politely refused and queue nothing")
def _():
    path, d = fresh()
    seed(path)
    Lg.log_brake_reminder()
    for _n in range(100):
        aid, msg = A.propose_brake_reminder()
        assert aid is None and "already on your schedule" in msg
        notes = X.extract_and_propose("add a brake reminder")
        assert len(notes) == 1 and "already on your schedule" in notes[0]
    assert queue_actions() == [] and len(brake_rows(path)) == 1
    shutil.rmtree(d)


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 corrupt vehicle file: proposing fails LOUDLY, via extraction it becomes one honest note, nothing queued, file untouched")
def _():
    path, d = fresh()
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"vehicles": [ {"broken"')
    before = raw_bytes(path)
    assert raises(A.propose_brake_reminder, RuntimeError)
    notes = X.extract_and_propose("add a brake reminder")
    assert len(notes) == 1 and "couldn't turn that into a brake reminder" in notes[0] and "Nothing was proposed" in notes[0]
    assert queue_actions() == [] and raw_bytes(path) == before
    shutil.rmtree(d)


@check("L5 junk entries in the schedule are all preserved; the reminder is added once at the end")
def _():
    path, d = fresh()
    junk = ["j", None, {"service_type": "oil_change"}, {"nope": 1}, 5]
    seed(path, upcoming_maintenance=list(junk))
    assert Lg.log_brake_reminder()[0] is True
    up = vehicle(path)["upcoming_maintenance"]
    assert up[:5] == junk and len(up) == 6 and up[5]["service_type"] == "brake_inspection"
    assert Lg.log_brake_reminder()[0] is False
    shutil.rmtree(d)


@check("L5 hostile service text: empty/falsy values rejected, odd types and huge text never crash, unicode kept, the 1,000-character cut applies first")
def _():
    for bad in (None, [], {}, "", 0, False):
        assert raises(lambda b=bad: Lg.normalize_maintenance({"service_type": b}), ValueError), bad
    for odd in (123, True, 1.5):
        assert isinstance(Lg.normalize_maintenance({"service_type": odd})["service_type"], str)
    assert Lg.normalize_maintenance({"service_type": "replaced " + "brake " * 20000})["service_type"] == "brake_replacement"
    far = Lg.normalize_maintenance({"service_type": "brake " * 20000 + "replaced"})["service_type"]
    assert isinstance(far, str) and far.startswith("brake")
    assert Lg.normalize_maintenance({"service_type": "Bremsen 泳ぐ 🔧"})["service_type"] == "Bremsen 泳ぐ 🔧"
    assert Lg.normalize_maintenance({"service_type": "[(.*)] brake \\ replaced"})["service_type"] == "brake_replacement"


@check("L5 10,000 schedule rows: adding, refusing and replacing the brake row all stay correct and fast")
def _():
    path, d = fresh()
    big = [{"service_type": f"svc{n}", "display_name": f"svc{n}", "due_date": "2999-01-01"} for n in range(10000)]
    seed(path, upcoming_maintenance=big)
    start = time.time()
    assert Lg.log_brake_reminder()[0] is True and len(vehicle(path)["upcoming_maintenance"]) == 10001
    assert Lg.log_brake_reminder()[0] is False
    Lg.log_maintenance({"service_type": "brake replacement", "mileage": 56000, "date": "2026-01-10"})
    up = vehicle(path)["upcoming_maintenance"]
    assert len(up) == 10001 and len(brake_rows(path)) == 1 and brake_rows(path)[0]["last_done_date"] == "2026-01-10"
    assert time.time() - start < 30, time.time() - start
    shutil.rmtree(d)


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)