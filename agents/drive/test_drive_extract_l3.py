"""
DRIVE increment (b), Part 3b-2 — L3: REAL end-to-end with your REAL local model
(Ollama must be running with gemma3:12b). No cloud calls, no cost. TEMP data and
queue files only — your real vehicle.json / pending_actions.json are never touched.

For every case it prints what DRIVE would show you plus the exact data that was
queued. Mechanical checks catch the obvious; YOU read the output for the rest:
are the numbers exactly what you said? anything invented? sensible notes?

Run from the repo root:  python -m agents.drive.test_drive_extract_l3
"""
import json
import os
import re
import tempfile
import time
from datetime import datetime, timedelta

_QUEUE_DIR = tempfile.mkdtemp(prefix="drive_extract_l3_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")
_DATA_DIR = tempfile.mkdtemp(prefix="drive_extract_l3_data_")
os.environ["VEHICLE_DATA_PATH"] = os.path.join(_DATA_DIR, "vehicle.json")

from agents.drive import chat
from agents.drive import drive_actions as A
from agents.drive import drive_extract as X
from agents.drive import drive_logging as Lg
from agents.drive import drive_tools as t
from shared import pending_actions as pa

QUEUE = pa.PENDING_ACTIONS_PATH
VEHICLE = os.environ["VEHICLE_DATA_PATH"]
_real_stream = chat.stream_by_tier
_passed = 0
_total = 0


def queue():
    if not os.path.exists(QUEUE):
        return []
    with open(QUEUE, encoding="utf-8") as f:
        return json.load(f)["actions"]


def reset_queue():
    if os.path.exists(QUEUE):
        os.remove(QUEUE)


def vehicle():
    with open(VEHICLE, encoding="utf-8") as f:
        return json.load(f)["vehicles"][0]


def reset_vehicle(issues=()):
    if os.path.exists(VEHICLE):
        os.remove(VEHICLE)
    Lg.log_mileage({"mileage": 55500})
    for text in issues:
        Lg.log_issue({"description": text})


def issue_id(word):
    return [i["id"] for i in vehicle()["issues"] if word in i["description"].lower()][0]


def case(title, message, expect, issues=None):
    """expect(actions, notes) -> None, or raises AssertionError."""
    global _passed, _total
    _total += 1
    print("\n" + "=" * 78 + f"\nCASE: {title}\nJOEY: {message}\n" + "=" * 78)
    reset_queue()
    if issues is not None:
        reset_vehicle(issues)
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


def only_type(actions, kind):
    assert [a["type"] for a in actions] == [kind], f"expected exactly one {kind}, got {[a['type'] for a in actions]}"
    return actions[0]["details"]


def types(actions):
    return sorted(a["type"] for a in actions)


def near(x, want, tol=0.011):
    return isinstance(x, (int, float)) and abs(x - want) <= tol


# ── mileage ──
case("mileage statement 1", "my car has 52,000 miles on it",
     lambda a, n: (lambda d: None if d["mileage"] == 52000 else (_ for _ in ()).throw(AssertionError(d)))(only_type(a, "log_mileage")))
case("mileage statement 2", "I made it to 53,000 miles",
     lambda a, n: (lambda d: None if d["mileage"] == 53000 else (_ for _ in ()).throw(AssertionError(d)))(only_type(a, "log_mileage")))


# ── fill-ups ──
def fill1(a, n):
    d = only_type(a, "log_fillup")
    assert near(d["gallons"], 10) and near(d["total_cost"], 30) and d["mileage"] is None, d


def fill2(a, n):
    d = only_type(a, "log_fillup")
    assert near(d["gallons"], 9.67) and near(d["total_cost"], 28.87) and d["mileage"] is None, d


def fill3(a, n):
    d = only_type(a, "log_fillup")
    assert near(d["gallons"], 10.2) and near(d["price_per_gallon"], 3.45) and d["mileage"] == 56100, d


