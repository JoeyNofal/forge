"""
ATLAS increment (a) — L3: REAL end-to-end. Real Gemini (free cloud), real
SerpApi search, real Ollama (local tier), and one real Sonnet 5 call
(paid cloud, roughly 1-2 cents). Your keys come from .env.

The data is a TEMP file with made-up but realistic workouts — your real
fitness.json is never touched.

Run from the repo root:
    python -m agents.atlas.test_atlas_l3
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

from agents.atlas import chat, atlas_tools
from shared.web_search import WEB_SEARCH_FAILED_PREFIX
from shared import api_budget

SKIP_LOCAL = "--skip-local" in sys.argv
SKIP_PAID = "--skip-paid" in sys.argv

_results = []
model_calls = []
search_log = []

# Count real calls without changing what they do.
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

DATA = {
    "profile": {"name": "Joey", "units": "imperial",
                "notes": "Former competitive swimmer. Specialized in breaststroke, IM, and long-distance freestyle."},
    "workouts": [
        {"type": "swim", "date": "2026-09-01", "total_distance_yards": 2000, "duration_minutes": 55,
         "strokes": ["freestyle", "breaststroke"], "difficulty_1_to_10": 6, "weaknesses": "kick timing"},
        {"type": "swim", "date": "2026-09-08", "total_distance_yards": 1500, "duration_minutes": 45,
         "strokes": ["breaststroke"], "difficulty_1_to_10": 7, "weaknesses": ["pullout", "breathing rhythm"]},
        {"type": "swim", "date": "2026-09-15", "total_distance_yards": 2500, "duration_minutes": 65,
         "strokes": ["im"], "difficulty_1_to_10": 8},
        {"type": "gym", "date": "2026-09-03", "exercises": [
            {"name": "bench press", "sets": 3, "reps": 8, "weight_lbs": 135},
            {"name": "barbell row", "sets": 3, "reps": 10, "weight_lbs": 115}],
         "duration_minutes": 50, "difficulty_1_to_10": 6},
        {"type": "gym", "date": "2026-09-10", "exercises": ["squat", "deadlift"], "duration_minutes": 45},
    ],
    "injuries": [
        {"status": "none", "description": "placeholder"},
        {"date_logged": "2026-08-20T09:00:00", "description": "mild left shoulder soreness", "status": "recovering"},
    ],
}

INVENTED = re.compile(r"you(?:'ve| have)?\s+(?:logged|done|completed|swum|swam)\s+\d+", re.I)
BAD_MARKERS = ("FITNESS DATA UNAVAILABLE", WEB_SEARCH_FAILED_PREFIX, "Traceback")


def temp_data(obj=None, raw=None):
    d = tempfile.mkdtemp(prefix="atlas_l3_")
    path = os.path.join(d, "fitness.json")
    os.environ["FITNESS_DATA_PATH"] = path
    if raw is not None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)
    elif obj is not None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f)
    return path, d


def ask(message, history=None, tier=None):
    return "".join(chat.stream_atlas(message, history, "", tier))


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
    print("--- ATLAS says ---")
    print(text)
    print("--- end ---")


def basic_ok(text, min_len=60):
    assert len(text.strip()) >= min_len, f"response too short ({len(text.strip())} chars)"
    for m in BAD_MARKERS:
        assert m not in text, f"leaked marker: {m}"
    assert text != chat.REFUSAL_MESSAGE, "wrongly refused"


# Safety: every case points ATLAS at a TEMP file. Prove that once, up front.
_probe, _probe_dir = temp_data(DATA)
assert "atlas_l3_" in atlas_tools.get_data_path(), "L3 must only ever use a temp data file"
shutil.rmtree(_probe_dir)


@case("1. Grounded coaching on real-shaped data (free cloud default)")
def _():
    path, d = temp_data(DATA)
    out = ask("Give me a swim workout for tomorrow.")
    show(out)
    basic_ok(out, 100)
    assert model_calls == [None], model_calls        # None = live default tier (free cloud)
    shutil.rmtree(d)


@case("2. Empty log: must NOT invent workout counts")
def _():
    path, d = temp_data()          # missing file -> auto-created empty
    out = ask("How am I doing lately?")
    show(out)
    basic_ok(out, 40)
    assert not INVENTED.search(out), "invented a workout count on an empty log"
    shutil.rmtree(d)


@case("3. Off-topic refusal: exact Goggins line, zero model calls")
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
    out = ask("How many swim workouts have I logged?")
    show(out)
    assert "3 session(s), 6,000 total yards" in out, out
    assert "pullout, breathing rhythm" in out          # list-shaped weaknesses render as text
    assert model_calls == []
    shutil.rmtree(d)


@case("5. Research question: real SerpApi search + real Gemini answer")
def _():
    path, d = temp_data(DATA)
    out = ask("What's the best way to improve my breaststroke pullout technique?")
    show(out)
    basic_ok(out, 100)
    assert len(search_log) == 1, f"expected exactly 1 search, got {len(search_log)}"
    q, r = search_log[0]
    print(f"(search query used: {q!r}; result was {len(r)} chars)")
    assert not r.startswith(WEB_SEARCH_FAILED_PREFIX), "real search FAILED — check SERPAPI key / balance"
    shutil.rmtree(d)


@case("6. Multi-turn: remembers what was said earlier in THIS conversation")
def _():
    path, d = temp_data(DATA)
    q1 = "I'm going to focus on my breaststroke pullout this month."
    a1 = ask(q1)
    show(a1)
    hist = [{"role": "user", "content": q1}, {"role": "assistant", "content": a1}]
    a2 = ask("What did I just say I'm focusing on this month?", hist)
    show(a2)
    basic_ok(a2, 15)
    assert "pullout" in a2.lower(), "did not recall the earlier statement"
    shutil.rmtree(d)


@case("7. Unreadable data file: still coaches, doesn't crash, doesn't invent")
def _():
    path, d = temp_data(raw='{"workouts": [')
    out = ask("Give me a leg day plan.")
    show(out)
    basic_ok(out.replace("FITNESS DATA UNAVAILABLE", ""), 40)
    assert not INVENTED.search(out)
    shutil.rmtree(d)


@case("8. Coach mode: injury talk (voice check — read this one)")
def _():
    path, d = temp_data(DATA)
    out = ask("My left shoulder is sore after swimming. What should I do?")
    show(out)
    basic_ok(out, 100)
    shutil.rmtree(d)


@case("9. Local tier (real Ollama)", skip=SKIP_LOCAL)
def _():
    path, d = temp_data(DATA)
    out = ask("Give me a 20 minute core workout.", tier="local")
    show(out)
    basic_ok(out, 60)
    assert model_calls == ["local"]
    shutil.rmtree(d)


@case("10. Paid Cloud tier (real Sonnet 5, ~1-2 cents) + budget actually moves", skip=SKIP_PAID)
def _():
    path, d = temp_data(DATA)
    before = api_budget.get_balance()
    out = ask("Give me a 20 minute core workout.", tier="paid_cloud")
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
print("Now READ every response above: Goggins voice? grounded in the data? nothing invented?")
print("=" * 78)
if passed != len(_results):
    raise SystemExit(1)