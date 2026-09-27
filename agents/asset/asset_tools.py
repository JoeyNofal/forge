# ============================================================
# ASSET TOOLS — Financial Analysis Engine
# Reads and analyzes Joey's real financial data
# Read-only — never modifies the data file
#
# Rebuilt from reference/asset_tools.py with real fixes:
# - FINANCIAL_DATA_PATH is now an env var (was hardcoded to a specific
#   drive/path), same convention as everywhere else in FORGE
# - load_data() now RAISES a clear, specific error instead of silently
#   returning None (Lesson #12 — fail loudly). It also tells apart a
#   genuinely missing file from the real Financial Tracker app being
#   mid-write the instant we happen to read it (one quick retry) from
#   an actual malformed-JSON problem — the old code treated all three
#   identically as a generic "Could not load financial data."
# - Every tool function below now just calls load_data() and trusts it
#   (no more "if not data: return ..." repeated 9 times) — a real
#   failure propagates up to chat.py, which decides how to present it,
#   rather than being swallowed silently inside each tool.
# - get_net_worth() is fixed (Decisions, this session):
#     * cc/cc2 sign is flipped: a POSITIVE balance is money owed
#       (liability), a NEGATIVE balance is credit in your favor (asset)
#       — the old code silently skipped these entirely either way
#     * car_loan is always a liability regardless of the sign stored
#     * BREX counts as a normal asset like any other account (the old
#       code's OWN COMMENT claimed it was excluded from net worth, but
#       the actual loop never excluded it — the comment was wrong, not
#       the math; confirmed with Youssef and keeping BREX counted)
#     * an overdraft (negative balance) on an ordinary account now
#       correctly counts as a liability instead of being silently
#       dropped, same bug shape as the cc/cc2 one
# - search_financial_news() removed entirely — ASSET now uses
#   shared/web_search.py (the same tested SerpApi wrapper CIPHER/NEXUS
#   use) instead of its own separate, untested duplicate (Lesson #9)
# ============================================================

import json
import os
from datetime import datetime, date, timedelta
from collections import defaultdict

# D:\Projects\Financial Tracker\FinancialTracker\financial-tracker-data.json
# on Youssef's machine — the real file the actual Financial Tracker app
# writes to. FORGE only ever reads it.
FINANCIAL_DATA_PATH = os.getenv(
    "FINANCIAL_DATA_PATH",
    r"D:\Projects\Financial Tracker\FinancialTracker\financial-tracker-data.json",
)

ACCOUNT_NAMES = {
    "vault":    "VAULT (Chase Checking)",
    "flex":     "FLEX (SoFi Checking)",
    "funds":    "FUNDS (SoFi Savings)",
    "cc":       "FREEDOM (Chase CC)",
    "cc2":      "SAVOR (Capital One CC)",
    "car_loan": "Car Loan",
    "brex":     "BREX (loan to friend)",
}

CREDIT_CARD_ACCOUNTS = {"cc", "cc2"}
LOAN_ACCOUNTS = {"car_loan"}


# ============================================================
# LOAD DATA
# ============================================================

