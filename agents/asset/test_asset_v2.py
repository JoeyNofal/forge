"""
ASSET v2 - L1 (static) + L2 (smoke) + L4 (sustained) + L5 (extreme) for reading Financial Tracker v2 files.
Synthetic data throughout - NEVER touches Youssef's real financial-tracker-data.json.
Covers: the loader (old and v2 files, loud failures), account names, net worth, account settings.
The old-format outputs are compared BYTE FOR BYTE with what the tools produced before v2 support existed.
Run from the repo root:  python -m agents.asset.test_asset_v2
"""
import ast, copy, inspect, json, os, random, re, sys, tempfile
sys.path.insert(0, os.path.abspath("."))

from agents.asset import asset_tools as T

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail and status == "FAIL" else ""))

_GOLDEN = json.loads(r"""{
 "V1": {
  "accounts": {
   "vault": 5000.0,
   "flex": 300.5,
   "funds": 2000.0,
   "cc": 70.0,
   "cc2": -12.5,
   "car_loan": 2500.0,
   "brex": 1640.0
  },
  "settings": {
   "carLoanInitial": 10000,
   "carLoanMonthlyTarget": 1500,
   "ccLimit": 5000,
   "ccTargetMin": 0,
   "ccTargetMax": 500,
   "cc2Limit": 7000,
   "cc2TargetMin": 0,
   "cc2TargetMax": 300,
   "flexFloor": 300,
   "carFundTarget": 1500,
   "carFundMinimum": 500,
   "creditScoreTarget": 750,
   "creditScoreTarget2": 740,
   "brexStartingBalance": 2000
  },
  "transactions": [],
  "paychecks": [],
  "fixedExpenses": [],
  "groceries": {},
  "creditScores": []
 },
 "nw": "NET WORTH SNAPSHOT:\n\n  ASSETS:\n    VAULT (Chase Checking): $5,000.00\n    FLEX (SoFi Checking): $300.50\n    FUNDS (SoFi Savings): $2,000.00\n    SAVOR (Capital One CC): $12.50 (credit in your favor)\n    BREX (loan to friend): $1,640.00\n  Total assets: $8,953.00\n\n  LIABILITIES:\n    FREEDOM (Chase CC): $70.00 (owed)\n    Car Loan: $2,500.00\n  Total liabilities: $2,570.00\n\n  NET WORTH: $6,383.00",
 "settings": "ACCOUNT SETTINGS & STATIC FACTS:\n\n  CAR LOAN:\n    Current balance: $2,500.00\n    Initial amount:  $10,000.00\n    Interest rate:   0% (no interest - confirmed fact)\n    Monthly target:  $1,500.00 (this is the SAME real target as 'CAR FUND TARGET' below \u2014 one target, tracked under two settings names, not two separate goals)\n\n  FREEDOM CARD (Chase):\n    Limit: $5,000.00\n    Target range: $0.00 - $500.00\n\n  SAVOR CARD (Capital One):\n    Limit: $7,000.00\n    Target range: $0.00 - $300.00\n\n  FLEX FLOOR: $300.00 (minimum balance to maintain)\n\n  CAR FUND TARGET: $1,500.00 (SAME target as the car loan's Monthly target above \u2014 do not treat as a second, separate goal)\n  CAR FUND MINIMUM: $500.00\n\n  CREDIT SCORE TARGETS: VantageScore 750, FICO 740\n\n  BREX (money lent to friend, counted as a normal asset):\n    Outstanding: $1,640.00 of $2,000.00 starting\n    Paid back so far: 18.0%"
}""")
AS_OF = "2026-11-24"

def acct(i, kind="bank", opening=0, name=None, role="none", closed=False, open_date="2025-01-01"):
    return {"id": i, "name": name or i.upper(), "kind": kind, "role": role, "openingCents": opening, "openingDate": open_date, "closed": closed}

def tx(i, a, d, cents, typ="transaction"):
    return {"id": i, "accountId": a, "date": d, "description": "d " + i, "amountCents": cents, "type": typ}

