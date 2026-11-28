"""
ASSET v2 - L3 (real end-to-end): the real ASSET tools and (unless --no-model) your real local Ollama model
reading a Financial Tracker v2 file. By default it reads the THROWAWAY copy
D:\\Projects\\Forge\\data\\ft-handson\\converted-v2.json  - never your live financial-tracker-data.json.
Memory uses a throwaway temp folder. Real figures appear in your own terminal only; nothing is sent anywhere.

PART 1 (no model): every tool's text is printed and checked against the tracker's own ledger.js, to the cent.
PART 2 (real model): six real questions; the answers are printed so they can be READ for wrong or invented numbers.

Run from the repo root:
    python -m agents.asset.test_asset_v2_l3
    python -m agents.asset.test_asset_v2_l3 "D:\\some\\other\\copy.json"
    python -m agents.asset.test_asset_v2_l3 --no-model        (part 1 only)
"""
import json, os, re, shutil, subprocess, sys, tempfile
from datetime import date, timedelta
sys.path.insert(0, os.path.abspath("."))

os.environ["ASSET_MEMORY_PATH"] = tempfile.mkdtemp(prefix="asset_memory_v2_l3_")

args = [a for a in sys.argv[1:] if not a.startswith("--")]
NO_MODEL = "--no-model" in sys.argv
PATH = args[0] if args else r"D:\Projects\Forge\data\ft-handson\converted-v2.json"

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail and status == "FAIL" else ""))

if not os.path.exists(PATH):
    print(f"[FAIL] the copy to read was not found: {PATH}")
    print("Make it first (see the instructions), or pass the path of another converted v2 copy.")
    sys.exit(1)

from agents.asset import asset_tools as T
T.FINANCIAL_DATA_PATH = PATH
TODAY = date.today()

print("=" * 70)
print(f"FILE: {PATH}")
print(f"TODAY: {TODAY.isoformat()}")
print("=" * 70)

raw = json.load(open(PATH, encoding="utf-8"))
check("the file is a version 2 file", raw.get("schemaVersion") == 2)
data = T.load_data()
check("ASSET loads it in the tools' shape", "accounts_meta" in data and len(data["accounts_meta"]) > 0)
print("\nACCOUNTS ASSET SEES:")
for m in data["accounts_meta"]:
    print(f"  {m['id']:<10} {m['kind']:<12} role={m['role']:<6} {'CLOSED ' if m['closed'] else '       '} balance ${m['balance']:,.2f}   name: {m['name']}")
print(f"  net worth (reader): ${data['net_worth']:,.2f}")

