"""
DRIVE increment (b), Part 3b-3 — L1, L2, L4, L5 tests for issue_match.py (pure text
matching: no files, no model, no network).
Run from the repo root:  python -m agents.drive.test_issue_match
"""
import re
import threading
import time

from agents.drive import issue_match as M

_results = []


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


OPEN = [("i1", "squeaky brakes when stopping"), ("i2", "tire pressure light is on")]


@check("L1 issue_match is pure: no file, model, network or subprocess access")
def _():
    with open(M.__file__, encoding="utf-8") as f:
        src = f.read()
    assert not re.search(r"\bopen\(", src)
    for banned in ("import os", "import json", "ollama", "requests", "subprocess", "socket"):
        assert banned not in src, banned


@check("L2 content_words: case, plurals, punctuation, filler words, short words")
def _():
    assert M.content_words("my tire pressure light is on") == {"tire", "pressure", "light"}
    assert M.content_words("The BRAKES are fixed now!") == {"brake"}
    assert M.content_words("Squeaky brakes, when stopping...") == {"squeaky", "brake", "stopping"}
    assert M.content_words("check engine light came on") == {"check", "engine", "light", "came"}
    assert M.content_words("it's at a 100%") == {"100"}
    assert M.content_words("what does this mean") == {"mean"}
    assert M.content_words("lights glass bus") == {"light", "glass", "bus"}


@check("L2 overlap counts shared content words")
def _():
    assert M.overlap("my light is fixed", "tire pressure light is on") == 1
    assert M.overlap("got the brakes replaced", "squeaky brakes when stopping") == 1
    assert M.overlap("oil change", "tire pressure light") == 0


@check("L2 is_duplicate: same words, or 2+ words inside the other; a single shared word is NOT a duplicate")
def _():
    assert M.is_duplicate("Tire pressure light is on", "tire pressure light is on")
    assert M.is_duplicate("tire light on", "tire pressure light is on")
    assert M.is_duplicate("noise", "noise")
    assert not M.is_duplicate("noise", "weird noise")
    assert not M.is_duplicate("check engine light is on", "tire pressure light is on")
    for bad in ("", None, 123, [], {}):
        assert not M.is_duplicate(bad, "tire pressure light is on")
        assert not M.is_duplicate("tire pressure light is on", bad)


@check("L2 find_duplicate returns the saved description, or None")
def _():
    assert M.find_duplicate("my tire pressure light is on", OPEN) == "tire pressure light is on"
    assert M.find_duplicate("check engine light", OPEN) is None
    assert M.find_duplicate("x", []) is None and M.find_duplicate("tire light on", None) is None


@check("L2 issue_scores: ties and clear winners")
def _():
    two = [("a", "tire pressure light is on"), ("b", "check engine light is on")]
    assert M.issue_scores("my light is fixed", two) == [1, 1]
    assert M.issue_scores("my tire pressure light is fixed", two) == [3, 1]
    assert M.issue_scores("the second one is fixed now", two) == [0, 0]


@check("L4 the same inputs always give the same answers, in a loop and across 20 threads at once")
def _():
    def answer():
        return (M.content_words("my tire pressure light is on"), M.issue_scores("my light is fixed", OPEN),
                M.find_duplicate("tire light on", OPEN))
    want = answer()
    assert all(answer() == want for _n in range(2000))
    got, lock = [], threading.Lock()

    def go():
        r = answer()
        with lock:
            got.append(r)

    threads = [threading.Thread(target=go) for _n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert len(got) == 20 and all(r == want for r in got)


@check("L5 hostile inputs (None, numbers, lists, junk tuples, unicode, regex characters) never crash")
def _():
    for bad in (None, 123, [], {}, b"x", 1.5):
        assert M.content_words(bad) == set() and M.overlap(bad, bad) == 0
        assert M.issue_scores(bad, OPEN) == [0, 0] and M.issue_scores("light", bad) == []
        assert M.find_duplicate(bad, OPEN) is None
    assert M.issue_scores("light", [None, 5, ("a",), ("i", "light")]) == [0, 0, 0, 1]
    assert M.find_duplicate("light light", [None, 5, ("a",), ("i", "light light")]) == "light light"
    assert M.content_words("Bremsen 🔧 泳ぐ [(.*)] \\") == {"bremsen"}


@check("L5 a 1 MB message and 10,000 open issues stay fast")
def _():
    start = time.time()
    assert M.content_words("word " * 200000) == {"word"}
    many = [(f"i{n}", f"light problem number {n}") for n in range(10000)]
    scores = M.issue_scores("my light is fixed", many)
    assert len(scores) == 10000 and all(s == 1 for s in scores)
    assert time.time() - start < 10, time.time() - start


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)