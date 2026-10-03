"""
DRIVE increment (b), Part 6a — L1, L2, L4, L5 tests for shared/nhtsa.py (the official NHTSA
recall client). The NETWORK IS FAKED: nothing leaves your machine.
(L3 — the real NHTSA — is test_nhtsa_l3.py.)

Run from the repo root:  python -m shared.test_nhtsa
"""
import io
import json
import re
import threading
import time
import urllib.error
import urllib.parse
from datetime import datetime
from email.message import Message

from shared import nhtsa as N

_results = []
calls = []
_lock = threading.Lock()
_answer = {"v": None}


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
        calls.append((url, timeout))
    r = _answer["v"]
    if callable(r):
        r = r(url)
    if isinstance(r, BaseException):
        raise r
    return r


N._http_get = fake_http


def reset(answer=None):
    calls.clear()
    _answer["v"] = answer


def item(n=1, **kw):
    d = {"NHTSACampaignNumber": f"15V{n:06d}", "Manufacturer": "Honda (American Honda Motor Co.)",
         "ReportReceivedDate": "19/03/2015", "Component": "AIR BAGS", "Summary": "The airbag may rupture.",
         "Consequence": "Metal fragments could injure occupants.", "Remedy": "Dealers will replace the inflator.",
         "Notes": "Owners may contact Honda.", "parkIt": False}
    d.update(kw)
    return d


def body(results, key="results"):
    return json.dumps({"Count": len(results), "Message": "Results returned successfully", key: results})


def raises(fn, exc: type[BaseException] = N.NHTSAError):
    try:
        fn()
    except exc as e:
        return str(e)
    return None


with open(N.__file__, encoding="utf-8") as _f:
    SRC = _f.read()


def _function_source(name):
    m = re.search(rf"^def {name}\(.*?(?=^def |\Z)", SRC, re.S | re.M)
    assert m, name
    return m.group(0)


# ───────────────────────── L1 — STATIC ─────────────────────────

@check("L1 the network is touched in exactly ONE place (_http_get), only the official host, only the standard library")
def _():
    assert SRC.count("urlopen(") == 1 and "urlopen(" in _function_source("_http_get")
    assert N.NHTSA_RECALLS_URL == "https://api.nhtsa.gov/recalls/recallsByVehicle"
    for banned in ("import requests", "serpapi", "api_key", "API_KEY", "token", "password"):
        assert banned not in SRC, banned


@check("L1 no bare 'except:', no raw file access, and shared/ stays independent of the agents")
def _():
    assert not re.search(r"except\s*:", SRC) and not re.search(r"\bopen\(", SRC)
    assert "from agents" not in SRC and "import agents" not in SRC


@check("L1 every failure path raises NHTSAError (nothing returns an empty result for a failure)")
def _():
    body_src = _function_source("lookup_recalls")
    assert body_src.count("raise NHTSAError") >= 8
    assert "return {" in body_src and "except" in body_src
    assert not re.search(r"except[^\n]*:\s*\n\s*return", body_src)


@check("L1 the model-facing texts say 'NOT the VIN' and 'do not guess'")
def _():
    assert "NOT Joey's VIN" in SRC and "Do not guess" in SRC and "nhtsa.gov/recalls" in SRC


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 the request URL: make, model and modelYear parameters, special characters encoded, case kept, 15-second timeout")
def _():
    reset(body([]))
    N.lookup_recalls("Honda", "Civic", 2016)
    url, timeout = calls[0]
    assert url.startswith("https://api.nhtsa.gov/recalls/recallsByVehicle?") and timeout == 15.0
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q == {"make": ["Honda"], "model": ["Civic"], "modelYear": ["2016"]}
    N.lookup_recalls("Ford", "F-150", 2018)
    assert urllib.parse.parse_qs(urllib.parse.urlparse(calls[1][0]).query)["model"] == ["F-150"]
    N.lookup_recalls("Tesla", "Model 3", 2023)
    assert "Model+3" in calls[2][0] and urllib.parse.parse_qs(urllib.parse.urlparse(calls[2][0]).query)["model"] == ["Model 3"]


