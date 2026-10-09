"""
DRIVE UNITS FIX — L1, L2, L4, L5 tests. The fix: the model reports a mileage or fuel
amount EXACTLY as Joey said it (plus a unit only if he wrote one); PYTHON converts
kilometers and liters; a unit the message doesn't contain is ignored. The local model
is FAKED (no Ollama, no keys, no cost). TEMP files only.

Run from the repo root:  python -m agents.drive.test_drive_units
"""
import json
import os
import re
import shutil
import tempfile
import threading

_QUEUE_DIR = tempfile.mkdtemp(prefix="drive_units_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from agents.drive import drive_actions as A
from agents.drive import drive_extract as X
from agents.drive import drive_logging as L
from agents.drive import drive_units as U
from shared import pending_actions as pa

QUEUE = pa.PENDING_ACTIONS_PATH
_HERE = os.path.dirname(os.path.abspath(__file__))
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


def raises(fn, exc=Exception):
    try:
        fn()
    except exc:
        return True
    return False


def fresh():
    d = tempfile.mkdtemp(prefix="drive_units_test_")
    os.environ["VEHICLE_DATA_PATH"] = os.path.join(d, "vehicle.json")
    if os.path.exists(QUEUE):
        os.remove(QUEUE)
    return os.environ["VEHICLE_DATA_PATH"], d


def queue_actions():
    if not os.path.exists(QUEUE):
        return []
    with open(QUEUE, encoding="utf-8") as f:
        return json.load(f)["actions"]


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_src(name):
    with open(os.path.join(_HERE, name), encoding="utf-8") as f:
        return f.read()


def km(n):
    return int(round(n * 0.621371))


def run(message, payload):
    """One faked-model extraction. Returns (queued actions, notes)."""
    path, d = fresh()
    X.complete_ollama_json = lambda system_prompt, user_text, timeout=90.0: json.dumps(payload)
    notes = X.extract_and_propose(message)
    actions = queue_actions()
    shutil.rmtree(d)
    return actions, notes


def only(actions, action_type):
    hits = [a for a in actions if a["type"] == action_type]
    assert hits, (action_type, [a["type"] for a in actions])
    return hits[0]["details"]


# ───────────────────────── L1 — STATIC ─────────────────────────

@check("L1 the prompts no longer tell the model to convert; all four carry the unit fields and the NEVER-convert rule")
def _():
    for kind in (X.KIND_MILEAGE, X.KIND_FILLUP, X.KIND_MAINTENANCE, X.KIND_CARFAX):
        p = X._PROMPTS[kind]
        assert "Convert units" not in p and "1 L = 0.264" not in p and "1 km = 0.621" not in p, kind
        assert "NEVER convert" in p, kind
        if kind == X.KIND_FILLUP:
            assert '"fuel_amount"' in p and '"fuel_unit"' in p and '"gallons": 10' not in p
        assert '"mileage_unit"' in p or kind == X.KIND_FILLUP, kind
    assert '"mileage_unit"' in X._PROMPTS[X.KIND_FILLUP]


@check("L1 conversion arithmetic lives ONLY in drive_units.py / drive_logging.py, never in the extraction module")
def _():
    ex = read_src("drive_extract.py")
    assert "0.264172" in read_src("drive_units.py") and "0.621371" in read_src("drive_units.py")
    for banned in ("0.264", "0.621", "km_to_miles", "liters_to_gallons"):
        assert banned not in ex, banned
    assert "drive_units" in ex and "drive_logging" not in ex and ".lower()" not in ex


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 unit_family recognises the unit words and nothing else")
def _():
    for text, fam in ((" KM ", "km"), ("Kilometres", "km"), ("mi", "miles"), ("Miles", "miles"),
                      ("Gal", "gallons"), ("gallons", "gallons"), ("L", "liters"), ("liter", "liters"), ("Litres", "liters")):
        assert U.unit_family(text) == fam, text
    for junk in ("stone", "", None, 123, {}, [], ["km"], "x" * 50000, "ｋｍ"):
        assert U.unit_family(junk) == "", junk


@check("L2 mileage: km converted by PYTHON; miles / no unit / unknown unit unchanged")
def _():
    assert L.normalize_mileage({"mileage": 80000, "mileage_unit": "km"}) == {"mileage": km(80000)}
    assert L.normalize_mileage({"mileage": "80,000", "mileage_unit": "Kilometers"}) == {"mileage": km(80000)}
    for kw in ({}, {"mileage_unit": ""}, {"mileage_unit": "miles"}, {"mileage_unit": "furlongs"}):
        assert L.normalize_mileage(dict({"mileage": 80000}, **kw)) == {"mileage": 80000}, kw


@check("L2 maintenance and Carfax mileage convert km the same way (Carfax inherits it)")
def _():
    m = L.normalize_maintenance({"service_type": "oil change", "mileage": 80000, "mileage_unit": "km", "cost": 65})
    assert m["mileage"] == km(80000) and m["cost"] == 65
    c = L.normalize_carfax({"service_type": "oil_change", "date": "2024-03-15", "mileage": 80000, "mileage_unit": "km"})
    assert c["mileage"] == km(80000) and c["performed_by"] == "previous_owner"
    assert L.normalize_maintenance({"service_type": "oil change", "mileage": 56000})["mileage"] == 56000


@check("L2 fill-up: liters converted by PYTHON; price per gallon worked out from the converted gallons")
def _():
    f = L.normalize_fillup({"fuel_amount": 20, "fuel_unit": "liters", "total_cost": 30})
    g = round(20 * 0.264172, 2)
    assert f["gallons"] == g == 5.28 and f["price_per_gallon"] == round(30 / g, 3) and f["total_cost"] == 30
    f2 = L.normalize_fillup({"fuel_amount": 20, "fuel_unit": "L", "total_cost": 30, "mileage": 80000, "mileage_unit": "km"})
    assert f2["gallons"] == g and f2["mileage"] == km(80000)


@check("L2 fill-up: gallons stated, no unit, unknown unit and the older 'gallons' key are all taken as gallons; fuel_amount wins")
def _():
    for payload in ({"fuel_amount": 10, "fuel_unit": "gallons", "total_cost": 30}, {"fuel_amount": 10, "total_cost": 30},
                    {"fuel_amount": 10, "fuel_unit": "barrels", "total_cost": 30}, {"gallons": 10, "total_cost": 30},
                    {"fuel_amount": 10, "gallons": 99, "total_cost": 30}):
        f = L.normalize_fillup(payload)
        assert f["gallons"] == 10 and f["price_per_gallon"] == 3.0, payload


@check("L2 clean records are idempotent: re-checking what was queued never converts twice")
def _():
    f = L.normalize_fillup({"fuel_amount": 20, "fuel_unit": "liters", "total_cost": 30, "mileage": 80000, "mileage_unit": "km"})
    assert L.normalize_fillup(f) == f
    m = L.normalize_mileage({"mileage": 80000, "mileage_unit": "km"})
    assert L.normalize_mileage(m) == m
    mt = L.normalize_maintenance({"service_type": "oil change", "mileage": 80000, "mileage_unit": "km"})
    assert L.normalize_maintenance(mt)["mileage"] == mt["mileage"]


@check("L2 out-of-range after conversion is refused: 10 million km, 500 liters, negatives")
def _():
    assert raises(lambda: L.normalize_mileage({"mileage": 10**7, "mileage_unit": "km"}), ValueError)
    assert raises(lambda: L.normalize_fillup({"fuel_amount": 500, "fuel_unit": "liters", "total_cost": 30}), ValueError)
    assert raises(lambda: L.normalize_mileage({"mileage": -5, "mileage_unit": "km"}), ValueError)
    assert raises(lambda: L.normalize_fillup({"fuel_amount": -5, "fuel_unit": "liters", "total_cost": 30}), ValueError)


@check("L2 trigger words: a km mileage statement and a liters fill-up are now noticed at all")
def _():
    assert X.KIND_MILEAGE in X.detect_report_kinds("my car has 80,000 km on it")
    assert X.KIND_FILLUP in X.detect_report_kinds("bought 20 liters for $30")
    assert X.KIND_MILEAGE in X.detect_report_kinds("my odometer says 80,000")


# ───────────────────────── L2 — END TO END WITH A FAKED MODEL ─────────────────────────

@check("L2 end to end: Joey wrote km -> converted exactly once by Python and shown in miles")
def _():
    actions, notes = run("my car has 80,000 km on it", {"kind": "mileage", "mileage": 80000, "mileage_unit": "km"})
    assert only(actions, "log_mileage") == {"mileage": km(80000)}
    assert f"{km(80000):,} miles" in notes[0]


@check("L2 end to end: the model GUESSES km but Joey gave no unit -> NOT converted")
def _():
    actions, notes = run("my odometer says 80,000", {"kind": "mileage", "mileage": 80000, "mileage_unit": "km"})
    assert only(actions, "log_mileage") == {"mileage": 80000}


@check("L2 end to end: liters stated ('20 liters' and attached '20L') are converted; a guessed 'liters' for '40' is NOT")
def _():
    for msg in ("filled up with 20 liters for $30", "filled up with 20L for $30"):
        actions, _n = run(msg, {"kind": "fillup", "fuel_amount": 20, "fuel_unit": "liters", "total_cost": 30})
        assert only(actions, "log_fillup")["gallons"] == 5.28, msg
    for msg in ("filled up 40 for $50", "I'll be honest, filled up 40 for $50"):
        actions, _n = run(msg, {"kind": "fillup", "fuel_amount": 40, "fuel_unit": "liters", "total_cost": 50})
        d = only(actions, "log_fillup")
        assert d["gallons"] == 40 and d["price_per_gallon"] == 1.25, (msg, d)


@check("L2 end to end: maintenance and Carfax km are converted; a guessed km on a miles message is not")
def _():
    actions, _n = run("got an oil change at 80,000 km for $65",
                      {"kind": "maintenance", "service_type": "oil_change", "mileage": 80000, "mileage_unit": "km", "cost": 65})
    assert only(actions, "log_maintenance")["mileage"] == km(80000)
    actions, _n = run("carfax shows an oil change on 2024-03-15 at 80,000 km",
                      {"kind": "carfax", "service_type": "oil_change", "date": "2024-03-15", "mileage": 80000, "mileage_unit": "km"})
    assert only(actions, "log_carfax")["mileage"] == km(80000)
    actions, _n = run("got an oil change at 56,000 miles for $65",
                      {"kind": "maintenance", "service_type": "oil_change", "mileage": 56000, "mileage_unit": "km", "cost": 65})
    assert only(actions, "log_maintenance")["mileage"] == 56000


@check("L2 older-shaped model answers (gallons key, no unit keys) still work exactly as before")
def _():
    actions, _n = run("just fueled up 10 gal for $30", {"kind": "fillup", "gallons": 10, "total_cost": 30})
    d = only(actions, "log_fillup")
    assert d["gallons"] == 10 and d["price_per_gallon"] == 3.0


@check("L2 approval saves miles/gallons only: no unit keys in the vehicle file; the converted numbers are what's saved")
def _():
    path, d = fresh()
    X.complete_ollama_json = lambda s, u, timeout=90.0: json.dumps(
        {"kind": "fillup", "fuel_amount": 20, "fuel_unit": "liters", "total_cost": 30, "mileage": 80000, "mileage_unit": "km"})
    X.extract_and_propose("filled up with 20 liters for $30, odometer says 80,000 km")
    q = queue_actions()
    assert len(q) >= 1
    fill = [a for a in q if a["type"] == "log_fillup"][0]
    assert "logged" in A.approve_and_execute(fill["id"]).lower()
    vehicle = read_json(path)["vehicles"][0]
    entry = vehicle["gas_log"][-1]
    assert entry["gallons"] == 5.28 and entry["mileage"] == km(80000) and vehicle["current_mileage"] == km(80000)
    assert not any(k in entry for k in ("fuel_amount", "fuel_unit", "mileage_unit"))
    shutil.rmtree(d)


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 threads x 50 conversions at once: every result exactly right, no cross-talk")
def _():
    bad, lock = [], threading.Lock()

    def worker(i):
        for n in range(50):
            v = 1000 + i * 50 + n
            m = L.normalize_mileage({"mileage": v, "mileage_unit": "km"})
            f = L.normalize_fillup({"fuel_amount": 10 + n, "fuel_unit": "liters", "total_cost": 30})
            ok = m == {"mileage": km(v)} and f["gallons"] == round((10 + n) * 0.264172, 2)
            if not ok:
                with lock:
                    bad.append((i, n))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert bad == [], bad[:3]


@check("L4 20 simultaneous km mileage proposals: all 20 queued with the converted value, none lost")
def _():
    path, d = fresh()
    ids, lock = [], threading.Lock()

    def worker(i):
        aid, _msg = A.propose_mileage({"mileage": 1000 + i, "mileage_unit": "km"})
        with lock:
            ids.append(aid)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    q = queue_actions()
    assert len(q) == 20 and len(set(ids)) == 20
    assert sorted(a["details"]["mileage"] for a in q) == sorted(km(1000 + i) for i in range(20))
    shutil.rmtree(d)


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 junk unit words never crash and never convert: None, numbers, lists, dicts, 50,000 characters, unicode")
def _():
    for u in (None, 123, ["km"], {"a": 1}, "x" * 50000, "ｋｍ", "килограмм", "🚗"):
        assert L.normalize_mileage({"mileage": 80000, "mileage_unit": u}) == {"mileage": 80000}, u
        assert L.normalize_fillup({"fuel_amount": 20, "fuel_unit": u, "total_cost": 30})["gallons"] == 20, u


@check("L5 junk amounts: words become 'not stated'; NaN / infinity are refused loudly (same as before)")
def _():
    f = L.normalize_fillup({"fuel_amount": "far", "fuel_unit": "liters", "total_cost": 30})
    assert f["gallons"] is None and f["total_cost"] == 30
    f2 = L.normalize_fillup({"fuel_amount": True, "gallons": 10, "total_cost": 30})
    assert f2["gallons"] == 10
    assert raises(lambda: L.normalize_mileage({"mileage": "far", "mileage_unit": "km"}), ValueError)      # nothing stated
    for v in ("nan", "inf", float("nan"), float("inf")):
        assert raises(lambda: L.normalize_mileage({"mileage": v, "mileage_unit": "km"}), ValueError), v
        assert raises(lambda: L.normalize_fillup({"fuel_amount": v, "fuel_unit": "liters", "total_cost": 30}), ValueError), v


@check("L5 the guard never crashes on junk: non-string units, missing keys, 50,000-character messages, unicode")
def _():
    for data in ({}, {"mileage_unit": 5, "fuel_unit": None}, {"mileage_unit": ["km"], "fuel_unit": {"a": 1}},
                 {"mileage_unit": "km"}, {"fuel_unit": "liters"}, {"mileage_unit": "x" * 50000}):
        X._enforce_stated_units(data, "my odometer says 80,000 🚗" + "y" * 50000)
    d = {"mileage_unit": "km", "fuel_unit": "liters"}
    X._enforce_stated_units(d, "")
    assert d == {"mileage_unit": "", "fuel_unit": ""}
    d2 = {"mileage_unit": "km", "fuel_unit": "liters"}
    X._enforce_stated_units(d2, "80,000km and 20L")
    assert d2 == {"mileage_unit": "km", "fuel_unit": "liters"}


@check("L5 words that merely LOOK like units never count: 'I'll', 'minutes', 'mild', 'kilo' alone")
def _():
    for msg in ("I'll say 80,000", "it took 30 minutes, 80,000", "mild day, 80,000"):
        d = {"mileage_unit": "km", "fuel_unit": "liters"}
        X._enforce_stated_units(d, msg)
        assert d == {"mileage_unit": "", "fuel_unit": ""}, msg


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)