SETTINGS = {"ccLimit": 5000, "ccTargetMin": 0, "ccTargetMax": 500, "cc2Limit": 7000, "cc2TargetMin": 0, "cc2TargetMax": 300,
            "flexFloor": 300, "creditScoreTarget": 750, "creditScoreTarget2": 740, "brexStartingBalance": 2000}

def v2file(accounts, txns=None, settings=None, **extra):
    d = {"schemaVersion": 2, "accounts": accounts, "transactions": txns or [], "settings": dict(SETTINGS if settings is None else settings),
         "fixedExpenses": [], "groceries": {}, "creditScores": [], "paychecks": []}
    d.update(extra)
    return d

def tools_on(raw, as_of=AS_OF):
    """Run the two tools on a v2 file exactly as chat would, without touching any real file."""
    adapted = T._adapt(raw, as_of)
    T.load_data = lambda: adapted
    return T.get_net_worth(), T.get_account_settings(), adapted

BASE = v2file([
    acct("vault", opening=500000, name="VAULT", role="vault"), acct("flex", opening=30050, name="FLEX", role="flex"),
    acct("funds", "savings", opening=200000, name="FUNDS", role="funds"),
    acct("cc", "credit_card", opening=7000, name="FREEDOM (Chase)"), acct("cc2", "credit_card", opening=-1250, name="SAVOR (Capital One)"),
    acct("car_loan", "loan", opening=250000, name="Car Loan", closed=True), acct("brex", "receivable", opening=164000, name="BREX"),
    acct("amex", "credit_card", opening=4000, name="Amex Gold"), acct("chk2", "bank", opening=-2500, name="Old Checking"),
], [tx("p1", "car_loan", "2025-06-01", 250000)])

print("=== L1 STATIC ===")
src = open("agents/asset/asset_tools.py", encoding="utf-8").read()
tree = ast.parse(src)
check("asset_tools imports the shared v2 reader", "from shared import financial_v2" in src)
check("asset_tools has no bare except", not any(isinstance(n, ast.ExceptHandler) and n.type is None for n in ast.walk(tree)))
v2_src = inspect.getsource(T._account_settings_v2)
check("the v2 settings tool has no car fund / car loan setting lines (they do not exist in v2)", not any(k in v2_src for k in ("carFund", "carLoanInitial", "carLoanMonthlyTarget")))
check("both tools branch on a v2 file", 'if "accounts_meta" in data:' in inspect.getsource(T.get_net_worth) and 'if "accounts_meta" in data:' in inspect.getsource(T.get_account_settings))
check("the old fixed names list is still there for old files", T.ACCOUNT_NAMES["vault"] == "VAULT (Chase Checking)" and "car_loan" in T.ACCOUNT_NAMES)
check("the only readers of the data file are _read_raw and nothing else opens it", src.count("open(FINANCIAL_DATA_PATH") == 2)

print("\n=== OLD FILES ARE UNCHANGED ===")
T.load_data = lambda: copy.deepcopy(_GOLDEN["V1"])
check("old-format net worth output is identical to before v2 support", T.get_net_worth() == _GOLDEN["nw"], T.get_net_worth()[:200])
check("old-format account settings output is identical to before v2 support", T.get_account_settings() == _GOLDEN["settings"])
check("an old-format file is returned by _adapt exactly as it is", T._adapt(_GOLDEN["V1"]) is _GOLDEN["V1"])

print("\n=== L2 V2 NET WORTH ===")
nw, st, adapted = tools_on(BASE)
check("v2 file: the loader result carries accounts_meta and dollars", "accounts_meta" in adapted and adapted["accounts"]["vault"] == 5000.0)
check("total assets = 5000 + 300.50 + 2000 + 12.50 credit + 1640 = 8,953.00", "Total assets: $8,953.00" in nw, nw)
check("total liabilities = 70 + 40 + 25 overdraft = 135.00", "Total liabilities: $135.00" in nw, nw)
check("net worth = 8,818.00 and matches the reader's own number", "NET WORTH: $8,818.00" in nw and adapted["net_worth"] == 8818.0)
check("default accounts show where they live: VAULT (Chase Checking), FLEX (SoFi Checking), FUNDS (SoFi Savings), BREX (loan to friend)",
      all(x in nw for x in ("VAULT (Chase Checking): $5,000.00", "FLEX (SoFi Checking): $300.50", "FUNDS (SoFi Savings): $2,000.00", "BREX (loan to friend): $1,640.00")), nw)
