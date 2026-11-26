"""
ASSET v2 activity - L1 (static) + L2 (smoke) + L4 (sustained) + L5 (extreme) for the spending summary and
the recent transactions tool reading Financial Tracker v2 files.
Synthetic data throughout - NEVER touches Youssef's real financial-tracker-data.json.
OLD FILES: the exact code of both tools from before v2 support (read from git commit dcf5784) is run side by side with the
new code on 300 random old-format files; the output must be IDENTICAL.
Run from the repo root:  python -m agents.asset.test_asset_v2_activity
"""
import ast, copy, os, random, re, subprocess, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.abspath("."))

from agents.asset import asset_tools as T
from shared import financial_v2

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail and status == "FAIL" else ""))

# The code of both tools exactly as it was BEFORE v2 support, read from git (commit dcf5784 is permanent history).
_OLD_COMMIT = "dcf5784"
def _old_function_source(name):
    p = subprocess.run(["git", "show", f"{_OLD_COMMIT}:agents/asset/asset_tools.py"], capture_output=True, text=True, encoding="utf-8", cwd=os.path.abspath("."))
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError(f"could not read the old asset_tools.py from git commit {_OLD_COMMIT} (is git on the PATH, and are you in the repo root?): {p.stderr[:200]}")
    old_tree = ast.parse(p.stdout)
    node = next(n for n in old_tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(p.stdout, node) or ""
_OLD = {"spending": _old_function_source("get_spending_summary"), "recent": _old_function_source("get_recent_transactions")}

TODAY = date.today()
def d(n):
    return (TODAY + timedelta(days=n)).isoformat()

def acct(i, kind="bank", opening=0, name=None, closed=False):
    return {"id": i, "name": name or i.upper(), "kind": kind, "role": "none", "openingCents": opening, "openingDate": "2020-01-01", "closed": closed}

def tx(i, a, dt, cents, typ="transaction"):
    return {"id": i, "accountId": a, "date": dt, "description": "d " + i, "amountCents": cents, "type": typ}

def v2file(accounts, txns):
    return {"schemaVersion": 2, "accounts": accounts, "transactions": txns, "settings": {}, "fixedExpenses": [], "groceries": {}, "creditScores": [], "paychecks": []}

def adapt(raw):
    return T._adapt(raw, TODAY.isoformat())

def run_new(data, fn, *a, **k):
    T.load_data = lambda: data
    return getattr(T, fn)(*a, **k)

def run_old(data, which, *a, **k):
    ns = dict(T.__dict__)
    ns["load_data"] = lambda: data
    exec(_OLD[which], ns)
    return ns["get_spending_summary" if which == "spending" else "get_recent_transactions"](*a, **k)

print("=== L1 STATIC ===")
src = open("agents/asset/asset_tools.py", encoding="utf-8").read()
tree = ast.parse(src)
fn_rec = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "get_recent_transactions")
stores = {n.id for n in ast.walk(fn_rec) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
check("get_recent_transactions no longer hides the account_label helper with a local variable of the same name", "account_label" not in stores, str(sorted(stores)))
check("the spending tool uses the tracker's list of non-spending types", "financial_v2.NON_ACTIVITY_TYPES" in src)
check("no bare except in asset_tools", not any(isinstance(n, ast.ExceptHandler) and n.type is None for n in ast.walk(tree)))
check("the non-spending types are transfer, correction and migration_adjustment", set(financial_v2.NON_ACTIVITY_TYPES) == {"transfer", "correction", "migration_adjustment"})

print("\n=== OLD FILES: NEW CODE = OLD CODE, 300 random files ===")
def random_v1(rng):
    accounts = {k: round(rng.uniform(-500, 9000), 2) for k in ("vault", "flex", "funds", "cc", "cc2", "car_loan", "brex")}
    txns = []
    for j in range(rng.randint(0, 40)):
        r = rng.random()
        day = TODAY - timedelta(days=rng.randint(0, 120))
        raw_date = rng.choice([day.isoformat(), day.isoformat() + "T10:00:00Z", "garbage", "", None, day.isoformat()])
        t = {"id": str(j), "accountId": rng.choice(["vault", "flex", "cc", "cc2", "car_loan", "brex", "xyz"]), "date": raw_date,
             "amount": round(rng.uniform(-300, 300), 2), "type": rng.choice([None, "transfer", "transaction", "transaction", "correction", "migration_adjustment"]),
             "description": rng.choice(["x", "coffee", "", None])}
        if r < 0.05:
            del t["description"]
        txns.append(t)
    return {"accounts": accounts, "transactions": txns, "settings": {}, "fixedExpenses": [], "groceries": {}, "creditScores": [], "paychecks": []}
rng = random.Random(20261124)
same = True; why = ""
for i in range(300):
    data = random_v1(rng)
    m = rng.choice([1, 1, 2, 3, 6])
    acc = rng.choice([None, None, "vault", "cc", "xyz", "nope"])
    lim = rng.choice([1, 5, 10, 50])
    try:
        a1 = run_new(data, "get_spending_summary", m); a2 = run_old(data, "spending", m)
        b1 = run_new(data, "get_recent_transactions", acc, lim); b2 = run_old(data, "recent", acc, lim)
    except Exception as e:
        same = False; why = f"case {i} crashed: {e!r}"; break
    if a1 != a2 or b1 != b2:
        same = False; why = f"case {i}: spending same={a1 == a2}, recent same={b1 == b2}"; break
check("spending summary and recent transactions give IDENTICAL text for old-format files", same, why)
check("the old-format spending text has no v2 note", "Money spent from every account" not in run_new(random_v1(random.Random(1)), "get_spending_summary", 3))

print("\n=== L2 V2 SPENDING ===")
FIX = v2file([acct("vault", opening=1000000, name="VAULT"), acct("cc", "credit_card", name="FREEDOM (Chase)"), acct("flex", opening=50000, name="FLEX")], [
    tx("s1", "vault", d(-3), -2500), tx("s2", "vault", d(-10), -1000),
    tx("c1", "cc", d(-5), -4000),
    tx("t1", "vault", d(-4), -4000, "transfer"), tx("t2", "cc", d(-4), 4000, "transfer"),
    tx("corr", "vault", d(-2), -700, "correction"), tx("mig", "cc", d(-20), -999, "migration_adjustment"),
    tx("fut", "vault", d(5), -5000), tx("old", "vault", d(-400), -9999),
    tx("in1", "flex", d(-6), 12000),
])
data = adapt(FIX)
sp = run_new(data, "get_spending_summary", 1)
check("last month: VAULT $35.00 (2), FREEDOM card $40.00 (1), total $75.00", "VAULT (Chase Checking): $35.00 (2 transactions)" in sp and "FREEDOM (Chase): $40.00 (1 transactions)" in sp and "TOTAL SPENT: $75.00" in sp, sp)
check("credit card purchases count as spending (answer 5)", "FREEDOM (Chase): $40.00" in sp)
check("transfers, balance corrections and migration adjustments are NOT spending (answer 2)", "$4,000" not in sp and "$7.00" not in sp and "$9.99" not in sp, sp)
check("an entry dated in the future is not spent yet", "$50.00" not in sp)
check("money coming in is not spending", "FLEX" not in sp)
check("a payment into the card (positive) is not spending", "$80.00" not in sp)
check("the v2 note explains what is counted", "(Money spent from every account, credit cards included." in sp)
sp24 = run_new(data, "get_spending_summary", 24)
check("24 months also includes the old $99.99 entry: VAULT $134.99 (3), total $174.99", "VAULT (Chase Checking): $134.99 (3 transactions)" in sp24 and "TOTAL SPENT: $174.99" in sp24, sp24)
check("spending lines are sorted by account id (cc before vault)", sp.index("FREEDOM") < sp.index("VAULT"))
empty = adapt(v2file([acct("vault", opening=100)], [tx("x", "vault", d(-1), 500), tx("y", "vault", d(-1), -50, "transfer")]))
check("no spending at all says so", run_new(empty, "get_spending_summary", 1) == "No spending transactions found in the last 1 month(s).")
check("an entry exactly 30 days ago is still in 'last month'; 31 days is not", "$3.00" in run_new(adapt(v2file([acct("v")], [tx("a", "v", d(-30), -300)])), "get_spending_summary", 1) and "No spending" in run_new(adapt(v2file([acct("v")], [tx("a", "v", d(-31), -300)])), "get_spending_summary", 1))
check("a renamed account shows its new name", "Main (Chase Checking)" in run_new(adapt(v2file([acct("vault", name="Main")], [tx("a", "vault", d(-1), -100)])), "get_spending_summary", 1))

print("\n=== L2 V2 RECENT TRANSACTIONS ===")
rc = run_new(data, "get_recent_transactions")
lines = rc.split("\n")
check("heading says all accounts", lines[0] == "RECENT TRANSACTIONS — ALL ACCOUNTS:", lines[0])
body = [l for l in lines[1:] if l.strip()]
check("9 entries (10 minus the future one)", len(body) == 9, str(len(body)))
check("newest first", body[0].startswith("  " + d(-2)) and body[1].startswith("  " + d(-3)) and body[-1].startswith("  " + d(-400)), rc)
check("signs and amounts: -25.00 and +40.00", any("-25.00  d s1" in l for l in body) and any("+40.00  d t2" in l for l in body), rc)
check("the three special types are labelled", any("d corr" in l and l.endswith("[balance correction]") for l in body) and any("d mig" in l and l.endswith("[migration adjustment]") for l in body) and sum(l.endswith("[transfer]") for l in body) == 2, rc)
check("names come from the file", any("(VAULT (Chase Checking))" in l for l in body) and any("(FREEDOM (Chase))" in l for l in body))
check("the future entry never shows", "d fut" not in rc)
rv = run_new(data, "get_recent_transactions", "vault", 10)
check("filtering by account: heading shows the account, only its 5 entries", rv.split("\n")[0] == "RECENT TRANSACTIONS — VAULT (Chase Checking):" and len([l for l in rv.split("\n")[1:] if l.strip()]) == 5, rv)
r2 = run_new(data, "get_recent_transactions", "vault", 2)
check("the limit is respected and keeps the newest", len([l for l in r2.split("\n")[1:] if l.strip()]) == 2 and "d corr" in r2 and "d s1" in r2 and "d s2" not in r2, r2)
ru = run_new(data, "get_recent_transactions", "nope", 10)
check("an unknown account is named as unknown, not shown as all accounts", ru.split("\n")[0] == "RECENT TRANSACTIONS — UNKNOWN ACCOUNT (nope):" and len([l for l in ru.split("\n")[1:] if l.strip()]) == 0, ru)

print("\n=== L4 SUSTAINED ===")
def random_v2(rng):
    kinds = ["bank", "savings", "credit_card", "loan", "receivable"]
    accts = [acct(f"a{i}", rng.choice(kinds), rng.randint(-300000, 4000000), name=f"Acct {i}") for i in range(rng.randint(1, 6))]
    types = ["transaction", "transaction", "transaction", "transfer", "correction", "migration_adjustment"]
    txns = [tx(f"t{j}", rng.choice(accts)["id"], d(rng.randint(-150, 20)), rng.randint(-900000, 900000), rng.choice(types)) for j in range(rng.randint(0, 50))]
    return v2file(accts, txns)
rng = random.Random(77)
ok = True; why = ""
for i in range(300):
    raw = random_v2(rng)
    m = rng.choice([1, 2, 3, 6])
    cutoff = (TODAY - timedelta(days=30 * m)).isoformat(); today_s = TODAY.isoformat()
    expect = sum(-t["amountCents"] for t in raw["transactions"] if t["amountCents"] < 0 and t["type"] == "transaction" and cutoff <= t["date"] <= today_s)
    out = run_new(adapt(raw), "get_spending_summary", m)
    if expect == 0:
        good = out.startswith("No spending transactions found")
    else:
        mt = re.search(r"TOTAL SPENT: \$([\d,]+\.\d\d)", out)
        good = bool(mt) and round(float(mt.group(1).replace(",", "")) * 100) == expect
    if not good:
        ok = False; why = f"case {i}: expected {expect} cents, got: {out[-120:]}"; break
check("300 random v2 files: the printed total always equals an independent count in cents", ok, why)
ok = True; why = ""
for i in range(300):
    raw = random_v2(rng)
    lim = rng.choice([1, 3, 10, 50])
    out = run_new(adapt(raw), "get_recent_transactions", None, lim)
    rows = [l for l in out.split("\n")[1:] if l.strip()]
    dates = [l.strip()[:10] for l in rows]
    if len(rows) > lim or dates != sorted(dates, reverse=True) or any(x > TODAY.isoformat() for x in dates):
        ok = False; why = f"case {i}: {len(rows)} rows, dates {dates[:4]}"; break
check("300 random v2 files: recent transactions respect the limit, are newest first and never show the future", ok, why)

print("\n=== L5 EXTREME ===")
rng = random.Random(4242)
vals = [None, [], {}, "x", 5, -1, 1e999, True, "2026-01-01", 2**70]
crashed = ""
for i in range(1000):
    raw = random_v2(rng)
    for _ in range(rng.randint(0, 4)):
        if raw["transactions"] and rng.random() < 0.7:
            rng.choice(raw["transactions"])[rng.choice(["accountId", "date", "amountCents", "type", "description", "id"])] = rng.choice(vals)
        elif raw["accounts"]:
            rng.choice(raw["accounts"])[rng.choice(["id", "kind", "name", "closed"])] = rng.choice(vals)
    try:
        dd = adapt(raw)
        run_new(dd, "get_spending_summary", rng.choice([1, 3, 12]))
        run_new(dd, "get_recent_transactions", rng.choice([None, "a0", "zzz"]), rng.choice([1, 10]))
    except Exception as e:
        crashed = f"case {i}: {e!r}"; break
check("1,000 randomly damaged v2 files never crash either tool", crashed == "", crashed)
big = adapt(v2file([acct("a")], [tx(f"t{i}", "a", d(-(i % 20)), -(i % 500 + 1)) for i in range(30000)]))
import time
t0 = time.time(); run_new(big, "get_spending_summary", 1); run_new(big, "get_recent_transactions", None, 10)
check("30,000 entries are summarised quickly", time.time() - t0 < 5, f"{time.time() - t0:.1f}s")
before = copy.deepcopy(FIX)
run_new(adapt(FIX), "get_spending_summary", 1)
check("the input file data is never changed", FIX == before)

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, dd_ in results:
        if s == "FAIL":
            print(f"  - {n}: {dd_}")
sys.exit(0 if failed == 0 else 1)