"""
DRIVE UNITS — L3: the REAL local model, free. Does the new prompt (no conversion
asked of the model) still produce the right numbers, and does the guard stop a
guessed unit? Mechanical checks plus output for you to READ.

Run from the repo root:  python -m agents.drive.test_drive_units_l3
"""
import json
import os
import tempfile
import time

_D = tempfile.mkdtemp(prefix="drive_units_l3_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_D, "pending_actions.json")
os.environ["VEHICLE_DATA_PATH"] = os.path.join(_D, "vehicle.json")

from agents.drive import drive_extract as X
from shared import pending_actions as pa

QUEUE = pa.PENDING_ACTIONS_PATH


def km(n):
    return int(round(n * 0.621371))


def queue():
    if not os.path.exists(QUEUE):
        return []
    with open(QUEUE, encoding="utf-8") as f:
        return json.load(f)["actions"]


def detail(actions, action_type):
    for a in actions:
        if a["type"] == action_type:
            return a["details"]
    return {}


CASES = [
    ("km stated", "my car has 80,000 km on it",
     lambda q: detail(q, "log_mileage").get("mileage") == km(80000)),
    ("no unit at all: stays 80,000", "my odometer says 80,000",
     lambda q: detail(q, "log_mileage").get("mileage") == 80000),
    ("miles stated", "my car has 52,000 miles on it",
     lambda q: detail(q, "log_mileage").get("mileage") == 52000),
    ("liters stated", "filled up with 20 liters for $30",
     lambda q: detail(q, "log_fillup").get("gallons") == 5.28),
    ("NO unit: must stay 40 gallons, not converted", "filled up 40 for $50",
     lambda q: detail(q, "log_fillup").get("gallons") == 40),
    ("gallons stated", "just fueled up 10 gal for $30",
     lambda q: detail(q, "log_fillup").get("gallons") == 10),
    ("fill-up with km odometer", "filled up 10 gallons for $35, odometer says 80,000 km",
     lambda q: detail(q, "log_fillup").get("gallons") == 10 and detail(q, "log_fillup").get("mileage") == km(80000)),
    ("service at km", "got an oil change at 56,000 km for $65",
     lambda q: detail(q, "log_maintenance").get("mileage") == km(56000)),
    ("service at miles", "got an oil change at 56,000 miles for $65",
     lambda q: detail(q, "log_maintenance").get("mileage") == 56000),
]

passed = 0
for name, message, ok_fn in CASES:
    print("\n" + "=" * 78 + f"\nCASE: {name}\nJOEY: {message}\n" + "=" * 78)
    if os.path.exists(QUEUE):
        os.remove(QUEUE)
    start = time.time()
    try:
        notes = X.extract_and_propose(message)
        q = queue()
        for n in notes:
            print(n)
        for a in q:
            print(f"--- queued: {a['type']} ---\n{json.dumps(a['details'], indent=1)}")
        ok = bool(ok_fn(q))
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        ok = False
    print(f">>> MECHANICAL CHECK: {'PASS' if ok else 'FAIL'}  ({time.time() - start:.1f}s)")
    passed += ok

print("\n" + "=" * 78)
print(f"L3 MECHANICAL: {passed}/{len(CASES)} passed")
print("Now READ every case: exactly the numbers you said? 'filled up 40 for $50' must NOT become ~10.6 gallons.")
print("=" * 78)