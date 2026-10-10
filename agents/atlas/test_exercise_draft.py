"""
ATLAS exercise library, increment 2b-i - L1, L2, L4, L5 tests for
agents/atlas/exercise_draft.py. The model call is replaced by a fake that records
what it is asked, so there are no keys, no cost and no network. The real-model
pass is the separate test_exercise_draft_l3.py.

Run from the repo root:  python -m agents.atlas.test_exercise_draft
"""
import ast
import json
import os
import random
import re
import threading
import time
from typing import Any

from agents.atlas import exercise_draft as D
from agents.atlas import exercise_library as L

_HERE = os.path.dirname(os.path.abspath(__file__))
_results = []
CALLS: list = []
RESPONSE: dict[str, Any] = {"value": ""}


def fake(agent, tier, system, messages, location=""):
    CALLS.append({"agent": agent, "tier": tier, "system": system, "messages": messages})
    r = RESPONSE["value"]
    if callable(r):
        r = r(messages)
    if isinstance(r, BaseException):
        raise r
    if not isinstance(r, str):
        raise TypeError("the fake model response must be text")
    for i in range(0, len(r), 37):                   # chunked, like a real stream
        yield r[i:i + 37]


D.stream_by_tier = fake


def say(v):
    RESPONSE["value"] = json.dumps(v) if isinstance(v, (dict, list)) else v


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


def raises(fn, exc=Exception):
    try:
        fn()
    except exc:
        return True
    return False


GOOD = {
    "name": "Windmill arms",
    "aliases": ["arm windmills"],
    "steps": ["Stand tall with your feet shoulder-width apart.", "Raise one arm straight up.",
              "Circle it slowly backward in a full arc.", "Switch arms after the set."],
    "primary_muscles": ["shoulders"],
    "secondary_muscles": ["upper back"],
    "common_mistakes": ["Swinging too fast", "Arching the lower back"],
    "equipment": [],
}

with open(os.path.join(_HERE, "exercise_draft.py"), encoding="utf-8") as f:
    SRC = f.read()


# ---------------- L1 static ----------------
@check("L1 static: imports only the library, the model router and the JSON helper; writes nothing")
def _():
    tree = ast.parse(SRC)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported <= {"re", "agents.atlas", "shared.model_client", "shared.model_json"}, imported
    for banned in ("open(", "update_json", "add_entry(", "mark_reviewed(", "json.dump"):
        assert banned not in SRC, banned


@check("L1 static: always the free cloud tier, never paid; no secrets or old paths")
def _():
    assert D.DRAFT_TIER == "free_cloud" and "paid_cloud" not in SRC and "claude" not in SRC.lower()
    assert "stream_by_tier(" in SRC and "DRAFT_TIER" in SRC
    assert not re.search(r"(api[_-]?key|sk-[A-Za-z0-9]|AIza|NEXUS SYSTEM)", SRC, re.I)


# ---------------- L2 smoke ----------------
@check("L2 a good answer becomes a clean AI-drafted entry; ONLY the name is sent, on the free tier")
def _():
    CALLS.clear()
    say(GOOD)
    e = D.draft_exercise("Windmill arms")
    assert e["name"] == "Windmill arms" and e["status"] == "ai_drafted" and len(e["steps"]) == 4
    assert e["primary_muscles"] == ["shoulders"] and "arm windmills" in e["aliases"]
    assert len(CALLS) == 1 and CALLS[0]["agent"] == "atlas" and CALLS[0]["tier"] == "free_cloud"
    assert CALLS[0]["messages"] == [{"role": "user", "content": "Exercise: Windmill arms"}]
    assert "JSON" in CALLS[0]["system"]


@check("L2 the entry always carries the name Joey typed; a renamed answer keeps the model's spelling as another name")
def _():
    say(dict(GOOD, name="Incline Dumbbell Bench Press", aliases="incline chest press, incline press"))
    e = D.draft_exercise("incline DB press")
    assert e["name"] == "incline DB press"
    assert "Incline Dumbbell Bench Press" in e["aliases"] and "incline chest press" in e["aliases"]
    assert L.normalize_name(e["name"]) == "incline dumbbell press"
    assert e["status"] == "ai_drafted"


@check("L2 a model claiming 'reviewed' (or sending extra keys) changes nothing")
def _():
    say(dict(GOOD, status="reviewed", id="evil", reviewed_at="now"))
    e = D.draft_exercise("Windmill arms")
    assert e["status"] == "ai_drafted" and "id" not in e and "reviewed_at" not in e


@check("L2 tolerated wrappers: code fences, and a sentence of chatter around ONE object")
def _():
    say("```json\n" + json.dumps(GOOD) + "\n```")
    assert D.draft_exercise("Windmill arms")["name"] == "Windmill arms"
    say("Sure! Here you go:\n" + json.dumps(GOOD) + "\nHope that helps.")
    assert D.draft_exercise("Windmill arms")["name"] == "Windmill arms"


