"""
DRIVE increment (b), Part 1 — L1, L2, L4, L5 tests for drive_logging.py
(normalizers + locked writers). No model, no keys, no cost. Uses TEMP files
only: your real vehicle.json is never touched.

Run from the repo root:  python -m agents.drive.test_drive_logging
(L3 — real end-to-end — comes after extraction is built in Part 3.)
"""
import json
import os
import re
import shutil
import tempfile
import threading
import time

from agents.drive import drive_logging as L
from agents.drive import drive_tools as t

SRC = os.path.join(t._REPO_ROOT, "agents", "drive", "drive_logging.py")
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


def fresh_path():
    d = tempfile.mkdtemp(prefix="drive_log_test_")
    os.environ["VEHICLE_DATA_PATH"] = os.path.join(d, "vehicle.json")
    return os.environ["VEHICLE_DATA_PATH"], d


def write_raw(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def raw_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    return False


def vehicle(path):
    return read(path)["vehicles"][0]


def seed(path, **fields):
    v = {"id": "vehicle_001", "active": True, "make": "Honda", "model": "Civic", "year": 2016,
         "vin": "TESTVIN", "current_mileage": 55500, "mileage_last_updated": None,
         "maintenance_log": [], "upcoming_maintenance": [], "gas_log": [], "issues": [], "recalls": []}
    v.update(fields)
    write_raw(path, {"vehicles": [v]})


today = time.strftime("%Y-%m-%d")

# ───────────────────────── L1 — STATIC ─────────────────────────

with open(SRC, encoding="utf-8") as _f:
    _src = _f.read()


@check("L1 writes go through the locked helper; no raw open()/json.dump in this file")
def _():
    assert "update_json" in _src
    assert not re.search(r"\bopen\(", _src) and "json.dump" not in _src


@check("L1 no bare 'except:', no secrets, no old-system path")
def _():
    assert not re.search(r"except\s*:", _src)
    assert "NEXUS SYSTEM" not in _src and "API_KEY" not in _src


@check("L1 drive_tools.py is still read-only (all writing lives in drive_logging.py)")
def _():
    with open(t.__file__, encoding="utf-8") as f:
        tools_src = f.read()
    assert "def log_" not in tools_src and "update_json" not in tools_src


@check("L1 the readers know both the tracker's field names and the old agent's")
def _():
    with open(t.__file__, encoding="utf-8") as f:
        tools_src = f.read()
    for name in ("due_mileage", "next_due_miles", "due_date", "next_due_date", "reported_date", "date_reported"):
        assert name in tools_src, name


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 mileage: commas/floats accepted; 0, missing, negative, NaN, absurd, bool, non-dict all rejected")
def _():
    assert L.normalize_mileage({"mileage": "55,500"}) == {"mileage": 55500}
    assert L.normalize_mileage({"mileage": 55500.0}) == {"mileage": 55500}
    for bad in (None, [], "x", 5, {}, {"mileage": None}, {"mileage": 0}, {"mileage": -5},
                {"mileage": "nan"}, {"mileage": 10**7}, {"mileage": True}, {"mileage": "lots"}):
        assert raises(lambda b=bad: L.normalize_mileage(b), ValueError), bad


@check("L2 maintenance: known service -> key + display name; free-text service kept; values tidied")
def _():
    m = L.normalize_maintenance({"service_type": "Oil Change", "mileage": "55,500", "date": "2026-01-10",
                                 "shop": "  Joe's  ", "cost": "42.5", "performed_by": "Dealership",
                                 "parts_used": "filter, 5 quarts"})
    assert m["service_type"] == "oil_change" and m["display_name"] == "Oil Change"
    assert m["mileage"] == 55500 and m["date"] == "2026-01-10"
    assert m["shop"] == "Joe's" and m["cost"] == 42.5 and m["performed_by"] == "shop"
    assert m["parts_used"] == ["filter", "5 quarts"]
    assert L.normalize_maintenance({"service": "tire-rotation"})["service_type"] == "tire_rotation"
    u = L.normalize_maintenance({"service_type": "Replaced left headlight"})
    assert u["service_type"] == "Replaced left headlight" and u["display_name"] == "Replaced left headlight"


@check("L2 maintenance: unstated values stay None (never 0 or invented); performed_by aliases map; junk -> None")
def _():
    n = L.normalize_maintenance({"service_type": "oil change"})
    assert n["mileage"] is None and n["cost"] is None and n["shop"] is None
    assert n["performed_by"] is None and n["parts_used"] == [] and n["notes"] == "" and n["date"] == today
    assert L.normalize_maintenance({"service_type": "oil_change", "cost": 0})["cost"] is None
    assert L.normalize_maintenance({"service_type": "oil_change", "mileage": 0})["mileage"] is None
    for said, want in (("dealer", "shop"), ("DIY", "diy"), ("myself", "diy"), ("a guy I know", None)):
        assert L.normalize_maintenance({"service_type": "oil_change", "performed_by": said})["performed_by"] == want
    assert L.normalize_maintenance({"service_type": "oil_change", "date": "2999-01-01"})["date"] == today
    assert L.normalize_maintenance({"service_type": "oil_change", "date": "last tuesday"})["date"] == today


@check("L2 maintenance rejects: not-a-dict, no service, 'gas', negative/NaN/absurd mileage or cost")
def _():
    for bad in (None, [], "oil", 5, {}, {"service_type": ""}, {"service_type": "  "},
                {"service_type": "gas"}, {"service_type": "Gas"},
                {"service_type": "oil_change", "mileage": -1}, {"service_type": "oil_change", "mileage": "nan"},
                {"service_type": "oil_change", "cost": 10**9}, {"service_type": "oil_change", "mileage": 10**8}):
        assert raises(lambda b=bad: L.normalize_maintenance(b), ValueError), bad


@check("L2 fill-up: total worked out from gallons x price, price from total / gallons, a stated total wins")
def _():
    f = L.normalize_fillup({"gallons": 10, "price_per_gallon": 3.5, "mileage": 56000, "date": "2026-01-10"})
    assert f["total_cost"] == 35 and f["gallons"] == 10 and f["mileage"] == 56000
    f = L.normalize_fillup({"gallons": 8, "total_cost": 28})
    assert f["price_per_gallon"] == 3.5 and f["total_cost"] == 28 and f["mileage"] is None
    f = L.normalize_fillup({"total_cost": 30})
    assert f["gallons"] is None and f["price_per_gallon"] is None and f["total_cost"] == 30
    f = L.normalize_fillup({"gallons": 9})
    assert f["total_cost"] is None and f["price_per_gallon"] is None
    f = L.normalize_fillup({"gallons": 10, "price_per_gallon": 3, "total_cost": 31})
    assert f["total_cost"] == 31 and f["price_per_gallon"] == 3
    f = L.normalize_fillup({"gallons": "9.5", "price_per_gallon": "$3.49", "mileage": "50,300"})
    assert f["gallons"] == 9.5 and f["mileage"] == 50300 and abs(f["total_cost"] - 33.155) < 0.01


@check("L2 fill-up rejects: nothing stated, zero/negative/absurd gallons, absurd price or total, NaN")
def _():
    for bad in (None, [], "gas", {}, {"mileage": 5000}, {"gallons": 0}, {"gallons": -2}, {"gallons": 500},
                {"gallons": 10, "price_per_gallon": 999}, {"total_cost": 10**6}, {"gallons": "nan"}):
        assert raises(lambda b=bad: L.normalize_fillup(b), ValueError), bad


@check("L2 issue: severity words map to low/medium/high; unstated or unknown severity is None; needs a description")
def _():
    i = L.normalize_issue({"description": " Check engine light on ", "severity": "Severe"})
    assert i["description"] == "Check engine light on" and i["severity"] == "high"
    assert L.normalize_issue({"description": "x", "severity": "moderate"})["severity"] == "medium"
    assert L.normalize_issue({"description": "x", "severity": "mild"})["severity"] == "low"
    assert L.normalize_issue({"description": "x"})["severity"] is None
    assert L.normalize_issue({"description": "x", "severity": "purple"})["severity"] is None
    assert L.normalize_issue({"description": "x"})["date"] == today
    for bad in (None, {}, {"description": ""}, {"severity": "high"}, "noise", {"description": {"a": 1}}):
        assert raises(lambda b=bad: L.normalize_issue(b), ValueError), bad


@check("L2 issue update input: needs an id and new_status 'resolved' (nothing else is accepted)")
def _():
    u = L.normalize_issue_update({"issue_id": " abc ", "new_status": "Resolved", "resolution_notes": "new sensor"})
    assert u["issue_id"] == "abc" and u["new_status"] == "resolved" and u["resolution_notes"] == "new sensor"
    for bad in (None, {}, {"issue_id": "a"}, {"issue_id": "a", "new_status": "open"},
                {"new_status": "resolved"}, "x", {"issue_id": "a", "new_status": "fixed"}):
        assert raises(lambda b=bad: L.normalize_issue_update(b), ValueError), bad


@check("L2 log_mileage: creates the file if missing, sets mileage, warns (but still saves) when LOWER")
def _():
    path, d = fresh_path()
    assert not os.path.exists(path)
    msg = L.log_mileage({"mileage": 55500})
    v = vehicle(path)
    assert v["current_mileage"] == 55500 and v["mileage_last_updated"]
    assert "55,500" in msg and "LOWER" not in msg
    msg = L.log_mileage({"mileage": 54000})
    assert vehicle(path)["current_mileage"] == 54000 and "LOWER" in msg and "55,500" in msg
    assert "LOWER" not in L.log_mileage({"mileage": 60000})
    shutil.rmtree(d)


@check("L2 maintenance write: exact keys, tracker-named schedule, correct due numbers, readers can read it")
def _():
    path, d = fresh_path()
    seed(path, current_mileage=50000)
    msg = L.log_maintenance({"service_type": "oil_change", "mileage": 50000, "date": "2026-01-10",
                             "shop": "Honda", "cost": 60, "performed_by": "dealership"})
    v = vehicle(path)
    e = v["maintenance_log"][0]
    for k in ("id", "source", "service_type", "display_name", "date", "logged_at", "mileage",
              "shop", "cost", "notes", "performed_by", "parts_used"):
        assert k in e, k
    assert e["source"] == "owner" and e["performed_by"] == "shop"
    up = v["upcoming_maintenance"]
    assert len(up) == 1 and up[0]["service_type"] == "oil_change"
    assert up[0]["due_mileage"] == 55000 and up[0]["due_date"] == "2026-07-09"
    assert up[0]["last_done_mileage"] == 50000 and up[0]["last_done_date"] == "2026-01-10"
    assert "next_due_miles" not in up[0]
    assert "55,000" in msg and "2026-07-09" in msg
    assert "Oil Change" in t.get_recent_maintenance() and "55,000" in t.get_upcoming_maintenance()
    shutil.rmtree(d)


@check("L2 a newer service of the same kind REPLACES its schedule entry (no duplicates); other services untouched")
def _():
    path, d = fresh_path()
    seed(path, current_mileage=50000)
    L.log_maintenance({"service_type": "tire_rotation", "mileage": 49000, "date": "2026-02-01"})
    L.log_maintenance({"service_type": "oil_change", "mileage": 50000, "date": "2026-01-10"})
    L.log_maintenance({"service_type": "oil_change", "mileage": 54800, "date": "2026-06-01"})
    v = vehicle(path)
    up = v["upcoming_maintenance"]
    oil = [u for u in up if u["service_type"] == "oil_change"]
    assert len(oil) == 1 and oil[0]["due_mileage"] == 59800 and oil[0]["last_done_date"] == "2026-06-01"
    assert len([u for u in up if u["service_type"] == "tire_rotation"]) == 1
    assert len(v["maintenance_log"]) == 3
    shutil.rmtree(d)


@check("L2 a BACKDATED service never rewinds the schedule (the old code's bug); an old-named entry is replaced by a newer one")
def _():
    path, d = fresh_path()
    old_entry = {"service_type": "oil_change", "display_name": "Oil Change", "last_done_mileage": 52000,
                 "last_done_date": "2026-06-16", "next_due_miles": 57000, "next_due_date": "2026-12-13"}
    seed(path, upcoming_maintenance=[old_entry])
    msg = L.log_maintenance({"service_type": "oil_change", "mileage": 40000, "date": "2025-01-01"})
    v = vehicle(path)
    assert v["upcoming_maintenance"] == [old_entry]
    assert len(v["maintenance_log"]) == 1 and "left alone" in msg
    L.log_maintenance({"service_type": "oil_change", "mileage": 58000, "date": "2026-09-01"})
    up = vehicle(path)["upcoming_maintenance"]
    assert len(up) == 1 and up[0]["due_mileage"] == 63000 and "next_due_miles" not in up[0]
    shutil.rmtree(d)


@check("L2 unknown service and wiper fluid make no schedule and no invented mileage; date-only / mileage-only schedules work")
def _():
    path, d = fresh_path()
    seed(path, current_mileage=55000)
    L.log_maintenance({"service_type": "wiper_fluid"})
    L.log_maintenance({"service_type": "Replaced left headlight", "mileage": 55000})
    v = vehicle(path)
    assert v["maintenance_log"][0]["mileage"] is None
    assert v["upcoming_maintenance"] == []
    L.log_maintenance({"service_type": "wiper_blades", "mileage": 50000, "date": "2026-01-10"})
    w = vehicle(path)["upcoming_maintenance"][0]
    assert w["due_mileage"] is None and w["due_date"] == "2027-01-10"
    L.log_maintenance({"service_type": "oil_change", "date": "2026-01-10"})       # mileage unstated
    o = [u for u in vehicle(path)["upcoming_maintenance"] if u["service_type"] == "oil_change"][0]
    assert o["due_mileage"] is None and o["last_done_mileage"] is None and o["due_date"] == "2026-07-09"
    shutil.rmtree(d)


@check("L2 current mileage only goes UP from a service/fill-up; never down; never from an unstated mileage")
def _():
    path, d = fresh_path()
    seed(path, current_mileage=50000)
    L.log_maintenance({"service_type": "oil_change", "mileage": 52000, "date": "2026-01-10"})
    v = vehicle(path)
    assert v["current_mileage"] == 52000 and v["mileage_last_updated"]
    L.log_maintenance({"service_type": "wiper_blades", "mileage": 40000, "date": "2026-01-10"})
    assert vehicle(path)["current_mileage"] == 52000
    L.log_maintenance({"service_type": "wiper_fluid"})
    assert vehicle(path)["current_mileage"] == 52000
    L.log_fillup({"gallons": 9, "mileage": 53000})
    assert vehicle(path)["current_mileage"] == 53000
    msg = L.log_maintenance({"service_type": "tire_rotation", "mileage": 60000})
    assert "raised" in msg and vehicle(path)["current_mileage"] == 60000
    shutil.rmtree(d)


@check("L2 MPG: nearest EARLIER fill-up by mileage (not list order); none when no earlier one / no mileage / implausible")
def _():
    path, d = fresh_path()
    seed(path, current_mileage=None)
    msg = L.log_fillup({"gallons": 10, "price_per_gallon": 3.0, "mileage": 50000, "date": "2026-01-01"})
    assert "MPG not calculated" in msg
    L.log_fillup({"gallons": 10, "price_per_gallon": 3.0, "mileage": 50300, "date": "2026-01-15"})
    L.log_fillup({"gallons": 5, "mileage": 50100, "date": "2026-01-08"})       # out of order on purpose
    L.log_fillup({"gallons": 10, "mileage": 50600, "date": "2026-01-20"})
    g = vehicle(path)["gas_log"]
    assert g[0]["mpg"] is None and g[1]["mpg"] == 30.0
    assert g[2]["mpg"] == 20.0          # 100 miles / 5 gal, vs the 50000 fill-up
    assert g[3]["mpg"] == 30.0          # vs 50300 (nearest lower), not vs 50100
    msg = L.log_fillup({"gallons": 1, "mileage": 90000})
    assert vehicle(path)["gas_log"][4]["mpg"] is None and "implausible" in msg
    L.log_fillup({"gallons": 8})
    assert vehicle(path)["gas_log"][5]["mpg"] is None
    shutil.rmtree(d)


@check("L2 fill-up write: exact keys, total worked out, mileage raised, the gas reader can read it")
def _():
    path, d = fresh_path()
    seed(path, current_mileage=50000)
    L.log_fillup({"gallons": 8.5, "price_per_gallon": 3.2, "mileage": 50400, "date": "2026-01-10"})
    e = vehicle(path)["gas_log"][0]
    for k in ("id", "date", "logged_at", "mileage", "gallons", "price_per_gallon", "total_cost", "mpg"):
        assert k in e, k
    assert abs(e["total_cost"] - 27.2) < 0.001
    assert vehicle(path)["current_mileage"] == 50400
    assert "27.20" in t.get_gas_summary()
    shutil.rmtree(d)


@check("L2 issue write: exact keys (tracker names), unstated severity is None, the open-issues reader shows it")
def _():
    path, d = fresh_path()
    seed(path)
    L.log_issue({"description": "Check engine light on", "severity": "high", "date": "2026-01-10"})
    e = vehicle(path)["issues"][0]
    for k in ("id", "description", "severity", "status", "reported_date", "logged_at",
              "notes", "resolved_date", "resolution_notes"):
        assert k in e, k
    assert e["status"] == "open" and e["severity"] == "high" and e["reported_date"] == "2026-01-10"
    assert e["resolved_date"] is None
    out = t.get_open_issues()
    assert "Check engine light on" in out and "2026-01-10" in out and "[HIGH]" in out
    L.log_issue({"description": "Squeak"})
    assert "[UNKNOWN]" in t.get_open_issues()
    write_raw(path, {"vehicles": [{"active": True, "issues": [
        {"id": "o1", "description": "old style", "severity": "mild", "date_reported": "2026-09-01", "status": "open"}]}]})
    assert "2026-09-01" in t.get_open_issues()        # the old agent's field name still reads fine
    shutil.rmtree(d)


@check("L2 issue update: resolves exactly the one issue by id, others untouched, reader stops listing it")
def _():
    path, d = fresh_path()
    seed(path)
    L.log_issue({"description": "Check engine light on"})
    L.log_issue({"description": "Squeaky brakes"})
    ids = [i["id"] for i in vehicle(path)["issues"]]
    ok, msg = L.update_issue_status({"issue_id": ids[0], "new_status": "resolved",
                                     "resolution_notes": "new gas cap", "date": "2026-02-02"})
    assert ok and "resolved" in msg and "Check engine light on" in msg
    a, b = vehicle(path)["issues"]
    assert a["status"] == "resolved" and a["resolved_date"] == "2026-02-02" and a["resolution_notes"] == "new gas cap"
    assert b["status"] == "open" and b["resolved_date"] is None
    out = t.get_open_issues()
    assert "Check engine light on" not in out and "Squeaky brakes" in out
    shutil.rmtree(d)


@check("L2 issue update never guesses: unknown id / already resolved / no issues list change NOTHING")
def _():
    path, d = fresh_path()
    seed(path)
    L.log_issue({"description": "Check engine light on"})
    iid = vehicle(path)["issues"][0]["id"]
    L.update_issue_status({"issue_id": iid, "new_status": "resolved"})
    before = read(path)
    ok, msg = L.update_issue_status({"issue_id": "nope", "new_status": "resolved"})
    assert not ok and "No issue" in msg
    ok, msg = L.update_issue_status({"issue_id": iid, "new_status": "resolved"})
    assert not ok and "already resolved" in msg
    assert read(path) == before
    seed(path, issues=None)
    before = read(path)
    ok, msg = L.update_issue_status({"issue_id": "x", "new_status": "resolved"})
    assert not ok and read(path) == before
    shutil.rmtree(d)


@check("L2 readers accept BOTH the tracker's and the old agent's schedule field names")
def _():
    path, d = fresh_path()
    seed(path, current_mileage=50000, upcoming_maintenance=[
        {"service_type": "oil_change", "display_name": "Oil Change", "due_mileage": 50300, "due_date": "2999-01-01"},
        {"service_type": "tire_rotation", "display_name": "Tire Rotation",
         "next_due_miles": 60000, "next_due_date": "2999-01-01"}])
    out = t.get_upcoming_maintenance()
    assert "50,300" in out and "60,000" in out
    assert "Oil Change" in out.split("UPCOMING SCHEDULE")[0]      # 300 miles away = coming due soon
    shutil.rmtree(d)


@check("L2 logging keeps everything already in the file (recalls dict, extra keys, junk entries, other vehicles)")
def _():
    path, d = fresh_path()
    seed(path, recalls={"searched_at": "x", "query": "q", "result": "r é"}, extra_key={"keep": 1},
         gas_log=["junk", None, {"mileage": 50000, "gallons": 10}],
         issues=[5, {"id": "i1", "description": "d", "status": "open"}],
         maintenance_log=[7],
         upcoming_maintenance=["j", {"service_type": "oil_change", "last_done_date": "2026-06-16",
                                     "next_due_miles": 57000}])
    data = read(path)
    data["vehicles"].append({"id": "vehicle_002", "active": False, "make": "Other"})
    data["top_extra"] = [1, 2]
    write_raw(path, data)
    other = read(path)["vehicles"][1]
    L.log_fillup({"gallons": 10, "mileage": 50300})
    L.log_maintenance({"service_type": "tire_rotation", "mileage": 50300})
    L.log_issue({"description": "new"})
    L.update_issue_status({"issue_id": "i1", "new_status": "resolved"})
    after = read(path)
    v = after["vehicles"][0]
    assert v["recalls"] == {"searched_at": "x", "query": "q", "result": "r é"} and v["extra_key"] == {"keep": 1}
    assert after["vehicles"][1] == other and after["top_extra"] == [1, 2]
    assert v["gas_log"][:3] == ["junk", None, {"mileage": 50000, "gallons": 10}] and len(v["gas_log"]) == 4
    assert v["gas_log"][3]["mpg"] == 30.0
    assert v["issues"][0] == 5 and v["maintenance_log"][0] == 7 and v["upcoming_maintenance"][0] == "j"
    assert len(v["issues"]) == 3 and v["issues"][1]["status"] == "resolved"
    shutil.rmtree(d)


@check("L2 a missing file is created automatically (Honda Civic starting structure) on the first log")
def _():
    path, d = fresh_path()
    assert not os.path.exists(path)
    L.log_issue({"description": "x"})
    v = vehicle(path)
    assert v["make"] == "Honda" and v["current_mileage"] is None and len(v["issues"]) == 1
    shutil.rmtree(d)


@check("L2 a real write stamps last_updated")
def _():
    path, d = fresh_path()
    seed(path)
    assert "last_updated" not in read(path)
    L.log_issue({"description": "x"})
    assert read(path)["last_updated"]
    shutil.rmtree(d)


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 simultaneous mixed logs: exactly the right counts, unique ids, valid JSON, zero errors")
def _():
    path, d = fresh_path()
    errors = []

    def go(n):
        try:
            k = n % 4
            if k == 0:
                L.log_maintenance({"service_type": f"custom job {n}", "mileage": 50000 + n})
            elif k == 1:
                L.log_fillup({"gallons": 10, "mileage": 51000 + n})
            elif k == 2:
                L.log_issue({"description": f"issue {n}"})
            else:
                L.log_mileage({"mileage": 52000 + n})
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go, args=(n,)) for n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    v = vehicle(path)
    assert not errors, errors
    assert len(v["maintenance_log"]) == 5 and len(v["gas_log"]) == 5 and len(v["issues"]) == 5
    ids = [e["id"] for key in ("maintenance_log", "gas_log", "issues") for e in v[key]]
    assert len(set(ids)) == 15
    assert isinstance(v["current_mileage"], int)
    shutil.rmtree(d)


