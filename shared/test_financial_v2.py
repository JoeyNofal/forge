"""
FINANCIAL TRACKER v2 READER — L1, L2, L4, L5 tests for shared/financial_v2.py.
No model, no keys, never touches the real data file. One group of checks RUNS THE TRACKER'S OWN
JavaScript (apps/financial-tracker/ledger.js) on the same random files and demands identical
balances and net worth, so this Python copy can never drift from the app.
Needs Node.js on the PATH (the tracker is an Electron app, so it is there).

Run from the repo root:  python -m shared.test_financial_v2
"""
import ast
import copy
import json
import os
import random
import shutil
import subprocess
import time
from datetime import date, timedelta

from shared import financial_v2 as F

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_LEDGER_JS = os.path.join(_ROOT, "apps", "financial-tracker", "ledger.js")
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


def acct(i, kind="bank", opening=0, open_date="2026-01-01", **kw):
    a = {"id": i, "name": i.upper(), "kind": kind, "role": "none", "openingCents": opening, "openingDate": open_date, "closed": False}
    a.update(kw)
    return a


def tx(i, a, d, cents, typ="transaction", **kw):
    t = {"id": i, "accountId": a, "date": d, "description": "d " + i, "amountCents": cents, "type": typ}
    t.update(kw)
    return t


def file(accounts, txns, **extra):
    d = {"schemaVersion": 2, "accounts": accounts, "transactions": txns}
    d.update(extra)
    return d


AS_OF = "2026-11-24"

# ---------------------------------------------------------------- L1 static
with open(os.path.join(_HERE, "financial_v2.py"), encoding="utf-8") as _f:
    _SRC = _f.read()
_TREE = ast.parse(_SRC)


@check("L1 the module parses and imports only datetime and typing")
def _():
    mods = set()
    for n in ast.walk(_TREE):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        if isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[0])
    assert mods <= {"datetime", "typing", "__future__"}, mods


@check("L1 no file, network, clock or environment access in the module")
def _():
    for bad in ("open(", "os.", "requests", "urllib", "socket", "datetime.now", "date.today", "getenv", "environ"):
        assert bad not in _SRC.replace("os.path", "").replace("# ", "#"), bad


@check("L1 the kinds and the non-activity types are the tracker's")
def _():
    assert F.KINDS == ("bank", "savings", "credit_card", "loan", "receivable")
    assert F.DEBT_KINDS == ("credit_card", "loan")
    assert set(F.NON_ACTIVITY_TYPES) == {"transfer", "correction", "migration_adjustment"}


# ---------------------------------------------------------------- L2 hand-worked numbers
@check("is_v2: only a dict with schemaVersion 2 and an accounts list")
def _():
    assert F.is_v2(file([], []))
    for bad in (None, [], "x", 5, {}, {"schemaVersion": 1, "accounts": []}, {"schemaVersion": 2}, {"schemaVersion": 2, "accounts": {}},
                {"schemaVersion": "2", "accounts": []}, {"schemaVersion": True, "accounts": []}, {"schemaVersion": 3, "accounts": []}):
        assert not F.is_v2(bad), bad


@check("bank: opening + entries, future entries wait for their date")
def _():
    d = file([acct("v", opening=10000)], [tx("1", "v", "2026-02-01", -2500), tx("2", "v", "2026-03-01", 700), tx("3", "v", "2027-01-01", 99999)])
    assert F.balances_cents(d, AS_OF) == {"v": 8200}
    assert F.balances_cents(d, "2027-01-01") == {"v": 108199}
    assert F.balances_cents(d, "2026-02-01") == {"v": 7500}, "an entry counts ON its own date"
    assert F.balances_cents(d, "2026-01-31") == {"v": 10000}


@check("entries dated before the account's openingDate are not counted")
def _():
    d = file([acct("v", opening=1000, open_date="2026-06-01")], [tx("1", "v", "2026-05-31", 5000), tx("2", "v", "2026-06-01", 200)])
    assert F.balances_cents(d, AS_OF) == {"v": 1200}


@check("credit card: spending is negative cash flow and makes the debt grow; a payment shrinks it")
def _():
    d = file([acct("c", "credit_card", opening=5000)], [tx("1", "c", "2026-02-01", -2000), tx("2", "c", "2026-03-01", 3000)])
    assert F.balances_cents(d, AS_OF) == {"c": 4000}


