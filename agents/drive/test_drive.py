"""
DRIVE increment (a), Part 2 — L1 (static) + L2 (smoke) tests for chat.py.
The model and web search are FAKED (no API keys, no cost), and the data
file is always a TEMP file — your real vehicle.json is never touched.

Run from the repo root:  python -m agents.drive.test_drive
"""
import json
import os
import re
import shutil
import tempfile

from agents.drive import chat
from agents.drive import drive_tools
from agents.drive.prompt import DRIVE_PROMPT
from shared import agent_topics
from shared.web_search import WEB_SEARCH_FAILED_PREFIX

REPO_ROOT = drive_tools._REPO_ROOT
CHAT_SRC = os.path.join(REPO_ROOT, "agents", "drive", "chat.py")

_results = []
model_calls = []
search_calls = []
search_reply = ["Web search results:\n\n1. Title\n   snippet\n   link"]


def fake_stream_by_tier(agent, tier, system_prompt, messages, location=""):
    model_calls.append({"agent": agent, "tier": tier, "system": system_prompt,
                        "messages": list(messages), "location": location})
    yield "Now. "
    yield "Listen carefully."


def fake_web_search(query, num_results=3):
    search_calls.append(query)
    return search_reply[0]


chat.stream_by_tier = fake_stream_by_tier
chat.web_search = fake_web_search

# Logging extraction has its OWN tests (test_drive_extract.py, test_drive_chat_extract.py); switched off here.
chat.extract_and_propose = lambda message: []


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


def reset():
    model_calls.clear()
    search_calls.clear()
    search_reply[0] = "Web search results:\n\n1. Title\n   snippet\n   link"


def run(message, history=None, tier=None, location=""):
    return "".join(chat.stream_drive(message, history, location, tier))


def temp_data(obj=None, raw=None):
    d = tempfile.mkdtemp(prefix="drive_chat_test_")
    path = os.path.join(d, "vehicle.json")
    os.environ["VEHICLE_DATA_PATH"] = path
    if raw is not None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)
    elif obj is not None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f)
    return path, d


SAMPLE = {"vehicles": [{
    "active": True, "make": "Honda", "model": "Civic", "year": 2016,
    "vin": "19XFC2F57GE016309", "current_mileage": 48200,
    "maintenance_log": [
        {"service_type": "oil_change", "date": "2026-06-01", "mileage": 45000, "cost": 89.99},
    ],
    "gas_log": [
        {"date": "2026-08-01", "mileage": 47000, "gallons": 11.2, "price_per_gallon": 3.45,
         "total_cost": 38.64, "mpg": None},
        {"date": "2026-08-20", "mileage": 47500, "gallons": 10.8, "price_per_gallon": 3.5,
         "total_cost": 37.8, "mpg": 46.3},
    ],
    "issues": [{"description": "clicking noise on left turns", "severity": "mild", "status": "open"}],
}]}

# ───────────────────────── L1 — STATIC ─────────────────────────

with open(CHAT_SRC, encoding="utf-8") as _f:
    SRC = _f.read()


@check("L1 chat.py routes ONLY through stream_by_tier (Lesson #1/#11)")
def _():
    for direct in ("stream_gemini(", "stream_ollama(", "stream_claude("):
        assert direct not in SRC, direct
    assert 'stream_by_tier("drive"' in SRC


@check("L1 no substring keyword matching, no bare except, no secrets in chat.py")
def _():
    assert ".lower()" not in SRC
    assert not re.search(r"^\s*except\s*:\s*$", SRC, re.M)  # a real bare except, not prose mentioning one
    assert not re.search(r"(api[_-]?key|sk-ant|AIza)\s*=\s*['\"]", SRC, re.I)


@check("L1 every DRIVE keyword list exists and is non-empty")
def _():
    for name in ("DRIVE_NON_TOPIC", "DRIVE_INTENT", "DRIVE_SEARCH_TRIGGERS", "DRIVE_HISTORY_PHRASES",
                 "DRIVE_HISTORY_QUANTITY", "DRIVE_HISTORY_SUBJECTS", "DRIVE_ADVICE_SIGNALS",
                 "DRIVE_REPORT_PHRASES", "DRIVE_MAINTENANCE_WORDS", "DRIVE_GAS_WORDS", "DRIVE_ISSUE_WORDS"):
        assert getattr(agent_topics, name), name


@check("L1 DRIVE has no memory or logging yet (increments b/c not built)")
def _():
    assert "save_memory" not in SRC and "search_memory" not in SRC
    assert "log_maintenance" not in SRC and "MEMORY_SAVE" not in SRC


@check("L1 refusal message matches DRIVE's own prompt line, not a generic one")
def _():
    assert chat.REFUSAL_MESSAGE in DRIVE_PROMPT


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 off-topic messages get DRIVE's own refusal, no model call, no search")
def _():
    reset(); path, d = temp_data(SAMPLE)
    for msg in ["what's the weather today", "help me write python code",
                "give me a recipe for dinner", "what's a good workout program"]:
        assert run(msg) == chat.REFUSAL_MESSAGE, msg
    assert not model_calls and not search_calls
    shutil.rmtree(d)