def load_data() -> dict:
    """
    Loads the real financial data file. Raises a clear, specific error
    on a genuine problem (Lesson #12) rather than returning None the
    way the old code did, which hid whether the real cause was a
    missing file, a real bug, or the Financial Tracker app simply
    mid-write the instant we happened to read it.
    """
    try:
        with open(FINANCIAL_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise RuntimeError(
            f"Financial data file not found at {FINANCIAL_DATA_PATH}. "
            "Check the FINANCIAL_DATA_PATH environment variable, or "
            "confirm the Financial Tracker app has been run at least once."
        )
    except json.JSONDecodeError:
        # Most likely the Financial Tracker app was mid-write the
        # instant we read it, not real corruption - one quick retry is
        # worth it before treating this as a genuine problem.
        import time
        time.sleep(0.2)
        try:
            with open(FINANCIAL_DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Financial data file is malformed JSON at {FINANCIAL_DATA_PATH} "
                f"(tried twice, 0.2s apart, still failed): {e}"
            )


# ============================================================
# TOOL 0 — ACCOUNT SETTINGS & STATIC FACTS
# ============================================================

def get_account_settings() -> str:
    """
    Returns static financial facts and targets that rarely change —
    loan terms, card limits/targets, fund targets, BREX status. This is
    context ASSET should already know, not something to ask Joey for.
    """
    data = load_data()
    settings = data.get("settings", {})
    accounts = data.get("accounts", {})

    lines = ["ACCOUNT SETTINGS & STATIC FACTS:\n"]

    car_loan_balance = accounts.get("car_loan", 0)
    lines.append(f"  CAR LOAN:")
    lines.append(f"    Current balance: ${car_loan_balance:,.2f}")
    lines.append(f"    Initial amount:  ${settings.get('carLoanInitial', 0):,.2f}")
    lines.append(f"    Interest rate:   0% (no interest - confirmed fact)")
    lines.append(f"    Monthly target:  ${settings.get('carLoanMonthlyTarget', 0):,.2f}")

    lines.append(f"\n  FREEDOM CARD (Chase):")
    lines.append(f"    Limit: ${settings.get('ccLimit', 0):,.2f}")
    lines.append(f"    Target range: ${settings.get('ccTargetMin', 0):,.2f} - ${settings.get('ccTargetMax', 0):,.2f}")

    lines.append(f"\n  SAVOR CARD (Capital One):")
    lines.append(f"    Limit: ${settings.get('cc2Limit', 0):,.2f}")
    lines.append(f"    Target range: ${settings.get('cc2TargetMin', 0):,.2f} - ${settings.get('cc2TargetMax', 0):,.2f}")

    lines.append(f"\n  FLEX FLOOR: ${settings.get('flexFloor', 0):,.2f} (minimum balance to maintain)")

    lines.append(f"\n  CAR FUND TARGET: ${settings.get('carFundTarget', 0):,.2f}")
    lines.append(f"  CAR FUND MINIMUM: ${settings.get('carFundMinimum', 0):,.2f}")

    lines.append(f"\n  CREDIT SCORE TARGETS: VantageScore {settings.get('creditScoreTarget', 0)}, FICO {settings.get('creditScoreTarget2', 0)}")

    # BREX — loan to a friend, IS counted in net worth (Decision,
    # confirmed with Youssef — the old comment here was simply wrong)
    brex_balance = accounts.get("brex", 0)
    brex_starting = settings.get("brexStartingBalance", 0)
    if brex_starting > 0:
        pct_paid = ((brex_starting - brex_balance) / brex_starting * 100) if brex_starting > 0 else 0
        lines.append(f"\n  BREX (money lent to friend, counted as a normal asset):")
        lines.append(f"    Outstanding: ${brex_balance:,.2f} of ${brex_starting:,.2f} starting")
        lines.append(f"    Paid back so far: {pct_paid:.1f}%")

    return "\n".join(lines)


# ============================================================
# TOOL 1 — SPENDING SUMMARY
# ============================================================

def get_spending_summary(months_back: int = 1) -> str:
    """
    Returns a plain-English spending summary for the last N months.
    Only counts outgoing money (negative amounts) that are real
    transactions, not transfers between Joey's own accounts.
    """
    data = load_data()
    transactions = data.get("transactions", [])
    cutoff = date.today() - timedelta(days=30 * months_back)

    spending_by_account = defaultdict(float)
    transaction_count = defaultdict(int)

    for t in transactions:
        if t.get("type") == "transfer":
            continue

        raw_date = t.get("date", "")
        try:
            if "T" in raw_date:
                t_date = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date()
            else:
                t_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue

        if t_date < cutoff:
            continue

        amount = t.get("amount", 0)
        account_id = t.get("accountId", "unknown")

        if amount < 0:
            spending_by_account[account_id] += abs(amount)
            transaction_count[account_id] += 1

    if not spending_by_account:
        return f"No spending transactions found in the last {months_back} month(s)."

    period = "last month" if months_back == 1 else f"last {months_back} months"
    lines = [f"SPENDING SUMMARY — {period.upper()}:\n"]

    total = 0
    for account_id, amount in sorted(spending_by_account.items()):
        name = ACCOUNT_NAMES.get(account_id, account_id)
        count = transaction_count[account_id]
        lines.append(f"  {name}: ${amount:,.2f} ({count} transactions)")
        total += amount

    lines.append(f"\n  TOTAL SPENT: ${total:,.2f}")
    return "\n".join(lines)


# ============================================================
# TOOL 2 — INCOME SUMMARY
# ============================================================

def get_income_summary(paychecks_back: int = 8) -> str:
    """Returns a summary of recent paychecks including averages and totals."""
    data = load_data()
    paychecks = data.get("paychecks", [])
    if not paychecks:
        return "No paycheck data found."

    recent = paychecks[-paychecks_back:]

    total_gross = sum(p.get("grossPay", 0) for p in recent)
    total_net = sum(p.get("netPay", 0) for p in recent)
    total_taxes = sum(sum(p.get("taxes", {}).values()) for p in recent)
    total_deductions = sum(sum(p.get("deductions", {}).values()) for p in recent)

    avg_net = total_net / len(recent)
    avg_gross = total_gross / len(recent)

    latest = recent[-1]

    lines = [
        f"INCOME SUMMARY - LAST {len(recent)} PAYCHECKS:\n",
        f"  Latest paycheck date: {latest.get('date', 'N/A')}",
        f"  Latest net pay:       ${latest.get('netPay', 0):,.2f}",
        f"  Latest gross pay:     ${latest.get('grossPay', 0):,.2f}",
        f"\n  Average net pay:      ${avg_net:,.2f}/paycheck",
        f"  Average gross pay:    ${avg_gross:,.2f}/paycheck",
        f"\n  Total gross earned:   ${total_gross:,.2f}",
        f"  Total net received:   ${total_net:,.2f}",
        f"  Total taxes paid:     ${total_taxes:,.2f}",
        f"  Total deductions:     ${total_deductions:,.2f}",
    ]
    if total_gross > 0:
        lines.append(f"\n  Effective take-home:  {(total_net/total_gross*100):.1f}% of gross")

    return "\n".join(lines)


# ============================================================
# TOOL 3 — NET WORTH SNAPSHOT (FIXED - Decisions, this session)
# ============================================================

def get_net_worth() -> str:
    """
    Calculates Joey's current net worth.
    - Ordinary accounts (vault, flex, funds, brex, ...): positive = asset,
      negative = a real liability (overdraft) — previously silently dropped.
    - Credit cards (cc, cc2): SIGN IS FLIPPED — positive = money owed
      (liability), negative = credit in your favor (asset). The old
      code skipped these entirely regardless of sign.
    - car_loan: always a liability, sign-agnostic (abs()).
    - BREX counts as a normal asset (Decision, confirmed with Youssef).
    """
    data = load_data()
    accounts = data.get("accounts", {})

    assets = 0.0
    liabilities = 0.0
    asset_lines = []
    liability_lines = []

    for account_id, balance in accounts.items():
        name = ACCOUNT_NAMES.get(account_id, account_id)

        if account_id in LOAN_ACCOUNTS:
            amount = abs(balance)
            liabilities += amount
            liability_lines.append(f"    {name}: ${amount:,.2f}")
        elif account_id in CREDIT_CARD_ACCOUNTS:
            if balance > 0:
                liabilities += balance
                liability_lines.append(f"    {name}: ${balance:,.2f} (owed)")
            elif balance < 0:
                amount = abs(balance)
                assets += amount
                asset_lines.append(f"    {name}: ${amount:,.2f} (credit in your favor)")
        else:
            if balance > 0:
                assets += balance
                asset_lines.append(f"    {name}: ${balance:,.2f}")
            elif balance < 0:
                amount = abs(balance)
                liabilities += amount
                liability_lines.append(f"    {name}: ${amount:,.2f} (overdraft)")

    lines = ["NET WORTH SNAPSHOT:\n", "  ASSETS:"]
    lines.extend(asset_lines)
    lines.append(f"  Total assets: ${assets:,.2f}")
    lines.append(f"\n  LIABILITIES:")
    lines.extend(liability_lines)
    lines.append(f"  Total liabilities: ${liabilities:,.2f}")

    net_worth = assets - liabilities
    lines.append(f"\n  NET WORTH: ${net_worth:,.2f}")

    return "\n".join(lines)


# ============================================================
# TOOL 4 — SAVINGS RATE
# ============================================================

def get_savings_rate(paychecks_back: int = 8) -> str:
    """Calculates Joey's savings rate based on recent paychecks and estimated monthly spending."""
    data = load_data()
    paychecks = data.get("paychecks", [])
    fixed_expenses = data.get("fixedExpenses", [])
    groceries = data.get("groceries", {})

    if not paychecks:
        return "No paycheck data found."

    recent = paychecks[-paychecks_back:]
    total_net = sum(p.get("netPay", 0) for p in recent)
    avg_monthly_net = (total_net / len(recent)) * 4.33

    monthly_fixed = 0
    for exp in fixed_expenses:
        if exp.get("frequency") == "monthly":
            monthly_fixed += exp.get("amount", 0)
        elif exp.get("frequency") == "weekly":
            monthly_fixed += exp.get("amount", 0) * 4.33

    grocery_months = sorted(groceries.keys())[-3:]
    avg_groceries = sum(groceries[m] for m in grocery_months) / len(grocery_months) if grocery_months else 0

    total_estimated_expenses = monthly_fixed + avg_groceries
    estimated_savings = avg_monthly_net - total_estimated_expenses
    savings_rate = (estimated_savings / avg_monthly_net * 100) if avg_monthly_net > 0 else 0

    lines = [
        "SAVINGS RATE ANALYSIS:\n",
        f"  Avg monthly take-home:     ${avg_monthly_net:,.2f}",
        f"  Estimated monthly expenses: ${total_estimated_expenses:,.2f}",
        f"    Fixed bills:   ${monthly_fixed:,.2f}",
        f"    Groceries:     ${avg_groceries:,.2f}",
        f"  Estimated monthly savings:  ${estimated_savings:,.2f}",
        f"  Savings rate:               {savings_rate:.1f}%",
    ]

    if savings_rate >= 20:
        lines.append("\n  Status: Excellent - above the recommended 20% savings rate.")
    elif savings_rate >= 10:
        lines.append("\n  Status: Good — above 10%. Room to grow toward 20%.")
    elif savings_rate > 0:
        lines.append("\n  Status: Low — below 10%. Worth reviewing expenses.")
    else:
        lines.append("\n  Status: Spending exceeds income estimate. Review needed.")

    return "\n".join(lines)


# ============================================================
# TOOL 5 — CREDIT SCORE HISTORY
# ============================================================

def get_credit_score_history() -> str:
    """Returns credit score history sorted by date."""
    data = load_data()
    scores = data.get("creditScores", [])
    if not scores:
        return "No credit score history recorded."

    sorted_scores = sorted(scores, key=lambda x: x.get("date", ""))
    recent = sorted_scores[-10:]

    lines = ["CREDIT SCORE HISTORY (last 10 entries):\n"]
    for s in recent:
        lines.append(f"  {s.get('date', '?')}  {str(s.get('score', '?')):>4}  {s.get('source', '')}")

    first = sorted_scores[0]
    latest = sorted_scores[-1]
    change = latest.get("score", 0) - first.get("score", 0)
    direction = "▲" if change > 0 else "▼" if change < 0 else "—"

    lines.append(f"\n  Overall change: {direction} {abs(change)} points")
    lines.append(f"  ({first.get('score')} on {first.get('date')} → {latest.get('score')} on {latest.get('date')})")

    return "\n".join(lines)


# ============================================================
# TOOL 6 — RECENT TRANSACTIONS
# ============================================================

def get_recent_transactions(account_id: str | None = None, limit: int = 10) -> str:
    """Returns the most recent transactions, optionally filtered by account."""
    data = load_data()
    transactions = data.get("transactions", [])

    if account_id:
        transactions = [t for t in transactions if t.get("accountId") == account_id]

    def parse_date(t):
        raw = t.get("date", "")
        try:
            if "T" in raw:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
            else:
                return datetime.strptime(raw, "%Y-%m-%d")
        except (ValueError, TypeError):
            return datetime.min

    sorted_txns = sorted(transactions, key=parse_date, reverse=True)[:limit]

    account_label = ACCOUNT_NAMES.get(account_id, "ALL ACCOUNTS") if account_id else "ALL ACCOUNTS"
    lines = [f"RECENT TRANSACTIONS — {account_label}:\n"]

    for t in sorted_txns:
        raw_date = t.get("date", "")
        try:
            if "T" in raw_date:
                d = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).strftime("%Y-%m-%d")
            else:
                d = raw_date
        except (ValueError, TypeError):
            d = raw_date

        amount = t.get("amount", 0)
        sign = "+" if amount >= 0 else ""
        desc = t.get("description", "No description")
        acct = ACCOUNT_NAMES.get(t.get("accountId", ""), t.get("accountId", ""))
        txn_type = t.get("type", "")
        label = " [transfer]" if txn_type == "transfer" else ""

        lines.append(f"  {d}  {sign}{amount:,.2f}  {desc}  ({acct}){label}")

    return "\n".join(lines)