def fill4(a, n):
    d = only_type(a, "log_fillup")
    assert d["date"] == (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"), f"date {d['date']}"
    assert near(d["gallons"], 11) and near(d["total_cost"], 35), d


def fill5(a, n):
    d = only_type(a, "log_fillup")
    assert 5.0 < d["gallons"] < 5.6, f"20 liters should be about 5.28 gal, got {d['gallons']}"


case("fill-up 1: no mileage stated", "just fueled up 10 gal for $30", fill1)
case("fill-up 2: no mileage stated", "filled her up, 9.67 gal for $28.87", fill2)
case("fill-up 3: price per gallon + odometer", "filled up 10.2 gallons at 3.45 a gallon, odometer says 56,100", fill3)
case("fill-up 4: 'yesterday' becomes the right date", "yesterday I filled up 11 gallons for $35", fill4)
case("fill-up 5: liters converted to gallons", "filled up with 20 liters for $30", fill5)


# ── services ──
def svc1(a, n):
    d = only_type(a, "log_maintenance")
    assert d["service_type"] == "oil_change" and d["mileage"] is None and d["cost"] is None, d


def svc2(a, n):
    d = only_type(a, "log_maintenance")      # exactly ONE proposal: the mileage rides along, no separate mileage update
    assert d["service_type"] == "oil_change" and d["mileage"] == 56000 and near(d["cost"], 65) and d["performed_by"] == "shop", d
    assert d["shop"] in (None, ""), f"'dealership' is not a shop name: {d['shop']!r}"


case("service 1: nothing but the oil change stated", "i just serviced my car. i got her oil changed", svc1)
case("service 2: mileage, cost, dealership", "got an oil change at 56,000 miles for $65 at the dealership", svc2)


def svc3(a, n):
    assert types(a) == ["log_maintenance", "update_issue"], types(a)
    up = [x for x in a if x["type"] == "update_issue"][0]["details"]
    assert up["issue_id"] == issue_id("squeaky"), up
    m = [x for x in a if x["type"] == "log_maintenance"][0]["details"]
    assert "_" not in m["display_name"], f"raw snake_case shown to Joey: {m['display_name']!r}"


case("service that fixes an open issue -> service + resolve proposals", "got the brakes replaced", svc3,
     issues=["squeaky brakes when stopping", "tire pressure light is on"])


def svc4(a, n):
    assert types(a) == ["log_maintenance", "update_issues"], types(a)
    up = [x for x in a if x["type"] == "update_issues"][0]["details"]
    assert len(up["issue_ids"]) == 2, up
    m = [x for x in a if x["type"] == "log_maintenance"][0]["details"]
    assert "100" not in m["notes"], f"'100%' leaked into the service notes: {m['notes']!r}"


case("YOUR example (e): service + '100%' -> resolve ALL open issues, no duplicates",
     "got the brakes replaced. i services my vehicle and it's at a 100%", svc4,
     issues=["squeaky brakes when stopping", "tire pressure light is on"])


# ── new issues ──
def iss1(a, n):
    d = only_type(a, "log_issue")
    assert "tire" in d["description"].lower(), d
    assert "joey" not in d["notes"].lower(), f"notes talk about Joey/his question: {d['notes']!r}"


case("YOUR example (d): problem + a question -> logs the problem, doesn't answer",
     "my tire pressure light is on and idk what to do. What does the buzzing mean while driving", iss1, issues=[])


def iss2(a, n):
    assert "log_issue" not in types(a), f"logged a DUPLICATE of an already-open issue: {types(a)}"


case("same problem again while it's already open -> no duplicate",
     "my tire pressure light is on and idk what to do. What does the buzzing mean while driving", iss2,
     issues=["tire pressure light is on"])


# ── "it's fixed" ──
def fix1(a, n):
    d = only_type(a, "update_issue")
    assert d["issue_id"] == issue_id("check engine"), d


case("one named issue is fixed -> resolves exactly that one, logs nothing new", "my check engine light is fixed now", fix1,
     issues=["check engine light is on", "squeaky brakes when stopping"])


def fix2(a, n):
    d = only_type(a, "update_issues")
    assert len(d["issue_ids"]) == 3, d


case("everything is fixed -> resolve ALL three in one proposal", "everything's fixed, all good now", fix2,
     issues=["check engine light is on", "squeaky brakes when stopping", "tire pressure light is on"])


def fix3(a, n):
    assert not [x for x in a if x["type"] in ("update_issue", "update_issues")], f"resolved something wrongly: {types(a)}"


case("'the brakes are fixed' but NO brake issue is open -> resolves nothing", "the brakes are fixed", fix3,
     issues=["tire pressure light is on", "check engine light is on"])


def fix4(a, n):
    assert a == [], f"guessed instead of asking: {types(a)}"


case("ambiguous: two light issues open -> asks, doesn't guess", "my light is fixed", fix4,
     issues=["tire pressure light is on", "check engine light is on"])


# ── things that must NOT be logged ──
def nothing(a, n):
    assert a == [], f"proposed something for a question/plan: {types(a)}"


case("advice question", "should I change my oil at 55,000 miles?", nothing, issues=[])
case("a plan, not his current mileage", "I need an oil change at 55,000 miles", nothing)
case("a service interval, not his mileage", "my oil change is due at 60,000 miles", nothing)
case("a price question", "how much does a fill-up cost for 15 gallons?", nothing)

# ── the whole chat path: real extraction, faked reply ──
_total += 1
print("\n" + "=" * 78 + "\nCASE: full chat path (DRIVE's reply faked, extraction REAL)\n" + "=" * 78)
reset_queue()
reset_vehicle()
chat.stream_by_tier = lambda agent, tier, system, messages, location="": iter(["Now. ", "Fine."])
out = "".join(chat.stream_drive("just fueled up 10 gal for $30"))
print(out)
try:
    assert out.startswith("Now. Fine.\n\nProposed: log fill-up") and "id:" in out
    assert len(queue()) == 1 and queue()[0]["status"] == "pending"
    print(">>> MECHANICAL CHECKS: PASS")
    _passed += 1
except AssertionError:
    print(">>> MECHANICAL CHECKS: FAIL")

# ── approve for real (temp files) and read it back ──
_total += 1
print("\n" + "=" * 78 + "\nCASE: approve that proposal for real (temp file) and read it back\n" + "=" * 78)
aid = queue()[0]["id"]
print(A.approve_and_execute(aid[:8]))
print(t.get_gas_summary())
try:
    assert "30.00" in t.get_gas_summary() and len(vehicle()["gas_log"]) == 1
    print(">>> MECHANICAL CHECKS: PASS")
    _passed += 1
except AssertionError:
    print(">>> MECHANICAL CHECKS: FAIL")

# ── the REAL local DRIVE reply: does it falsely claim it saved something? (free: local model only) ──
_total += 1
print("\n" + "=" * 78 + "\nCASE: REAL local DRIVE reply must not claim it logged anything\n" + "=" * 78)
reset_queue()
reset_vehicle()
chat.stream_by_tier = _real_stream
out = "".join(chat.stream_drive("just fueled up 10 gal for $30", None, "", "local"))
print(out)
reply = out.split("\n\nProposed:")[0]
try:
    assert re.search(r"\b(i've|i have|i)\s+(just\s+)?(logged|saved|recorded)\b", reply, re.I) is None, "DRIVE claimed it saved something"
    assert "proposal" not in reply.lower() and "waiting for your approval" not in reply.lower(), "DRIVE promised/described a proposal"
    assert "Proposed: log fill-up" in out
    print(">>> MECHANICAL CHECKS: PASS")
    _passed += 1
except AssertionError as e:
    print(f">>> MECHANICAL CHECKS: FAIL  {e}")

print("\n" + "=" * 78)
print(f"L3 MECHANICAL: {_passed}/{_total} passed")
print("Now READ every case above: exactly the numbers you said? nothing invented? sensible notes?")
print("=" * 78)