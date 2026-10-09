"""
SHARED NORMALIZERS — L1, L2, L4, L5 tests for shared/normalizers.py, plus proof that
ATLAS and DRIVE really use the ONE shared copy (and that ATLAS gained the two fixes).
No model, no files, no keys.

Run from the repo root:  python -m shared.test_normalizers
"""
import ast
import os
import re
import threading
from datetime import datetime

from shared import normalizers as N

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
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


def raises(fn, exc=Exception):
    try:
        fn()
    except exc:
        return True
    return False


def read(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


TODAY = datetime.now().strftime("%Y-%m-%d")


# ───────────────────────── L1 — STATIC ─────────────────────────

@check("L1 parses; shared code imports nothing from agents/; no bare except, no open(), no secrets")
def _():
    src = read("shared", "normalizers.py")
    ast.parse(src)
    assert "from agents" not in src and "import agents" not in src
    assert not re.search(r"except\s*:", src) and not re.search(r"\bopen\(", src)
    assert "NEXUS SYSTEM" not in src and "API_KEY" not in src


@check("L1 ATLAS and DRIVE no longer carry private copies: the logging files use the shared functions")
def _():
    from agents.atlas import atlas_logging as AL
    from agents.drive import drive_logging as DL
    for mod, src_name in ((AL, ("agents", "atlas", "atlas_logging.py")), (DL, ("agents", "drive", "drive_logging.py"))):
        src = read(*src_name)
        for fn in ("_num", "_text", "_str_list", "_date", "_require_dict"):
            assert f"def {fn}(" not in src, (src_name[-1], fn)
        assert mod._num is N.num and mod._text is N.text and mod._str_list is N.str_list
        assert mod._date is N.date_or_today and mod._require_dict is N.require_dict
        assert mod.MAX_TEXT == N.MAX_TEXT and mod.MAX_LIST == N.MAX_LIST


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 num: not stated is 0; commas and dollar signs are understood; whole numbers stay ints")
def _():
    for v in (None, "", True, False, "far", [], {}, "abc", "  "):
        assert N.num(v, 0, 100, "x") == 0, v
    assert N.num("1,500", 0, 10**6, "x") == 1500 and N.num("$30", 0, 100, "x") == 30
    assert N.num(" 12 ", 0, 100, "x") == 12 and N.num(5.0, 0, 100, "x") == 5 and isinstance(N.num(5.0, 0, 100, "x"), int)
    assert N.num(2.5, 0, 100, "x") == 2.5 and N.num("$1,234.50", 0, 10**6, "x") == 1234.5


@check("L2 num: a stated number outside the range raises ValueError naming what it was (never clamped)")
def _():
    for v in (-1, 101, "101", "nan", "inf", "-inf", float("nan"), float("inf")):
        try:
            N.num(v, 0, 100, "weight")
        except ValueError as e:
            assert "weight out of range" in str(e), e
        else:
            raise AssertionError(f"{v!r} did not raise")


@check("L2 text: None and dicts are '', lists are joined, numbers are text, always trimmed and capped")
def _():
    assert N.text(None) == "" and N.text({"a": 1}) == "" and N.text({}) == ""
    assert N.text(["a", None, "", "b"]) == "a, b" and N.text(5) == "5" and N.text("  hi  ") == "hi"
    assert len(N.text("x" * 5000)) == N.MAX_TEXT


@check("L2 str_list: lists or comma strings; dict items use description/name; items cut at 200; list capped at 30")
def _():
    assert N.str_list(None) == [] and N.str_list("") == [] and N.str_list(5) == [] and N.str_list({"a": 1}) == []
    assert N.str_list("a, b ,,c") == ["a", "b", "c"]
    assert N.str_list([{"description": "d"}, {"name": "n"}, {"x": 1}, "s", None]) == ["d", "n", "s", "None"]
    assert len(N.str_list(["y" * 500])[0]) == 200
    assert len(N.str_list([str(i) for i in range(100)])) == N.MAX_LIST


@check("L2 date_or_today: a real past date is kept (time part ignored); future, junk and impossible dates become today")
def _():
    assert N.date_or_today("2020-01-02") == "2020-01-02" and N.date_or_today("2020-01-02T10:00:00") == "2020-01-02"
    assert N.date_or_today(TODAY) == TODAY
    for v in ("2999-01-01", None, "", "x", 5, [], {}, "2020-13-45", "2020-02-30", "yesterday"):
        assert N.date_or_today(v) == TODAY, v


@check("L2 require_dict: a dict passes; anything else raises ValueError naming the kind and the type")
def _():
    N.require_dict({}, "swim")
    for bad, tname in (([], "list"), (None, "NoneType"), ("x", "str"), (5, "int")):
        try:
            N.require_dict(bad, "swim")
        except ValueError as e:
            assert "swim" in str(e) and tname in str(e), e
        else:
            raise AssertionError(bad)


@check("L2 the two ATLAS gaps are FIXED by the shared copy: '1,500' is a distance, a dict is not saved as its Python repr")
def _():
    from agents.atlas import atlas_logging as AL
    swim = AL.normalize_swim({"total_distance_yards": "1,500", "duration_minutes": 30})
    assert swim["total_distance_yards"] == 1500
    swim2 = AL.normalize_swim({"total_distance_yards": 1500, "form_notes": {"a": 1}})
    assert swim2["form_notes"] == ""


@check("L2 DRIVE behaves exactly as before (its copy was the one adopted)")
def _():
    from agents.drive import drive_logging as DL
    assert DL.normalize_mileage({"mileage": "52,000"}) == {"mileage": 52000}
    assert DL.normalize_fillup({"gallons": 10, "total_cost": "$30"})["total_cost"] == 30


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 threads x 500 calls of every helper at once: every result exactly right")
def _():
    bad, lock = [], threading.Lock()

    def worker():
        for i in range(500):
            ok = (N.num("1,500", 0, 10**6, "x") == 1500 and N.text(["a", "b"]) == "a, b"
                  and N.str_list("a,b") == ["a", "b"] and N.date_or_today("2999-01-01") == TODAY
                  and N.num(i, 0, 10**6, "x") == i)
            if not ok:
                with lock:
                    bad.append(i)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert bad == [], bad[:3]


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 huge and hostile inputs: 5 MB text, 100,000-item list, deeply nested list, unicode/emoji — no crash, caps hold")
def _():
    assert len(N.text("x" * 5_000_000)) == N.MAX_TEXT
    assert len(N.str_list(["a"] * 100_000)) == N.MAX_LIST
    nested = []
    for _i in range(500):
        nested = [nested]
    assert isinstance(N.text(nested), str)
    assert N.text("Schwimmen 泳ぐ 🏊 résumé") == "Schwimmen 泳ぐ 🏊 résumé"
    assert N.str_list("🏊, 泳ぐ") == ["🏊", "泳ぐ"]


@check("L5 junk types everywhere never crash the always-safe helpers (text, str_list, date_or_today)")
def _():
    junk = [None, True, 0, -1, 3.14, float("nan"), float("inf"), "", " ", b"bytes", object(), [], {}, (), set(), "\x00\x01"]
    for v in junk:
        assert isinstance(N.text(v), str)
        assert isinstance(N.str_list(v), list)
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", N.date_or_today(v)), v


@check("L5 num on junk types: either 'not stated' or a loud ValueError, never another exception type")
def _():
    for v in [None, True, 0, -1, 3.14, float("nan"), float("inf"), "", " ", b"bytes", object(), [], {}, (), set(), "\x00\x01", "1e999"]:
        try:
            r = N.num(v, 0, 100, "x")
            assert r == 0 or isinstance(r, (int, float))
        except ValueError:
            pass


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)