@check("loan: amount owed falls with a payment")
def _():
    d = file([acct("l", "loan", opening=500000)], [tx("1", "l", "2026-03-01", 250000)])
    assert F.balances_cents(d, AS_OF) == {"l": 250000}


@check("receivable (BREX) behaves like a bank and is an asset")
def _():
    d = file([acct("b", "receivable", opening=164000)], [tx("1", "b", "2026-03-01", -4000)])
    assert F.balances_cents(d, AS_OF) == {"b": 160000}
    assert F.net_worth_cents(d, AS_OF) == 160000


@check("net worth: assets minus what is owed")
def _():
    d = file([acct("v", opening=100000), acct("s", "savings", opening=50000), acct("c", "credit_card", opening=7000), acct("l", "loan", opening=250000), acct("b", "receivable", opening=164000)], [])
    assert F.net_worth_cents(d, AS_OF) == 100000 + 50000 - 7000 - 250000 + 164000


@check("an overdraft (negative bank balance) lowers net worth")
def _():
    d = file([acct("v", opening=-3000)], [])
    assert F.net_worth_cents(d, AS_OF) == -3000


@check("a card in credit (negative owed) counts as an asset")
def _():
    d = file([acct("c", "credit_card", opening=-1500)], [])
    assert F.net_worth_cents(d, AS_OF) == 1500


@check("normalize: dollars, owed amounts positive, cash-flow signs kept")
def _():
    d = file([acct("v", opening=10000, name="VAULT"), acct("c", "credit_card", opening=5000, name="FREEDOM")],
             [tx("1", "c", "2026-02-01", -2000), tx("2", "v", "2026-02-02", 12345, "transaction", note="hi")])
    n = F.normalize_for_asset(d, AS_OF)
    assert n["accounts"] == {"v": 223.45, "c": 70.0}
    assert n["net_worth"] == 153.45
    assert [m["name"] for m in n["accounts_meta"]] == ["VAULT", "FREEDOM"]
    assert n["transactions"][0]["amount"] == -20.0 and n["transactions"][1]["amount"] == 123.45
    assert n["transactions"][1]["note"] == "hi" and "transferId" not in n["transactions"][1]
    assert n["asOf"] == AS_OF and n["warnings"] == [] and n["schemaVersion"] == 2


@check("normalize: future entries are flagged, types and transfer ids carried")
def _():
    d = file([acct("v"), acct("f")], [tx("1", "v", "2027-05-05", 100), tx("2", "v", "2026-03-03", -500, "transfer", transferId="t1"),
                                      tx("3", "f", "2026-03-03", 500, "transfer", transferId="t1"), tx("4", "v", "2026-04-04", 7, "correction"),
                                      tx("5", "v", "2026-01-02", 9, "migration_adjustment")])
    n = F.normalize_for_asset(d, AS_OF)
    t = {x["id"]: x for x in n["transactions"]}
    assert t["1"]["future"] is True and t["2"]["future"] is False
    edge = F.normalize_for_asset(file([acct("v")], [tx("today", "v", AS_OF, 1), tx("tomorrow", "v", "2026-11-25", 1)]), AS_OF)["transactions"]
    assert edge[0]["future"] is False and edge[1]["future"] is True, "an entry dated today counts today; the next day is future"
    assert t["2"]["type"] == "transfer" and t["2"]["transferId"] == "t1"
    assert {x["type"] for x in n["transactions"]} == {"transaction", "transfer", "correction", "migration_adjustment"}
    assert t["4"]["type"] == "correction" and t["5"]["type"] == "migration_adjustment"


@check("normalize: closed flag, names and roles come from the file; settings etc. pass through")
def _():
    d = file([acct("car", "loan", closed=True, name="Car Loan", role="none"), acct("v", role="vault", name="  My   Vault ")], [],
             settings={"vaultBufferMonths": 7}, fixedExpenses=[{"name": "Rent"}], groceries={"2026-10": 400}, creditScores=[{"score": 700}], paychecks=[{"netPay": 1}])
    n = F.normalize_for_asset(d, AS_OF)
    m = {x["id"]: x for x in n["accounts_meta"]}
    assert m["car"]["closed"] is True and m["v"]["closed"] is False
    assert m["v"]["name"] == "My Vault" and m["v"]["role"] == "vault"
    assert n["settings"] == {"vaultBufferMonths": 7} and n["fixedExpenses"] == [{"name": "Rent"}] and n["groceries"] == {"2026-10": 400}
    assert n["creditScores"] == [{"score": 700}] and n["paychecks"] == [{"netPay": 1}]


