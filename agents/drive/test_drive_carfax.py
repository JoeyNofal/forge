"""
DRIVE increment (b), Part 5 — L1, L2, L4, L5 tests for typed Carfax entries (history
records of work a PREVIOUS owner had done). The local model is FAKED. TEMP files only.

Run from the repo root:  python -m agents.drive.test_drive_carfax
"""
import json
import os
import re
import shutil
import tempfile
import threading
import time
from datetime import datetime, timedelta

_QUEUE_DIR = tempfile.mkdtemp(prefix="drive_carfax_queue_")
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
    assert "ONE service record from a Carfax vehicle history report" in system_prompt, "unexpected prompt"
    with _lock:
        model_calls.append(user_text)
    a = answers.get("carfax", '{"kind": "none"}')
    if isinstance(a, Exception):
        raise a
    return a if isinstance(a, str) else json.dumps(a)


X.complete_ollama_json = fake_local

CARFAX_JSON = {"kind": "carfax", "service_type": "oil_change", "date": "2024-03-15", "mileage": 40000,
               "shop": "", "cost": None, "notes": "", "parts_used": [], "more_jobs": False}
MSG = "Carfax shows an oil change on 2024-03-15 at 40,000 miles"
ENTRY = {"service_type": "oil_change", "date": "2024-03-15", "mileage": 40000}


def fresh():
    d = tempfile.mkdtemp(prefix="drive_carfax_test_")
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


def _function_source(src, name):
    m = re.search(rf"^def {name}\(.*?(?=^def |\Z)", src, re.S | re.M)
    assert m, name
    return m.group(0)


with open(Lg.__file__, encoding="utf-8") as _f:
    LSRC = _f.read()
with open(A.__file__, encoding="utf-8") as _f:
    ASRC = _f.read()

# ───────────────────────── L1 — STATIC ─────────────────────────


@check("L1 the Carfax writer uses the locked helper, never calls the schedule or mileage code, and the date is never defaulted")
def _():
    body = _function_source(LSRC, "log_carfax_entry")
    assert "_modify_vehicle" in body and not re.search(r"\bopen\(", body) and "json.dump" not in body
    assert "_update_schedule" not in body and "_maybe_raise_mileage" not in body
    assert "datetime.now().strftime" not in _function_source(LSRC, "_strict_date").split("future")[0]
    assert not re.search(r"\bopen\(", LSRC)


@check("L1 proposing a Carfax entry never writes; only approve_and_execute calls the Carfax writer")
def _():
    assert "log.log_" not in _function_source(ASRC, "propose_carfax")
    callers = [fn for fn in re.findall(r"^def (\w+)\(", ASRC, re.M)
               if "log.log_carfax_entry" in _function_source(ASRC, fn)]
    assert callers == ["_run_carfax"], callers


@check("L1 the Carfax prompt spells out an exact shape, refuses today's/relative dates, and the trigger words live in shared/agent_topics")
def _():
    p = X._PROMPTS["carfax"]
    assert '"kind": "carfax"' in p and '{"kind": "none"}' in p and "never use today's date" in p
    assert "carfax" in agent_topics.DRIVE_CARFAX_WORDS


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 normalize_carfax: clean entry; performed_by is ALWAYS 'previous_owner'; the date must be stated, real and not in the future")
def _():
    c = Lg.normalize_carfax({"service_type": "Oil Change", "date": "2024-03-15", "mileage": "40,000",
                             "shop": "Honda of South Bend", "cost": "45.50", "notes": "synthetic oil",
                             "performed_by": "diy", "parts_used": "filter"})
    assert c["service_type"] == "oil_change" and c["display_name"] == "Oil Change" and c["date"] == "2024-03-15"
    assert c["mileage"] == 40000 and c["shop"] == "Honda of South Bend" and c["cost"] == 45.5
    assert c["performed_by"] == "previous_owner" and c["parts_used"] == ["filter"] and c["notes"] == "synthetic oil"
    assert Lg.normalize_carfax({"service_type": "oil_change", "date": "2024-03-15T10:30:00"})["date"] == "2024-03-15"
    assert Lg.normalize_carfax({"service_type": "oil_change", "date": today_str})["date"] == today_str
    n = Lg.normalize_carfax({"service_type": "oil_change", "date": "2024-03-15"})
    assert n["mileage"] is None and n["cost"] is None and n["shop"] is None
    for bad_date in (None, "", "yesterday", "March 2024", "2024-13-45", "last year", 20240315, "2999-01-01", []):
        assert raises(lambda b=bad_date: Lg.normalize_carfax({"service_type": "oil_change", "date": b}), ValueError), bad_date
    for bad in (None, [], "x", 5, {}, {"date": "2024-03-15"}, {"service_type": "gas", "date": "2024-03-15"}):
        assert raises(lambda b=bad: Lg.normalize_carfax(b), ValueError), bad