@check("L2 'not an exercise', too-short drafts and unusable drafts are refused with a plain reason")
def _():
    say({"error": "not a recognised exercise"})
    try:
        D.draft_exercise("Banana flurb")
        assert False
    except D.DraftError as e:
        assert "does not recognise 'Banana flurb'" in str(e)
    say(dict(GOOD, steps=["Only one.", "Only two."]))
    assert raises(lambda: D.draft_exercise("Windmill arms"), D.DraftError)
    say(dict(GOOD, primary_muscles=[]))
    assert raises(lambda: D.draft_exercise("Windmill arms"), D.DraftError)
    say(dict(GOOD, steps=[]))
    assert raises(lambda: D.draft_exercise("Windmill arms"), D.DraftError)


@check("L2 bad requests never reach the model: empty, symbols, non-text, too long")
def _():
    say(GOOD)
    CALLS.clear()
    for bad in ("", "   ", "!!!", None, 5, ["x"], "one two three four five six seven eight nine ten eleven"):
        assert raises(lambda b=bad: D.draft_exercise(b), D.DraftError), bad
    assert CALLS == []
    assert D.clean_request_name("  incline   db  press ") == "incline db press"
    assert len(D.clean_request_name("x" * 500)) == L.MAX_NAME


@check("L2 a failing model call, and answers that are not usable JSON, become DraftError (never a raw crash)")
def _():
    say(ValueError("GEMINI_API_KEY is not set"))
    try:
        D.draft_exercise("Windmill arms")
        assert False
    except D.DraftError as e:
        assert "ValueError" in str(e) and "GEMINI_API_KEY" in str(e)
    for junk in ("", "   ", "I cannot help with that.", "[1, 2, 3]", "{not json", '"a string"', "null", "42"):
        say(junk)
        assert raises(lambda: D.draft_exercise("Windmill arms"), D.DraftError), junk


# ---------------- L4 sustained / concurrency ----------------
@check("L4 100 drafts in a row are identical")
def _():
    say(GOOD)
    first = D.draft_exercise("Windmill arms")
    for _i in range(100):
        assert D.draft_exercise("Windmill arms") == first


@check("L4 20 threads drafting different exercises at once: each gets its own name, no cross-talk")
def _():
    def echo(messages):
        name = messages[-1]["content"][len("Exercise: "):]
        return json.dumps(dict(GOOD, name=name + " (model spelling)", aliases=[]))

    RESPONSE["value"] = echo
    errors = []

    def work(n):
        try:
            requested = f"Lift {chr(65 + n)}"
            for _i in range(25):
                e = D.draft_exercise(requested)
                assert e["name"] == requested and f"{requested} (model spelling)" in e["aliases"]
        except Exception as ex:
            errors.append(repr(ex))

    threads = [threading.Thread(target=work, args=(n,)) for n in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors[:2]


# ---------------- L5 extreme / breaking ----------------
@check("L5 400 random hostile model answers: a clean entry or a DraftError, never any other crash")
def _():
    rng = random.Random(4)
    values = [None, 5, True, "", " ", "x", "a" * 500, "1. a\n2. b\n3. c", [], ["a", None, {"text": "b"}],
              {"a": 1}, [[1]], 1e308, "\x00\x01", "Bench press", "chest, back", ["Do this.", "Do that.", "Then this."]]
    keys = ["name", "aliases", "steps", "primary_muscles", "secondary_muscles", "common_mistakes", "equipment", "status", "error"]
    for _i in range(400):
        obj = {k: rng.choice(values) for k in keys if rng.random() < 0.8}
        text = json.dumps(obj)
        if rng.random() < 0.3:
            text = text[:rng.randrange(len(text) + 1)]
        say(rng.choice([text, "```json\n" + text + "\n```", "Here: " + text + " done"]))
        try:
            e = D.draft_exercise("Windmill arms")
        except D.DraftError:
            continue
        json.dumps(e)
        assert e["status"] == "ai_drafted" and e["name"] == "Windmill arms" and len(e["steps"]) >= D.MIN_STEPS


@check("L5 a 1 MB answer and absurdly nested JSON are refused quickly and cleanly")
def _():
    t0 = time.time()
    for junk in ("x" * 1_000_000, "[" * 100000 + "]" * 100000, '{"a":' * 100000 + "1" + "}" * 100000):
        say(junk)
        assert raises(lambda: D.draft_exercise("Windmill arms"), D.DraftError)
    assert time.time() - t0 < 10.0


@check("L5 unicode and emoji survive")
def _():
    say(dict(GOOD, steps=["\u4e2d\u6587 step one \U0001F525", "Step two.", "Step three."]))
    e = D.draft_exercise("D\u00e9velop\u00e9 \U0001F4AA")
    assert e["name"] == "D\u00e9velop\u00e9 \U0001F4AA" and "\U0001F525" in e["steps"][0]


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)