@check("normalize never changes its input")
def _():
    d = file([acct("v", opening=1), acct("c", "credit_card")], [tx("1", "v", "2026-02-01", 5), {"junk": 1}, "x"], settings={"a": [1, 2]})
    before = copy.deepcopy(d)
    F.normalize_for_asset(d, AS_OF)
    F.balances_cents(d, AS_OF)
    F.net_worth_cents(d, AS_OF)
    assert d == before


@check("a date object works as as_of")
def _():
    d = file([acct("v", opening=5)], [tx("1", "v", "2026-02-01", 5)])
    assert F.balances_cents(d, date(2026, 11, 24)) == {"v": 10}


# ---------------------------------------------------------------- bad rows are ignored or reported, never guessed
@check("bad entries are ignored: not a dict, unknown account, bad amount, bad date")
def _():
    junk = ["x", None, 5, [], {"accountId": "v", "date": "2026-02-01"}, tx("a", "nope", "2026-02-01", 100), tx("b", "v", "2026-02-01", "100"),
            tx("c", "v", "2026-02-01", 12.5), tx("d", "v", "2026-02-01", True), tx("e", "v", "2026-02-30", 100), tx("f", "v", "02/01/2026", 100),
            tx("g", "v", "1899-12-31", 100), tx("h", "v", "2201-01-01", 100), tx("i", "v", "2026-02-01", 2**60), tx("j", "v", "2026-02-01", float("nan"))]
    d = file([acct("v", opening=1000)], junk + [tx("ok", "v", "2026-03-03", 50)])
    assert F.balances_cents(d, AS_OF) == {"v": 1050}


@check("a whole-number float counts as cents (JSON from JavaScript can look like 5000.0)")
def _():
    d = file([acct("v", opening=1000)], [tx("1", "v", "2026-02-01", 250.0)])
    assert F.balances_cents(d, AS_OF) == {"v": 1250}


@check("bad accounts are skipped with a warning: no id, duplicate id, unknown kind")
def _():
    d = file([acct("v", opening=100), {"name": "no id"}, "x", acct("v", opening=999), acct("w", "crypto")], [])
    n = F.normalize_for_asset(d, AS_OF)
    assert list(n["accounts"]) == ["v"] and n["accounts"]["v"] == 1.0
    assert len(n["warnings"]) == 4, n["warnings"]


@check("normalize reports skipped transactions in one warning line")
def _():
    d = file([acct("v")], ["x", tx("a", "v", "bad", 1), tx("b", "v", "2026-02-01", 5)])
    n = F.normalize_for_asset(d, AS_OF)
    assert len(n["transactions"]) == 1 and any("2 transaction(s) skipped" in w for w in n["warnings"]), n["warnings"]


@check("not a v2 file or a bad as_of raises a clear ValueError")
def _():
    for bad in (None, {}, [], {"schemaVersion": 1, "accounts": {}}):
        for fn in (lambda x: F.normalize_for_asset(x, AS_OF), lambda x: F.balances_cents(x, AS_OF), lambda x: F.net_worth_cents(x, AS_OF)):
            try:
                fn(bad)
            except ValueError as e:
                assert "v2" in str(e)
            else:
                raise AssertionError("should have refused " + repr(bad))
    for bad_date in ("", "2026-13-01", "2026-02-30", "tomorrow", None, 5, "1899-12-31", "2201-01-01", "2026-1-1"):
        try:
            F.normalize_for_asset(file([], []), bad_date)
        except ValueError as e:
            assert "as_of" in str(e)
        else:
            raise AssertionError("should have refused as_of " + repr(bad_date))


