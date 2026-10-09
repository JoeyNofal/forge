"""
SHARED model_json — L1, L2, L4, L5 tests for shared/model_json.py, plus proof that ATLAS,
DRIVE and DRIVE's memory extractor all use the ONE shared error class and parser.
No model, no files, no keys.

Run from the repo root:  python -m shared.test_model_json
"""
import ast
import os
import re
import threading

from shared import model_json as M

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


def read(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def fails_with(text, fragment):
    try:
        M.parse_model_json(text)
    except M.ExtractionError as e:
        assert fragment in str(e), (text if not isinstance(text, str) else text[:60], str(e))
        return True
    raise AssertionError(f"did not raise ExtractionError for {text!r:.60}")


# ───────────────────────── L1 — STATIC ─────────────────────────

@check("L1 parses; shared code imports nothing from agents/; no bare except, no open(), no secrets")
def _():
    src = read("shared", "model_json.py")
    ast.parse(src)
    assert "from agents" not in src and "import agents" not in src
    assert not re.search(r"except\s*:", src) and not re.search(r"\bopen\(", src)
    assert "NEXUS SYSTEM" not in src and "API_KEY" not in src


@check("L1 ATLAS, DRIVE and DRIVE's memory extractor share ONE error class and ONE parser; the private copies are gone")
def _():
    from agents.atlas import atlas_extract as AX
    from agents.drive import drive_extract as DX
    from agents.drive import drive_remember as DR
    assert AX.ExtractionError is M.ExtractionError and DX.ExtractionError is M.ExtractionError
    assert DR.ExtractionError is M.ExtractionError
    assert AX.parse_model_json is M.parse_model_json and DX.parse_model_json is M.parse_model_json
    assert DR.parse_model_json is M.parse_model_json
    for path in (("agents", "atlas", "atlas_extract.py"), ("agents", "drive", "drive_extract.py"),
                 ("agents", "drive", "drive_remember.py")):
        src = read(*path)
        assert "class ExtractionError" not in src and "def _parse_model_json" not in src, path
        assert "_parse_model_json" not in src and "the local model call failed" not in src, path


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 valid answers: plain, fenced (```json / ``` / any case), padded with whitespace, nested, unicode")
def _():
    assert M.parse_model_json('{"kind": "none"}') == {"kind": "none"}
    assert M.parse_model_json('  \n {"a": 1}  \n') == {"a": 1}
    assert M.parse_model_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert M.parse_model_json('```\n{"a": 1}\n```') == {"a": 1}
    assert M.parse_model_json('```JSON {"a": 1} ```') == {"a": 1}
    assert M.parse_model_json('{"a": {"b": [1, 2, {"c": null}]}}') == {"a": {"b": [1, 2, {"c": None}]}}
    assert M.parse_model_json('{"note": "Schwimmen 泳ぐ 🏊"}') == {"note": "Schwimmen 泳ぐ 🏊"}


@check("L2 unusable answers become ExtractionError with the right plain reason")
def _():
    for bad in (None, 5, [], {}, b'{"a": 1}', "", "   ", "\n\t"):
        fails_with(bad, "returned nothing")
    for bad in ("not json", "{'a': 1}", '{"a": 1} extra', '{"a": 1', '```json\n{"a": 1}', "{", "}"):
        fails_with(bad, "wasn't valid JSON")
    for bad, kind in (("[]", "list"), ("[1, 2]", "list"), ("5", "int"), ('"text"', "str"), ("null", "NoneType"), ("true", "bool")):
        fails_with(bad, f"expected a JSON object, got {kind}")


@check("L2 model_call_failed: one wording for every extractor, naming the real error type and message")
def _():
    e = M.model_call_failed(ConnectionError("boom"))
    assert isinstance(e, M.ExtractionError) and str(e) == "the local model call failed (ConnectionError: boom)"
    assert str(M.model_call_failed(TimeoutError())) == "the local model call failed (TimeoutError: )"


@check("L2 REAL GAP FIXED: a 100,000-level-deep answer is a typed ExtractionError, not a raw RecursionError")
def _():
    deep = '{"a":' * 100000 + "1" + "}" * 100000
    fails_with(deep, "nested too deeply")
    fails_with("```json\n" + deep + "\n```", "nested too deeply")


@check("L2 ExtractionError is a normal Exception that callers can catch alone or with ValueError/RuntimeError/OSError")
def _():
    assert issubclass(M.ExtractionError, Exception) and not issubclass(M.ExtractionError, (ValueError, RuntimeError, OSError))
    try:
        M.parse_model_json("nope")
    except (M.ExtractionError, ValueError, RuntimeError, OSError):
        return
    raise AssertionError("not caught by the callers' except clause")


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 threads x 500 parses (good and bad) at once: every result exactly right, no cross-talk")
def _():
    bad, lock = [], threading.Lock()

    def worker(i):
        for n in range(500):
            good = M.parse_model_json(f'```json\n{{"i": {i}, "n": {n}}}\n```')
            try:
                M.parse_model_json("[]")
                failed_right = False
            except M.ExtractionError as e:
                failed_right = "got list" in str(e)
            if good != {"i": i, "n": n} or not failed_right:
                with lock:
                    bad.append((i, n))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert bad == [], bad[:3]


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 huge answers: a 5 MB valid object parses; 5 MB of garbage is a clean ExtractionError")
def _():
    big = M.parse_model_json('{"a": "' + "x" * 5_000_000 + '"}')
    assert len(big["a"]) == 5_000_000
    fails_with("z" * 5_000_000, "wasn't valid JSON")


@check("L5 junk types never raise anything but ExtractionError: bytes, numbers, lists, dicts, objects, None, bools")
def _():
    for junk in (None, True, False, 0, -1, 3.14, float("nan"), b"bytes", bytearray(b"x"), object(), [], {}, (), set()):
        try:
            M.parse_model_json(junk)
        except M.ExtractionError:
            continue
        raise AssertionError(f"{junk!r} did not raise ExtractionError")


@check("L5 odd-but-real model output: a BOM and trailing prose are loud ExtractionErrors; NaN inside an object still parses")
def _():
    fails_with("\ufeff" + '{"a": 1}', "wasn't valid JSON")
    fails_with('{"a": 1}\nHope this helps!', "wasn't valid JSON")
    got = M.parse_model_json('{"a": NaN}')
    assert isinstance(got, dict) and got["a"] != got["a"]      # NaN: downstream normalizers reject it loudly


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)