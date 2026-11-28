"""
ASSET v2 savings - L1 (static) + L2 (smoke) + L4 (sustained) + L5 (extreme) for the savings rate and the
emergency fund tools: the Financial Tracker's monthly-cost rules, and the FUNDS account of a version 2 file.
Synthetic data throughout - NEVER touches Youssef's real financial-tracker-data.json.
OLD FILES: the exact code of both tools from before this change (read from git commit ed356b3) is run side by
side with the new code on 300 random old-format files that only use monthly and weekly bills (where the old
rule was right); the output must be IDENTICAL. Where the old rule was wrong (biweekly, quarterly, yearly,
finished bills) the new numbers are checked by hand below.
Run from the repo root:  python -m agents.asset.test_asset_v2_savings
"""
import ast, copy, os, random, re, subprocess, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.abspath("."))

from agents.asset import asset_tools as T

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail and status == "FAIL" else ""))

# The code of both tools exactly as it was BEFORE this change, read from git (commit ed356b3 is permanent history).
_OLD_COMMIT = "ed356b3"
def _old_function_source(name):
    p = subprocess.run(["git", "show", f"{_OLD_COMMIT}:agents/asset/asset_tools.py"], capture_output=True, text=True, encoding="utf-8", cwd=os.path.abspath("."))
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError(f"could not read the old asset_tools.py from git commit {_OLD_COMMIT} (is git on the PATH, and are you in the repo root?): {p.stderr[:200]}")
    old_tree = ast.parse(p.stdout)
    node = next(n for n in old_tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(p.stdout, node) or ""
_OLD = {"savings": _old_function_source("get_savings_rate"), "emergency": _old_function_source("get_emergency_fund_status")}

TODAY = date.today()
def d(n):
    return (TODAY + timedelta(days=n)).isoformat()

def acct(i, kind="bank", opening=0, name=None, role="none", closed=False):
    return {"id": i, "name": name or i.upper(), "kind": kind, "role": role, "openingCents": opening, "openingDate": "2020-01-01", "closed": closed}

def v2file(accounts, expenses=None, groceries=None, paychecks=None):
    return {"schemaVersion": 2, "accounts": accounts, "transactions": [], "settings": {}, "fixedExpenses": expenses if expenses is not None else [],
            "groceries": groceries if groceries is not None else {}, "creditScores": [], "paychecks": paychecks if paychecks is not None else []}

def adapt(raw):
    return T._adapt(raw, TODAY.isoformat())

def run_new(data, fn, *a, **k):
    T.load_data = lambda: data
    return getattr(T, fn)(*a, **k)

def run_old(data, which, *a, **k):
    ns = dict(T.__dict__)
    ns["load_data"] = lambda: data
    exec(_OLD[which], ns)
    return ns["get_savings_rate" if which == "savings" else "get_emergency_fund_status"](*a, **k)

def exp(amount, freq, **kw):
    e = {"name": "x", "amount": amount, "frequency": freq}
    e.update(kw)
    return e

print("=== L1 STATIC ===")
src = open("agents/asset/asset_tools.py", encoding="utf-8").read()
tree = ast.parse(src)
fn = {n.name: ast.get_source_segment(src, n) or "" for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
check("both tools use the shared monthly-cost rule", "monthly_cost.monthly_total(" in fn["get_savings_rate"] and "monthly_cost.monthly_total(" in fn["get_emergency_fund_status"])
check("neither tool keeps its own copy of the old monthly/weekly loop", "monthly_fixed +=" not in fn["get_savings_rate"] and "monthly_fixed +=" not in fn["get_emergency_fund_status"])
check("the emergency fund tool no longer reads the old savings/car split for a v2 file", "_funds_account(data)" in fn["get_emergency_fund_status"])
check("no bare except in asset_tools", not any(isinstance(n, ast.ExceptHandler) and n.type is None for n in ast.walk(tree)))

print("\n=== OLD FILES: NEW CODE = OLD CODE (monthly and weekly bills only), 300 random files ===")
def random_v1(rng):
    exps = [exp(rng.choice([round(rng.uniform(5, 2500), 2), rng.randint(5, 2500)]), rng.choice(["monthly", "weekly"])) for _ in range(rng.randint(0, 12))]
    groc = {f"2026-{m:02d}": round(rng.uniform(200, 900), 2) for m in rng.sample(range(1, 13), rng.randint(0, 6))}
    pays = [{"netPay": round(rng.uniform(500, 2500), 2)} for _ in range(rng.randint(0, 12))]
    return {"accounts": {"funds": 0}, "fundsSubAccounts": {"savingsFund": round(rng.uniform(0, 20000), 2), "carFund": 100}, "transactions": [],
            "fixedExpenses": exps, "groceries": groc, "paychecks": pays, "settings": {}, "creditScores": []}
rng = random.Random(20261124)
same = True; why = ""
for i in range(300):
    data = random_v1(rng)
    k = rng.choice([1, 3, 8, 50])
    try:
        a1 = run_new(data, "get_savings_rate", k); a2 = run_old(data, "savings", k)
        b1 = run_new(data, "get_emergency_fund_status"); b2 = run_old(data, "emergency")
    except Exception as e:
        same = False; why = f"case {i} crashed: {e!r}"; break
    if a1 != a2 or b1 != b2:
        same = False; why = f"case {i}: savings same={a1 == a2}, emergency same={b1 == b2}\n{a1}\n--\n{a2}"; break
check("savings rate and emergency fund give IDENTICAL text for old-format files with monthly and weekly bills", same, why)

print("\n=== L2 HAND-WORKED NUMBERS (the tracker's monthly-cost rules) ===")
EXPENSES = [exp(1000, "monthly"), exp(100, "weekly"), exp(100, "biweekly"), exp(300, "quarterly"), exp(120, "yearly"),
            exp(500, "monthly", endDate=d(-1)), exp(40, "monthly", startDate=d(30)), exp(77, "daily")]
GROC = {"2026-07": 9999, "2026-08": 400, "2026-09": 500, "2026-10": 600}
PAYS = [{"netPay": 1000}, {"netPay": 1200}]
V2 = adapt(v2file([acct("funds", "savings", opening=300000, name="FUNDS", role="funds"), acct("vault", opening=500000, role="vault")], EXPENSES, GROC, PAYS))
em = run_new(V2, "get_emergency_fund_status")
check("monthly expenses = 1,799.67 fixed + 500.00 groceries = 2,299.67", "Estimated monthly expenses: $2,299.67" in em, em)
check("3-month and 6-month targets", "3-month target:             $6,899.00" in em and "6-month target:             $13,798.00" in em, em)
check("the whole FUNDS balance is used: $3,000.00 = 43.5% of the 3-month goal, still needed $3,899.00", "FUNDS (SoFi Savings) balance:       $3,000.00" in em and "Progress to 3-month goal:   43.5%" in em and "Still needed:               $3,899.00" in em, em)
sv = run_new(V2, "get_savings_rate", 8)
check("savings rate: take-home 4,763.00, fixed 1,799.67, groceries 500.00, savings 2,463.33, rate 51.7%",
      "Avg monthly take-home:     $4,763.00" in sv and "Fixed bills:   $1,799.67" in sv and "Groceries:     $500.00" in sv and "Estimated monthly savings:  $2,463.33" in sv and "Savings rate:               51.7%" in sv and "Excellent" in sv, sv)
v1_same = {"accounts": {"funds": 3000}, "fundsSubAccounts": {"savingsFund": 3000, "carFund": 0}, "transactions": [], "fixedExpenses": copy.deepcopy(EXPENSES), "groceries": GROC, "paychecks": PAYS, "settings": {}, "creditScores": []}
em1 = run_new(v1_same, "get_emergency_fund_status"); sv1 = run_new(v1_same, "get_savings_rate", 8)
check("an OLD-format file gets the same corrected bill math (biweekly, quarterly, yearly counted; finished bill skipped)", "Estimated monthly expenses: $2,299.67" in em1 and "Fixed bills:   $1,799.67" in sv1, em1 + sv1)
check("and an old-format file still reads its savings fund from fundsSubAccounts", "Savings Fund balance:       $3,000.00" in em1)
check("the bill that ended yesterday is not counted; the one starting in 30 days is", "$2,799.67" not in em and "$2,339.67" not in em)
check("the last 3 months of groceries are averaged (the 9,999 month is too old)", "Groceries:     $500.00" in sv)

print("\n=== L2 THE FUNDS ACCOUNT ===")
def em_for(accounts, **kw):
    return run_new(adapt(v2file(accounts, EXPENSES, GROC, PAYS)), "get_emergency_fund_status")
renamed = em_for([acct("sav", "savings", opening=120000, name="Rainy Day", role="funds")])
check("a renamed FUNDS account (found by its role) is used with its own name", "Rainy Day balance:       $1,200.00" in renamed, renamed)
by_id = em_for([acct("funds", "savings", opening=80000, name="FUNDS")])
check("an account called funds without the role is still found", "FUNDS (SoFi Savings) balance:       $800.00" in by_id, by_id)
both = em_for([acct("funds", "savings", opening=111100, name="Old"), acct("sav", "savings", opening=222200, name="Real", role="funds")])
check("the account with the funds role wins over one that is only called funds", "Real balance:       $2,222.00" in both, both)
none = em_for([acct("vault", opening=500000)])
check("no FUNDS account: says so clearly instead of reporting $0", "No open FUNDS (savings) account was found" in none and "Progress" not in none, none)
closed = em_for([acct("funds", "savings", opening=0, name="FUNDS", role="funds", closed=True)])
check("a closed FUNDS account is not used", "No open FUNDS (savings) account was found" in closed, closed)
reached = em_for([acct("funds", "savings", opening=900000, name="FUNDS", role="funds")])
check("goal reached message", "3-month goal REACHED!" in reached and "Still needed" not in reached, reached)
zero = run_new(adapt(v2file([acct("funds", "savings", opening=50000, role="funds")], [], {}, PAYS)), "get_emergency_fund_status")
check("no bills and no groceries: targets are 0 and it does not divide by zero", "3-month target:             $0.00" in zero and "Progress to 3-month goal:   0.0%" in zero, zero)

print("\n=== L2 ODD DATA ===")
check("amounts written as text count; junk amounts count as 0", "Estimated monthly expenses: $120.50" in run_new(adapt(v2file([acct("funds", "savings", role="funds")], [exp("100.50", "monthly"), exp("abc", "monthly"), exp("20", "monthly"), exp(None, "monthly")], {}, PAYS)), "get_emergency_fund_status"))
check("fixed expenses that are not a list count as 0", "Estimated monthly expenses: $0.00" in run_new(adapt({**v2file([acct("funds", "savings", role="funds")], [], {}, PAYS), "fixedExpenses": "oops"}), "get_emergency_fund_status"))
mix = run_new(adapt(v2file([acct("funds", "savings", role="funds")], [], {"2026-10": "x", "2026-09": 500, "2026-08": True}, PAYS)), "get_savings_rate", 8)
check("grocery months that are not numbers are ignored (this used to crash the tool)", "Groceries:     $500.00" in mix, mix)
check("groceries that are not a dictionary count as 0", "Groceries:     $0.00" in run_new(adapt({**v2file([acct("funds", "savings", role="funds")], [], {}, PAYS), "groceries": [1, 2]}), "get_savings_rate", 8))
v1_list_groceries = {"accounts": {}, "fundsSubAccounts": {"savingsFund": 100}, "transactions": [], "fixedExpenses": [], "groceries": [1, 2], "paychecks": PAYS, "settings": {}, "creditScores": []}
check("an OLD-format file whose groceries are not a dictionary no longer crashes either tool", "Groceries:     $0.00" in run_new(v1_list_groceries, "get_savings_rate", 8) and "Estimated monthly expenses: $0.00" in run_new(v1_list_groceries, "get_emergency_fund_status"))
check("no paychecks still says so", run_new(adapt(v2file([acct("funds", "savings", role="funds")], EXPENSES, GROC, [])), "get_savings_rate", 8) == "No paycheck data found.")

print("\n=== L4 SUSTAINED ===")
FACTOR = {"monthly": 1.0, "weekly": 4.33, "biweekly": 26 / 12, "quarterly": 1 / 3, "yearly": 1 / 12}
def independent_monthly(exps):
    total = 0.0
    for e in exps:
        if e.get("endDate") and e["endDate"] < TODAY.isoformat():
            continue
        total += float(e["amount"]) * FACTOR.get(e["frequency"], 0)
    return total
def random_v2(rng):
    exps = []
    for _ in range(rng.randint(0, 15)):
        e = exp(round(rng.uniform(1, 3000), 2), rng.choice(list(FACTOR) + ["daily", ""]))
        if rng.random() < 0.4:
            e["endDate"] = d(rng.randint(-60, 60))
        if rng.random() < 0.3:
            e["startDate"] = d(rng.randint(-60, 60))
        exps.append(e)
    groc = {f"2026-{m:02d}": round(rng.uniform(100, 900), 2) for m in rng.sample(range(1, 13), rng.randint(0, 6))}
    pays = [{"netPay": round(rng.uniform(300, 2500), 2)} for _ in range(rng.randint(1, 10))]
    accts = [acct("funds", "savings", opening=rng.randint(0, 2000000), name="FUNDS", role="funds"), acct("vault", opening=rng.randint(0, 900000))]
    return v2file(accts, exps, groc, pays), exps, groc
rng = random.Random(777)
ok = True; why = ""
for i in range(300):
    raw, exps, groc = random_v2(rng)
    last3 = [groc[m] for m in sorted(groc)[-3:]]
    avg_g = sum(last3) / len(last3) if last3 else 0
    expect = independent_monthly(exps) + avg_g
    out = run_new(adapt(raw), "get_emergency_fund_status")
    m = re.search(r"Estimated monthly expenses: \$([\d,]+\.\d\d)", out)
    t3 = re.search(r"3-month target:\s+\$([\d,]+\.\d\d)", out)
    if not m or abs(float(m.group(1).replace(",", "")) - expect) > 0.006 or not t3 or abs(float(t3.group(1).replace(",", "")) - expect * 3) > 0.011:
        ok = False; why = f"case {i}: expected {expect:.2f}, got: {out[:160]}"; break
    sv_out = run_new(adapt(raw), "get_savings_rate", 8)
    fx = re.search(r"Fixed bills:\s+\$([\d,]+\.\d\d)", sv_out)
    if not fx or abs(float(fx.group(1).replace(",", "")) - independent_monthly(exps)) > 0.006:
        ok = False; why = f"case {i}: savings fixed bills expected {independent_monthly(exps):.2f}, got: {sv_out[:200]}"; break
check("300 random v2 files: both tools print the same monthly cost as an independent calculation", ok, why)
big = adapt(v2file([acct("funds", "savings", role="funds")], [exp(1, "monthly") for _ in range(50000)], {}, PAYS))
import time
t0 = time.time(); run_new(big, "get_emergency_fund_status"); run_new(big, "get_savings_rate", 8)
check("50,000 bills are added up quickly", time.time() - t0 < 5, f"{time.time() - t0:.1f}s")

print("\n=== L5 EXTREME ===")
rng = random.Random(4242)
vals = [None, [], {}, "x", 5, -1, 1e999, True, "2026-01-01", 2**70, float("nan"), "", [1], {"a": 1}]
crashed = ""
for i in range(1000):
    raw, exps, groc = random_v2(rng)
    for _ in range(rng.randint(1, 4)):
        k = rng.choice(["exp", "groc", "acct", "top"])
        if k == "exp" and isinstance(raw["fixedExpenses"], list) and raw["fixedExpenses"]:
            victim = rng.choice(raw["fixedExpenses"])
            if isinstance(victim, dict):
                victim[rng.choice(["amount", "frequency", "endDate", "startDate"])] = rng.choice(vals)
        elif k == "groc" and isinstance(raw["groceries"], dict) and raw["groceries"]:
            raw["groceries"][rng.choice(list(raw["groceries"]))] = rng.choice(vals)
        elif k == "acct":
            rng.choice(raw["accounts"])[rng.choice(["id", "role", "kind", "closed", "openingCents"])] = rng.choice(vals)
        else:
            raw[rng.choice(["fixedExpenses", "groceries"])] = rng.choice(vals)
    try:
        dd = adapt(raw)
        run_new(dd, "get_emergency_fund_status")
        run_new(dd, "get_savings_rate", rng.choice([1, 8]))
    except Exception as e:
        crashed = f"case {i}: {e!r}"; break
check("1,000 randomly damaged v2 files never crash either tool", crashed == "", crashed)
_before = copy.deepcopy(v2file([acct("funds", "savings", role="funds")], EXPENSES, GROC, PAYS))
_data = copy.deepcopy(_before)
run_new(adapt(_data), "get_emergency_fund_status")
check("the input file data is never changed", _data == _before)

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, dd_ in results:
        if s == "FAIL":
            print(f"  - {n}: {dd_}")
sys.exit(0 if failed == 0 else 1)