# ---------------------------------------------------------------- L4: the tracker's own JavaScript must agree
def _random_file(rng):
    kinds = list(F.KINDS)
    accts = []
    for i in range(rng.randint(1, 8)):
        a = {"id": f"a{i}", "name": f"Acct {i}", "kind": rng.choice(kinds), "role": "none", "closed": rng.random() < 0.1,
             "openingCents": rng.randint(-500000, 5000000)}
        r = rng.random()
        if r < 0.8:
            a["openingDate"] = (date(2025, 1, 1) + timedelta(days=rng.randint(0, 700))).isoformat()
        elif r < 0.9:
            a["openingDate"] = "garbage"
        if rng.random() < 0.05:
            a["openingCents"] = 12.5
        accts.append(a)
    txns = []
    for j in range(rng.randint(0, 60)):
        r = rng.random()
        amt = rng.randint(-3000000, 3000000)
        row = {"id": f"t{j}", "accountId": rng.choice(accts)["id"] if rng.random() > 0.05 else "ghost",
               "date": (date(2025, 1, 1) + timedelta(days=rng.randint(-100, 900))).isoformat(), "description": "x",
               "amountCents": amt, "type": rng.choice(["transaction", "transfer", "correction", "migration_adjustment"])}
        if r < 0.03:
            txns.append("junk")
            continue
        if r < 0.06:
            row["amountCents"] = str(amt)
        elif r < 0.09:
            row["amountCents"] = amt + 0.5
        elif r < 0.12:
            row["amountCents"] = float(amt)
        elif r < 0.14:
            row["date"] = "2026-02-30"
        elif r < 0.16:
            row["amountCents"] = True
        txns.append(row)
    return {"schemaVersion": 2, "accounts": accts, "transactions": txns}


_JS = (
    "const fs=require('fs');const L=require(process.argv[1]);"
    "const cases=JSON.parse(fs.readFileSync(0,'utf8'));"
    "console.log(JSON.stringify(cases.map(c=>({b:c.asOfs.map(d=>L.allBalances(c.data,d)),n:c.asOfs.map(d=>L.netWorthCents(c.data,d))}))));"
)