@check("L2 a normal answer is cleaned into a small, JSON-safe result")
def _():
    reset(body([item(1), item(2, Component="BRAKES")]))
    r = N.lookup_recalls("Honda", "Civic", 2016)
    assert r["source"] == "NHTSA recallsByVehicle" and (r["make"], r["model"], r["model_year"]) == ("Honda", "Civic", 2016)
    assert r["count"] == 2 and r["shown"] == 2 and r["url"].startswith(N.NHTSA_RECALLS_URL)
    assert datetime.fromisoformat(r["fetched_at"]).date() == datetime.now().date()
    assert set(r["recalls"][0]) == {"campaign", "manufacturer", "component", "summary", "consequence",
                                    "remedy", "reported", "park_it"}
    assert r["recalls"][0]["campaign"] == "15V000001" and r["recalls"][1]["component"] == "BRAKES"
    assert json.loads(json.dumps(r)) == r


@check("L2 both 'results' and 'Results' are accepted; no list at all is an error, not 'no recalls'")
def _():
    reset(body([item(1)], key="Results"))
    assert N.lookup_recalls("Honda", "Civic", 2016)["count"] == 1
    for bad in ('{"Count": 0}', '{"results": "x"}', '{"results": null}', '{"results": {"a": 1}}'):
        reset(bad)
        msg = raises(lambda: N.lookup_recalls("Honda", "Civic", 2016))
        assert msg and "no list of results" in msg, (bad, msg)


@check("L2 an EMPTY list is a real, successful 'no recalls' answer")
def _():
    reset(body([]))
    r = N.lookup_recalls("Honda", "Civic", 2016)
    assert r["count"] == 0 and r["recalls"] == [] and "NO recalls" in N.format_for_context(r)


@check("L2 junk entries are skipped (not a dict, no campaign number); only real recalls are counted")
def _():
    reset(body([5, None, "x", {}, {"NHTSACampaignNumber": ""}, {"NHTSACampaignNumber": None}, item(1)]))
    r = N.lookup_recalls("Honda", "Civic", 2016)
    assert r["count"] == 1 and r["recalls"][0]["campaign"] == "15V000001"


@check("L2 text is cleaned: whitespace collapsed, long text cut, nested/None values empty, numbers become text")
def _():
    reset(body([item(1, Summary="  a\n\n b\t c  ", Consequence="z" * 5000, Remedy={"a": 1}, Component=None,
                     Manufacturer=["x"], NHTSACampaignNumber=12345)]))
    rec = N.lookup_recalls("Honda", "Civic", 2016)["recalls"][0]
    assert rec["summary"] == "a b c" and len(rec["consequence"]) == 601 and rec["consequence"].endswith("…")
    assert rec["remedy"] == "" and rec["component"] == "" and rec["manufacturer"] == "" and rec["campaign"] == "12345"


@check("L2 only a real JSON true counts as 'park it' (text 'true', 1, missing do not)")
def _():
    reset(body([item(1, parkIt=True), item(2, parkIt="true"), item(3, parkIt=1), item(4)]))
    flags = [r["park_it"] for r in N.lookup_recalls("Honda", "Civic", 2016)["recalls"]]
    assert flags == [True, False, False, False]


@check("L2 more than 40 recalls: count says the true total, only the first 40 are kept")
def _():
    reset(body([item(n) for n in range(1, 56)]))
    r = N.lookup_recalls("Honda", "Civic", 2016)
    assert r["count"] == 55 and r["shown"] == 40 and len(r["recalls"]) == 40
    assert r["recalls"][0]["campaign"] == "15V000001" and r["recalls"][39]["campaign"] == "15V000040"


@check("L2 bad input is rejected BEFORE any network call: empty make/model, text/bool/float/absurd years")
def _():
    reset(body([]))
    for args in (("", "Civic", 2016), ("Honda", "", 2016), (None, "Civic", 2016), ("Honda", None, 2016),
                 ("Honda", "Civic", "2016"), ("Honda", "Civic", True), ("Honda", "Civic", 2016.0),
                 ("Honda", "Civic", 1900), ("Honda", "Civic", 2999), ("Honda", "Civic", None), ("   ", "Civic", 2016)):
        assert raises(lambda a=args: N.lookup_recalls(*a)), args
    assert calls == []