check("names that already have brackets are not doubled", "FREEDOM (Chase): $70.00 (owed)" in nw and "(Chase CC)" not in nw and "SAVOR (Capital One): $12.50 (credit in your favor)" in nw, nw)
check("an added card uses its own name; an overdraft is a liability", "Amex Gold: $40.00 (owed)" in nw and "Old Checking: $25.00 (overdraft)" in nw)
check("the closed, paid-off car loan is not listed", "Car Loan" not in nw)
renamed = copy.deepcopy(BASE); renamed["accounts"][0]["name"] = "Main"
check("a renamed account shows its new name plus where it lives", "Main (Chase Checking): $5,000.00" in tools_on(renamed)[0])
open_loan_nw = copy.deepcopy(BASE); open_loan_nw["accounts"][5]["closed"] = False; open_loan_nw["transactions"] = []
nw2 = tools_on(open_loan_nw)[0]
check("an open car loan with $2,500 still owed is a liability", "Car Loan: $2,500.00 (owed)" in nw2 and "Total liabilities: $2,635.00" in nw2 and "NET WORTH: $6,318.00" in nw2, nw2)
bad_closed = copy.deepcopy(BASE); bad_closed["transactions"] = []
nw3 = tools_on(bad_closed)[0]
check("a closed account that is NOT at zero is shown, never hidden", "Car Loan (closed account): $2,500.00 (owed)" in nw3, nw3)
check("net worth matches the reader with that account too", "NET WORTH: $6,318.00" in nw3, nw3)

print("\n=== L2 V2 ACCOUNT SETTINGS ===")
check("lists every account with its kind", "ACCOUNTS ON FILE:" in st and "VAULT (Chase Checking) - bank account" in st and "Car Loan - loan - CLOSED" in st and "BREX (loan to friend) - money owed to you" in st, st)
check("paid-off loan says so", "CAR LOAN: PAID OFF (account closed)" in st)
check("cards show balance owed, limit and target range", "FREEDOM (CHASE):" in st and "Balance owed: $70.00" in st and "Limit: $5,000.00" in st and "Target range: $0.00 - $500.00" in st, st)
check("second card too", "SAVOR (CAPITAL ONE):" in st and "Limit: $7,000.00" in st and "Target range: $0.00 - $300.00" in st)
check("an added card shows only its balance (no invented limit)", "AMEX GOLD:\n    Balance owed: $40.00" in st and st.count("Limit:") == 2, st)
check("flex floor and credit score targets", "FLEX FLOOR: $300.00" in st and "VantageScore 750, FICO 740" in st)
check("BREX paid-back percentage uses the starting balance", "Outstanding: $1,640.00 of $2,000.00 starting" in st and "Paid back so far: 18.0%" in st)
check("no car fund or car loan target lines in v2", not any(k in st for k in ("CAR FUND", "Initial amount", "Monthly target", "SAME")))
open_loan = copy.deepcopy(BASE); open_loan["accounts"][5]["closed"] = False; open_loan["transactions"] = []
st2 = tools_on(open_loan)[1]
check("an open car loan shows what is still owed and the 0% interest fact", "CAR LOAN:" in st2 and "Still owed: $2,500.00" in st2 and "Interest rate:   0% (no interest - confirmed fact)" in st2, st2)
st_closed_nonzero = tools_on(bad_closed)[1]
check("a closed loan that still owes money is NOT called paid off in the settings tool", "PAID OFF" not in st_closed_nonzero and "Still owed: $2,500.00" in st_closed_nonzero, st_closed_nonzero)
other_loan = copy.deepcopy(BASE); other_loan["accounts"].append(acct("mortgage", "loan", opening=9000000, name="House Loan"))
st_other = tools_on(other_loan)[1]
check("another loan shows what is owed but never the car loan's 0% interest fact", "HOUSE LOAN:" in st_other and "Still owed: $90,000.00" in st_other and st_other.count("Interest rate") == 0, st_other)
fake_brex = copy.deepcopy(BASE); fake_brex["accounts"][6]["kind"] = "bank"
check("BREX details only appear for a money-owed-to-you account", "BREX (money lent" not in tools_on(fake_brex)[1])
junk_settings = v2file(copy.deepcopy(BASE["accounts"]), settings={"ccLimit": "5000", "ccTargetMin": None, "ccTargetMax": [1], "cc2Limit": float("inf"), "flexFloor": True, "creditScoreTarget": {}, "brexStartingBalance": "x"})
st3 = tools_on(junk_settings)[1]
check("junk setting values count as 0 and never crash", "Limit: $0.00" in st3 and "FLEX FLOOR: $0.00" in st3 and "BREX (money lent" not in st3, st3)
no_settings = v2file(copy.deepcopy(BASE["accounts"])); del no_settings["settings"]
check("a file with no settings section still works", "FLEX FLOOR: $0.00" in tools_on(no_settings)[1])