@check("L2 a missing date reads as a plain request for the date (no leftover 'maintenance:' wording)")
def _():
    try:
        Lg.normalize_carfax({"service_type": "oil_change"})
    except ValueError as e:
        assert "full date" in str(e) and "maintenance" not in str(e)
    else:
        raise AssertionError("no error")
    try:
        Lg.normalize_carfax({"date": "2024-03-15"})
    except ValueError as e:
        assert "no service stated" in str(e) and "maintenance:" not in str(e)
    else:
        raise AssertionError("no error")


@check("L2 service wording works like owner services: brake work, generic shop words, free text")
def _():
    n = Lg.normalize_carfax({"service_type": "brake pad replacement", "date": "2022-06-10", "shop": "dealership"})
    assert n["service_type"] == "brake_replacement" and n["shop"] is None and n["performed_by"] == "previous_owner"
    assert Lg.normalize_carfax({"service_type": "Replaced timing belt", "date": "2022-06-10"})["service_type"] == "Replaced timing belt"


@check("L2 log_carfax_entry: exact record, and it leaves the schedule and current mileage ALONE (even at a higher mileage)")
def _():
    path, d = fresh()
    oil = {"service_type": "oil_change", "display_name": "Oil Change", "last_done_mileage": 52000,
           "last_done_date": "2026-06-16", "due_mileage": 57000, "due_date": "2026-12-13"}
    seed(path, upcoming_maintenance=[oil], current_mileage=55500)
    ok, msg = Lg.log_carfax_entry({"service_type": "oil_change", "date": "2024-03-15", "mileage": 99999})
    assert ok and msg == "Carfax entry logged: Oil Change on 2024-03-15 at 99,999 miles."
    v = vehicle(path)
    e = v["maintenance_log"][0]
    for k in ("id", "source", "service_type", "display_name", "date", "logged_at", "mileage", "shop",
              "cost", "notes", "performed_by", "parts_used"):
        assert k in e, k
    assert e["source"] == "carfax" and e["performed_by"] == "previous_owner" and e["parts_used"] == []
    assert v["upcoming_maintenance"] == [oil] and v["current_mileage"] == 55500 and v["mileage_last_updated"] is None
    assert read(path)["last_updated"]
    shutil.rmtree(d)


@check("L2 an identical Carfax record is refused (file untouched); a different mileage/date or an OWNER entry with the same details is fine")
def _():
    path, d = fresh()
    seed(path)
    assert Lg.log_carfax_entry(ENTRY)[0] is True
    before = read(path)
    ok, msg = Lg.log_carfax_entry(ENTRY)
    assert not ok and "already logged" in msg and read(path) == before
    assert Lg.log_carfax_entry(dict(ENTRY, mileage=41000))[0] is True
    assert Lg.log_carfax_entry(dict(ENTRY, date="2023-03-15"))[0] is True
    Lg.log_maintenance({"service_type": "tire_rotation", "mileage": 38500, "date": "2023-10-02"})
    assert Lg.log_carfax_entry({"service_type": "tire_rotation", "mileage": 38500, "date": "2023-10-02"})[0] is True
    assert len(vehicle(path)["maintenance_log"]) == 5
    shutil.rmtree(d)