@check("L2 every network/HTTP failure becomes an NHTSAError with a plain reason")
def _():
    http = lambda code: urllib.error.HTTPError("http://x", code, "err", Message(), None)
    cases = ((http(400), "doesn't recognize"), (http(404), "doesn't recognize"), (http(500), "HTTP 500"),
             (urllib.error.URLError("no route"), "couldn't reach NHTSA"), (TimeoutError("timed out"), "couldn't reach NHTSA"),
             (ConnectionResetError("reset"), "couldn't reach NHTSA"),
             (UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"), "couldn't reach NHTSA"),
             (N.NHTSAError("NHTSA's answer was unexpectedly huge"), "unexpectedly huge"))
    for exc, expect in cases:
        reset(exc)
        msg = raises(lambda: N.lookup_recalls("Honda", "Civic", 2016))
        assert msg and expect in msg, (exc, msg)


@check("L2 junk answers are NHTSAErrors, never 'no recalls': empty, text, HTML, arrays, numbers, null")
def _():
    for bad in ("", "not json", "<html>Service unavailable</html>", "[]", "123", "null", '"x"'):
        reset(bad)
        assert raises(lambda: N.lookup_recalls("Honda", "Civic", 2016)), bad


@check("L2 format_for_context: dated, says 'NOT Joey's VIN', names the VIN-check page, lists recalls, flags 'park it', trims long text, says how many more")
def _():
    reset(body([item(1, parkIt=True), item(2), item(3, Summary="x" * 600)]))
    out = N.format_for_context(N.lookup_recalls("Honda", "Civic", 2016))
    assert datetime.now().strftime("%Y-%m-%d") in out and "NOT Joey's VIN" in out and "nhtsa.gov/recalls" in out
    assert "3 recall(s)" in out and "Campaign 15V000001" in out and "AIR BAGS" in out and "'park it'" in out
    assert "x" * 220 in out and "x" * 221 not in out and out.startswith("[NHTSA RECALL DATA") and out.endswith("]")
    reset(body([item(n) for n in range(1, 16)]))
    out = N.format_for_context(N.lookup_recalls("Honda", "Civic", 2016))
    assert "15 recall(s)" in out and "10. Campaign" in out and "11. Campaign" not in out and "and 5 more" in out


@check("L2 failure_note tells the model the lookup failed and not to guess")
def _():
    note = N.failure_note("couldn't reach NHTSA (URLError: no route)")
    assert note.startswith(N.NHTSA_FAILED_PREFIX) and "Do not guess" in note and "couldn't reach NHTSA" in note
    assert "nhtsa.gov/recalls" in note


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 100 lookups in a row all succeed (and each is its own request)")
def _():
    reset(body([item(1)]))
    for _n in range(100):
        assert N.lookup_recalls("Honda", "Civic", 2016)["count"] == 1
    assert len(calls) == 100


@check("L4 20 simultaneous lookups for different years: no cross-talk, none lost")
def _():
    def answer(url):
        year = int(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["modelYear"][0])
        return body([item(year)])

    reset(answer)
    out, errors = {}, []

    def go(year):
        try:
            r = N.lookup_recalls("Honda", "Civic", year)
            with _lock:
                out[year] = r
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go, args=(2000 + n,)) for n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert not errors, errors
    assert len(out) == 20
    for year, r in out.items():
        assert r["model_year"] == year and r["recalls"][0]["campaign"] == f"15V{year:06d}"


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 hostile answers: 100,000-level nesting, NaN/Infinity, a 5 MB body, unicode/emoji — never a crash, always a clean result or an NHTSAError")
def _():
    reset("[" * 100000)
    assert raises(lambda: N.lookup_recalls("Honda", "Civic", 2016))
    reset('{"results": [{"NHTSACampaignNumber": "15V1", "Summary": NaN, "Consequence": Infinity}]}')
    r = N.lookup_recalls("Honda", "Civic", 2016)
    assert r["count"] == 1 and r["recalls"][0]["summary"] == "nan"
    reset(body([item(1, Summary="Bremsen 泳ぐ 🔧 épaule [(.*)] \\")]))
    assert N.lookup_recalls("Honda", "Civic", 2016)["recalls"][0]["summary"] == "Bremsen 泳ぐ 🔧 épaule [(.*)] \\"
    reset(body([item(1, Summary="y" * 5_000_000)]))
    assert len(N.lookup_recalls("Honda", "Civic", 2016)["recalls"][0]["summary"]) == 601


