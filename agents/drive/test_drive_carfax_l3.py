"""
DRIVE increment (b), Part 5 — L3: REAL local model (Ollama + gemma3:12b) extracting typed
Carfax records. No cloud calls, no cost. TEMP data and queue files only.

For each case it prints what DRIVE would show you plus the exact data queued. Mechanical
checks catch the obvious; YOU read the output: exactly what you said? nothing invented?

Run from the repo root:  python -m agents.drive.test_drive_carfax_l3
"""
import json
import os
import tempfile
import time

_QUEUE_DIR = tempfile.mkdtemp(prefix="drive_carfax_l3_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")
_DATA_DIR = tempfile.mkdtemp(prefix="drive_carfax_l3_data_")
os.environ["VEHICLE_DATA_PATH"] = os.path.join(_DATA_DIR, "vehicle.json")

from agents.drive import drive_actions as A
from agents.drive import drive_extract as X
from agents.drive import drive_logging as Lg
from agents.drive import drive_tools as t
from shared import pending_actions as pa

QUEUE = pa.PENDING_ACTIONS_PATH
VEHICLE = os.environ["VEHICLE_DATA_PATH"]
_passed = 0
_total = 0


def queue():
    if not os.path.exists(QUEUE):
        return []
    with open(QUEUE, encoding="utf-8") as f:
        return json.load(f)["actions"]


def vehicle():
    with open(VEHICLE, encoding="utf-8") as f:
        return json.load(f)["vehicles"][0]


def reset():
    if os.path.exists(QUEUE):
        os.remove(QUEUE)
    if os.path.exists(VEHICLE):
        os.remove(VEHICLE)
    Lg.log_mileage({"mileage": 55500})


def case(title, message, expect):
    global _passed, _total
    _total += 1
    print("\n" + "=" * 78 + f"\nCASE: {title}\nJOEY: {message}\n" + "=" * 78)
    reset()
    start = time.time()
    try:
        notes = X.extract_and_propose(message)
    except Exception as e:
        print(f">>> CRASHED: {e!r}")
        return
    actions = queue()
    print("--- DRIVE would add ---")
    print("\n\n".join(notes) if notes else "(nothing — no proposal)")
    for a in actions:
        print(f"--- queued: {a['type']} ---\n{json.dumps(a['details'], ensure_ascii=False, indent=1)}")
    try:
        expect(actions, notes)
        print(f">>> MECHANICAL CHECKS: PASS  ({time.time() - start:.1f}s)")
        _passed += 1
    except AssertionError as e:
        print(f">>> MECHANICAL CHECKS: FAIL  {e}")


def one(actions):
    assert [a["type"] for a in actions] == ["log_carfax"], f"expected exactly one log_carfax, got {[a['type'] for a in actions]}"
    d = actions[0]["details"]
    assert d["performed_by"] == "previous_owner", d
    return d


def near(x, want, tol=0.011):
    return isinstance(x, (int, float)) and abs(x - want) <= tol


def c1(a, n):
    d = one(a)
    assert d["service_type"] == "oil_change" and d["date"] == "2024-03-15" and d["mileage"] == 40000, d


def c2(a, n):
    d = one(a)
    assert d["service_type"] == "tire_rotation" and d["date"] == "2023-10-02" and d["mileage"] == 38500, d
    assert d["shop"] in (None, "Honda dealer"), d


def c3(a, n):
    d = one(a)
    assert d["service_type"] == "brake_replacement" and d["date"] == "2022-06-10" and d["mileage"] == 29800, d
    assert d["shop"] and "joe" in d["shop"].lower(), d


def c4(a, n):
    d = one(a)
    assert d["date"] == "2021-11-20" and d["mileage"] == 52000 and near(d["cost"], 180), d


def nothing(a, n):
    assert a == [], f"proposed something it shouldn't have: {[x['type'] for x in a]}"


def c9(a, n):
    d = one(a)
    assert any("more than one Carfax record" in x for x in n), n


case("full record", "Carfax shows an oil change on 2024-03-15 at 40,000 miles", c1)
case("typed entry with a dealer", "add a Carfax entry: tire rotation, 2023-10-02, 38,500 miles, Honda dealer", c2)
case("brake work with a named shop", "my carfax says the brakes were replaced on 2022-06-10 at 29,800 miles by Joe's Garage", c3)
case("cost and a fluid service", "carfax: transmission fluid flush on 2021-11-20, 52,000 miles, $180", c4)
case("NO date -> must ask, not invent one", "carfax says there was an oil change at 30,000 miles", nothing)
case("relative date -> must not work it out", "carfax says the timing belt was done last year", nothing)
case("only a question", "what does carfax say about my brakes?", nothing)
case("advice about Carfax is not a record", "should I buy a carfax report for this car?", nothing)
case("two records -> first one + a note", "carfax shows an oil change on 2024-03-15 and a tire rotation on 2023-10-02", c9)

_total += 1
print("\n" + "=" * 78 + "\nCASE: approve for real (temp files): schedule and current mileage stay untouched\n" + "=" * 78)
reset()
X.extract_and_propose("Carfax shows an oil change on 2024-03-15 at 99,000 miles")
out = A.approve_and_execute(queue()[0]["id"][:8])
print(out)
print(t.get_recent_maintenance())
try:
    v = vehicle()
    assert out.startswith("Carfax entry logged") and v["current_mileage"] == 55500 and v["upcoming_maintenance"] == []
    assert "[Carfax]" in t.get_recent_maintenance()
    print(">>> MECHANICAL CHECKS: PASS")
    _passed += 1
except AssertionError:
    print(">>> MECHANICAL CHECKS: FAIL")

print("\n" + "=" * 78)
print(f"L3 MECHANICAL: {_passed}/{_total} passed")
print("Now READ every case above: exactly the dates/miles/costs you said? nothing invented?")
print("=" * 78)