@check("L2 DRIVE's and the tracker's readers see it: '[Carfax]' and '[previous_owner]' in the recent-maintenance list")
def _():
    path, d = fresh()
    seed(path)
    Lg.log_carfax_entry(ENTRY)
    out = t.get_recent_maintenance()
    assert "Oil Change on 2024-03-15" in out and "[Carfax]" in out and "[previous_owner]" in out and "40,000" in out
    assert vehicle(path)["maintenance_log"][0]["source"] == "carfax"      # what the tracker's 'Carfax History' filter checks
    shutil.rmtree(d)


@check("L2 proposing: clean proposal, queued as pending, vehicle file untouched; a missing date is rejected BEFORE anything is queued")
def _():
    path, d = fresh()
    seed(path)
    before = raw_bytes(path)
    aid, msg = A.propose_carfax(dict(ENTRY, performed_by="diy"))
    assert msg.startswith("Proposed: log Carfax entry (work by a previous owner): Oil Change on 2024-03-15, at 40,000 miles")
    assert "Nothing is saved until you approve" in msg
    q = queue_actions()
    assert len(q) == 1 and q[0]["type"] == "log_carfax" and q[0]["status"] == "pending"
    assert q[0]["details"]["performed_by"] == "previous_owner" and q[0]["details"]["date"] == "2024-03-15"
    assert raw_bytes(path) == before
    assert raises(lambda: A.propose_carfax({"service_type": "oil_change"}), ValueError)
    assert len(queue_actions()) == 1
    shutil.rmtree(d)


@check("L2 warnings: a Carfax mileage far ABOVE the current one warns about a typo; a lower one (normal for history) does not")
def _():
    path, d = fresh()
    seed(path, current_mileage=55500)
    assert "⚠" not in A.propose_carfax(dict(ENTRY, mileage=40000))[1]
    assert "typo" in A.propose_carfax(dict(ENTRY, mileage=80000))[1]
    shutil.rmtree(d)


@check("L2 approve saves once; approving again does nothing; an identical record logged before approval makes it fail cleanly")
def _():
    path, d = fresh()
    seed(path)
    aid, _m = A.propose_carfax(ENTRY)
    out = A.approve_and_execute(aid)
    assert out.startswith("Carfax entry logged") and status_of(aid) == "executed"
    assert "already executed" in A.approve_and_execute(aid)
    aid2, _m = A.propose_carfax(ENTRY)
    out = A.approve_and_execute(aid2)
    assert "already logged" in out and status_of(aid2) == "failed"
    assert len(vehicle(path)["maintenance_log"]) == 1
    shutil.rmtree(d)


@check("L2 deny saves nothing, a denied entry can't be approved later, and list_pending shows a waiting one")
def _():
    path, d = fresh()
    seed(path)
    before = raw_bytes(path)
    aid, _m = A.propose_carfax(ENTRY)
    assert aid[:8] in A.list_pending() and "Carfax entry" in A.list_pending()
    assert A.deny_action(aid).startswith("Denied: log Carfax entry")
    assert "already denied" in A.approve_and_execute(aid)
    assert raw_bytes(path) == before
    shutil.rmtree(d)


@check("L2 detection: Carfax messages are the Carfax kind (alone); advice about Carfax and look-alikes are not")
def _():
    cases = [
        (MSG, ["carfax"]),
        ("add a Carfax entry: tire rotation, 2023-10-02, 38,500 miles, Honda dealer", ["carfax"]),
        ("my carfax says brakes were replaced in 2022", ["carfax"]),
        ("CARFAX said oil change 2024-03-15", ["carfax"]),
        ("the car fax lists a tire rotation 2023-10-02", ["carfax"]),
        ("should I buy a carfax report?", []),
        ("got an oil change at 56,000 miles", ["maintenance"]),
        ("my car has 52,000 miles on it", ["mileage"]),
    ]
    for message, want in cases:
        assert X.detect_report_kinds(message) == want, (message, X.detect_report_kinds(message), want)