@check("L4 the tracker's real JavaScript agrees on 400 random files x 6 dates (balances and net worth, to the cent)")
def _():
    node = shutil.which("node")
    assert node, "Node.js was not found on the PATH: the cross-check with the tracker's own ledger.js cannot run (this is a FAIL on purpose, not a skip)"
    assert os.path.exists(_LEDGER_JS), _LEDGER_JS
    rng = random.Random(20261124)
    cases = []
    for _i in range(400):
        d = _random_file(rng)
        asofs = ["2025-03-01", "2026-01-01", "2026-06-15", AS_OF, "2027-03-01", (date(2025, 1, 1) + timedelta(days=rng.randint(0, 900))).isoformat()]
        cases.append({"data": d, "asOfs": asofs})
    p = subprocess.run([node, "-e", _JS, _LEDGER_JS], input=json.dumps(cases), capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert p.returncode == 0, p.stderr[:500]
    js = json.loads(p.stdout)
    assert len(js) == len(cases)
    compared = 0
    for c, j in zip(cases, js):
        d = c["data"]
        ids = [a["id"] for a in d["accounts"]]
        for k, ao in enumerate(c["asOfs"]):
            py_b = F.balances_cents(d, ao)
            js_b = j["b"][k]
            assert set(py_b) == set(ids)
            for i in ids:
                assert py_b[i] == js_b[i], (i, ao, py_b[i], js_b[i], d["accounts"])
                compared += 1
            assert F.net_worth_cents(d, ao) == j["n"][k], (ao, F.net_worth_cents(d, ao), j["n"][k])
    assert compared > 2000, compared


@check("L4 normalize agrees with balances_cents on every random file (dollars = cents / 100)")
def _():
    rng = random.Random(7)
    for _i in range(500):
        d = _random_file(rng)
        n = F.normalize_for_asset(d, AS_OF)
        b = F.balances_cents(d, AS_OF)
        for k, v in b.items():
            assert abs(n["accounts"][k] - v / 100) < 1e-9
        assert abs(n["net_worth"] - F.net_worth_cents(d, AS_OF) / 100) < 1e-9
        assert [m["id"] for m in n["accounts_meta"]] == list(b)


@check("L4 20,000 transactions read fast")
def _():
    rng = random.Random(1)
    d = file([acct("v", opening=100), acct("c", "credit_card")], [tx(f"t{i}", rng.choice(["v", "c"]), "2026-03-03", rng.randint(-999, 999)) for i in range(20000)])
    t0 = time.time()
    F.normalize_for_asset(d, AS_OF)
    assert time.time() - t0 < 3.0


@check("L4 the same file read twice gives the same answer")
def _():
    d = _random_file(random.Random(99))
    assert F.normalize_for_asset(d, AS_OF) == F.normalize_for_asset(d, AS_OF)


# ---------------------------------------------------------------- L5 extreme
@check("L5 junk top-level values never crash is_v2 and are refused by the readers")
def _():
    for bad in (None, [], "x", 5, 1.5, True, {}, {"schemaVersion": [2]}, {"schemaVersion": 2, "accounts": None}, {"accounts": []}):
        assert F.is_v2(bad) is False
        try:
            F.normalize_for_asset(bad, AS_OF)
        except ValueError:
            pass
        else:
            raise AssertionError(repr(bad))


@check("L5 absurd numbers and odd text never crash and never count")
def _():
    d = file([acct("v", opening=1000, name="x" * 10000), acct("u", name="\u0000\t\n😀 ünï", openingCents=2**70), acct("f", openingCents=float("inf")), acct("z", openingCents=None)],
             [tx("1", "v", "2026-02-01", 10**30), tx("2", "v", "2026-02-01", -(2**53)), tx("3", "v", "2026-02-01", 2**53 - 1), tx("4", "v", "2026-02-01", float("inf"))])
    n = F.normalize_for_asset(d, AS_OF)
    assert len(n["accounts_meta"][0]["name"]) == 60
    assert n["accounts"]["u"] == 0.0 and n["accounts"]["f"] == 0.0 and n["accounts"]["z"] == 0.0
    assert F.balances_cents(d, AS_OF)["v"] == 1000 + (2**53 - 1)


@check("L5 a transactions or accounts entry that is not a list is treated as empty (found by the fuzz test)")
def _():
    for bad in (5, "x", {}, None, True, 1.5):
        d = {"schemaVersion": 2, "accounts": [acct("v", opening=700)], "transactions": bad}
        assert F.balances_cents(d, AS_OF) == {"v": 700}
        n = F.normalize_for_asset(d, AS_OF)
        assert n["transactions"] == [] and n["accounts"] == {"v": 7.0}
    for bad in (5, "x", {}, None):
        d = {"schemaVersion": 2, "accounts": bad, "transactions": []}
        assert not F.is_v2(d)


@check("L5 deeply nested or huge junk inside rows is ignored")
def _():
    deep = cur = {}
    for _i in range(500):
        cur["x"] = {}
        cur = cur["x"]
    acct_with_junk = acct("v", opening=5)
    acct_with_junk["extra"] = deep
    d = file([acct_with_junk], [{"accountId": "v", "date": "2026-02-01", "amountCents": 5, "id": deep, "description": deep, "type": deep, "note": deep, "transferId": deep}])
    n = F.normalize_for_asset(d, AS_OF)
    t = n["transactions"][0]
    assert t["id"] == "" and t["description"] == "" and t["type"] == "transaction" and "note" not in t and "transferId" not in t and t["amount"] == 0.05


@check("L5 fuzz: 3,000 randomly damaged files never crash")
def _():
    rng = random.Random(4242)
    for _i in range(3000):
        d = _random_file(rng)
        for _k in range(rng.randint(0, 4)):
            path = rng.choice(["acct", "tx", "top"])
            if path == "acct" and isinstance(d["accounts"], list) and d["accounts"] and isinstance(d["accounts"][0], dict):
                a = rng.choice(d["accounts"])
                a[rng.choice(["id", "kind", "openingCents", "openingDate", "name", "closed"])] = rng.choice([None, [], {}, "x", 5, -1, 1e999, True, "2026-01-01"])
            elif path == "tx" and isinstance(d["transactions"], list) and d["transactions"]:
                t = rng.choice(d["transactions"])
                if isinstance(t, dict):
                    t[rng.choice(["id", "accountId", "date", "amountCents", "type", "description"])] = rng.choice([None, [], {}, "x", 5, -1, 1e999, True, "2026-01-01"])
            else:
                d[rng.choice(["transactions", "accounts", "schemaVersion", "settings"])] = rng.choice([None, [], {}, "x", 2, 1])
        if F.is_v2(d):
            n = F.normalize_for_asset(d, AS_OF)
            assert isinstance(n["accounts"], dict) and isinstance(n["warnings"], list)
        else:
            try:
                F.normalize_for_asset(d, AS_OF)
            except ValueError:
                pass


passed = sum(1 for _n, ok, _e in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)