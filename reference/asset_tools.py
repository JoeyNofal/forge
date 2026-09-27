# ============================================================
# ASSET TOOLS — Financial Analysis Engine
# Reads and analyzes Joey's real financial data
# Read-only — never modifies the data file
# ============================================================

import json
import os
import requests
import os
from dotenv import load_dotenv
load_dotenv(r"D:\Projects\NEXUS SYSTEM\.env", override=True)
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
from datetime import datetime, date, timedelta
from collections import defaultdict

# ── Path to the real financial data file ───────────────────
FINANCIAL_DATA_PATH = r"D:\Projects\Financial Tracker\FinancialTracker\financial-tracker-data.json"

# ── Account display names ───────────────────────────────────
ACCOUNT_NAMES = {
    "vault":    "VAULT (Chase Checking)",
    "flex":     "FLEX (SoFi Checking)",
    "funds":    "FUNDS (SoFi Savings)",
    "cc":       "FREEDOM (Chase CC)",
    "cc2":      "SAVOR (Capital One CC)",
    "car_loan": "Car Loan"
}


# ============================================================
# LOAD DATA
# ============================================================

def load_data():
    """Loads the financial data file. Returns None if it fails."""
    try:
        with open(FINANCIAL_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return None


# ============================================================
# TOOL 0 — ACCOUNT SETTINGS & STATIC FACTS
# Things that almost never change: loan terms, targets, BREX,
# card limits. ASSET should always have these, never guess or
# ask the user for something that's just sitting in the data.
# ============================================================

def get_account_settings():
    """
    Returns static financial facts and targets that rarely change —
    loan terms, card limits/targets, fund targets, BREX status.
    This is context ASSET should already know, not something to
    ask Joey for.
    """
    data = load_data()
    if not data:
        return "Could not load financial data."

    settings = data.get("settings", {})
    accounts = data.get("accounts", {})

    lines = ["ACCOUNT SETTINGS & STATIC FACTS:\n"]

    # Car loan — interest rate is a known fact, not stored in JSON,
    # hardcoded here because it's true and doesn't change.
    car_loan_balance = accounts.get("car_loan", 0)
    lines.append(f"  CAR LOAN:")
    lines.append(f"    Current balance: ${car_loan_balance:,.2f}")
    lines.append(f"    Initial amount:  ${settings.get('carLoanInitial', 0):,.2f}")
    lines.append(f"    Interest rate:   0% (no interest - confirmed fact)")
    lines.append(f"    Monthly target:  ${settings.get('carLoanMonthlyTarget', 0):,.2f}")

    # Credit cards
    lines.append(f"\n  FREEDOM CARD (Chase):")
    lines.append(f"    Limit: ${settings.get('ccLimit', 0):,.2f}")
    lines.append(f"    Target range: ${settings.get('ccTargetMin', 0):,.2f} - ${settings.get('ccTargetMax', 0):,.2f}")

    lines.append(f"\n  SAVOR CARD (Capital One):")
    lines.append(f"    Limit: ${settings.get('cc2Limit', 0):,.2f}")
    lines.append(f"    Target range: ${settings.get('cc2TargetMin', 0):,.2f} - ${settings.get('cc2TargetMax', 0):,.2f}")

    # FLEX floor
    lines.append(f"\n  FLEX FLOOR: ${settings.get('flexFloor', 0):,.2f} (minimum balance to maintain)")

    # Car fund / savings fund targets
    lines.append(f"\n  CAR FUND TARGET: ${settings.get('carFundTarget', 0):,.2f}")
    lines.append(f"  CAR FUND MINIMUM: ${settings.get('carFundMinimum', 0):,.2f}")

    # Credit score targets
    lines.append(f"\n  CREDIT SCORE TARGETS: VantageScore {settings.get('creditScoreTarget', 0)}, FICO {settings.get('creditScoreTarget2', 0)}")

    # BREX — loan to friend, not counted in net worth
    brex_balance = accounts.get("brex", 0)
    brex_starting = settings.get("brexStartingBalance", 0)
    if brex_starting > 0:
        pct_paid = ((brex_starting - brex_balance) / brex_starting * 100) if brex_starting > 0 else 0
        lines.append(f"\n  BREX (money lent to friend, NOT counted in net worth):")
        lines.append(f"    Outstanding: ${brex_balance:,.2f} of ${brex_starting:,.2f} starting")
        lines.append(f"    Paid back so far: {pct_paid:.1f}%")

    return "\n".join(lines)

# ============================================================
# TOOL 1 — SPENDING SUMMARY
# Shows how much was spent from each account over a time period
# ============================================================

def get_spending_summary(months_back=1):
    """
    Returns a plain-English spending summary for the last N months.
    Only counts outgoing money (negative amounts) that are real
    transactions, not transfers between Joey's own accounts.
    """
    data = load_data()
    if not data:
        return "Could not load financial data."

    transactions = data.get("transactions", [])
    cutoff = date.today() - timedelta(days=30 * months_back)

    # Group spending by account
    spending_by_account = defaultdict(float)
    transaction_count = defaultdict(int)

    for t in transactions:
        # Skip transfers between Joey's own accounts
        if t.get("type") == "transfer":
            continue

        # Parse the date
        raw_date = t.get("date", "")
        try:
            if "T" in raw_date:
                t_date = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date()
            else:
                t_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except:
            continue

        # Only include transactions within the time window
        if t_date < cutoff:
            continue

        amount = t.get("amount", 0)
        account_id = t.get("accountId", "unknown")

        # Only count spending (negative amounts)
        if amount < 0:
            spending_by_account[account_id] += abs(amount)
            transaction_count[account_id] += 1

    if not spending_by_account:
        return f"No spending transactions found in the last {months_back} month(s)."

    # Build the summary string
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
# Analyzes paycheck history
# ============================================================

def get_income_summary(paychecks_back=8):
    """
    Returns a summary of recent paychecks including averages,
    total gross, total net, and total taxes paid.
    """
    data = load_data()
    if not data:
        return "Could not load financial data."

    paychecks = data.get("paychecks", [])
    if not paychecks:
        return "No paycheck data found."

    recent = paychecks[-paychecks_back:]

    total_gross = sum(p.get("grossPay", 0) for p in recent)
    total_net = sum(p.get("netPay", 0) for p in recent)
    total_taxes = sum(
        sum(p.get("taxes", {}).values()) for p in recent
    )
    total_deductions = sum(
        sum(p.get("deductions", {}).values()) for p in recent
    )

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
        f"\n  Effective take-home:  {(total_net/total_gross*100):.1f}% of gross"
    ]

    return "\n".join(lines)


