"""
DRIVE increment (a), Part 1 — L1 (static) + L2 (smoke) tests for
prompt.py and drive_tools.py. Uses TEMP files only: your real
vehicle.json is never touched.

Run from the repo root:  python -m agents.drive.test_drive_tools
"""
import json
import os
import re
import shutil
import tempfile
import threading

from agents.drive import drive_tools as t
from agents.drive.prompt import DRIVE_PROMPT

REPO_ROOT = t._REPO_ROOT
TOOLS_SRC = os.path.join(REPO_ROOT, "agents", "drive", "drive_tools.py")

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
    d = tempfile.mkdtemp(prefix="drive_test_")
    os.environ["VEHICLE_DATA_PATH"] = os.path.join(d, "vehicle.json")
    return os.environ["VEHICLE_DATA_PATH"], d


def write_raw(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


# ───────────────────────── L1 — STATIC ─────────────────────────

@check("L1 prompt matches the old reference exactly (1,946 chars)")
def _():
    ref = os.path.join(REPO_ROOT, "reference", "agent_prompts.json")
    with open(ref, encoding="utf-8") as f:
        assert DRIVE_PROMPT == json.load(f)["drive"]
    assert len(DRIVE_PROMPT) == 1946


@check("L1 no hardcoded old-system path or secret in drive_tools.py")
def _():
    with open(TOOLS_SRC, encoding="utf-8") as f:
        src = f.read()
    assert not re.search(r"D:\\\\Projects\\\\NEXUS SYSTEM", src)
    assert not re.search(r"(api[_-]?key|sk-ant|AIza)\s*=\s*['\"]", src, re.I)
    assert "serpapi.com" not in src and "requests.get" not in src  # Lesson #9: no duplicate search here


@check("L1 every open() call passes encoding= (Windows cp1252 lesson)")
def _():
    with open(TOOLS_SRC, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if re.search(r"\bopen\(", line) and not line.strip().startswith("#"):
                assert "encoding=" in line, f"line {n}: {line.strip()}"


@check("L1 no bare 'except:' and no write-tools built yet")
def _():
    with open(TOOLS_SRC, encoding="utf-8") as f:
        src = f.read()
    assert not re.search(r"except\s*:", src)
    for name in ("def log_maintenance", "def log_gas_fillup", "def log_issue",
                 "def add_vehicle", "def set_initial_mileage", "def update_mileage",
                 "def log_carfax_entry", "def log_wiper_fluid", "def search_recalls"):
        assert name not in src, f"{name} belongs to increment (b)"


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 default path is FORGE-only, never the old NEXUS SYSTEM file")
def _():
    os.environ.pop("VEHICLE_DATA_PATH", None)
    p = t.get_data_path()
    assert "NEXUS SYSTEM" not in p
    assert p.endswith(os.path.join("data", "vehicle.json"))


@check("L2 auto-create: missing file gets Joey's real car, correct VIN, under a lock")
def _():
    path, d = fresh_path()
    assert not os.path.exists(path)
    data = t.load_data()
    assert os.path.exists(path)
    v = t.get_active_vehicle(data)
    assert v["make"] == "Honda" and v["model"] == "Civic" and v["year"] == 2016
    assert v["vin"] == "19XFC2F57GE016309"
    assert v["current_mileage"] is None
    assert not os.path.exists(path + ".tmp")
    shutil.rmtree(d)


@check("L2 empty-log readers return their clean 'nothing yet' message")
def _():
    path, d = fresh_path()
    assert t.get_recent_maintenance() == "No maintenance history logged yet."
    assert t.get_full_maintenance_history() == "No maintenance history logged yet."
    assert t.get_gas_summary() == "No gas fill-ups logged yet."
    assert "No upcoming maintenance" in t.get_upcoming_maintenance()
    assert t.get_open_issues() == "No open issues."
    assert "not yet recorded" in t.get_vehicle_info()
    assert "VEHICLE DATA SUMMARY" in t.get_data_summary_for_llm()
    shutil.rmtree(d)


@check("L2 realistic real-shaped data reads correctly")
def _():
    path, d = fresh_path()
    write_raw(path, {"vehicles": [{
        "id": "vehicle_001", "active": True, "make": "Honda", "model": "Civic",
        "year": 2016, "vin": "19XFC2F57GE016309", "current_mileage": 48200,
        "maintenance_log": [
            {"service_type": "oil_change", "display_name": "Oil Change", "date": "2026-06-01",
             "mileage": 45000, "shop": "Honda Dealership", "cost": 89.99, "performed_by": "dealership"},
            {"service_type": "tire_rotation", "date": "2026-08-15", "mileage": 47500, "source": "carfax"},
        ],
        "gas_log": [
            {"date": "2026-08-01", "mileage": 47000, "gallons": 11.2, "price_per_gallon": 3.45,
             "total_cost": 38.64, "mpg": None},
            {"date": "2026-08-20", "mileage": 47500, "gallons": 10.8, "price_per_gallon": 3.5,
             "total_cost": 37.8, "mpg": 46.3},
        ],
        "upcoming_maintenance": [
            {"service_type": "oil_change", "display_name": "Oil Change",
             "next_due_miles": 50000, "next_due_date": "2026-12-01"},
        ],
        "issues": [{"description": "faint clicking noise on left turns", "severity": "mild",
                     "date_reported": "2026-09-01", "status": "open"}],
    }]})
    info = t.get_vehicle_info()
    assert "2016 Honda Civic" in info and "48,200 miles" in info
    maint = t.get_recent_maintenance()
    assert "Oil Change" in maint and "45,000 miles" in maint and "[Carfax]" in maint
    gas = t.get_gas_summary()
    assert "2 fill-ups" in gas and "MPG: 46.3" in gas
    upcoming = t.get_upcoming_maintenance()
    assert "Oil Change" in upcoming
    issues = t.get_open_issues()
    assert "clicking noise" in issues and "[MILD]" in issues
    shutil.rmtree(d)


@check("L2 mixed real-world junk (missing keys, wrong types, non-dict entries) never crash")
def _():
    path, d = fresh_path()
    write_raw(path, {
        "vehicles": [
            "garbage", None, 5,
            {"active": False, "make": "Toyota"},  # missing lots of fields
            {"active": True, "make": "Honda", "model": "Civic", "year": 2016,
             "vin": "19XFC2F57GE016309", "current_mileage": 48200,
             "maintenance_log": [None, "junk", {}, {"service_type": "oil_change"},
                                  {"service_type": "weird_type", "date": "2026-01-01"}],
             "gas_log": [None, {"date": "2026-01-01"}],  # incomplete entry, no gallons/cost
             "upcoming_maintenance": [{"service_type": "oil_change", "next_due_miles": "notanumber",
                                        "next_due_date": "not-a-date"}],
             "issues": [None, {"status": "open"}]},  # missing description/severity
        ]
    })
    assert isinstance(t.get_vehicle_info(), str)
    assert isinstance(t.get_recent_maintenance(), str)
    assert isinstance(t.get_full_maintenance_history(), str)
    gas = t.get_gas_summary()
    assert "incomplete entry" in gas
    upcoming = t.get_upcoming_maintenance()
    assert "schedule unclear" in upcoming or "date unclear" in upcoming
    issues = t.get_open_issues()
    assert "[UNKNOWN]" in issues
    assert "VEHICLE DATA SUMMARY" in t.get_data_summary_for_llm()
    shutil.rmtree(d)


@check("L2 empty/all-invalid vehicles list fails loudly, not KeyError/IndexError")
def _():
    path, d = fresh_path()
    write_raw(path, {"vehicles": []})
    try:
        t.get_active_vehicle(t.load_data())
        raise AssertionError("should have raised")
    except RuntimeError as e:
        assert "No vehicle" in str(e)
    write_raw(path, {"vehicles": ["junk", None, 5]})
    try:
        t.get_active_vehicle(t.load_data())
        raise AssertionError("should have raised")
    except RuntimeError as e:
        assert "valid vehicle" in str(e)
    shutil.rmtree(d)


@check("L2 corrupt JSON fails LOUDLY with a specific error")
def _():
    path, d = fresh_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"vehicles": [')
    try:
        t.load_data()
        raise AssertionError("should have raised")
    except RuntimeError as e:
        assert "malformed" in str(e)
    shutil.rmtree(d)


@check("L2 top-level JSON list fails loudly (wrong shape)")
def _():
    path, d = fresh_path()
    write_raw(path, [1, 2, 3])
    try:
        t.load_data()
        raise AssertionError("should have raised")
    except RuntimeError as e:
        assert "wrong shape" in str(e)
    shutil.rmtree(d)


@check("L2 mid-write read: file fixed during the retry window loads fine")
def _():
    path, d = fresh_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"vehicles": [')

    good = {"vehicles": [{"active": True, "make": "Honda", "model": "Civic", "year": 2016, "vin": "x"}]}

    def fix_soon():
        import time
        time.sleep(0.1)
        write_raw(path, good)

    th = threading.Thread(target=fix_soon)
    th.start()
    data = t.load_data()
    th.join()
    assert data == good
    shutil.rmtree(d)


@check("L2 20 threads hitting a brand-new file at once: one clean file, zero errors")
def _():
    path, d = fresh_path()
    errors, created = [], []

    def worker():
        try:
            created.append(t.initialize_vehicle_data())
            t.load_data()
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for th in threads: th.start()
    for th in threads: th.join()
    assert not errors, errors
    assert created.count(True) == 1, created
    with open(path, encoding="utf-8") as f:
        assert json.load(f)["vehicles"][0]["vin"] == "19XFC2F57GE016309"
    assert not os.path.exists(path + ".tmp")
    shutil.rmtree(d)


@check("L2 reading never modifies an existing file (live-data safety)")
def _():
    path, d = fresh_path()
    write_raw(path, {"vehicles": [{"active": True, "make": "Honda", "model": "Civic",
                                    "year": 2016, "vin": "x", "current_mileage": 100}]})
    with open(path, "rb") as f:
        before = f.read()
    t.get_vehicle_info(); t.get_recent_maintenance(); t.get_gas_summary()
    t.get_upcoming_maintenance(); t.get_open_issues(); t.get_data_summary_for_llm()
    with open(path, "rb") as f:
        assert f.read() == before
    shutil.rmtree(d)


@check("L2 multi-vehicle: inactive vehicle ignored, list_vehicles shows both")
def _():
    path, d = fresh_path()
    write_raw(path, {"vehicles": [
        {"active": False, "make": "Toyota", "model": "Corolla", "year": 2012, "current_mileage": 90000},
        {"active": True, "make": "Honda", "model": "Civic", "year": 2016, "vin": "x", "current_mileage": 48200},
    ]})
    info = t.get_vehicle_info()
    assert "Honda Civic" in info and "Corolla" not in info
    lst = t.list_vehicles()
    assert "[ACTIVE]" in lst and "[archived]" in lst and "Corolla" in lst
    shutil.rmtree(d)


passed = sum(1 for _, ok, _ in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
if passed != len(_results):
    raise SystemExit(1)