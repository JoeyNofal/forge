"""
DRIVE increment (b), Part 6b — L3: REAL end to end. Real NHTSA (your internet), real LOCAL DRIVE
model (Ollama), TEMP data and queue files. One real SerpApi web search happens too (the existing
"recall" search trigger). No cloud model is used.

Mechanical checks catch the obvious; YOU read each reply: does it use the NHTSA list correctly?
Does it say the data is for the model year, not the VIN? Does it invent anything?

Run from the repo root:  python -m agents.drive.test_drive_recall_l3
"""
import json
import os
import re
import tempfile
import urllib.error

_QUEUE_DIR = tempfile.mkdtemp(prefix="drive_recall_l3_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")
_DATA_DIR = tempfile.mkdtemp(prefix="drive_recall_l3_data_")
os.environ["VEHICLE_DATA_PATH"] = os.path.join(_DATA_DIR, "vehicle.json")

from agents.drive import chat
from agents.drive import drive_actions as A
from agents.drive import drive_logging as Lg
from shared import nhtsa as N
from shared import pending_actions as pa

QUEUE = pa.PENDING_ACTIONS_PATH
VEHICLE = os.environ["VEHICLE_DATA_PATH"]
_real_http = N._http_get
_passed = 0
_total = 0
net_calls = []


def counting_http(url, timeout):
    net_calls.append(url)
    return _real_http(url, timeout)


N._http_get = counting_http


def queue():
    if not os.path.exists(QUEUE):
        return []
    with open(QUEUE, encoding="utf-8") as f:
        return json.load(f)["actions"]


def reset():
    for p in (QUEUE, VEHICLE):
        if os.path.exists(p):
            os.remove(p)
    Lg.log_mileage({"mileage": 55500})
    net_calls.clear()


def ask(message):
    return "".join(chat.stream_drive(message, None, "", "local"))


def case(title, fn):
    global _passed, _total
    _total += 1
    print("\n" + "=" * 78 + f"\nCASE: {title}\n" + "=" * 78)
    try:
        fn()
        print(">>> MECHANICAL CHECKS: PASS")
        _passed += 1
    except AssertionError as e:
        print(f">>> MECHANICAL CHECKS: FAIL  {e}")
    except Exception as e:
        print(f">>> CRASHED: {type(e).__name__}: {e}")


real = N.lookup_recalls("Honda", "Civic", 2016)
real_ids = {r["campaign"] for r in real["recalls"]}
print(f"(real NHTSA list for the 2016 Civic: {real['count']} recalls: {sorted(real_ids)})")


def recall_question():
    reset()
    out = ask("any recalls on my car?")
    print(out)
    reply = out.split("\n\nProposed:")[0]
    invented = set(re.findall(r"\b\d{2}V\d{6}\b", reply)) - real_ids
    assert not invented, f"the reply quotes campaign numbers NHTSA never listed: {invented}"
    if real["count"] > 0:
        low = reply.lower()
        assert "no recalls" not in low and "no open recalls" not in low and "no outstanding recalls" not in low, \
            "the reply claims there are no recalls although NHTSA lists some"
    assert "Proposed: save this recall check" in out and len(queue()) == 1
    assert "not your VIN specifically" in out and "nhtsa.gov/recalls" in out, "the VIN reminder is missing"
    assert any("recallsByVehicle" in u for u in net_calls)


def approve_then_again():
    out = A.approve_and_execute(queue()[0]["id"][:8])
    print(out)
    assert out.startswith("Recall check saved")
    again = ask("any recalls on my car?")
    print(again.split("\n\n")[-1])
    assert "hasn't changed since your last saved check" in again and len(queue()) == 1


def lookup_fails():
    reset()
    N._http_get = lambda url, timeout: (_ for _ in ()).throw(urllib.error.URLError("simulated: no internet"))
    try:
        out = ask("are there any recalls on my Civic?")
    finally:
        N._http_get = counting_http
    print(out)
    reply = out.split("\n\nProposed:")[0]
    assert not re.search(r"\b\d{2}V\d{6}\b", reply), "the reply names recall campaigns although the lookup FAILED"
    assert any(w in reply.lower() for w in ("fail", "couldn't", "could not", "unable", "nhtsa.gov", "vin")), \
        "the reply doesn't say the lookup failed"
    assert queue() == [], "an offer to save was made although the lookup failed"


def not_a_recall_question():
    reset()
    out = ask("is it time for an oil change?")
    print(out[:400])
    assert net_calls == [] and queue() == []


case("a real recall question (real NHTSA + real local DRIVE)", recall_question)
case("approve the offer for real; asking again says 'hasn't changed'", approve_then_again)
case("NHTSA unreachable -> DRIVE must say the lookup failed, must not guess recalls, no save offer", lookup_fails)
case("a non-recall question never touches NHTSA", not_a_recall_question)

print("\n" + "=" * 78)
print(f"L3 MECHANICAL: {_passed}/{_total} passed")
print("Now READ every reply: does it use the NHTSA list correctly? say it covers the model year, not the VIN? invent anything?")
print("=" * 78)