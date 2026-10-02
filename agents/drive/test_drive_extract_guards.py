"""
DRIVE increment (b), Part 3b-3 — tests for the Python guards added after the first
REAL-model run: no duplicate issues, "which one did you mean?", fix claims must
overlap, tidy service names. Local model FAKED. TEMP files only.

Run from the repo root:  python -m agents.drive.test_drive_extract_guards
"""
import json
import os
import re
import shutil
import tempfile
import threading

_QUEUE_DIR = tempfile.mkdtemp(prefix="drive_guards_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from agents.drive import drive_extract as X
from agents.drive import drive_logging as Lg
from shared import pending_actions as pa

QUEUE = pa.PENDING_ACTIONS_PATH
_results = []
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


def fresh():
    d = tempfile.mkdtemp(prefix="drive_guards_test_")
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


def queue_actions():
    return read(QUEUE)["actions"] if os.path.exists(QUEUE) else []


def types():
    return [a["type"] for a in queue_actions()]


def seed_issues(path, descs):
    issues = [{"id": f"i{n}", "description": d, "status": "open", "severity": "low",
               "reported_date": "2026-01-01"} for n, d in enumerate(descs, 1)]
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


X.complete_ollama_json = fake_local

ISSUE_JSON = {"kind": "issue", "description": "tire pressure light is on", "severity": "", "notes": "", "date": ""}
MAINT_JSON = {"kind": "maintenance", "service_type": "oil_change", "date": "", "mileage": None, "shop": "",
              "cost": None, "performed_by": "", "notes": "", "parts_used": [], "fixes_issue_numbers": [],
              "more_jobs": False}
MSG_D = "my tire pressure light is on and idk what to do. What does the buzzing mean while driving"


def upd(**kw):
    d = {"kind": "issue_update", "issue_numbers": [], "resolved_all": False, "ambiguous": False,
         "notes": "", "date": ""}
    d.update(kw)
    return d


@check("L1 extraction uses the issue_match guards, still has no substring keyword matching, and the new prompt rules are in")
def _():
    with open(X.__file__, encoding="utf-8") as f:
        src = f.read()
    assert "issue_match.find_duplicate" in src and "issue_match.issue_scores" in src and "issue_match.overlap" in src
    assert ".lower()" not in src and not re.search(r"\bopen\(", src)
    assert "Never write about his question" in X.ISSUE_PROMPT
    assert "the business name only if he named one" in X.MAINTENANCE_PROMPT
    assert "Never put percentages" in X.MAINTENANCE_PROMPT


@check("L2 a problem ALREADY on the open list is not proposed again (Joey is told); a different problem still is")
def _():
    path, d = fresh()
    seed_issues(path, ["tire pressure light is on"])
    answers["issue"] = ISSUE_JSON
    notes = X.extract_and_propose(MSG_D)
    assert len(notes) == 1 and "already on your open list" in notes[0] and "tire pressure light is on" in notes[0]
    assert queue_actions() == []
    answers["issue"] = dict(ISSUE_JSON, description="check engine light is on")
    notes = X.extract_and_propose("my check engine light came on")
    assert len(notes) == 1 and "Proposed:" in notes[0] and types() == ["log_issue"]
    shutil.rmtree(d)


@check("L2 a re-worded duplicate is caught ('tire light on'); one shared word is NOT a duplicate ('noise' vs 'weird noise')")
def _():
    path, d = fresh()
    seed_issues(path, ["tire pressure light is on", "weird noise"])
    answers["issue"] = dict(ISSUE_JSON, description="tire light on")
    notes = X.extract_and_propose("my tire light is on")
    assert len(notes) == 1 and "already on your open list" in notes[0] and queue_actions() == []
    answers["issue"] = dict(ISSUE_JSON, description="noise")
    notes = X.extract_and_propose("there's a noise when I turn")
    assert len(notes) == 1 and "Proposed:" in notes[0] and types() == ["log_issue"]
    shutil.rmtree(d)


@check("L2 'my light is fixed' with two light problems: a model that GUESSES one is overruled — Joey is asked")
def _():
    path, d = fresh()
    seed_issues(path, ["tire pressure light is on", "check engine light is on"])
    answers["issue_update"] = upd(issue_numbers=[2])
    notes = X.extract_and_propose("my light is fixed")
    assert len(notes) == 1 and "more than one open problem" in notes[0]
    assert "tire pressure light is on" in notes[0] and "check engine light is on" in notes[0]
    assert "Nothing was proposed" in notes[0] and queue_actions() == []
    shutil.rmtree(d)


@check("L2 a pick that contradicts Joey's words (said 'tire pressure', model chose 'check engine') is overruled and asked")
def _():
    path, d = fresh()
    seed_issues(path, ["tire pressure light is on", "check engine light is on"])
    answers["issue_update"] = upd(issue_numbers=[2])
    notes = X.extract_and_propose("my tire pressure light is fixed")
    assert len(notes) == 1 and "more than one open problem" in notes[0] and queue_actions() == []
    shutil.rmtree(d)


@check("L2 a CLEARLY matching pick goes through (right answer with a clear best match)")
def _():
    for msg, pick, want in (("my check engine light is fixed now", 2, "i2"), ("my tire pressure light is fixed", 1, "i1")):
        path, d = fresh()
        seed_issues(path, ["tire pressure light is on", "check engine light is on"])
        answers["issue_update"] = upd(issue_numbers=[pick])
        X.extract_and_propose(msg)
        q = queue_actions()
        assert [a["type"] for a in q] == ["update_issue"] and q[0]["details"]["issue_id"] == want, (msg, q)
        shutil.rmtree(d)


@check("L2 when Joey's words match NO issue ('that one is fixed'), the model's pick is trusted")
def _():
    path, d = fresh()
    seed_issues(path, ["alpha problem", "beta problem"])
    answers["issue_update"] = upd(issue_numbers=[2])
    X.extract_and_propose("that one is fixed now")
    q = queue_actions()
    assert [a["type"] for a in q] == ["update_issue"] and q[0]["details"]["issue_id"] == "i2"
    shutil.rmtree(d)


@check("L2 a service only 'fixes' an issue when the words overlap (the real model claimed brakes fixed a tire light)")
def _():
    msg = "got the brakes replaced"
    for fixes, want in (([2], ["log_maintenance"]), ([1], ["log_maintenance", "update_issue"])):
        path, d = fresh()
        seed_issues(path, ["squeaky brakes", "tire pressure light"])
        answers["maintenance"] = dict(MAINT_JSON, service_type="brake replacement", fixes_issue_numbers=fixes)
        X.extract_and_propose(msg)
        assert types() == want, (fixes, types())
        shutil.rmtree(d)
    path, d = fresh()            # the overlap may come from the service's own name
    seed_issues(path, ["squeaky brakes"])
    answers["maintenance"] = dict(MAINT_JSON, service_type="brake replacement", fixes_issue_numbers=[1])
    X.extract_and_propose("had the work done at the dealership")
    assert types() == ["log_maintenance", "update_issue"]
    path, d2 = fresh()
    seed_issues(path, ["squeaky brakes"])
    answers["maintenance"] = dict(MAINT_JSON, service_type="oil change", fixes_issue_numbers=[1])
    X.extract_and_propose("had the work done at the dealership")
    assert types() == ["log_maintenance"]
    shutil.rmtree(d); shutil.rmtree(d2)


@check("L2 a model-echoed snake_case service becomes readable ('brake replacement'); real keys and ordinary text are untouched")
def _():
    n = Lg.normalize_maintenance({"service_type": "turbo_swap"})
    assert n["service_type"] == "turbo swap" and n["display_name"] == "turbo swap"
    assert Lg.normalize_maintenance({"service_type": "brake_inspection"})["service_type"] == "brake_inspection"
    assert Lg.normalize_maintenance({"service_type": "Replaced left headlight"})["service_type"] == "Replaced left headlight"
    assert Lg.normalize_maintenance({"service_type": "a_b c"})["service_type"] == "a_b c"


@check("L4 20 simultaneous reports (10 repeats of an open issue, 10 new ones): exactly 10 proposals, 10 'already listed' notes, no cross-talk")
def _():
    path, d = fresh()
    seed_issues(path, ["tire pressure light is on"])

    def issue_answer(prompt, user_text):
        if "tire pressure" in user_text:
            return json.dumps(ISSUE_JSON)
        return json.dumps(dict(ISSUE_JSON, description=f"squealing noise {first_number(user_text)}"))

    answers["issue"] = issue_answer
    outs, errors = {}, []

    def go(n):
        try:
            msg = f"my tire pressure light is on {n}" if n % 2 == 0 else f"my brakes are squealing {n}"
            outs[n] = X.extract_and_propose(msg)
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go, args=(n,)) for n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert not errors, errors
    for n in range(20):
        assert len(outs[n]) == 1, (n, outs[n])
        assert ("already on your open list" in outs[n][0]) == (n % 2 == 0), (n, outs[n])
    assert types().count("log_issue") == 10 and len(queue_actions()) == 10
    shutil.rmtree(d)