print("\n=== L2 DATA NOTES (skipped entries are said out loud) ===")
odd = v2file([acct("v", opening=100), {"name": "no id"}, acct("v", opening=5)], [tx("1", "v", "bad-date", 5)])
nwn, stn, _ = tools_on(odd)
check("net worth says what was skipped", "DATA NOTES" in nwn and "skipped" in nwn, nwn)
check("account settings says it too", "DATA NOTES" in stn)
check("a clean file has no notes", "DATA NOTES" not in nw and "DATA NOTES" not in st)

print("\n=== L2 LOADER (real temp files) ===")
def with_file(obj_or_text):
    fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(obj_or_text if isinstance(obj_or_text, str) else json.dumps(obj_or_text))
    return path
import importlib
importlib.reload(T)   # a fresh module so load_data is the real one again
original_path = T.FINANCIAL_DATA_PATH
p2 = with_file(BASE)
T.FINANCIAL_DATA_PATH = p2
d2 = T.load_data()
check("load_data on a v2 file gives the tools' shape (dollars + accounts_meta)", d2["schemaVersion"] == 2 and d2["accounts"]["vault"] == 5000.0 and len(d2["accounts_meta"]) == 9)
check("the real tools read that file end to end", "NET WORTH: $8,818.00" in T.get_net_worth() and "ACCOUNTS ON FILE" in T.get_account_settings())
p1 = with_file(_GOLDEN["V1"])
T.FINANCIAL_DATA_PATH = p1
check("load_data on an old file returns it unchanged and the old output comes out", "accounts_meta" not in T.load_data() and T.get_net_worth() == _GOLDEN["nw"])
v1_marked = copy.deepcopy(_GOLDEN["V1"]); v1_marked["schemaVersion"] = 1
T.FINANCIAL_DATA_PATH = with_file(v1_marked)
check("an old file that says schemaVersion 1 is still read as old", "accounts_meta" not in T.load_data())
def raises(path, needle):
    T.FINANCIAL_DATA_PATH = path
    try:
        T.load_data()
    except RuntimeError as e:
        return needle in str(e)
    except Exception:
        return False
    return False
check("a newer format version fails loudly, not misread", raises(with_file({"schemaVersion": 3, "accounts": []}), "newer than ASSET understands"))
check("version 2 with a broken accounts list fails loudly", raises(with_file({"schemaVersion": 2, "accounts": {"vault": 5}}), "missing or broken"))
check("a missing file still gives the same clear error", raises(os.path.join(tempfile.gettempdir(), "no-such-asset-file.json"), "not found"))
check("a malformed file still gives the same clear error", raises(with_file("{not json"), "malformed JSON"))
T.FINANCIAL_DATA_PATH = original_path