@check("L4 20 threads all resolving the SAME issue: exactly one succeeds, 19 are told nothing changed")
def _():
    path, d = fresh_path()
    seed(path)
    L.log_issue({"description": "Check engine light on"})
    iid = vehicle(path)["issues"][0]["id"]
    results = []
    lock = threading.Lock()

    def go():
        r = L.update_issue_status({"issue_id": iid, "new_status": "resolved"})
        with lock:
            results.append(r)

    threads = [threading.Thread(target=go) for _ in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert sum(1 for ok, msg in results if ok) == 1, results
    assert len(results) == 20
    shutil.rmtree(d)


@check("L4 20 threads logging an oil change at once: 20 log entries, exactly ONE schedule entry")
def _():
    path, d = fresh_path()
    seed(path)
    errors = []

    def go(n):
        try:
            L.log_maintenance({"service_type": "oil_change", "mileage": 50000 + n, "date": "2026-01-10"})
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go, args=(n,)) for n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    v = vehicle(path)
    assert not errors, errors
    assert len(v["maintenance_log"]) == 20
    assert len([u for u in v["upcoming_maintenance"] if u.get("service_type") == "oil_change"]) == 1
    shutil.rmtree(d)


@check("L4 200 sequential fill-ups: all present, every MPG right, file stays valid, stays fast")
def _():
    path, d = fresh_path()
    seed(path, current_mileage=None)
    start = time.time()
    for n in range(200):
        L.log_fillup({"gallons": 10, "mileage": 50000 + n * 300})
    g = vehicle(path)["gas_log"]
    assert len(g) == 200 and g[0]["mpg"] is None and all(e["mpg"] == 30.0 for e in g[1:])
    assert time.time() - start < 30, time.time() - start
    shutil.rmtree(d)


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 corrupt JSON: every writer fails LOUDLY and the file is left exactly as it was")
def _():
    path, d = fresh_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"vehicles": [ {"broken"')
    before = raw_bytes(path)
    assert raises(lambda: L.log_mileage({"mileage": 50000}), Exception)
    assert raises(lambda: L.log_maintenance({"service_type": "oil_change"}), Exception)
    assert raises(lambda: L.log_fillup({"gallons": 9}), Exception)
    assert raises(lambda: L.log_issue({"description": "x"}), Exception)
    assert raises(lambda: L.update_issue_status({"issue_id": "a", "new_status": "resolved"}), Exception)
    assert raw_bytes(path) == before
    shutil.rmtree(d)


@check("L5 wrong-shape files (top-level list, vehicles not a list / empty / no dicts): RuntimeError, never overwritten")
def _():
    path, d = fresh_path()
    for content in ([1, 2, 3], {"vehicles": "oops"}, {"vehicles": []}, {"vehicles": [1, 2]}):
        write_raw(path, content)
        before = raw_bytes(path)
        assert raises(lambda: L.log_issue({"description": "x"}), RuntimeError), content
        assert raw_bytes(path) == before, content
    shutil.rmtree(d)


@check("L5 a list field that is NOT a list refuses to be overwritten, and NOTHING is partly saved")
def _():
    path, d = fresh_path()
    seed(path, maintenance_log="oops")
    before = raw_bytes(path)
    assert raises(lambda: L.log_maintenance({"service_type": "oil_change"}), RuntimeError)
    assert raw_bytes(path) == before
    seed(path, upcoming_maintenance={"a": 1})          # record would be added, THEN the schedule step fails
    before = raw_bytes(path)
    assert raises(lambda: L.log_maintenance({"service_type": "oil_change", "mileage": 50000}), RuntimeError)
    assert raw_bytes(path) == before
    assert vehicle(path)["maintenance_log"] == []
    seed(path, gas_log={"a": 1})
    assert raises(lambda: L.log_fillup({"gallons": 9}), RuntimeError)
    seed(path, issues="x")
    assert raises(lambda: L.log_issue({"description": "x"}), RuntimeError)
    shutil.rmtree(d)


@check("L5 missing or null list fields are created cleanly")
def _():
    path, d = fresh_path()
    write_raw(path, {"vehicles": [{"id": "v", "active": True}]})
    L.log_fillup({"gallons": 9}); L.log_issue({"description": "x"}); L.log_maintenance({"service_type": "oil_change"})
    v = vehicle(path)
    assert len(v["gas_log"]) == 1 and len(v["issues"]) == 1 and len(v["maintenance_log"]) == 1
    write_raw(path, {"vehicles": [{"active": True, "gas_log": None, "issues": None,
                                   "maintenance_log": None, "upcoming_maintenance": None}]})
    L.log_fillup({"gallons": 9}); L.log_issue({"description": "x"}); L.log_maintenance({"service_type": "oil_change"})
    v = vehicle(path)
    assert len(v["gas_log"]) == 1 and len(v["issues"]) == 1 and len(v["upcoming_maintenance"]) == 1
    shutil.rmtree(d)


@check("L5 50,000-character text is cut to 1,000; unicode and emoji survive intact")
def _():
    path, d = fresh_path()
    L.log_issue({"description": "y" * 50000, "notes": "Schwimmen 泳ぐ 🏊 résumé"})
    L.log_maintenance({"service_type": "Brake job 🔧 épaule", "notes": "x" * 50000, "shop": "Müller & Söhne"})
    v = vehicle(path)
    i, m = v["issues"][0], v["maintenance_log"][0]
    assert len(i["description"]) == 1000 and i["notes"] == "Schwimmen 泳ぐ 🏊 résumé"
    assert len(m["notes"]) == 1000 and m["service_type"] == "Brake job 🔧 épaule" and m["shop"] == "Müller & Söhne"
    shutil.rmtree(d)


@check("L5 hostile field types (bool, nested dicts, huge lists, regex characters) never crash or corrupt")
def _():
    path, d = fresh_path()
    m = L.normalize_maintenance({"service_type": "oil_change", "mileage": False, "cost": [], "shop": {"a": 1},
                                 "notes": {"x": 1}, "performed_by": ["x"], "parts_used": {"a": 1}})
    assert m["mileage"] is None and m["cost"] is None and m["shop"] is None
    assert m["notes"] == "" and m["performed_by"] is None and m["parts_used"] == []
    assert len(L.normalize_maintenance({"service_type": "oil_change", "parts_used": ["p"] * 500})["parts_used"]) == 30
    L.log_issue({"description": "knee (left) [ACL]+*?"})
    ok, msg = L.update_issue_status({"issue_id": "(.*)[", "new_status": "resolved"})
    assert ok is False
    shutil.rmtree(d)


@check("L5 with several vehicles, writes go to the ACTIVE one only")
def _():
    path, d = fresh_path()
    write_raw(path, {"vehicles": [{"id": "a", "active": False, "gas_log": []},
                                  {"id": "b", "active": True, "gas_log": []}]})
    L.log_fillup({"gallons": 9})
    data = read(path)
    assert data["vehicles"][0]["gas_log"] == [] and len(data["vehicles"][1]["gas_log"]) == 1
    shutil.rmtree(d)


@check("L5 invalid input is rejected BEFORE the file is touched (a missing file is not even created)")
def _():
    path, d = fresh_path()
    for fn in (lambda: L.log_fillup({}), lambda: L.log_issue(None), lambda: L.log_mileage({"mileage": -1}),
               lambda: L.log_maintenance({"service_type": "gas"}),
               lambda: L.update_issue_status({"issue_id": "a", "new_status": "open"})):
        assert raises(fn, ValueError)
    assert not os.path.exists(path)
    shutil.rmtree(d)


# ───────────────────────── SUMMARY ─────────────────────────

passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)