# ============================================================
# TOOL 7 — GROCERY SPENDING HISTORY
# ============================================================

def get_grocery_history() -> str:
    """Returns monthly grocery spending history."""
    data = load_data()
    groceries = data.get("groceries", {})
    if not groceries:
        return "No grocery data recorded."

    sorted_months = sorted(groceries.keys())
    lines = ["MONTHLY GROCERY SPENDING:\n"]

    total = 0
    for month in sorted_months:
        amount = groceries[month]
        lines.append(f"  {month}:  ${amount:,.2f}")
        total += amount

    avg = total / len(sorted_months)
    lines.append(f"\n  Average: ${avg:,.2f}/month")
    lines.append(f"  Total tracked: ${total:,.2f}")

    return "\n".join(lines)


# ============================================================
# TOOL 8 — EMERGENCY FUND STATUS
# ============================================================

def get_emergency_fund_status() -> str:
    """Calculates how close Joey is to having a 3-month emergency fund."""
    data = load_data()
    accounts = data.get("accounts", {})
    fixed_expenses = data.get("fixedExpenses", [])
    groceries = data.get("groceries", {})

    monthly_fixed = 0
    for exp in fixed_expenses:
        if exp.get("frequency") == "monthly":
            monthly_fixed += exp.get("amount", 0)
        elif exp.get("frequency") == "weekly":
            monthly_fixed += exp.get("amount", 0) * 4.33

    grocery_months = sorted(groceries.keys())[-3:]
    avg_groceries = sum(groceries[m] for m in grocery_months) / len(grocery_months) if grocery_months else 0

    monthly_expenses = monthly_fixed + avg_groceries
    target_3mo = monthly_expenses * 3
    target_6mo = monthly_expenses * 6

    savings_fund = data.get("fundsSubAccounts", {}).get("savingsFund", 0)

    pct_3mo = (savings_fund / target_3mo * 100) if target_3mo > 0 else 0
    shortfall_3mo = max(0, target_3mo - savings_fund)

    lines = [
        "EMERGENCY FUND STATUS:\n",
        f"  Estimated monthly expenses: ${monthly_expenses:,.2f}",
        f"  3-month target:             ${target_3mo:,.2f}",
        f"  6-month target:             ${target_6mo:,.2f}",
        f"\n  Savings Fund balance:       ${savings_fund:,.2f}",
        f"  Progress to 3-month goal:   {pct_3mo:.1f}%",
    ]

    if shortfall_3mo > 0:
        lines.append(f"  Still needed:               ${shortfall_3mo:,.2f}")
    else:
        lines.append(f"  Status: 3-month goal REACHED!")

    return "\n".join(lines)