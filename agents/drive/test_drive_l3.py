"""
DRIVE increment (a) — L3: REAL end-to-end. Real Gemini (free cloud), real
SerpApi search, real Ollama (local tier), and one real Sonnet 5 call
(paid cloud, roughly 1-2 cents). Your keys come from .env.

The data is a TEMP file with made-up but realistic vehicle data — your
real vehicle.json is never touched.

Run from the repo root:
    python -m agents.drive.test_drive_l3
Optional flags:  --skip-local  (Ollama not running)   --skip-paid  (no Sonnet call)

Mechanical checks catch the obvious failures. The printed responses are
the REAL test — paste the whole output back and we read them together.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import time

from agents.drive import chat, drive_tools
from shared.web_search import WEB_SEARCH_FAILED_PREFIX
from shared import api_budget

SKIP_LOCAL = "--skip-local" in sys.argv
SKIP_PAID = "--skip-paid" in sys.argv

_results = []
model_calls = []
search_log = []

_real_stream = chat.stream_by_tier
_real_search = chat.web_search


def counting_stream(agent, tier, system_prompt, messages, location=""):
    model_calls.append(tier)
    yield from _real_stream(agent, tier, system_prompt, messages, location)


def counting_search(query, num_results=3):
    result = _real_search(query, num_results)
    search_log.append((query, result))
    return result


chat.stream_by_tier = counting_stream
chat.web_search = counting_search

# Real logging extraction has its own real test (test_drive_extract_l3.py); switched off here.
chat.extract_and_propose = lambda message: []
chat.prepare_recall_context = lambda message: (None, None)    # the recall check has its own tests
chat.memory_context_block = lambda message: None
chat.remember_from_message = lambda message: []

chat.memory_context_block = lambda message: None
chat.remember_from_message = lambda message: []

DATA = {"vehicles": [{
    "id": "vehicle_001", "active": True, "make": "Honda", "model": "Civic", "year": 2016,
    "vin": "19XFC2F57GE016309", "current_mileage": 61500,
    "maintenance_log": [
        {"service_type": "oil_change", "date": "2026-06-01", "mileage": 58000,
         "shop": "Honda Dealership", "cost": 89.99, "performed_by": "dealership"},
        {"service_type": "tire_rotation", "date": "2026-07-15", "mileage": 59200, "source": "carfax"},
        {"service_type": "brake_inspection", "date": "2026-08-01", "mileage": 60000,
         "shop": "Midas", "cost": 45.00, "notes": "Front pads at 40%, rear fine"},
    ],
    "gas_log": [
        {"date": "2026-09-01", "mileage": 60800, "gallons": 11.5, "price_per_gallon": 3.29,
         "total_cost": 37.84, "mpg": 41.2},
        {"date": "2026-09-15", "mileage": 61500, "gallons": 10.9, "price_per_gallon": 3.35,
         "total_cost": 36.52, "mpg": 42.1},
    ],
    "upcoming_maintenance": [
        {"service_type": "oil_change", "display_name": "Oil Change",
         "next_due_miles": 63000, "next_due_date": "2026-12-01"},
    ],
    "issues": [{"description": "faint clicking noise on left turns", "severity": "mild",
                "date_reported": "2026-09-10", "status": "open"}],
}]}

INVENTED = re.compile(r"you(?:'ve| have)?\s+(?:logged|done|spent)\s+\$?\d+", re.I)
BAD_MARKERS = ("VEHICLE DATA UNAVAILABLE", WEB_SEARCH_FAILED_PREFIX, "Traceback")


def temp_data(obj=None, raw=None):
    d = tempfile.mkdtemp(prefix="drive_l3_")
    path = os.path.join(d, "vehicle.json")
    os.environ["VEHICLE_DATA_PATH"] = path
    if raw is not None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)
    elif obj is not None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f)
    return path, d


def ask(message, history=None, tier=None):
    return "".join(chat.stream_drive(message, history, "", tier))


def case(name, skip=False):
    def deco(fn):
        print("\n" + "=" * 78)
        print(f"CASE: {name}")
        print("=" * 78)
        if skip:
            print("SKIPPED (flag)")
            return fn
        model_calls.clear(); search_log.clear()
        t0 = time.time()
        try:
            fn()
            _results.append((name, True, ""))
            print(f"\n>>> MECHANICAL CHECKS: PASS  ({time.time() - t0:.1f}s)")
        except Exception as e:
            _results.append((name, False, repr(e)))
            print(f"\n>>> MECHANICAL CHECKS: FAIL  -> {e!r}")
        return fn
    return deco


def show(text):
    print("--- DRIVE says ---")
    print(text)
    print("--- end ---")


def basic_ok(text, min_len=60):
    assert len(text.strip()) >= min_len, f"response too short ({len(text.strip())} chars)"
    for m in BAD_MARKERS:
        assert m not in text, f"leaked marker: {m}"
    assert text != chat.REFUSAL_MESSAGE, "wrongly refused"


# Safety: every case points DRIVE at a TEMP file. Prove that once, up front.
_probe, _probe_dir = temp_data(DATA)
assert "drive_l3_" in drive_tools.get_data_path(), "L3 must only ever use a temp data file"
shutil.rmtree(_probe_dir)


@case("1. Grounded advice on real-shaped data (free cloud default)")
def _():
    path, d = temp_data(DATA)
    out = ask("Is it time for an oil change?")
    show(out)
    basic_ok(out, 100)
    assert model_calls == [None], model_calls
    shutil.rmtree(d)


@case("2. Empty log: must NOT invent maintenance history")
def _():
    path, d = temp_data()  # missing file -> auto-created with Joey's real car, empty logs
    out = ask("How's my car been doing?")
    show(out)
    basic_ok(out, 40)
    assert not INVENTED.search(out), "invented maintenance/spend history on an empty log"
    shutil.rmtree(d)


@case("3. Off-topic refusal: DRIVE's own line, zero model calls")
def _():
    path, d = temp_data(DATA)
    out = ask("What's the weather going to be tomorrow?")
    show(out)
    assert out == chat.REFUSAL_MESSAGE
    assert model_calls == []
    shutil.rmtree(d)


@case("4. 'Show me my data' is answered from the file, zero model calls")
def _():
    path, d = temp_data(DATA)
    out = ask("Show me my maintenance history.")
    show(out)
    assert "Brake Inspection" in out and "Midas" in out
    assert model_calls == []
    shutil.rmtree(d)


@case("5. Research question: real SerpApi search + real Gemini answer")
def _():
    path, d = temp_data(DATA)
    out = ask("Is there a recall on my car?")
    show(out)
    basic_ok(out, 60)
    assert len(search_log) == 1, f"expected exactly 1 search, got {len(search_log)}"
    q, r = search_log[0]
    print(f"(search query used: {q!r}; result was {len(r)} chars)")
    assert not r.startswith(WEB_SEARCH_FAILED_PREFIX), "real search FAILED — check SERPAPI key / balance"
    shutil.rmtree(d)


@case("6. Multi-turn: remembers what was said earlier in THIS conversation")
def _():
    path, d = temp_data(DATA)
    q1 = "That clicking noise on left turns is getting worse."
    a1 = ask(q1)
    show(a1)
    hist = [{"role": "user", "content": q1}, {"role": "assistant", "content": a1}]
    a2 = ask("What did I just tell you about my car?", hist)
    show(a2)
    basic_ok(a2, 15)
    assert "click" in a2.lower(), "did not recall the earlier statement"
    shutil.rmtree(d)


@case("7. Unreadable data file: still advises, doesn't crash, doesn't invent")
def _():
    path, d = temp_data(raw='{"vehicles": [')
    out = ask("Is it time for an oil change?")
    show(out)
    basic_ok(out.replace("VEHICLE DATA UNAVAILABLE", ""), 40)
    assert not INVENTED.search(out)
    shutil.rmtree(d)


@case("8. Voice check: brake pad wear (read this one)")
def _():
    path, d = temp_data(DATA)
    out = ask("My front brake pads are at 40%. Should I be worried?")
    show(out)
    basic_ok(out, 100)
    shutil.rmtree(d)


@case("9. Local tier (real Ollama)", skip=SKIP_LOCAL)
def _():
    path, d = temp_data(DATA)
    out = ask("What tire pressure should I run?", tier="local")
    show(out)
    basic_ok(out, 60)
    assert model_calls == ["local"]
    shutil.rmtree(d)


@case("10. Paid Cloud tier (real Sonnet 5, ~1-2 cents) + budget actually moves", skip=SKIP_PAID)
def _():
    path, d = temp_data(DATA)
    before = api_budget.get_balance()
    out = ask("What tire pressure should I run?", tier="paid_cloud")
    after = api_budget.get_balance()
    show(out)
    basic_ok(out, 60)
    print(f"(balance ${before:.5f} -> ${after:.5f}, cost ${before - after:.5f})")
    assert after < before, "paid call did not register any spend"
    assert before - after < 0.25, "suspiciously expensive for one short reply"
    shutil.rmtree(d)


passed = sum(1 for _, ok, _ in _results if ok)
print("\n" + "=" * 78)
print(f"L3 MECHANICAL: {passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"  FAILED: {n} -> {err}")
print("Now READ every response above: Clarkson voice? grounded in the data? nothing invented?")
print("=" * 78)
if passed != len(_results):
    raise SystemExit(1)