# ============================================================
# TOOL 3 — NET WORTH SNAPSHOT
# Calculates total assets minus total liabilities
# ============================================================

def get_net_worth():
    """
    Calculates Joey's current net worth.
    Assets = all positive account balances
    Liabilities = car loan
    """
    data = load_data()
    if not data:
        return "Could not load financial data."

    accounts = data.get("accounts", {})

    assets = 0
    liabilities = 0
    lines = ["NET WORTH SNAPSHOT:\n", "  ASSETS:"]

    for account_id, balance in accounts.items():
        name = ACCOUNT_NAMES.get(account_id, account_id)
        if account_id == "car_loan":
            liabilities += balance
            continue
        if balance > 0:
            assets += balance
            lines.append(f"    {name}: ${balance:,.2f}")

    lines.append(f"  Total assets: ${assets:,.2f}")
    lines.append(f"\n  LIABILITIES:")
    lines.append(f"    Car Loan: ${liabilities:,.2f}")
    lines.append(f"  Total liabilities: ${liabilities:,.2f}")

    net_worth = assets - liabilities
    lines.append(f"\n  NET WORTH: ${net_worth:,.2f}")

    return "\n".join(lines)


# ============================================================
# TOOL 4 — SAVINGS RATE
# What percentage of income is Joey actually saving?
# ============================================================

def get_savings_rate(paychecks_back=8):
    """
    Calculates Joey's savings rate based on recent paychecks
    and estimated monthly spending.
    """
    data = load_data()
    if not data:
        return "Could not load financial data."

    paychecks = data.get("paychecks", [])
    fixed_expenses = data.get("fixedExpenses", [])
    groceries = data.get("groceries", {})

    if not paychecks:
        return "No paycheck data found."

    recent = paychecks[-paychecks_back:]
    total_net = sum(p.get("netPay", 0) for p in recent)
    avg_monthly_net = (total_net / len(recent)) * 4.33  # weekly to monthly

    # Fixed monthly expenses
    monthly_fixed = 0
    for exp in fixed_expenses:
        if exp.get("frequency") == "monthly":
            monthly_fixed += exp.get("amount", 0)
        elif exp.get("frequency") == "weekly":
            monthly_fixed += exp.get("amount", 0) * 4.33

    # Average groceries
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
# Shows credit score trend over time
# ============================================================

