"""
DRIVE increment (b), Part 3b-2 — L1, L2, L4, L5 tests for the chat.py wiring
of extraction + the open-issues section of DRIVE's summary. Both the DRIVE
reply and the local extraction model are FAKED (no Ollama, no keys, no cost).
TEMP files only: your real vehicle.json and pending_actions.json are never touched.

Run from the repo root:  python -m agents.drive.test_drive_chat_extract
"""
import json
import os
import re
import shutil
import tempfile
import threading

_QUEUE_DIR = tempfile.mkdtemp(prefix="drive_chatx_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from agents.drive import chat
from agents.drive import drive_extract as X
from agents.drive import drive_logging as Lg
from agents.drive import drive_tools as t
from shared import pending_actions as pa

QUEUE = pa.PENDING_ACTIONS_PATH
_results = []
reply_calls = []
model_calls = []
answers = {}
_lock = threading.Lock()


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


def fake_reply(agent, tier, system_prompt, messages, location=""):
    with _lock:
        reply_calls.append({"agent": agent, "messages": list(messages)})
    yield "Now. "
    yield "Listen carefully."


def kind_of(prompt):
    if "how many miles his car has RIGHT NOW" in prompt:
        return "mileage"
    if "reporting a fuel fill-up he ALREADY did" in prompt:
        return "fillup"
    if "car maintenance or a repair he ALREADY had done" in prompt:
        return "maintenance"
    if "problem with his car that EXISTS RIGHT NOW" in prompt:
        return "issue"
    if "saying that a problem with his car is fixed or gone" in prompt:
        return "issue_update"
    raise AssertionError("unknown prompt")


def fake_local(system_prompt, user_text, timeout=90.0):
    kind = kind_of(system_prompt)
    with _lock:
        model_calls.append({"kind": kind, "user": user_text})
    a = answers.get(kind, '{"kind": "none"}')
    if isinstance(a, Exception):
        raise a
    if callable(a):
        return a(system_prompt, user_text)
    return a if isinstance(a, str) else json.dumps(a)


chat.stream_by_tier = fake_reply
chat.web_search = lambda q, num_results=3: "Web search results:\n\n1. x"
X.complete_ollama_json = fake_local

FILLUP_JSON = {"kind": "fillup", "date": "", "gallons": 10, "price_per_gallon": None, "total_cost": 30, "mileage": None}


def fresh():
    d = tempfile.mkdtemp(prefix="drive_chatx_test_")
    os.environ["VEHICLE_DATA_PATH"] = os.path.join(d, "vehicle.json")
    if os.path.exists(QUEUE):
        os.remove(QUEUE)
    reply_calls.clear()
    model_calls.clear()
    answers.clear()
    return os.environ["VEHICLE_DATA_PATH"], d


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def raw_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def queue_actions():
    return read(QUEUE)["actions"] if os.path.exists(QUEUE) else []


def say(message):
    return "".join(chat.stream_drive(message))


def first_number(text):
    m = re.search(r"\d[\d,]*", text)
    assert m, text
    return int(m.group(0).replace(",", ""))


# ───────────────────────── L1 — STATIC ─────────────────────────

with open(chat.__file__, encoding="utf-8") as _f:
    CHAT_SRC = _f.read()
with open(t.__file__, encoding="utf-8") as _f:
    TOOLS_SRC = _f.read()


@check("L1 chat.py asks extract_and_propose only AFTER the reply, and never touches writers or the approval step")
def _():
    assert "extract_and_propose(message)" in CHAT_SRC
    assert CHAT_SRC.index('stream_by_tier("drive"') < CHAT_SRC.index("extract_and_propose(message)")
    for banned in ("drive_logging", "drive_actions", "approve_and_execute", "update_json"):
        assert banned not in CHAT_SRC, banned
    assert "ollama" not in CHAT_SRC.lower().replace("stream_by_tier", "")


@check("L1 the model is told it cannot save anything (so it can't claim 'logged!')")
def _():
    note = chat.LOGGING_NOTE.lower()
    assert "cannot save" in note and "never say you have" in note and "never mention or promise a proposal" in note


@check("L1 DRIVE's summary has an OPEN ISSUES section")
def _():
    assert "OPEN ISSUES:" in TOOLS_SRC and "get_open_issues()" in TOOLS_SRC


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 reply first, then the proposal note; a normal message is untouched")
def _():
    path, d = fresh()
    answers["fillup"] = FILLUP_JSON
    out = say("just fueled up 10 gal for $30")
    assert out.startswith("Now. Listen carefully.\n\nProposed: log fill-up") and "id:" in out
    q = queue_actions()
    assert len(q) == 1 and q[0]["status"] == "pending" and q[0]["type"] == "log_fillup"
    assert say("is it time for an oil change?") == "Now. Listen carefully."
    assert len(queue_actions()) == 1
    shutil.rmtree(d)


@check("L2 refusals and data-history shortcuts never trigger extraction (even when the message looks like a report)")
def _():
    path, d = fresh()
    answers["fillup"] = FILLUP_JSON
    answers["issue_update"] = {"kind": "issue_update", "resolved_all": True}
    assert say("what's the weather today, I filled up 10 gal for $30") == chat.REFUSAL_MESSAGE
    out = say("show me my maintenance history, my check engine light is fixed")
    assert "Proposed" not in out
    assert model_calls == [] and queue_actions() == [] and reply_calls == []
    shutil.rmtree(d)


@check("L2 if the DRIVE reply itself fails, nothing is extracted or proposed")
def _():
    path, d = fresh()
    answers["fillup"] = FILLUP_JSON

    def boom(agent, tier, system_prompt, messages, location=""):
        yield "partial"
        raise ConnectionError("model down")

    chat.stream_by_tier = boom
    got = []
    try:
        for c in chat.stream_drive("just fueled up 10 gal for $30"):
            got.append(c)
    except ConnectionError:
        pass
    finally:
        chat.stream_by_tier = fake_reply
    assert got == ["partial"] and model_calls == [] and queue_actions() == []
    shutil.rmtree(d)


@check("L2 the DRIVE model sees the no-save note and the OPEN ISSUES section (open ones only), with Joey's message last")
def _():
    path, d = fresh()
    Lg.log_issue({"description": "squeaky brakes"})
    Lg.log_issue({"description": "old resolved thing"})
    iid = read(path)["vehicles"][0]["issues"][1]["id"]
    Lg.update_issue_status({"issue_id": iid, "new_status": "resolved"})
    say("is it time for an oil change?")
    ctx = reply_calls[-1]["messages"][-1]["content"]
    assert chat.LOGGING_NOTE in ctx and "OPEN ISSUES:" in ctx and "squeaky brakes" in ctx
    assert "old resolved thing" not in ctx
    assert ctx.endswith("Joey says: is it time for an oil change?")
    path2, d2 = fresh()
    say("is it time for an oil change?")
    assert "No open issues." in reply_calls[-1]["messages"][-1]["content"]
    shutil.rmtree(d); shutil.rmtree(d2)


@check("L2 an unexpected crash inside extraction never loses the reply: it becomes a visible note")
def _():
    path, d = fresh()
    saved = chat.extract_and_propose

    def boom(message):
        raise KeyError("boom")

    chat.extract_and_propose = boom
    try:
        out = say("is it time for an oil change?")
    finally:
        chat.extract_and_propose = saved
    assert out.startswith("Now. Listen carefully.\n\n") and "couldn't check" in out and "KeyError" in out
    shutil.rmtree(d)


@check("L2 a failed extraction is reported AFTER the reply as an honest note; nothing queued")
def _():
    path, d = fresh()
    answers["fillup"] = RuntimeError("model down")
    out = say("just fueled up 10 gal for $30")
    assert out.startswith("Now. Listen carefully.\n\n") and "couldn't turn that into a fill-up" in out
    assert "Nothing was proposed" in out and queue_actions() == []
    shutil.rmtree(d)


@check("L2 advice questions are never extracted (the extraction model isn't even called)")
def _():
    path, d = fresh()
    answers["mileage"] = {"kind": "mileage", "mileage": 55000}
    out = say("should I change my oil at 55,000 miles?")
    assert out == "Now. Listen carefully." and model_calls == [] and queue_actions() == []
    shutil.rmtree(d)


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 simultaneous chat messages: no cross-talk, each gets ITS OWN proposal, nothing saved without approval")
def _():
    path, d = fresh()
    answers["mileage"] = lambda p, u: json.dumps({"kind": "mileage", "mileage": first_number(u)})
    outs = {}

    def go(n):
        o = say(f"my car has {70000 + n} miles on it")
        with _lock:
            outs[n] = o

    threads = [threading.Thread(target=go, args=(n,)) for n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    for n in range(20):
        assert f"{70000 + n:,} miles" in outs[n], (n, outs[n])
        assert not [m for m in range(20) if m != n and f"{70000 + m:,} miles" in outs[n]], n
    q = queue_actions()
    assert len(q) == 20 and len({a["id"] for a in q}) == 20
    assert read(path)["vehicles"][0]["current_mileage"] is None       # nothing was saved
    shutil.rmtree(d)


@check("L4 50 messages in a row: the reply is identical every time and there are 50 distinct proposals")
def _():
    path, d = fresh()
    answers["fillup"] = lambda p, u: json.dumps(dict(FILLUP_JSON, gallons=first_number(u)))
    for n in range(50):
        out = say(f"just fueled up {10 + n} gal for $30")
        assert out.startswith("Now. Listen carefully.\n\nProposed: log fill-up"), out
    gallons = sorted(a["details"]["gallons"] for a in queue_actions())
    assert gallons == [10 + n for n in range(50)]
    shutil.rmtree(d)


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 a 50,000-character message and unicode/emoji never crash; only the first 4,000 chars reach the extraction model")
def _():
    path, d = fresh()
    answers["mileage"] = {"kind": "mileage", "mileage": 52000}
    assert isinstance(say("x" * 50000), str)
    out = say("my car has 52,000 miles on it 🏁 泳ぐ " + "y" * 50000)
    assert "Proposed:" in out
    assert all(len(c["user"]) <= 4000 for c in model_calls) and model_calls
    shutil.rmtree(d)


@check("L5 corrupt vehicle file: the reply still streams, the proposal still appears with a visible 'couldn't read' warning, file untouched")
def _():
    path, d = fresh()
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"vehicles": [ {"broken"')
    before = raw_bytes(path)
    answers["fillup"] = dict(FILLUP_JSON, mileage=56100)
    out = say("just fueled up 10 gal for $30 at 56,100 miles")
    assert out.startswith("Now. Listen carefully.\n\nProposed:") and "Couldn't read the vehicle file" in out
    assert "VEHICLE DATA UNAVAILABLE" in reply_calls[-1]["messages"][-1]["content"]
    assert raw_bytes(path) == before
    shutil.rmtree(d)


@check("L5 junk issue entries never break DRIVE's summary; real open issues still show")
def _():
    path, d = fresh()
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"vehicles": [{"active": True, "make": "Honda", "model": "Civic", "year": 2016,
                                 "issues": [5, None, {"description": "x"},
                                            {"id": "a", "status": "open", "description": "real one"},
                                            {"status": "open"}]}]}, f)
    s = t.get_data_summary_for_llm()
    assert "OPEN ISSUES:" in s and "real one" in s
    shutil.rmtree(d)


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)