@check("L5 junk issue descriptions from the model (number, null, list, dict, bool, empty) never crash: exactly one note each")
def _():
    for desc in (123, None, ["a"], {"a": 1}, True, "", "   "):
        path, d = fresh()
        answers["issue"] = {"kind": "issue", "description": desc}
        notes = X.extract_and_propose("my tire pressure light is on")
        assert len(notes) == 1 and isinstance(notes[0], str), (desc, notes)
        shutil.rmtree(d)


@check("L5 120 equally-matching open issues: the 'which one?' note stays short (5 names + 'more')")
def _():
    path, d = fresh()
    seed_issues(path, [f"light problem {k}" for k in range(1, 121)])
    answers["issue_update"] = upd(issue_numbers=[3])
    notes = X.extract_and_propose("my light is fixed")
    assert len(notes) == 1 and "more than one open problem" in notes[0] and "more)" in notes[0]
    assert len(notes[0]) < 1000 and queue_actions() == []
    shutil.rmtree(d)


@check("L2 a generic word in the shop field ('dealership', 'the garage', 'my mechanic') is NOT saved as a shop name, but still means a shop did the work")
def _():
    for said in ("dealership", "The Dealership", "a garage", "my mechanic", "shop"):
        n = Lg.normalize_maintenance({"service_type": "oil_change", "shop": said})
        assert n["shop"] is None and n["performed_by"] == "shop", (said, n)
    n = Lg.normalize_maintenance({"service_type": "oil_change", "shop": "Honda of South Bend"})
    assert n["shop"] == "Honda of South Bend" and n["performed_by"] is None
    n = Lg.normalize_maintenance({"service_type": "oil_change", "shop": "dealership", "performed_by": "diy"})
    assert n["shop"] is None and n["performed_by"] == "diy"


@check("L2 end to end: the real model's 'shop: dealership' answer is cleaned before it is queued")
def _():
    path, d = fresh()
    answers["maintenance"] = dict(MAINT_JSON, shop="dealership", cost=65, mileage=56000)
    X.extract_and_propose("got an oil change at 56,000 miles for $65 at the dealership")
    det = queue_actions()[0]["details"]
    assert det["shop"] is None and det["performed_by"] == "shop" and det["cost"] == 65 and det["mileage"] == 56000
    shutil.rmtree(d)


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)