@check("L2 old substring bugs stay fixed: real automotive questions are NOT refused")
def _():
    reset(); path, d = temp_data(SAMPLE)
    good = ["what's the diagnostic code for a check engine light",
            "should I be on a maintenance program for this car",
            "compare synthetic vs conventional oil",
            "is a lease worth it for my next car"]
    for msg in good:
        assert run(msg) == "Now. Listen carefully.", msg
    assert len(model_calls) == len(good)
    shutil.rmtree(d)


@check("L2 model gets DRIVE prompt, agent name, live data summary, and the message")
def _():
    reset(); path, d = temp_data(SAMPLE)
    out = run("is it time for an oil change?")
    assert out == "Now. Listen carefully."
    c = model_calls[0]
    assert c["agent"] == "drive" and c["system"] == DRIVE_PROMPT
    last = c["messages"][-1]
    assert last["role"] == "user"
    assert "VEHICLE DATA SUMMARY" in last["content"] and "48,200 miles" in last["content"]
    assert last["content"].endswith("Joey says: is it time for an oil change?")
    shutil.rmtree(d)


@check("L2 history is kept in order and the caller's list is never mutated")
def _():
    reset(); path, d = temp_data(SAMPLE)
    hist = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}]
    run("is it time for an oil change?", history=hist)
    sent = model_calls[0]["messages"]
    assert len(sent) == 3 and sent[0] == hist[0] and sent[1] == hist[1]
    assert len(hist) == 2
    shutil.rmtree(d)


@check("L2 tier and location pass through unchanged (None = DRIVE's live default)")
def _():
    reset(); path, d = temp_data(SAMPLE)
    run("is it time for an oil change?")
    run("is it time for an oil change?", tier="local")
    run("is it time for an oil change?", tier="paid_cloud", location="South Bend")
    assert [c["tier"] for c in model_calls] == [None, "local", "paid_cloud"]
    assert model_calls[2]["location"] == "South Bend"
    shutil.rmtree(d)


@check("L2 is_history_question table: real history asks vs advice/report messages")
def _():
    yes = ["show me my maintenance history", "what's my current mileage",
           "show me my gas history", "what open issues do I have",
           "how many oil changes have I logged", "what's due soon"]
    no = ["should I get an oil change soon", "how much should a brake job cost",
          "I just got an oil change", "is synthetic oil worth it",
          "how do I check my tire pressure"]
    for m in yes:
        assert chat.is_history_question(m), f"should be history: {m}"
    for m in no:
        assert not chat.is_history_question(m), f"should NOT be history: {m}"


@check("L2 history questions are answered from the data with NO model call")
def _():
    reset(); path, d = temp_data(SAMPLE)
    maint = run("show me my maintenance history")
    assert "89.99" in maint
    gas = run("show me my gas history")
    assert "2 fill-ups" in gas
    issues = run("what open issues do I have")
    assert "clicking noise" in issues
    allv = run("what have i logged")
    assert "2016 Honda Civic" in allv and "89.99" in allv
    assert not model_calls
    shutil.rmtree(d)


@check("L2 unreadable data: coaching still works with an explicit note; history says why")
def _():
    reset(); path, d = temp_data(raw='{"vehicles": [')
    assert run("is it time for an oil change?") == "Now. Listen carefully."
    assert "VEHICLE DATA UNAVAILABLE" in model_calls[0]["messages"][-1]["content"]
    assert "malformed" in model_calls[0]["messages"][-1]["content"]
    n = len(model_calls)
    out = run("show me my maintenance history")
    assert "can't read your vehicle data" in out and "malformed" in out
    assert len(model_calls) == n
    shutil.rmtree(d)


@check("L2 web search: only on trigger questions, plain query, labeled as background")
def _():
    reset(); path, d = temp_data(SAMPLE)
    run("is it time for an oil change?")
    assert not search_calls
    run("is there a recall on my car?")
    assert search_calls == ["is there a recall on my car?"]
    content = model_calls[-1]["messages"][-1]["content"]
    assert "Background web search results" in content and "may be outdated" in content
    shutil.rmtree(d)


@check("L2 a FAILED search is passed through as a failure, never dressed up as results")
def _():
    reset(); path, d = temp_data(SAMPLE)
    search_reply[0] = f"{WEB_SEARCH_FAILED_PREFIX} The search itself failed."
    run("should I get a new car or keep this one?")
    content = model_calls[-1]["messages"][-1]["content"]
    assert WEB_SEARCH_FAILED_PREFIX in content
    assert "Background web search results" not in content
    shutil.rmtree(d)


@check("L2 streamed chunks arrive intact and in order")
def _():
    reset(); path, d = temp_data(SAMPLE)
    assert list(chat.stream_drive("is it time for an oil change?")) == ["Now. ", "Listen carefully."]
    shutil.rmtree(d)


passed = sum(1 for _, ok, _ in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
if passed != len(_results):
    raise SystemExit(1)