print("\n=== PART 1a: BALANCES AND NET WORTH AGREE WITH THE TRACKER'S OWN ledger.js ===")
ledger = os.path.join("apps", "financial-tracker", "ledger.js")
node = shutil.which("node") or ""
js_ok = bool(node) and os.path.exists(ledger)
check("Node.js and the tracker's ledger.js are available for the cross-check", js_ok)
if js_ok:
    script = ("const fs=require('fs');const L=require(process.argv[1]);const d=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));"
              "console.log(JSON.stringify({b:L.allBalances(d,process.argv[3]),n:L.netWorthCents(d,process.argv[3])}));")
    p = subprocess.run([node, "-e", script, os.path.abspath(ledger), PATH, TODAY.isoformat()], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        check("ledger.js ran", False, p.stderr[:300])
    else:
        js = json.loads(p.stdout)
        bad = [(m["id"], round(m["balance"] * 100), js["b"].get(m["id"])) for m in data["accounts_meta"] if round(m["balance"] * 100) != js["b"].get(m["id"])]
        check("every account balance equals ledger.js, to the cent", not bad, str(bad))
        check("net worth equals ledger.js, to the cent", round(data["net_worth"] * 100) == js["n"], f"ASSET {data['net_worth']} vs ledger {js['n'] / 100}")

print("\n=== PART 1b: WHAT EACH TOOL SAYS ===")
def show(title, text):
    print(f"\n----- {title} -----\n{text}")
    return text
nw = show("get_net_worth", T.get_net_worth())
st = show("get_account_settings", T.get_account_settings())
sp = show("get_spending_summary(1)", T.get_spending_summary(1))
sp3 = show("get_spending_summary(3)", T.get_spending_summary(3))
rc = show("get_recent_transactions(limit 8)", T.get_recent_transactions(None, 8))
sr = show("get_savings_rate()", T.get_savings_rate())
ef = show("get_emergency_fund_status()", T.get_emergency_fund_status())
print("\n----- checks on those texts -----")
m = re.search(r"NET WORTH: \$(-?[\d,]+\.\d\d)", nw)
check("net worth text matches the reader's number", bool(m) and abs(float(m.group(1).replace(",", "")) - data["net_worth"]) < 0.006)
missing = [a["name"] for a in data["accounts_meta"] if not a["closed"] and a["balance"] != 0 and a["name"] not in nw]
check("every open account with a balance appears in the net worth text by its tracker name", not missing, str(missing))
missing2 = [a["name"] for a in data["accounts_meta"] if a["name"] not in st]
check("every account (even closed ones) is listed in the account settings text", not missing2, str(missing2))
check("no 'DATA NOTES' (nothing in the file had to be skipped)", "DATA NOTES" not in nw and "DATA NOTES" not in st, "the reader skipped something: see the notes above")
check("no old car loan / car fund target lines", "CAR FUND" not in st and "Initial amount" not in st)
funds = next((a for a in data["accounts_meta"] if a["role"] == "funds" and not a["closed"]), None)
check("the emergency fund uses the FUNDS account balance", funds is not None and f"${funds['balance']:,.2f}" in ef, "no open FUNDS account found" if funds is None else ef[:200])
# spending: independent count in cents from the raw file
NON = {"transfer", "correction", "migration_adjustment"}
cut = (TODAY - timedelta(days=30)).isoformat()
expect = sum(-t["amountCents"] for t in raw["transactions"] if isinstance(t, dict) and isinstance(t.get("amountCents"), int) and t["amountCents"] < 0
             and t.get("type", "transaction") not in NON and isinstance(t.get("date"), str) and cut <= t["date"] <= TODAY.isoformat())
mt = re.search(r"TOTAL SPENT: \$([\d,]+\.\d\d)", sp)
got = round(float(mt.group(1).replace(",", "")) * 100) if mt else 0
check("last month's spending equals an independent count from the raw file", got == expect, f"ASSET {got / 100:.2f} vs independent {expect / 100:.2f}")
check("recent transactions never show a future-dated entry", all(l.strip()[:10] <= TODAY.isoformat() for l in rc.split("\n")[1:] if l.strip()))

if NO_MODEL:
    print("\n(--no-model: part 2 skipped)")
else:
    print("\n=== PART 2: REAL MODEL (local Ollama) - read these answers ===")
    from dotenv import load_dotenv
    load_dotenv(override=True)
    from agents.asset import chat
    def ask(label, message):
        print(f"\n{'=' * 70}\n{label}\nMESSAGE: {message}\n{'-' * 70}")
        out = "".join(chat.stream_asset(message, history=None))
        print(out)
        print("-" * 70)
        return out
    o1 = ask("Q1 net worth", "What's my net worth right now?")
    check("Q1 answered, and quotes the real net worth figure", len(o1) > 0 and (f"{data['net_worth']:,.2f}" in o1 or f"{data['net_worth']:.2f}" in o1), f"expected ${data['net_worth']:,.2f} in the answer")
    o2 = ask("Q2 credit cards", "How much do I owe on my credit cards right now?")
    check("Q2 answered", len(o2) > 0)
    o3 = ask("Q3 spending", "How much did I spend last month, and where did most of it go?")
    check("Q3 answered", len(o3) > 0)
    o4 = ask("Q4 emergency fund", "How is my emergency fund doing?")
    check("Q4 answered", len(o4) > 0)
    o5 = ask("Q5 savings rate", "What's my savings rate?")
    check("Q5 answered", len(o5) > 0)
    o6 = ask("Q6 car loan", "Is my car loan paid off?")
    check("Q6 answered", len(o6) > 0)

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")
print("\nNOW READ THE TOOL TEXTS AND THE MODEL ANSWERS ABOVE: the numbers must match, nothing invented.")
sys.exit(0 if failed == 0 else 1)