@check("L2 through extraction: ONE model call with only Joey's words, a proposal is queued, the vehicle file is not even created")
def _():
    path, d = fresh()
    answers["carfax"] = CARFAX_JSON
    notes = X.extract_and_propose(MSG)
    assert len(notes) == 1 and "Proposed: log Carfax entry" in notes[0]
    assert model_calls == [MSG] and types() == ["log_carfax"] and not os.path.exists(path)
    shutil.rmtree(d)


@check("L2 failures become ONE honest note (no date, junk JSON, model down, wrong kind); a 'none' answer is silent")
def _():
    cases = (
        (dict(CARFAX_JSON, date=""), "full date"), ("not json", "valid JSON"), (RuntimeError("down"), "local model call failed"),
        ({"kind": "mileage", "mileage": 5}, "unexpected answer type"), (dict(CARFAX_JSON, service_type=""), "no service stated"),
        (dict(CARFAX_JSON, date="2999-01-01"), "future"),
    )
    for ans, expect in cases:
        path, d = fresh()
        answers["carfax"] = ans
        notes = X.extract_and_propose(MSG)
        assert len(notes) == 1 and "couldn't turn that into a Carfax entry" in notes[0] and expect in notes[0], (ans, notes)
        assert "Nothing was proposed" in notes[0] and queue_actions() == []
        shutil.rmtree(d)
    path, d = fresh()
    assert X.extract_and_propose(MSG) == [] and queue_actions() == []
    shutil.rmtree(d)


@check("L2 a second Carfax record in one message is NOT silently dropped (Joey is told to send it separately)")
def _():
    path, d = fresh()
    answers["carfax"] = dict(CARFAX_JSON, more_jobs=True)
    notes = X.extract_and_propose("carfax shows an oil change 2024-03-15 and a tire rotation 2023-10-02")
    assert len(notes) == 2 and "more than one Carfax record" in notes[1] and types() == ["log_carfax"]
    shutil.rmtree(d)


@check("L2 end to end: extract -> approve saves the record (schedule and mileage untouched); saying it again is caught as a duplicate")
def _():
    path, d = fresh()
    seed(path, current_mileage=55500)
    answers["carfax"] = CARFAX_JSON
    X.extract_and_propose(MSG)
    assert A.approve_and_execute(queue_actions()[0]["id"]).startswith("Carfax entry logged")
    v = vehicle(path)
    assert len(v["maintenance_log"]) == 1 and v["current_mileage"] == 55500 and v["upcoming_maintenance"] == []
    X.extract_and_propose(MSG)
    out = A.approve_and_execute(queue_actions()[1]["id"])
    assert "already logged" in out and len(vehicle(path)["maintenance_log"]) == 1
    shutil.rmtree(d)


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 identical Carfax proposals approved at the same time: exactly ONE is saved, 19 are turned away")
def _():
    path, d = fresh()
    seed(path)
    ids = [A.propose_carfax(ENTRY)[0] for _n in range(20)]
    results = []

    def go(aid):
        r = A.approve_and_execute(aid)
        with _lock:
            results.append(r)

    threads = [threading.Thread(target=go, args=(i,)) for i in ids]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert len([r for r in results if r.startswith("Carfax entry logged")]) == 1, results
    assert len([r for r in results if "already logged" in r]) == 19, results
    assert len(vehicle(path)["maintenance_log"]) == 1
    shutil.rmtree(d)


@check("L4 20 DIFFERENT records logged at the same time: all 20 saved, unique ids, valid file")
def _():
    path, d = fresh()
    seed(path)
    errors = []

    def go(n):
        try:
            day = (datetime(2020, 1, 1) + timedelta(days=n)).strftime("%Y-%m-%d")
            Lg.log_carfax_entry({"service_type": "oil_change", "date": day, "mileage": 30000 + n})
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go, args=(n,)) for n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    log = vehicle(path)["maintenance_log"]
    assert not errors, errors
    assert len(log) == 20 and len({e["id"] for e in log}) == 20 and {e["date"] for e in log}.__len__() == 20
    shutil.rmtree(d)


