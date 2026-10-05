"""
DRIVE increment (b), Part 6b — L1, L2, L4, L5 tests for the recall check: drive_recall.py, the saved
snapshot writer + approval, and the chat.py wiring. NHTSA, DRIVE's reply and the extraction step are
all FAKED. TEMP files only.

Run from the repo root:  python -m agents.drive.test_drive_recall
"""
import json
import os
import re
import shutil
import tempfile
import threading
import urllib.error
import urllib.parse
from email.message import Message
from typing import Any

_QUEUE_DIR = tempfile.mkdtemp(prefix="drive_recall_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from agents.drive import chat
from agents.drive import drive_actions as A
from agents.drive import drive_logging as Lg
from agents.drive import drive_recall as _drive_recall
from shared import agent_topics
from shared import nhtsa as N
from shared import pending_actions as pa

QUEUE = pa.PENDING_ACTIONS_PATH
R: Any = _drive_recall      # typed loosely on purpose: these tests read optional results and hand in junk
_results = []
_lock = threading.Lock()
net_calls = []
net: Any = {"v": None}
reply_calls = []


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


def fake_http(url, timeout):
    with _lock:
        net_calls.append(url)
    r = net["v"]
    if callable(r):
        r = r(url)
    if isinstance(r, BaseException):
        raise r
    return r


def fake_reply(agent, tier, system_prompt, messages, location=""):
    with _lock:
        reply_calls.append({"messages": list(messages)})
    yield "Now. "
    yield "Listen carefully."


N._http_get = fake_http
chat.stream_by_tier = fake_reply
chat.web_search = lambda q, num_results=3: "Web search results:\n\n1. x"
chat.extract_and_propose = lambda message: []
chat.memory_context_block = lambda message: None
chat.remember_from_message = lambda message: []

chat.memory_context_block = lambda message: None
chat.remember_from_message = lambda message: []

def fresh():
    d = tempfile.mkdtemp(prefix="drive_recall_test_")
    os.environ["VEHICLE_DATA_PATH"] = os.path.join(d, "vehicle.json")
    if os.path.exists(QUEUE):
        os.remove(QUEUE)
    net_calls.clear()
    reply_calls.clear()
    net["v"] = None
    return os.environ["VEHICLE_DATA_PATH"], d


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_raw(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def raw_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def raises(fn, exc: type[BaseException] = Exception):
    try:
        fn()
    except exc:
        return True
    return False


def seed(path, **fields):
    v = {"id": "vehicle_001", "active": True, "make": "Honda", "model": "Civic", "year": 2016,
         "vin": "TESTVIN", "current_mileage": 55500, "mileage_last_updated": None,
         "maintenance_log": [], "upcoming_maintenance": [], "gas_log": [], "issues": [], "recalls": []}
    v.update(fields)
    write_raw(path, {"vehicles": [v]})


def vehicle(path):
    return read(path)["vehicles"][0]


def queue_actions():
    return read(QUEUE)["actions"] if os.path.exists(QUEUE) else []


def status_of(action_id):
    a = pa.get_pending_action(action_id)
    return a["status"] if a else "missing"


def item(n=1, **kw):
    d = {"NHTSACampaignNumber": f"15V{n:06d}", "Manufacturer": "Honda (American Honda Motor Co.)",
         "ReportReceivedDate": "19/03/2015", "Component": "AIR BAGS", "Summary": "The airbag may rupture.",
         "Consequence": "Metal fragments could injure occupants.", "Remedy": "Dealers will replace the inflator.",
         "parkIt": False}
    d.update(kw)
    return d


def body(results):
    return json.dumps({"Count": len(results), "Message": "Results returned successfully", "results": results})


def say(message):
    return "".join(chat.stream_drive(message))


def snap(**kw):
    d = {"source": N and "NHTSA recallsByVehicle", "fetched_at": "2026-10-03T08:53:59", "make": "Honda",
         "model": "Civic", "model_year": 2016, "count": 1, "url": "https://x",
         "recalls": [{"campaign": "15V000001", "manufacturer": "Honda", "component": "AIR BAGS", "summary": "s",
                      "consequence": "c", "remedy": "r", "reported": "2015-03-19", "park_it": False}]}
    d.update(kw)
    return d


def _function_source(src, name):
    m = re.search(rf"^def {name}\(.*?(?=^def |\Z)", src, re.S | re.M)
    assert m, name
    return m.group(0)


with open(R.__file__, encoding="utf-8") as _f:
    RSRC = _f.read()
with open(chat.__file__, encoding="utf-8") as _f:
    CSRC = _f.read()
with open(Lg.__file__, encoding="utf-8") as _f:
    LSRC = _f.read()
with open(A.__file__, encoding="utf-8") as _f:
    ASRC = _f.read()

# ───────────────────────── L1 — STATIC ─────────────────────────


@check("L1 drive_recall only LOOKS and PROPOSES: no approval step, no writer, no raw file access")
def _():
    for banned in ("approve_and_execute", "deny_action", "update_json", "drive_logging", "json.dump"):
        assert banned not in RSRC, banned
    assert not re.search(r"\bopen\(", RSRC)
    assert "drive_actions.propose_recall_snapshot" in RSRC and "from shared import nhtsa" in RSRC


@check("L1 chat.py fetches recall data BEFORE the reply and offers the save AFTER it, and still never touches writers")
def _():
    i_ctx = CSRC.index("prepare_recall_context(message)")
    i_reply = CSRC.index('stream_by_tier("drive"')
    i_note = CSRC.index("propose_recall_snapshot_note(recall_result)")
    assert i_ctx < i_reply < i_note
    for banned in ("drive_logging", "drive_actions", "approve_and_execute", "update_json"):
        assert banned not in CSRC, banned


@check("L1 the snapshot writer uses the locked helper; proposing never writes; only approve_and_execute calls the writer")
def _():
    body_src = _function_source(LSRC, "save_recall_snapshot")
    assert "_modify_vehicle" in body_src and not re.search(r"\bopen\(", body_src)
    assert "log.save_recall_snapshot" not in _function_source(ASRC, "propose_recall_snapshot")
    callers = [fn for fn in re.findall(r"^def (\w+)\(", ASRC, re.M)
              if "log.save_recall_snapshot" in _function_source(ASRC, fn)]
    assert callers == ["approve_and_execute"], callers


@check("L1 the recall trigger words live in shared/agent_topics")
def _():
    assert agent_topics.DRIVE_RECALL_WORDS == ["recall", "recalls", "recalled"]


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 recall questions are recognized by whole words only")
def _():
    for msg, want in (("any recalls on my car?", True), ("Is my Civic recalled?", True), ("RECALL", True),
                      ("what's my mileage", False), ("recallable", False), ("", False)):
        assert R.is_recall_question(msg) is want, msg
    for bad in (None, 5, [], {}):
        assert R.is_recall_question(bad) is False


@check("L2 a message that isn't about recalls makes NO network call")
def _():
    path, d = fresh()
    seed(path)
    assert R.prepare_recall_context("what's my mileage") == (None, None) and net_calls == []
    assert R.prepare_recall_context(None) == (None, None)
    shutil.rmtree(d)


@check("L2 success: a labeled block ('official', 'NOT Joey's VIN') plus the result; year/make/model come from the vehicle FILE")
def _():
    path, d = fresh()
    seed(path)
    net["v"] = body([item(1), item(2)])
    block, result = R.prepare_recall_context("any recalls on my car?")
    assert block.startswith("[NHTSA RECALL DATA") and "2016 Honda Civic" in block and "NOT Joey's VIN" in block
    assert result["count"] == 2 and result["model_year"] == 2016
    q = urllib.parse.parse_qs(urllib.parse.urlparse(net_calls[0]).query)
    assert q == {"make": ["Honda"], "model": ["Civic"], "modelYear": ["2016"]}
    shutil.rmtree(d)


@check("L2 it follows the ACTIVE vehicle in the file (text year works); a missing year/make is a failure note, never a crash")
def _():
    path, d = fresh()
    net["v"] = body([])
    seed(path, make="Ford", model="F-150", year="2018")
    R.prepare_recall_context("recall?")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(net_calls[0]).query)
    assert q == {"make": ["Ford"], "model": ["F-150"], "modelYear": ["2018"]}
    for fields in ({"year": None}, {"make": ""}, {"model": None}, {"year": "twenty"}):
        seed(path, **fields)
        block, result = R.prepare_recall_context("recall?")
        assert block.startswith(N.NHTSA_FAILED_PREFIX) and result is None, fields
    shutil.rmtree(d)


@check("L2 every failure (no connection, HTTP error, junk answer, unreadable vehicle file) becomes a 'lookup failed, do not guess' note and NEVER raises")
def _():
    path, d = fresh()
    seed(path)
    for bad in (urllib.error.URLError("no route"), urllib.error.HTTPError("http://x", 400, "bad", Message(), None),
                "not json", "<html>down</html>", "", '{"results": "x"}'):
        net["v"] = bad
        block, result = R.prepare_recall_context("any recalls?")
        assert block.startswith(N.NHTSA_FAILED_PREFIX) and "Do not guess" in block and result is None, bad
        assert "NHTSA RECALL DATA" not in block
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"vehicles": [ {"broken"')
    net["v"] = body([item(1)])
    block, result = R.prepare_recall_context("any recalls?")
    assert block.startswith(N.NHTSA_FAILED_PREFIX) and result is None
    shutil.rmtree(d)


@check("L2 proposing: a clean proposal, queued as pending, vehicle file untouched; nothing for None")
def _():
    path, d = fresh()
    seed(path)
    net["v"] = body([item(1), item(2)])
    before = raw_bytes(path)
    _b, result = R.prepare_recall_context("recalls?")
    note = R.propose_recall_snapshot_note(result)
    assert note.startswith("Proposed: save this recall check to your vehicle file: NHTSA, 2016 Honda Civic, 2 recall(s), checked ")
    assert "Nothing is saved until you approve" in note
    q = queue_actions()
    assert len(q) == 1 and q[0]["type"] == "save_recall_check" and q[0]["status"] == "pending"
    assert q[0]["details"]["count"] == 2 and q[0]["details"]["source"] == "NHTSA recallsByVehicle"
    assert raw_bytes(path) == before and R.propose_recall_snapshot_note(None) is None
    shutil.rmtree(d)


@check("L2 approving saves a dated snapshot (old text-style entries untouched); approving again does nothing; deny saves nothing")
def _():
    path, d = fresh()
    old = [{"searched_at": "x", "query": "q", "result": "old text"}, "junk"]
    seed(path, recalls=list(old))
    net["v"] = body([item(1), item(2)])
    _b, result = R.prepare_recall_context("recalls?")
    aid, _m = A.propose_recall_snapshot(result)
    out = A.approve_and_execute(aid)
    assert out.startswith("Recall check saved: 2 recall(s) for 2016 Honda Civic (NHTSA, ") and status_of(aid) == "executed"
    rec = vehicle(path)["recalls"]
    last = rec[-1]
    assert rec[:2] == old and last["source"] == "NHTSA recallsByVehicle" and last["count"] == 2 and len(last["recalls"]) == 2
    assert last["query"].endswith("recalls (NHTSA)") and "not this VIN" in last["result"] and last["searched_at"] == last["fetched_at"]
    assert "already executed" in A.approve_and_execute(aid)
    net["v"] = body([item(1), item(2), item(3)])
    _b, result2 = R.prepare_recall_context("recalls?")
    aid2, _m = A.propose_recall_snapshot(result2)
    before = raw_bytes(path)
    assert A.deny_action(aid2).startswith("Denied: save this recall check") and "already denied" in A.approve_and_execute(aid2)
    assert raw_bytes(path) == before
    shutil.rmtree(d)


@check("L2 ONLY when the list changed: an unchanged check (even reordered) is not offered again; a new recall is")
def _():
    path, d = fresh()
    seed(path)
    net["v"] = body([item(1), item(2)])
    _b, result = R.prepare_recall_context("recalls?")
    A.approve_and_execute(A.propose_recall_snapshot(result)[0])
    for same in (body([item(1), item(2)]), body([item(2), item(1)])):
        net["v"] = same
        _b, r2 = R.prepare_recall_context("recalls?")
        note = R.propose_recall_snapshot_note(r2)
        assert "hasn't changed since your last saved check (" in note and "not offering to save it again" in note
    assert len(queue_actions()) == 1
    net["v"] = body([item(1), item(2), item(3)])
    _b, r3 = R.prepare_recall_context("recalls?")
    assert R.propose_recall_snapshot_note(r3).startswith("Proposed:") and len(queue_actions()) == 2
    shutil.rmtree(d)


@check("L2 only the last 10 NHTSA checks are kept (oldest dropped, and Joey is told); older text-style entries are never touched")
def _():
    path, d = fresh()
    originals = [{"searched_at": "x", "query": "q", "result": "old"}, "junk", None, {"source": "other"}]
    seed(path, recalls=list(originals))
    outs = []
    for n in range(12):
        net["v"] = body([item(100 + n)])
        _b, result = R.prepare_recall_context("recalls?")
        outs.append(A.approve_and_execute(A.propose_recall_snapshot(result)[0]))
    rec = vehicle(path)["recalls"]
    nhtsa_entries = [e for e in rec if isinstance(e, dict) and e.get("source") == "NHTSA recallsByVehicle"]
    assert len(nhtsa_entries) == 10 and rec[:4] == originals
    assert [e["recalls"][0]["campaign"] for e in nhtsa_entries] == [f"15V{100 + n:06d}" for n in range(2, 12)]
    assert all("dropped" not in o for o in outs[:10]) and all("dropped" in o for o in outs[10:])
    shutil.rmtree(d)


@check("L2 a recall check for a DIFFERENT vehicle than the active one is refused at approval; nothing saved")
def _():
    path, d = fresh()
    seed(path)
    net["v"] = body([item(1)])
    _b, result = R.prepare_recall_context("recalls?")
    aid, _m = A.propose_recall_snapshot(result)
    seed(path, make="Toyota", model="Corolla")
    before = read(path)
    out = A.approve_and_execute(aid)
    assert out == "That recall check was for a different vehicle than your active one, so nothing was saved."
    assert status_of(aid) == "failed" and read(path) == before
    shutil.rmtree(d)


@check("L2 snapshot validation: junk is rejected; long text and long lists are trimmed; junk recalls dropped; only a real true is 'park it'")
def _():
    for bad in (None, [], "x", 5, snap(source="x"), snap(make=""), snap(model=None), snap(model_year=True),
                snap(model_year="2016"), snap(model_year=1900), snap(fetched_at="yesterday"), snap(fetched_at=""),
                snap(recalls="x"), snap(recalls=None), snap(count=True), snap(count=0), snap(count=None)):
        assert raises(lambda b=bad: Lg.normalize_recall_snapshot(b), ValueError), bad
    long = snap(recalls=[dict(snap()["recalls"][0], summary="word " * 500, park_it="true")])
    n = Lg.normalize_recall_snapshot(long)
    assert len(n["recalls"][0]["summary"]) <= 301 and n["recalls"][0]["summary"].endswith("…")
    assert n["recalls"][0]["park_it"] is False
    many = snap(count=55, recalls=[dict(snap()["recalls"][0], campaign=f"C{k}") for k in range(55)])
    assert len(Lg.normalize_recall_snapshot(many)["recalls"]) == 40 and Lg.normalize_recall_snapshot(many)["count"] == 55
    junky = snap(count=1, recalls=[5, None, {"campaign": ""}, snap()["recalls"][0]])
    assert len(Lg.normalize_recall_snapshot(junky)["recalls"]) == 1


@check("L2 chat, success: the reply streams FIRST, the model got the labeled NHTSA block, then the save offer follows")
def _():
    path, d = fresh()
    seed(path)
    net["v"] = body([item(1), item(2)])
    out = say("any recalls on my car?")
    assert out.startswith("Now. Listen carefully.\n\nReminder: NHTSA's list covers ALL 2016 Honda Civic vehicles, not your VIN specifically.")
    assert out.index("Reminder: NHTSA's list") < out.index("Proposed: save this recall check to your vehicle file: NHTSA, 2016 Honda Civic, 2 recall(s)")
    ctx = reply_calls[-1]["messages"][-1]["content"]
    assert "[NHTSA RECALL DATA" in ctx and ctx.index("[NHTSA RECALL DATA") < ctx.index("Joey says:") and chat.LOGGING_NOTE in ctx
    q = queue_actions()
    assert len(q) == 1 and q[0]["type"] == "save_recall_check" and q[0]["status"] == "pending"
    shutil.rmtree(d)


@check("L2 chat, lookup failed: the model is told it failed (and not to guess); NO save offer; the reply is untouched")
def _():
    path, d = fresh()
    seed(path)
    net["v"] = urllib.error.URLError("no route")
    out = say("any recalls on my car?")
    ctx = reply_calls[-1]["messages"][-1]["content"]
    assert out == "Now. Listen carefully." and queue_actions() == []
    assert "[NHTSA_LOOKUP_FAILED]" in ctx and "Do not guess" in ctx and "NHTSA RECALL DATA" not in ctx
    shutil.rmtree(d)


@check("L2 chat: other questions, refusals and 'show me my history' never touch the network")
def _():
    path, d = fresh()
    seed(path)
    net["v"] = body([item(1)])
    assert say("is it time for an oil change?") == "Now. Listen carefully."
    assert say("what's the weather today, any recalls?") == chat.REFUSAL_MESSAGE
    n_before = len(reply_calls)
    assert isinstance(say("show me my maintenance history and recalls"), str) and len(reply_calls) == n_before + 0
    assert len(net_calls) == 0 and queue_actions() == []
    shutil.rmtree(d)


@check("L2 chat: logging notes come first, the recall offer after; a crash in the offer is a visible note and the reply survives")
def _():
    path, d = fresh()
    seed(path)
    net["v"] = body([item(1)])
    saved_extract, saved_note = chat.extract_and_propose, chat.propose_recall_snapshot_note
    try:
        chat.extract_and_propose = lambda message: ["EXTRACTION NOTE"]
        out = say("any recalls?")
        assert out.index("EXTRACTION NOTE") < out.index("Proposed: save this recall check")

        def boom(result):
            raise KeyError("boom")

        chat.propose_recall_snapshot_note = boom
        out = say("any recalls?")
        assert out.startswith("Now. Listen carefully.\n\n") and "couldn't prepare the offer to save that recall check" in out and "KeyError" in out
    finally:
        chat.extract_and_propose, chat.propose_recall_snapshot_note = saved_extract, saved_note
    shutil.rmtree(d)


@check("L2 chat: if DRIVE's reply itself fails, no save offer is made")
def _():
    path, d = fresh()
    seed(path)
    net["v"] = body([item(1)])

    def broken(agent, tier, system_prompt, messages, location=""):
        yield "partial"
        raise ConnectionError("model down")

    chat.stream_by_tier = broken
    got = []
    try:
        for c in chat.stream_drive("any recalls?"):
            got.append(c)
    except ConnectionError:
        pass
    finally:
        chat.stream_by_tier = fake_reply
    assert got == ["partial"] and queue_actions() == []
    shutil.rmtree(d)


@check("L2 end to end: ask -> approve the offer -> ask again -> 'hasn't changed', no second offer")
def _():
    path, d = fresh()
    seed(path)
    net["v"] = body([item(1), item(2)])
    say("any recalls on my car?")
    out = A.approve_and_execute(queue_actions()[0]["id"])
    assert out.startswith("Recall check saved") and vehicle(path)["recalls"][-1]["count"] == 2
    again = say("any recalls on my car?")
    assert "hasn't changed since your last saved check" in again and len(queue_actions()) == 1
    shutil.rmtree(d)


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 identical snapshots approved at the same time: exactly ONE is saved, 19 refused as duplicates")
def _():
    path, d = fresh()
    seed(path)
    net["v"] = body([item(1)])
    _b, result = R.prepare_recall_context("recalls?")
    ids = [A.propose_recall_snapshot(result)[0] for _n in range(20)]
    results = []

    def go(aid):
        r = A.approve_and_execute(aid)
        with _lock:
            results.append(r)

    threads = [threading.Thread(target=go, args=(i,)) for i in ids]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert len([r for r in results if r.startswith("Recall check saved")]) == 1, results
    assert len([r for r in results if "same as your last saved" in r]) == 19, results
    assert len([e for e in vehicle(path)["recalls"] if isinstance(e, dict) and e.get("source")]) == 1
    shutil.rmtree(d)


@check("L4 20 simultaneous recall questions: every reply intact, every model call got the NHTSA block, 20 separate offers, nothing saved")
def _():
    path, d = fresh()
    seed(path)
    net["v"] = body([item(1), item(2)])
    outs, errors = [], []

    def go():
        try:
            o = say("any recalls on my car?")
            with _lock:
                outs.append(o)
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go) for _n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert not errors, errors
    assert len(outs) == 20 and all(o.startswith("Now. Listen carefully.\n\nReminder:") and "Proposed: save this recall check" in o for o in outs)
    assert len(reply_calls) == 20 and all("[NHTSA RECALL DATA" in c["messages"][-1]["content"] for c in reply_calls)
    assert len(queue_actions()) == 20 and vehicle(path)["recalls"] == []
    shutil.rmtree(d)


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 hostile NHTSA answers (empty, text, HTML, arrays, 100,000-level nesting) never break the chat: reply intact, failure note to the model, no offer")
def _():
    path, d = fresh()
    seed(path)
    for raw in ("", "not json", "<html>down</html>", "[]", "null", '{"results": "x"}', "[" * 100000):
        net["v"] = raw
        reply_calls.clear()
        out = say("any recalls?")
        assert out == "Now. Listen carefully.", (raw[:20], out)
        assert "[NHTSA_LOOKUP_FAILED]" in reply_calls[-1]["messages"][-1]["content"]
    assert queue_actions() == []
    shutil.rmtree(d)


@check("L5 an unreadable vehicle file: the reply still streams, the model is told both the data AND the lookup are unavailable, no offer, file untouched")
def _():
    path, d = fresh()
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"vehicles": [ {"broken"')
    before = raw_bytes(path)
    net["v"] = body([item(1)])
    out = say("any recalls on my car?")
    ctx = reply_calls[-1]["messages"][-1]["content"]
    assert out == "Now. Listen carefully." and "VEHICLE DATA UNAVAILABLE" in ctx and "[NHTSA_LOOKUP_FAILED]" in ctx
    assert queue_actions() == [] and raw_bytes(path) == before and net_calls == []
    shutil.rmtree(d)


@check("L5 NHTSA listing 10,000 recalls: the saved snapshot stays small (40 recalls, true total count) and the proposal/approval work")
def _():
    path, d = fresh()
    seed(path)
    net["v"] = body([item(n, Summary="long text " * 200) for n in range(10000)])
    out = say("any recalls?")
    assert "Proposed: save this recall check" in out and "10000 recall(s)" in out
    assert A.approve_and_execute(queue_actions()[0]["id"]).startswith("Recall check saved: 10000 recall(s)")
    saved = vehicle(path)["recalls"][-1]
    assert saved["count"] == 10000 and len(saved["recalls"]) == 40 and len(json.dumps(saved)) < 80000
    shutil.rmtree(d)


@check("L5 junk already in the recalls list is preserved; a recalls field that isn't a list is never overwritten")
def _():
    path, d = fresh()
    junk = ["j", None, 5, {"nope": 1}, {"source": "NHTSA recallsByVehicle", "recalls": "bad", "count": "x"}]
    seed(path, recalls=list(junk))
    net["v"] = body([item(1)])
    _b, result = R.prepare_recall_context("recalls?")
    aid, _m = A.propose_recall_snapshot(result)
    assert A.approve_and_execute(aid).startswith("Recall check saved")
    assert vehicle(path)["recalls"][:5] == junk
    seed(path, recalls="oops")
    before = raw_bytes(path)
    aid2, _m = A.propose_recall_snapshot(result)
    out = A.approve_and_execute(aid2)
    assert out.startswith("Execution failed") and status_of(aid2) == "failed" and raw_bytes(path) == before
    shutil.rmtree(d)


@check("L5 unicode, emoji and regex characters in NHTSA's text survive the whole round trip intact")
def _():
    path, d = fresh()
    seed(path)
    net["v"] = body([item(1, Summary="Bremsen 泳ぐ 🔧 épaule [(.*)] \\", Component="FREINS 🛑")])
    say("any recalls?")
    A.approve_and_execute(queue_actions()[0]["id"])
    rec = vehicle(path)["recalls"][-1]["recalls"][0]
    assert rec["summary"] == "Bremsen 泳ぐ 🔧 épaule [(.*)] \\" and rec["component"] == "FREINS 🛑"
    shutil.rmtree(d)


@check("L2 the VIN caveat is written by PYTHON after the reply (the real model ignored it): shown on every successful lookup, even when no save is offered, never when the lookup failed")
def _():
    path, d = fresh()
    seed(path)
    net["v"] = body([item(1)])
    out = say("any recalls?")
    assert "Reminder: NHTSA's list covers ALL 2016 Honda Civic vehicles, not your VIN specifically" in out and "nhtsa.gov/recalls" in out
    A.approve_and_execute(queue_actions()[0]["id"])
    again = say("any recalls?")                  # unchanged: no new offer, but the reminder is still there
    assert "hasn't changed" in again and "Reminder:" in again and again.index("Reminder:") < again.index("hasn't changed")
    net["v"] = urllib.error.URLError("no route")
    assert "Reminder:" not in say("any recalls?")
    assert R.recall_footer(None) is None and R.recall_footer("x") is None
    shutil.rmtree(d)


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)