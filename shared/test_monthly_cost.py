"""
MONTHLY COST — L1, L2, L4, L5 tests for shared/monthly_cost.py. No model, no files, no keys.
One group of checks RUNS THE TRACKER'S OWN bills.js on the same random lists and demands the
same answer, so the Python copy can never drift from the app. Needs Node.js on the PATH.

Run from the repo root:  python -m shared.test_monthly_cost
"""
import ast
import json
import os
import random
import shutil
import subprocess
import time
from datetime import date, timedelta

from shared import monthly_cost as M

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_BILLS_JS = os.path.join(_ROOT, "apps", "financial-tracker", "bills.js")
_results = []
TODAY = "2026-11-24"


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


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol


def exp(amount, freq, **kw):
    e = {"name": "x", "amount": amount, "frequency": freq}
    e.update(kw)
    return e


with open(os.path.join(_HERE, "monthly_cost.py"), encoding="utf-8") as _f:
    _SRC = _f.read()


# ---------------------------------------------------------------- L1 static
@check("L1 the module imports only re, datetime and typing and does no file, network or clock work")
def _():
    mods = set()
    for n in ast.walk(ast.parse(_SRC)):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        if isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[0])
    assert mods <= {"re", "datetime", "typing", "__future__"}, mods
    for bad in ("open(", "requests", "urllib", "socket", "datetime.now", "date.today", "getenv", "environ"):
        assert bad not in _SRC, bad


@check("L1 the weekly factor is 4.33, as in the tracker")
def _():
    assert M.WEEKS_PER_MONTH == 4.33


# ---------------------------------------------------------------- L2 hand-worked numbers
@check("each frequency: monthly 1000, biweekly 100, weekly 100, quarterly 300, yearly 1200")
def _():
    assert close(M.monthly_amount(exp(1000, "monthly")), 1000)
    assert close(M.monthly_amount(exp(100, "biweekly")), 100 * 26 / 12)
    assert close(M.monthly_amount(exp(100, "weekly")), 433)
    assert close(M.monthly_amount(exp(300, "quarterly")), 100)
    assert close(M.monthly_amount(exp(1200, "yearly")), 100)


@check("an unknown or missing frequency costs 0 (never guessed)")
def _():
    for f in ("daily", "Monthly", "", None, 5, [], "monthly "):
        assert M.monthly_amount(exp(100, f)) == 0.0, f
    assert M.monthly_amount({"amount": 100}) == 0.0


@check("monthly_total adds everything up as of today")
def _():
    items = [exp(1000, "monthly"), exp(100, "weekly"), exp(300, "quarterly"), exp(1200, "yearly"), exp(100, "biweekly")]
    assert close(M.monthly_total(items, TODAY), 1000 + 433 + 100 + 100 + 100 * 26 / 12)


@check("an expense that ended before today is skipped; ending today still counts; ending later counts")
def _():
    assert M.monthly_total([exp(100, "monthly", endDate="2026-11-23")], TODAY) == 0.0
    assert M.monthly_total([exp(100, "monthly", endDate="2026-11-24")], TODAY) == 100.0
    assert M.monthly_total([exp(100, "monthly", endDate="2026-11-25")], TODAY) == 100.0
    assert M.monthly_total([exp(100, "monthly", endDate="")], TODAY) == 100.0
    assert M.monthly_total([exp(100, "monthly", endDate="not a date")], TODAY) == 100.0


@check("an expense that has not started yet still counts")
def _():
    assert M.monthly_total([exp(100, "monthly", startDate="2027-05-01")], TODAY) == 100.0


@check("numbers written as text work: '12.5', ' 5 ', '.5', '7.'")
def _():
    assert close(M.monthly_amount(exp("12.5", "monthly")), 12.5)
    assert close(M.monthly_amount(exp(" 5 ", "monthly")), 5)
    assert close(M.monthly_amount(exp(".5", "monthly")), 0.5)
    assert close(M.monthly_amount(exp("7.", "monthly")), 7)


@check("junk amounts count as 0: text, empty, null, true, nan, infinity, lists, dicts, hex, exponent text")
def _():
    for a in ("abc", "", "  ", None, True, False, float("nan"), float("inf"), float("-inf"), [], [5], {}, "0x10", "1e3", "1,000", "$5", "5 dollars", "--5"):
        assert M.monthly_amount(exp(a, "monthly")) == 0.0, a


@check("negative amounts are allowed (a credit) and reduce the total")
def _():
    assert close(M.monthly_total([exp(1000, "monthly"), exp(-50, "monthly")], TODAY), 950)


@check("not a list, empty list and non-dict entries give 0 or are skipped")
def _():
    for bad in (None, {}, "x", 5, True):
        assert M.monthly_total(bad, TODAY) == 0.0
    assert M.monthly_total([], TODAY) == 0.0
    assert M.monthly_total(["x", None, 5, [], exp(10, "monthly")], TODAY) == 10.0


@check("a date object works as today; a bad today raises a clear ValueError")
def _():
    assert M.monthly_total([exp(100, "monthly", endDate="2026-11-23")], date(2026, 11, 24)) == 0.0
    for bad in ("", "2026-13-01", "tomorrow", None, 5, "2026-1-1"):
        try:
            M.monthly_total([], bad)
        except ValueError as e:
            assert "today" in str(e)
        else:
            raise AssertionError(repr(bad))