@check("L4 100 distinct records in a row all land, and the duplicate check stays fast")
def _():
    path, d = fresh()
    seed(path)
    start = time.time()
    for n in range(100):
        day = (datetime(2015, 1, 1) + timedelta(days=n * 7)).strftime("%Y-%m-%d")
        assert Lg.log_carfax_entry({"service_type": "tire_rotation", "date": day, "mileage": 10000 + n})[0] is True
    assert len(vehicle(path)["maintenance_log"]) == 100 and time.time() - start < 30
    shutil.rmtree(d)


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 hostile input (odd types, 50,000-character text, unicode/emoji, regex characters) never crashes: a clean record or a ValueError")
def _():
    path, d = fresh()
    seed(path)
    for raw in ({"service_type": "oil_change", "date": "2024-03-15", "notes": "x" * 50000, "shop": {"a": 1}, "cost": []},
                {"service_type": "Bremsen 泳ぐ 🔧", "date": "2024-03-15", "notes": "épaule [(.*)] \\"},
                {"service_type": 123, "date": "2024-03-15"}, {"service_type": True, "date": "2024-03-15", "mileage": False}):
        ok, _msg = Lg.log_carfax_entry(raw)
        assert ok is True, raw
    log = vehicle(path)["maintenance_log"]
    assert len(log) == 4 and len(log[0]["notes"]) == 1000 and log[1]["service_type"] == "Bremsen 泳ぐ 🔧"
    for bad in ({"service_type": "oil_change", "date": {"a": 1}}, {"service_type": "oil_change", "date": 1e30},
                {"service_type": "oil_change", "date": "2024-02-30"}):
        assert raises(lambda b=bad: Lg.log_carfax_entry(b), ValueError), bad
    shutil.rmtree(d)


@check("L5 a corrupt vehicle file at approval time: the action fails loudly, file left exactly as it was")
def _():
    path, d = fresh()
    aid, _m = A.propose_carfax(ENTRY)
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"vehicles": [ {"broken"')
    before = raw_bytes(path)
    out = A.approve_and_execute(aid)
    assert out.startswith("Execution failed") and status_of(aid) == "failed" and raw_bytes(path) == before
    assert raises(lambda: Lg.log_carfax_entry(ENTRY), Exception)
    shutil.rmtree(d)


@check("L5 a maintenance log that isn't a list is never overwritten; junk entries in it are preserved and don't break the duplicate check")
def _():
    path, d = fresh()
    seed(path, maintenance_log="oops")
    before = raw_bytes(path)
    assert raises(lambda: Lg.log_carfax_entry(ENTRY), RuntimeError) and raw_bytes(path) == before
    junk = ["j", None, 5, {"nope": 1}, {"source": "carfax"}]
    seed(path, maintenance_log=list(junk))
    assert Lg.log_carfax_entry(ENTRY)[0] is True
    log = vehicle(path)["maintenance_log"]
    assert log[:5] == junk and len(log) == 6
    assert Lg.log_carfax_entry(ENTRY)[0] is False
    shutil.rmtree(d)


@check("L5 hostile model answers (not-an-object, junk/absurd fields, impossible or relative dates) -> exactly ONE honest note, nothing queued, no crash")
def _():
    hostile = ["[]", "null", "123", "{}", '{"kind":"carfax"}',
               '{"kind":"carfax","service_type":"oil_change","date":"yesterday"}',
               '{"kind":"carfax","service_type":"oil_change","date":"2999-01-01"}',
               '{"kind":"carfax","service_type":{"a":1},"date":"2024-03-15"}',
               '{"kind":"carfax","service_type":"oil_change","date":"2024-03-15","mileage":-5}',
               '{"kind":"carfax","service_type":"oil_change","date":"2024-03-15","mileage":1e12}',
               "garbage {", ""]
    for raw in hostile:
        path, d = fresh()
        answers["carfax"] = raw
        notes = X.extract_and_propose(MSG)
        assert len(notes) == 1 and "couldn't" in notes[0] and queue_actions() == [], (raw, notes)
        shutil.rmtree(d)


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)