print("\n=== account_label ===")
check("old-style lookup for unknown ids and non-text ids never crashes", T.account_label({}, "vault") == "VAULT (Chase Checking)" and T.account_label({}, "zzz") == "zzz" and T.account_label({}, None) == "None" and T.account_label({}, ["x"]) == "['x']")

print("\n=== L4 SUSTAINED ===")
def random_v2(rng):
    kinds = ["bank", "savings", "credit_card", "loan", "receivable"]
    accts = [acct(f"a{i}", rng.choice(kinds), rng.randint(-300000, 4000000), name=f"Acct {i}", closed=rng.random() < 0.15) for i in range(rng.randint(1, 9))]
    txns = [tx(f"t{j}", rng.choice(accts)["id"], f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}", rng.randint(-900000, 900000)) for j in range(rng.randint(0, 40))]
    return v2file(accts, txns)
rng = random.Random(20261124)
ok = True; why = ""
for i in range(300):
    raw = random_v2(rng)
    try:
        nw_i, st_i, ad = tools_on(raw)
        m = re.search(r"NET WORTH: \$(-?[\d,]+\.\d\d)", nw_i)
        a = re.search(r"Total assets: \$(-?[\d,]+\.\d\d)", nw_i); l = re.search(r"Total liabilities: \$(-?[\d,]+\.\d\d)", nw_i)
        if not (m and a and l):
            ok = False; why = f"case {i}: could not find the totals in the text"; break
        printed = float(m.group(1).replace(",", ""))
        if abs(printed - ad["net_worth"]) > 0.005:
            ok = False; why = f"case {i}: printed {printed} vs reader {ad['net_worth']}"; break
        if abs(float(a.group(1).replace(",", "")) - float(l.group(1).replace(",", "")) - printed) > 0.011:
            ok = False; why = f"case {i}: assets - liabilities != net worth"; break
    except Exception as e:
        ok = False; why = f"case {i}: {e!r}"; break
check("300 random v2 files: the printed net worth always equals the reader's own number, and assets - liabilities = net worth", ok, why)
big = v2file([acct(f"a{i}", "bank", i * 100, name=f"A{i}") for i in range(500)], [tx(f"t{i}", f"a{i % 500}", "2025-03-03", 1) for i in range(20000)])
import time
t0 = time.time(); tools_on(big)
check("500 accounts and 20,000 entries are read quickly", time.time() - t0 < 5, f"{time.time() - t0:.1f}s")
check("the same file gives the same text twice", tools_on(BASE)[0] == tools_on(BASE)[0] and tools_on(BASE)[1] == tools_on(BASE)[1])

print("\n=== L5 EXTREME ===")
rng = random.Random(4242)
vals = [None, [], {}, "x", 5, -1, 1e999, True, "2026-01-01", 2**70]
crashed = ""
for i in range(1500):
    raw = random_v2(rng)
    for _ in range(rng.randint(0, 4)):
        k = rng.choice(["acct", "tx", "settings"])
        if k == "acct" and raw["accounts"]:
            rng.choice(raw["accounts"])[rng.choice(["id", "kind", "openingCents", "openingDate", "name", "closed", "role"])] = rng.choice(vals)
        elif k == "tx" and raw["transactions"]:
            rng.choice(raw["transactions"])[rng.choice(["accountId", "date", "amountCents", "type"])] = rng.choice(vals)
        else:
            raw["settings"][rng.choice(list(SETTINGS))] = rng.choice(vals)
    try:
        tools_on(raw)
    except Exception as e:
        crashed = f"case {i}: {e!r}"; break
check("1,500 randomly damaged v2 files never crash either tool", crashed == "", crashed)
weird_names = v2file([acct("v", opening=100, name="x" * 5000), acct("w", opening=5, name="\u0000\n\t emoji"), acct("c", "credit_card", opening=10**15, name="Big")])
nwx, stx, _ = tools_on(weird_names)
check("huge numbers and strange names are handled", "NET WORTH" in nwx and len(nwx) < 3000, str(len(nwx)))
_before = copy.deepcopy(BASE)
tools_on(BASE)
check("the input file data is never changed by the tools", BASE == _before)

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")
sys.exit(0 if failed == 0 else 1)