@check("the input is never changed")
def _():
    items = [exp(100, "weekly", endDate="2026-01-01"), exp("5", "monthly")]
    import copy
    before = copy.deepcopy(items)
    M.monthly_total(items, TODAY)
    assert items == before


# ---------------------------------------------------------------- L4 the tracker's own JavaScript must agree
def _random_list(rng):
    out = []
    for _i in range(rng.randint(0, 25)):
        r = rng.random()
        if r < 0.04:
            out.append(rng.choice(["junk", None, 5, [], True]))
            continue
        amt = rng.choice([round(rng.uniform(0, 3000), 2), rng.randint(0, 3000), str(round(rng.uniform(0, 500), 2)), " " + str(rng.randint(1, 99)) + " ", ".5", "7.", "abc", "", None, -12.5])
        e = {"name": "e", "amount": amt, "frequency": rng.choice(["monthly", "weekly", "biweekly", "quarterly", "yearly", "monthly", "weekly", "daily", "", None, "Monthly"])}
        if rng.random() < 0.5:
            e["endDate"] = rng.choice([(date(2026, 1, 1) + timedelta(days=rng.randint(0, 700))).isoformat(), "", "garbage", "2026-02-30", None])
        if rng.random() < 0.3:
            e["startDate"] = (date(2026, 1, 1) + timedelta(days=rng.randint(0, 700))).isoformat()
        out.append(e)
    return out


_JS = (
    "const fs=require('fs');const B=require(process.argv[1]);"
    "const cases=JSON.parse(fs.readFileSync(0,'utf8'));"
    "console.log(JSON.stringify(cases.map(c=>({t:c.todays.map(d=>B.monthlyTotal(c.items,d)),a:c.items.map(e=>B.monthlyAmount(e))}))));"
)


@check("L4 the tracker's real bills.js agrees on 600 random lists x 4 dates (every item and every total)")
def _():
    node = shutil.which("node")
    assert node, "Node.js was not found on the PATH: the cross-check with the tracker's own bills.js cannot run (this is a FAIL on purpose, not a skip)"
    assert os.path.exists(_BILLS_JS), _BILLS_JS
    rng = random.Random(20261124)
    cases = []
    for _i in range(600):
        todays = ["2026-01-01", "2026-06-15", TODAY, (date(2026, 1, 1) + timedelta(days=rng.randint(0, 800))).isoformat()]
        cases.append({"items": _random_list(rng), "todays": todays})
    p = subprocess.run([node, "-e", _JS, _BILLS_JS], input=json.dumps(cases), capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert p.returncode == 0, p.stderr[:500]
    js = json.loads(p.stdout)
    assert len(js) == len(cases)
    compared = 0
    for c, j in zip(cases, js):
        for k, t in enumerate(c["todays"]):
            py = M.monthly_total(c["items"], t)
            assert close(py, j["t"][k], 1e-6), (t, py, j["t"][k], c["items"])
            compared += 1
        for e, ja in zip(c["items"], j["a"]):
            assert close(M.monthly_amount(e), ja, 1e-9), (e, M.monthly_amount(e), ja)
            compared += 1
    assert compared > 5000, compared


@check("L4 100,000 expenses add up fast, and more than the cap are ignored like the tracker does")
def _():
    items = [exp(1, "monthly") for _i in range(100000)]
    t0 = time.time()
    assert M.monthly_total(items, TODAY) == 100000.0
    assert time.time() - t0 < 3.0
    assert M.monthly_total(items + [exp(1, "monthly")] * 50, TODAY) == 100000.0


@check("L4 the same list gives the same answer every time")
def _():
    items = _random_list(random.Random(5))
    assert M.monthly_total(items, TODAY) == M.monthly_total(items, TODAY)


# ---------------------------------------------------------------- L5 extreme
@check("L5 absurd values never crash")
def _():
    deep = cur = {}
    for _i in range(500):
        cur["x"] = {}
        cur = cur["x"]
    items = [exp(10**300, "monthly"), exp("9" * 5000, "weekly"), exp(5e-324, "yearly"), exp(deep, "monthly"), exp(1, deep),
             {"amount": 5, "frequency": "monthly", "endDate": deep}, exp(float("nan"), "monthly"), exp("\u0000\U0001F600", "monthly")]
    r = M.monthly_total(items, TODAY)
    assert isinstance(r, float)


@check("L5 fuzz: 3,000 random lists of random junk never crash")
def _():
    rng = random.Random(77)
    vals = [None, [], {}, "x", "5", 5, -1, 1e999, True, "2026-01-01", 2.5, "", [1, 2], {"a": 1}]
    for _i in range(3000):
        items = _random_list(rng)
        for _k in range(rng.randint(0, 3)):
            if items:
                e = items[rng.randrange(len(items))]
                if isinstance(e, dict):
                    e[rng.choice(["amount", "frequency", "endDate", "startDate", "name"])] = rng.choice(vals)
        M.monthly_total(items, TODAY)


passed = sum(1 for _n, ok, _e in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)