def get_credit_score_history():
    """Returns credit score history sorted by date."""
    data = load_data()
    if not data:
        return "Could not load financial data."

    scores = data.get("creditScores", [])
    if not scores:
        return "No credit score history recorded."

    sorted_scores = sorted(scores, key=lambda x: x.get("date", ""))
    recent = sorted_scores[-10:]  # last 10 entries

    lines = ["CREDIT SCORE HISTORY (last 10 entries):\n"]
    for s in recent:
        lines.append(f"  {s.get('date','?')}  {s.get('score','?'):>4}  {s.get('source','')}")

    first = sorted_scores[0]
    latest = sorted_scores[-1]
    change = latest.get("score", 0) - first.get("score", 0)
    direction = "▲" if change > 0 else "▼" if change < 0 else "—"

    lines.append(f"\n  Overall change: {direction} {abs(change)} points")
    lines.append(f"  ({first.get('score')} on {first.get('date')} → {latest.get('score')} on {latest.get('date')})")

    return "\n".join(lines)


# ============================================================
# TOOL 6 — RECENT TRANSACTIONS
# Shows the last N transactions for a given account or all accounts
# ============================================================

def get_recent_transactions(account_id=None, limit=10):
    """
    Returns the most recent transactions.
    account_id — optional filter (vault, flex, funds, cc, cc2, car_loan)
    limit      — how many to return (default 10)
    """
    data = load_data()
    if not data:
        return "Could not load financial data."

    transactions = data.get("transactions", [])

    # Filter by account if specified
    if account_id:
        transactions = [t for t in transactions if t.get("accountId") == account_id]

    # Sort by date descending and take the most recent
    def parse_date(t):
        raw = t.get("date", "")
        try:
            if "T" in raw:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
            else:
                return datetime.strptime(raw, "%Y-%m-%d")
        except:
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
        except:
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

def get_grocery_history():
    """Returns monthly grocery spending history."""
    data = load_data()
    if not data:
        return "Could not load financial data."

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
# How close is Joey to a 3-month emergency fund?
# ============================================================

def get_emergency_fund_status():
    """
    Calculates how close Joey is to having a 3-month emergency fund.
    Uses FUNDS (savings account) as the emergency fund balance.
    """
    data = load_data()
    if not data:
        return "Could not load financial data."

    accounts = data.get("accounts", {})
    fixed_expenses = data.get("fixedExpenses", [])
    groceries = data.get("groceries", {})

    # Monthly expenses estimate
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

    funds_balance = accounts.get("funds", 0)
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


# ============================================================
# TEST — Run this file directly to verify all tools work
# ============================================================
# ============================================================
# TOOL 9 — WEB SEARCH
# Searches DuckDuckGo for financial news and information
# Only used when Joey explicitly asks for news or rates
# ============================================================

def search_financial_news(query):
    """
    Searches the web for financial information relevant to Joey's query.
    Uses SerpApi to query Google search results reliably.
    Only used when Joey explicitly asks for news or rates.
    """
    try:
        url = "https://serpapi.com/search"
        params = {
            "q": query,
            "api_key": SERPAPI_KEY,
            "num": 5        # Return top 5 results
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        results = data.get("organic_results", [])

        if not results:
            return f"No results found for: {query}"

        output = f"WEB SEARCH — {query.upper()}:\n\n"
        for r in results:
            title = r.get("title", "No title")
            snippet = r.get("snippet", "No description available")
            link = r.get("link", "")
            output += f"- {title}\n  {snippet}\n  {link}\n\n"

        return output.strip()

    except requests.exceptions.Timeout:
        return "Web search timed out. Please try again."
    except Exception as e:
        return f"Web search unavailable: {e}"

if __name__ == "__main__":
    print("Testing ASSET tools...\n")
    print("=" * 50)

    print(get_spending_summary(months_back=1))
    print("\n" + "=" * 50)

    print(get_income_summary())
    print("\n" + "=" * 50)

    print(get_net_worth())
    print("\n" + "=" * 50)

    print(get_savings_rate())
    print("\n" + "=" * 50)

    print(get_credit_score_history())
    print("\n" + "=" * 50)

    print(get_recent_transactions(limit=5))
    print("\n" + "=" * 50)

    print(get_grocery_history())
    print("\n" + "=" * 50)

    print(get_emergency_fund_status())
    print("\n" + "=" * 50)

    print("\nAll tools tested.")