@check("L5 10,000 recalls: counted correctly, capped at 40, and fast")
def _():
    reset(body([item(n) for n in range(10000)]))
    start = time.time()
    r = N.lookup_recalls("Honda", "Civic", 2016)
    assert r["count"] == 10000 and len(r["recalls"]) == 40 and time.time() - start < 10
    assert len(N.format_for_context(r)) < 20000


@check("L5 every field with the wrong type (numbers, lists, dicts, bools, nulls) never crashes")
def _():
    weird = {k: v for k, v in zip(("Manufacturer", "Component", "Summary", "Consequence", "Remedy", "ReportReceivedDate"),
                                  ([1, 2], {"a": 1}, True, 3.5, None, ["x"]))}
    reset(body([dict(item(1), **weird), {"NHTSACampaignNumber": ["x"]}, {"NHTSACampaignNumber": {"a": 1}}, item(2)]))
    r = N.lookup_recalls("Honda", "Civic", 2016)
    assert r["count"] == 2 and r["recalls"][0]["summary"] == "True" and r["recalls"][0]["consequence"] == "3.5"
    assert r["recalls"][0]["manufacturer"] == "" and r["recalls"][0]["remedy"] == ""


@check("L5 the real _http_get: a BOM-prefixed body decodes cleanly; an oversized or non-UTF-8 body is refused")
def _():
    class FakeResponse:
        def __init__(self, data):
            self._data = data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return self._data if n < 0 else self._data[:n]

    real_urlopen = N.urllib.request.urlopen
    # The module-level _http_get was replaced by fake_http above, so rebuild the real one from source.
    namespace = dict(vars(N))
    exec(compile(_function_source("_http_get"), "nhtsa_http_get", "exec"), namespace)
    real_get = namespace["_http_get"]
    try:
        N.urllib.request.urlopen = lambda req, timeout=None: FakeResponse(b"\xef\xbb\xbf" + b'{"results": []}')
        assert json.loads(real_get("https://x", 5)) == {"results": []}
        N.urllib.request.urlopen = lambda req, timeout=None: FakeResponse(b"x" * (N.MAX_RESPONSE_BYTES + 5))
        assert raises(lambda: real_get("https://x", 5))
        N.urllib.request.urlopen = lambda req, timeout=None: FakeResponse(b"\xff\xfe\xfa")
        assert raises(lambda: real_get("https://x", 5), UnicodeDecodeError) is not None
    finally:
        N.urllib.request.urlopen = real_urlopen


@check("L2 long text is cut at a WORD boundary (a phone number is never cut in half) and the cut is marked")
def _():
    text = "Honda will notify owners. Owners may contact Honda customer service at 1-888-234-2138. Honda's numbers are KGC."
    reset(body([item(1, Remedy=text)]))
    assert N.lookup_recalls("Honda", "Civic", 2016)["recalls"][0]["remedy"] == text
    cut = N.trim_text(text, 80)                      # 80 characters lands INSIDE the phone number
    assert cut.endswith("…") and "1-888" not in cut
    assert N.trim_text("short", 70) == "short" and N.trim_text("abc def ghi", 5) == "abc…"


@check("L2 NHTSA's day/month/year dates are shown as YYYY-MM-DD; anything else is kept as given")
def _():
    reset(body([item(1, ReportReceivedDate="11/07/2016"), item(2, ReportReceivedDate="18/12/2023"),
                item(3, ReportReceivedDate="31/02/2020"), item(4, ReportReceivedDate="2020-05-05"),
                item(5, ReportReceivedDate=None)]))
    got = [r["reported"] for r in N.lookup_recalls("Honda", "Civic", 2016)["recalls"]]
    assert got == ["2016-07-11", "2023-12-18", "31/02/2020", "2020-05-05", ""]


@check("L2 the model is told the texts are shortened and never to quote phone numbers")
def _():
    reset(body([item(1)]))
    assert "never quote phone numbers" in N.format_for_context(N.lookup_recalls("Honda", "Civic", 2016))


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)