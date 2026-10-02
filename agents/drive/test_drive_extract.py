"""
DRIVE increment (b), Part 3b-1 — L1, L2, L4, L5 tests for drive_extract.py.
The LOCAL MODEL IS FAKED (no Ollama, no keys, no cost). TEMP files only: your
real vehicle.json and pending_actions.json are never touched.
(L3 — the real local model — comes in 3b-2.)

Run from the repo root:  python -m agents.drive.test_drive_extract
"""
import inspect
import json
import os
import re
import shutil
import tempfile
import threading
import time

_QUEUE_DIR = tempfile.mkdtemp(prefix="drive_extract_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from agents.drive import drive_extract as X
from agents.drive import drive_actions as A
from agents.drive import drive_tools as t
from shared import pending_actions as pa

QUEUE = pa.PENDING_ACTIONS_PATH
_results = []
model_calls = []
answers = {}
_lock = threading.Lock()
today = time.strftime("%Y-%m-%d")


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


def fresh():
    d = tempfile.mkdtemp(prefix="drive_extract_test_")
    os.environ["VEHICLE_DATA_PATH"] = os.path.join(d, "vehicle.json")
    if os.path.exists(QUEUE):
        os.remove(QUEUE)
    model_calls.clear()
    answers.clear()
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


def raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    return False


def queue_actions():
    return read(QUEUE)["actions"] if os.path.exists(QUEUE) else []


def types():
    return [a["type"] for a in queue_actions()]


def seed_issues(path, descs, closed=()):
    issues = [{"id": f"i{n}", "description": d, "status": "resolved" if f"i{n}" in closed else "open",
               "severity": "low", "reported_date": "2026-01-01"} for n, d in enumerate(descs, 1)]
    write_raw(path, {"vehicles": [{"id": "v", "active": True, "make": "Honda", "model": "Civic",
                                   "year": 2016, "current_mileage": 55500, "issues": issues}]})


def first_number(text):
    m = re.search(r"\d[\d,]*", text)
    assert m, text
    return int(m.group(0).replace(",", ""))


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


# The FAKE local model. An answer may be a JSON string, a dict (dumped), a function
# (prompt, user_text) -> text, or an Exception to raise. Default: {"kind": "none"}.
def fake_local(system_prompt, user_text, timeout=90.0):
    kind = kind_of(system_prompt)
    with _lock:
        model_calls.append({"kind": kind, "prompt": system_prompt, "user": user_text})
    a = answers.get(kind, '{"kind": "none"}')
    if isinstance(a, Exception):
        raise a
    if callable(a):
        return a(system_prompt, user_text)
    return a if isinstance(a, str) else json.dumps(a)


X.complete_ollama_json = fake_local

MILEAGE_JSON = {"kind": "mileage", "mileage": 52000}
FILLUP_JSON = {"kind": "fillup", "date": "", "gallons": 10, "price_per_gallon": None, "total_cost": 30, "mileage": None}
MAINT_JSON = {"kind": "maintenance", "service_type": "oil_change", "date": "", "mileage": None, "shop": "",
              "cost": None, "performed_by": "", "notes": "", "parts_used": [], "fixes_issue_numbers": [],
              "more_jobs": False}
ISSUE_JSON = {"kind": "issue", "description": "tire pressure light is on", "severity": "", "notes": "", "date": ""}


def upd(**kw):
    d = {"kind": "issue_update", "issue_numbers": [], "resolved_all": False, "ambiguous": False,
         "notes": "", "date": ""}
    d.update(kw)
    return d


# ───────────────────────── L1 — STATIC ─────────────────────────

with open(X.__file__, encoding="utf-8") as _f:
    SRC = _f.read()
with open(A.__file__, encoding="utf-8") as _f:
    ACT_SRC = _f.read()


@check("L1 extraction only PROPOSES: it never approves, denies, saves, or touches a writer")
def _():
    assert "drive_actions.propose_" in SRC
    for banned in ("approve_and_execute", "deny_action", "update_json", "drive_logging", "json.dump"):
        assert banned not in SRC, banned
    assert not re.search(r"\bopen\(", SRC)


@check("L1 local model only via the shared helper; whole-word matching; no bare except, no secrets, no old paths")
def _():
    assert "from shared.model_client import complete_ollama_json" in SRC and "import ollama" not in SRC
    assert "contains_keyword" in SRC and ".lower()" not in SRC
    assert not re.search(r"except\s*:", SRC)
    assert "NEXUS SYSTEM" not in SRC and "API_KEY" not in SRC


@check("L1 every prompt spells out an exact JSON shape and the 'none' escape")
def _():
    for kind, prompt in X._PROMPTS.items():
        assert f'"kind": "{kind}"' in prompt, kind
        assert '{"kind": "none"}' in prompt, kind


@check("L1 list_open_issues (the helper extraction uses) is read-only")
def _():
    m = re.search(r"^def list_open_issues\(.*?(?=^def |\Z)", ACT_SRC, re.S | re.M)
    assert m
    body = m.group(0)
    assert "log." not in body and "create_pending_action" not in body and "claim_action" not in body


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 detection: Joey's real example messages, plus questions/advice and look-alike words")
def _():
    cases = [
        ("my car has 52,000 miles on it", ["mileage"]),
        ("I made it to 53,000 miles", ["mileage"]),
        ("just fueled up 10 gal for $30", ["fillup"]),
        ("filled her up, 9.67 gal for $28.87", ["fillup"]),
        ("i just serviced my car. i got her oil changed", ["maintenance"]),
        ("my tire pressure light is on and idk what to do. What does the buzzing mean while driving", ["issue"]),
        ("got the brakes replaced. i services my vehicle and it's at a 100%", ["issue_update", "maintenance"]),
        ("got an oil change at 56,000 miles", ["maintenance"]),
        ("filled up 10 gal for $30 at 56,100 miles", ["fillup"]),
        ("my check engine light is fixed now", ["issue_update", "issue"]),
        ("everything\u2019s fixed", ["issue_update"]),
        ("I need an oil change at 55,000 miles", ["mileage"]),
        ("should I change my oil at 55,000 miles?", []),
        ("how much does an oil change cost", []),
        ("what's my current mileage", []),
        ("digital gallery 200 visitors", []),
        ("", []), ("     ", []), ("hello there", []),
    ]
    for message, want in cases:
        assert X.detect_report_kinds(message) == want, (message, X.detect_report_kinds(message), want)


@check("L2 a non-string message fails loudly (TypeError), never guesses")
def _():
    for bad in (None, 123, [], {}, b"bytes"):
        assert raises(lambda b=bad: X.detect_report_kinds(b), TypeError), bad  # type: ignore
        assert raises(lambda b=bad: X.extract_and_propose(b), TypeError), bad  # type: ignore


@check("L2 extract_and_propose takes ONLY Joey's message (no history, no replies, no memory can reach the model)")
def _():
    assert list(inspect.signature(X.extract_and_propose).parameters) == ["message", "today"]


@check("L2 mileage: queued as a clean proposal, vehicle file untouched (not even created); the model saw only Joey's words")
def _():
    path, d = fresh()
    answers["mileage"] = MILEAGE_JSON
    msg = "my car has 52,000 miles on it"
    notes = X.extract_and_propose(msg)
    assert len(notes) == 1 and "Nothing is saved until you approve" in notes[0]
    q = queue_actions()
    assert len(q) == 1 and q[0]["type"] == "log_mileage" and q[0]["status"] == "pending"
    assert q[0]["details"] == {"mileage": 52000}
    assert not os.path.exists(path)
    assert [c["kind"] for c in model_calls] == ["mileage"] and model_calls[0]["user"] == msg
    shutil.rmtree(d)


@check("L2 fill-up: 10 gal for $30 -> price worked out, mileage honestly 'not stated'")
def _():
    path, d = fresh()
    answers["fillup"] = FILLUP_JSON
    notes = X.extract_and_propose("just fueled up 10 gal for $30")
    assert len(notes) == 1 and "mileage not stated" in notes[0]
    det = queue_actions()[0]["details"]
    assert queue_actions()[0]["type"] == "log_fillup"
    assert det["gallons"] == 10 and det["total_cost"] == 30 and det["price_per_gallon"] == 3 and det["mileage"] is None
    assert [c["kind"] for c in model_calls] == ["fillup"]
    shutil.rmtree(d)


@check("L2 service: 'I got her oil changed' -> oil_change proposal with nothing invented, vehicle file untouched")
def _():
    path, d = fresh()
    answers["maintenance"] = MAINT_JSON
    notes = X.extract_and_propose("i just serviced my car. i got her oil changed")
    assert len(notes) == 1 and "Oil Change" in notes[0] and "mileage not stated" in notes[0]
    det = queue_actions()[0]["details"]
    assert det["service_type"] == "oil_change" and det["mileage"] is None and det["cost"] is None
    assert det["date"] == today and not os.path.exists(path)
    shutil.rmtree(d)


@check("L2 issue: Joey's tire-light message -> an issue proposal (severity honestly 'not stated')")
def _():
    path, d = fresh()
    answers["issue"] = ISSUE_JSON
    msg = "my tire pressure light is on and idk what to do. What does the buzzing mean while driving"
    notes = X.extract_and_propose(msg)
    assert len(notes) == 1 and "tire pressure light is on" in notes[0] and "severity: not stated" in notes[0]
    q = queue_actions()
    assert q[0]["type"] == "log_issue" and q[0]["details"]["severity"] is None
    shutil.rmtree(d)


@check("L2 a {'kind': 'none'} answer means no notes, nothing queued")
def _():
    path, d = fresh()
    notes = X.extract_and_propose("my car has 52,000 miles on it")
    assert notes == [] and queue_actions() == [] and len(model_calls) == 1
    shutil.rmtree(d)


@check("L2 prompts: today's date, the service keys and the NUMBERED open problems are filled in; nothing left unfilled")
def _():
    path, d = fresh()
    seed_issues(path, ["squeaky brakes", "tire light"])
    answers["maintenance"] = MAINT_JSON
    X.extract_and_propose("got an oil change", today="2026-05-05")
    p = model_calls[0]["prompt"]
    assert "2026-05-05" in p and "{{" not in p and "oil_change" in p and "brake_inspection" in p
    assert "1 — squeaky brakes" in p and "2 — tire light" in p
    X.extract_and_propose("my brakes are squealing")
    ip = [c for c in model_calls if c["kind"] == "issue"][0]["prompt"]
    assert "1 — squeaky brakes" in ip
    fresh()
    X.extract_and_propose("got an oil change")
    assert "(none)" in model_calls[0]["prompt"]
    shutil.rmtree(d)


@check("L2 every failure becomes ONE honest note and queues nothing (junk JSON, model down, empty, wrong kind, rejected data); a ```json fence is fine")
def _():
    msg = "just fueled up 10 gal for $30"
    bad_cases = (
        ("not json", "valid JSON"), (RuntimeError("boom"), "local model call failed"),
        ("", "returned nothing"), (MILEAGE_JSON, "unexpected answer type"),
        ({"kind": "fillup", "gallons": None, "total_cost": None, "price_per_gallon": None}, "gallons or the total cost"),
    )
    for ans, expect in bad_cases:
        path, d = fresh()
        answers["fillup"] = ans
        notes = X.extract_and_propose(msg)
        assert len(notes) == 1 and "couldn't" in notes[0] and expect in notes[0], (ans, notes)
        assert "Nothing was proposed" in notes[0] and queue_actions() == []
        shutil.rmtree(d)
    path, d = fresh()
    answers["fillup"] = "```json\n" + json.dumps(FILLUP_JSON) + "\n```"
    notes = X.extract_and_propose(msg)
    assert len(notes) == 1 and "Proposed:" in notes[0] and len(queue_actions()) == 1
    shutil.rmtree(d)


@check("L2 a mileage that rides along with a service goes on THAT record; no separate mileage proposal")
def _():
    path, d = fresh()
    answers["maintenance"] = dict(MAINT_JSON, mileage=56000)
    X.extract_and_propose("got an oil change at 56,000 miles")
    assert [c["kind"] for c in model_calls] == ["maintenance"]
    assert types() == ["log_maintenance"] and queue_actions()[0]["details"]["mileage"] == 56000
    shutil.rmtree(d)


@check("L2 two things in one message -> two proposals")
def _():
    path, d = fresh()
    answers["fillup"] = FILLUP_JSON
    answers["maintenance"] = MAINT_JSON
    notes = X.extract_and_propose("filled up 10 gal for $30 and got my oil changed")
    assert len(notes) == 2 and sorted(types()) == ["log_fillup", "log_maintenance"]
    shutil.rmtree(d)


@check("L2 a 4th thing in one message is NOT silently dropped: only 3 are handled and Joey is told")
def _():
    path, d = fresh()
    seed_issues(path, ["squeaky brakes"])
    answers["issue_update"] = upd(issue_numbers=[1])
    answers["fillup"] = FILLUP_JSON
    answers["maintenance"] = MAINT_JSON
    notes = X.extract_and_propose("filled up 10 gal for $30, got my oil changed, my check engine light came on, and the brakes are fixed")
    assert [c["kind"] for c in model_calls] == ["issue_update", "fillup", "maintenance"]
    assert sorted(types()) == ["log_fillup", "log_maintenance", "update_issue"]
    assert len(notes) == 4 and "first 3" in notes[-1]
    shutil.rmtree(d)


@check("L2 'the second one is fixed': ONE named issue -> a single-issue proposal naming it; the proposal changes nothing")
def _():
    path, d = fresh()
    seed_issues(path, ["squeaky brakes", "tire pressure light"])
    before = raw_bytes(path)
    answers["issue_update"] = upd(issue_numbers=[2])
    notes = X.extract_and_propose("the second one is fixed now")
    assert len(notes) == 1 and "tire pressure light" in notes[0]
    q = queue_actions()
    assert q[0]["type"] == "update_issue" and q[0]["details"]["issue_id"] == "i2"
    assert raw_bytes(path) == before
    shutil.rmtree(d)


@check("L2 two named issues -> ONE bulk proposal naming both")
def _():
    path, d = fresh()
    seed_issues(path, ["squeaky brakes", "tire pressure light", "wobbly mirror"])
    answers["issue_update"] = upd(issue_numbers=[1, 3])
    notes = X.extract_and_propose("the brakes and the mirror are fixed")
    assert len(notes) == 1 and "squeaky brakes" in notes[0] and "wobbly mirror" in notes[0]
    q = queue_actions()
    assert q[0]["type"] == "update_issues" and q[0]["details"]["issue_ids"] == ["i1", "i3"]
    shutil.rmtree(d)


@check("L2 'everything's fixed' resolves ALL open issues (Python decides, whatever numbers the model gave); one open -> single-issue type")
def _():
    path, d = fresh()
    seed_issues(path, ["a", "b", "c", "d"], closed=("i4",))
    answers["issue_update"] = upd(resolved_all=True, issue_numbers=[99])
    X.extract_and_propose("all good now, everything's fixed")
    q = queue_actions()
    assert q[0]["type"] == "update_issues" and q[0]["details"]["issue_ids"] == ["i1", "i2", "i3"]
    path, d2 = fresh()
    seed_issues(path, ["only one"])
    answers["issue_update"] = upd(resolved_all=True)
    X.extract_and_propose("all good now, everything's fixed")
    assert types() == ["update_issue"]
    shutil.rmtree(d); shutil.rmtree(d2)


@check("L2 ambiguous -> candidates are listed, Joey is asked, nothing queued")
def _():
    path, d = fresh()
    seed_issues(path, ["tire pressure light is on", "check engine light is on"])
    answers["issue_update"] = upd(issue_numbers=[1, 2], ambiguous=True)
    notes = X.extract_and_propose("my light is fixed")
    assert len(notes) == 1 and "tire pressure light is on" in notes[0] and "check engine light is on" in notes[0]
    assert "Nothing was proposed" in notes[0] and queue_actions() == []
    shutil.rmtree(d)


@check("L2 junk issue numbers are ignored (bool, 1.5, text, negative, 0, too big, null, dict) -> 'couldn't tell'; '2' and 2.0 are accepted")
def _():
    path, d = fresh()
    seed_issues(path, ["first", "second"])
    answers["issue_update"] = upd(issue_numbers=[True, 1.5, "x", -1, 0, 99, None, {"a": 1}])
    notes = X.extract_and_propose("the second one is fixed now")
    assert len(notes) == 1 and "couldn't tell which" in notes[0] and queue_actions() == []
    for good in (["2"], [2.0]):
        fresh_path, d2 = fresh()
        seed_issues(fresh_path, ["first", "second"])
        answers["issue_update"] = upd(issue_numbers=good)
        X.extract_and_propose("the second one is fixed now")
        assert queue_actions()[0]["details"]["issue_id"] == "i2", good
        shutil.rmtree(d2)
    shutil.rmtree(d)


@check("L2 nothing open to fix -> the model isn't even called and Joey hears nothing")
def _():
    path, d = fresh()
    assert X.extract_and_propose("the council fixed my sidewalk") == [] and model_calls == []
    seed_issues(path, ["old one"], closed=("i1",))
    assert X.extract_and_propose("the council fixed my sidewalk") == [] and model_calls == []
    shutil.rmtree(d)


@check("L2 unreadable vehicle file: 'it's fixed' says so plainly (no proposal); a plain service report still works")
def _():
    path, d = fresh()
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"vehicles": [ {"broken"')
    before = raw_bytes(path)
    notes = X.extract_and_propose("the second one is fixed now")
    assert len(notes) == 1 and "couldn't read your open issues" in notes[0] and model_calls == []
    answers["maintenance"] = MAINT_JSON
    notes = X.extract_and_propose("got the oil changed")
    assert len(notes) == 1 and "Proposed:" in notes[0] and types() == ["log_maintenance"]
    assert raw_bytes(path) == before
    shutil.rmtree(d)


@check("L2 a service that clearly fixes an open issue -> TWO separate proposals (service + resolve), each deniable")
def _():
    path, d = fresh()
    seed_issues(path, ["squeaky brakes", "tire light"])
    answers["maintenance"] = dict(MAINT_JSON, service_type="brake replacement", fixes_issue_numbers=[1])
    notes = X.extract_and_propose("got the brakes replaced")
    assert len(notes) == 2 and "Brake Replacement" in notes[0] and "squeaky brakes" in notes[1]
    q = queue_actions()
    assert [a["type"] for a in q] == ["log_maintenance", "update_issue"] and q[1]["details"]["issue_id"] == "i1"
    shutil.rmtree(d)


@check("L2 'brakes replaced ... 100%' never proposes the same issue twice (resolve-all covers the service's fix)")
def _():
    msg = "got the brakes replaced. i services my vehicle and it's at a 100%"
    path, d = fresh()
    seed_issues(path, ["squeaky brakes", "tire light"])
    answers["issue_update"] = upd(resolved_all=True)
    answers["maintenance"] = dict(MAINT_JSON, service_type="brake replacement", fixes_issue_numbers=[1])
    X.extract_and_propose(msg)
    assert types() == ["update_issues", "log_maintenance"]
    path, d2 = fresh()
    seed_issues(path, ["squeaky brakes"])
    answers["issue_update"] = upd(resolved_all=True)
    answers["maintenance"] = dict(MAINT_JSON, service_type="brake replacement", fixes_issue_numbers=[1])
    X.extract_and_propose(msg)
    assert types() == ["update_issue", "log_maintenance"]
    shutil.rmtree(d); shutil.rmtree(d2)


@check("L2 a second job in a service report is NOT silently dropped (Joey is told to send it separately)")
def _():
    path, d = fresh()
    answers["maintenance"] = dict(MAINT_JSON, more_jobs=True)
    notes = X.extract_and_propose("got an oil change and new tires")
    assert len(notes) == 2 and "more than one job" in notes[1] and types() == ["log_maintenance"]
    shutil.rmtree(d)


@check("L2 dates: a stated date is kept; a future date becomes today")
def _():
    path, d = fresh()
    answers["fillup"] = dict(FILLUP_JSON, date="2026-01-15")
    X.extract_and_propose("just fueled up 10 gal for $30")
    answers["fillup"] = dict(FILLUP_JSON, date="2999-01-01")
    X.extract_and_propose("just fueled up 10 gal for $30")
    q = queue_actions()
    assert q[0]["details"]["date"] == "2026-01-15" and q[1]["details"]["date"] == today
    shutil.rmtree(d)


@check("L2 end to end: extract -> approve really saves (fill-up and a resolved issue)")
def _():
    path, d = fresh()
    answers["fillup"] = FILLUP_JSON
    X.extract_and_propose("just fueled up 10 gal for $30")
    out = A.approve_and_execute(queue_actions()[0]["id"])
    assert out.startswith("Fill-up logged") and len(read(path)["vehicles"][0]["gas_log"]) == 1
    seed_issues(path, ["first", "second"])
    answers["issue_update"] = upd(issue_numbers=[1])
    X.extract_and_propose("the first one is fixed")
    aid = [a for a in queue_actions() if a["type"] == "update_issue"][0]["id"]
    assert "Issue marked resolved" in A.approve_and_execute(aid)
    assert [i for i, _desc in A.list_open_issues()] == ["i2"]
    shutil.rmtree(d)


@check("L2 list_open_issues: open ones only, in file order, junk skipped, text cut to 100; missing file = none (not created); corrupt = RuntimeError")
def _():
    path, d = fresh()
    assert A.list_open_issues() == [] and not os.path.exists(path)
    write_raw(path, {"vehicles": [{"active": True, "issues": [
        5, None, {"id": "a", "description": "d1", "status": "open"}, {"id": "b", "description": "d2", "status": "resolved"},
        {"id": "c", "status": None}, {"id": 7}, {"id": "e", "description": "x" * 500}]}]})
    assert A.list_open_issues() == [("a", "d1"), ("c", ""), ("e", "x" * 100)]
    with open(path, "w", encoding="utf-8") as f:
        f.write("{broken")
    assert raises(A.list_open_issues, RuntimeError)
    shutil.rmtree(d)


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 100 extractions in a row: 100 distinct pending proposals, each with its own mileage, vehicle file untouched")
def _():
    path, d = fresh()
    answers["mileage"] = lambda p, u: json.dumps({"kind": "mileage", "mileage": first_number(u)})
    for n in range(100):
        assert len(X.extract_and_propose(f"my car has {50000 + n} miles on it")) == 1
    q = queue_actions()
    assert len(q) == 100 and all(a["status"] == "pending" for a in q)
    assert {a["details"]["mileage"] for a in q} == {50000 + n for n in range(100)}
    assert not os.path.exists(path)
    shutil.rmtree(d)


@check("L4 20 simultaneous extractions: no cross-talk (each proposal carries its OWN message's number), none lost")
def _():
    path, d = fresh()
    answers["mileage"] = lambda p, u: json.dumps({"kind": "mileage", "mileage": first_number(u)})
    errors = []

    def go(n):
        try:
            X.extract_and_propose(f"my car has {60000 + n} miles on it")
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go, args=(n,)) for n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    q = queue_actions()
    assert not errors, errors
    assert len(q) == 20 and len({a["id"] for a in q}) == 20
    assert {a["details"]["mileage"] for a in q} == {60000 + n for n in range(20)}
    shutil.rmtree(d)


@check("L4 20 simultaneous MIXED extractions (fill-up / service / issue): right counts, right values")
def _():
    path, d = fresh()
    answers["fillup"] = lambda p, u: json.dumps(dict(FILLUP_JSON, gallons=first_number(u)))
    answers["maintenance"] = MAINT_JSON
    answers["issue"] = ISSUE_JSON
    errors = []

    def go(n):
        try:
            k = n % 3
            msg = (f"just fueled up {10 + n} gal for $30" if k == 0
                   else "got an oil change" if k == 1 else "my check engine light came on")
            X.extract_and_propose(msg)
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go, args=(n,)) for n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert not errors, errors
    q = queue_actions()
    assert types().count("log_fillup") == 7 and types().count("log_maintenance") == 7 and types().count("log_issue") == 6
    gallons = {a["details"]["gallons"] for a in q if a["type"] == "log_fillup"}
    assert gallons == {10 + n for n in range(20) if n % 3 == 0}
    shutil.rmtree(d)


@check("L4 20 'everything's fixed' proposals approved at once: exactly ONE resolves the issues, the rest fail cleanly")
def _():
    path, d = fresh()
    seed_issues(path, ["a", "b", "c"])
    answers["issue_update"] = upd(resolved_all=True)
    for _n in range(20):
        X.extract_and_propose("all good now, everything's fixed")
    ids = [a["id"] for a in queue_actions()]
    assert len(ids) == 20
    results, lock = [], threading.Lock()

    def go(aid):
        r = A.approve_and_execute(aid)
        with lock:
            results.append(r)

    threads = [threading.Thread(target=go, args=(i,)) for i in ids]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert len([r for r in results if r.startswith("Marked 3 issue(s) resolved")]) == 1, results
    assert all(i["status"] == "resolved" for i in read(path)["vehicles"][0]["issues"])
    shutil.rmtree(d)


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 empty / huge / unicode / regex-special messages never crash; only the first 4,000 chars reach the model")
def _():
    path, d = fresh()
    answers["mileage"] = MILEAGE_JSON
    for msg in ("", "     ", "x" * 50000, "my car has 52,000 miles 🏁 泳ぐ [(.*)] \\", "[", "(", "\\"):
        assert isinstance(X.extract_and_propose(msg), list), msg
    model_calls.clear()
    X.extract_and_propose("my car has 52,000 miles on it " + "x" * 50000)
    assert len(model_calls) == 1 and len(model_calls[0]["user"]) == 4000
    shutil.rmtree(d)


@check("L5 hostile model answers (not-an-object, wrong kind, junk/absurd numbers, garbage) -> exactly ONE honest note, nothing queued, no crash")
def _():
    hostile = ["[]", '"x"', "null", "123", "{}", '{"kind": 5}', '{"kind": ["x"]}', '{"kind": "mileage"}',
               '{"kind":"mileage","mileage":{"a":1}}', '{"kind":"mileage","mileage":"abc"}',
               '{"kind":"mileage","mileage":-5}', '{"kind":"mileage","mileage":1e12}', "garbage {", ""]
    for raw in hostile:
        path, d = fresh()
        answers["mileage"] = raw
        notes = X.extract_and_propose("my car has 52,000 miles on it")
        assert len(notes) == 1 and "couldn't" in notes[0] and queue_actions() == [], (raw, notes)
        shutil.rmtree(d)


@check("L5 hostile issue numbers (Infinity, NaN, 1e999, text instead of a list, 'true' as text) never crash or resolve anything")
def _():
    raws = ['{"kind":"issue_update","issue_numbers":[Infinity,NaN,1e999,true,1.5,"x",-1,0,99,null,{"a":1}]}',
            '{"kind":"issue_update","issue_numbers":"1"}',
            '{"kind":"issue_update","issue_numbers":[],"resolved_all":"true"}',
            '{"kind":"issue_update","issue_numbers":[1],"ambiguous":"yes"}']
    for i, raw in enumerate(raws):
        path, d = fresh()
        seed_issues(path, ["alpha problem", "beta problem"])
        answers["issue_update"] = raw
        notes = X.extract_and_propose("the second one is fixed now")
        if i == 3:                                   # a text 'yes' is not a real true: the numbers are used as given
            assert types() == ["update_issue"], notes
        else:
            assert len(notes) == 1 and "couldn't tell which" in notes[0] and queue_actions() == [], (raw, notes)
        shutil.rmtree(d)


@check("L5 one failing extraction never blocks another in the same message")
def _():
    path, d = fresh()
    answers["fillup"] = RuntimeError("model went away")
    answers["maintenance"] = MAINT_JSON
    notes = X.extract_and_propose("filled up 10 gal for $30 and got my oil changed")
    assert len(notes) == 2 and "couldn't" in notes[0] and "Proposed:" in notes[1]
    assert types() == ["log_maintenance"]
    shutil.rmtree(d)


@check("L5 a corrupt approval-queue file is reported as a note (never swallowed, never saved around), vehicle file untouched")
def _():
    path, d = fresh()
    os.makedirs(os.path.dirname(QUEUE), exist_ok=True)
    with open(QUEUE, "w", encoding="utf-8") as f:
        f.write("{not json")
    answers["mileage"] = MILEAGE_JSON
    notes = X.extract_and_propose("my car has 52,000 miles on it")
    assert len(notes) == 1 and "couldn't" in notes[0] and not os.path.exists(path)
    os.remove(QUEUE)
    shutil.rmtree(d)


@check("L5 120 open issues: the model is shown only the most recent 50, numbers map to the RIGHT ids")
def _():
    path, d = fresh()
    seed_issues(path, [f"problem {k}" for k in range(1, 121)])
    answers["issue_update"] = upd(issue_numbers=[50])
    X.extract_and_propose("the last one is fixed")
    assert model_calls[0]["prompt"].count("— problem") == 50
    q = queue_actions()
    assert q[0]["type"] == "update_issue" and q[0]["details"]["issue_id"] == "i120"
    shutil.rmtree(d)


@check("L5 'everything's fixed' with MORE than 50 open issues is refused with a clear note, nothing queued")
def _():
    path, d = fresh()
    seed_issues(path, [f"problem {k}" for k in range(1, 121)])
    answers["issue_update"] = upd(resolved_all=True)
    notes = X.extract_and_propose("all good now, everything's fixed")
    assert len(notes) == 1 and "too many" in notes[0] and queue_actions() == []
    shutil.rmtree(d)


@check("L5 unicode/emoji in saved issue descriptions reaches the model prompt and proposals intact")
def _():
    path, d = fresh()
    seed_issues(path, ["Bremsen quietschen 🔧 泳ぐ"])
    answers["issue_update"] = upd(issue_numbers=[1])
    notes = X.extract_and_propose("the first one is fixed")
    assert "Bremsen quietschen 🔧 泳ぐ" in model_calls[0]["prompt"] and "Bremsen quietschen 🔧 泳ぐ" in notes[0]
    shutil.rmtree(d)


@check("L1 the model is told to keep routine reports short: no speculating, no unrequested recommendations, no doing arithmetic itself")
def _():
    note = chat.LOGGING_NOTE.lower()
    assert "do not speculate" in note and "do not recommend a service or a dealership" in note
    assert "do not work out prices" in note and "few sentences" in note


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)