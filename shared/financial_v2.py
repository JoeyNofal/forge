"""
FINANCIAL TRACKER v2 READER (shared, pure Python, read-only)

Reads the data file of the Financial Tracker app (format version 2) and answers
the money questions the same way the app's own ledger.js does, so FORGE agents
(ASSET first) never invent a second set of rules.

THE RULES (copied from apps/financial-tracker/ledger.js, checked against it by
shared/test_financial_v2.py, which runs the real JavaScript):
  - Money is whole CENTS in the file. Here it is turned into dollars only at the edge.
  - A transaction's amountCents is CASH FLOW: negative = money out, positive = money in.
  - bank / savings / receivable:  balance = opening + sum(amounts)
  - credit_card / loan (AMOUNT OWED, positive = owed):  balance = opening - sum(amounts)
  - A transaction counts from its own date through the as-of day, and only if its
    date is on or after the account's openingDate.
  - Net worth = every account's balance, with credit cards and loans counted as minus.
  - Malformed rows are ignored, never guessed (ledger.js does the same).

This module does NO file or network work: callers pass in the already-loaded data.
Where the data is invalid in ways ledger.js would reject (duplicate account ids,
an unknown account kind) this reader skips the account and says so in "warnings"
instead of guessing.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

KINDS = ("bank", "savings", "credit_card", "loan", "receivable")
DEBT_KINDS = ("credit_card", "loan")
# Transaction types that move or fix money but are not real spending or income.
NON_ACTIVITY_TYPES = ("transfer", "correction", "migration_adjustment")

_MAX_SAFE = 2**53 - 1          # JavaScript's largest safe integer, like ledger.js
_MIN_YEAR, _MAX_YEAR = 1900, 2200   # dates.js only accepts these years
_NAME_MAX = 60


def _valid_date(s: Any) -> bool:
    if not isinstance(s, str) or len(s) != 10:
        return False
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return False
    return d.strftime("%Y-%m-%d") == s and _MIN_YEAR <= d.year <= _MAX_YEAR


def _cents(x: Any) -> int | None:
    """A whole, safe number of cents, or None. 5000 and 5000.0 both count (JSON from
    JavaScript can look either way); true, 12.5, text and huge numbers do not."""
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x if abs(x) <= _MAX_SAFE else None
    if isinstance(x, float):
        if x != x or x in (float("inf"), float("-inf")) or not x.is_integer() or abs(x) > _MAX_SAFE:
            return None
        return int(x)
    return None


def _dollars(cents: int) -> float:
    return round(cents / 100, 2)


def _rows(x: Any) -> list:
    """The entries of a list, or an empty list when the file holds something else there."""
    return x if isinstance(x, list) else []


def is_v2(data: Any) -> bool:
    """True only for a dict whose schemaVersion is the whole number 2 and whose accounts are a list."""
    if not isinstance(data, dict):
        return False
    v = data.get("schemaVersion")
    return isinstance(v, int) and not isinstance(v, bool) and v == 2 and isinstance(data.get("accounts"), list)


def _clean_as_of(as_of: Any) -> str:
    if hasattr(as_of, "strftime") and not isinstance(as_of, str):
        as_of = as_of.strftime("%Y-%m-%d")
    if not _valid_date(as_of):
        raise ValueError(f"as_of must be a real date like 2026-11-24, got {as_of!r}")
    return as_of


def _accounts(data: dict, warnings: list[str]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for i, a in enumerate(_rows(data.get("accounts"))):
        if not isinstance(a, dict) or not isinstance(a.get("id"), str) or not a["id"]:
            warnings.append(f"account #{i + 1} skipped: it has no usable id")
            continue
        aid = a["id"]
        if aid in seen:
            warnings.append(f"account '{aid}' skipped: its id is used twice")
            continue
        kind = a.get("kind")
        if kind not in KINDS:
            warnings.append(f"account '{aid}' skipped: unknown kind {kind!r}")
            continue
        seen.add(aid)
        opening = _cents(a.get("openingCents"))
        open_date = a.get("openingDate")
        name = a.get("name")
        name = " ".join(name.split())[:_NAME_MAX] if isinstance(name, str) and name.strip() else aid
        role = a.get("role") if isinstance(a.get("role"), str) else "none"
        out.append({
            "id": aid, "name": name, "kind": kind, "role": role,
            "closed": a.get("closed") is True,
            "opening": opening if opening is not None else 0,
            "open_date": open_date if _valid_date(open_date) else "0000-00-00",
        })
    return out


def balances_cents(data: Any, as_of: Any) -> dict[str, int]:
    """Balance of every account on as_of, in cents (debts = amount owed, positive)."""
    return {k: v["balance"] for k, v in _balance_table(data, _clean_as_of(as_of), [])[0].items()}


def _balance_table(data: Any, as_of: str, warnings: list[str]):
    if not is_v2(data):
        raise ValueError("not a Financial Tracker v2 file (schemaVersion 2 with an accounts list is required)")
    accts = _accounts(data, warnings)
    table = {a["id"]: dict(a, balance=a["opening"]) for a in accts}
    for t in _rows(data.get("transactions")):
        if not isinstance(t, dict):
            continue
        a = table.get(t.get("accountId")) if isinstance(t.get("accountId"), str) else None
        amt = _cents(t.get("amountCents"))
        d = t.get("date")
        if a is None or amt is None or not isinstance(d, str) or not _valid_date(d):
            continue
        if d > as_of or d < a["open_date"]:
            continue
        a["balance"] += -amt if a["kind"] in DEBT_KINDS else amt
    return table, accts


def net_worth_cents(data: Any, as_of: Any) -> int:
    table, accts = _balance_table(data, _clean_as_of(as_of), [])
    return sum(-table[a["id"]]["balance"] if a["kind"] in DEBT_KINDS else table[a["id"]]["balance"] for a in accts)


def normalize_for_asset(data: Any, as_of: Any) -> dict:
    """
    A v2 file turned into the shape ASSET's tools read (dollars, plain dicts):
      accounts       {id: balance in dollars}  (credit cards and loans = amount OWED, positive, like the old file)
      accounts_meta  [{id, name, kind, role, closed, balance}]  every readable account, in file order
      transactions   [{id, accountId, date, description, amount (dollars, cash flow: negative = out),
                       type, future (dated after as_of), plus transferId / note when present}]
      net_worth      dollars
      warnings       things skipped or odd (never silently dropped)
      settings / fixedExpenses / groceries / creditScores / paychecks  passed through as they are
    The input is never changed.
    """
    as_of = _clean_as_of(as_of)
    warnings: list[str] = []
    table, accts = _balance_table(data, as_of, warnings)
    meta = []
    accounts: dict[str, float] = {}
    net = 0
    for a in accts:
        bal = table[a["id"]]["balance"]
        net += -bal if a["kind"] in DEBT_KINDS else bal
        accounts[a["id"]] = _dollars(bal)
        meta.append({"id": a["id"], "name": a["name"], "kind": a["kind"], "role": a["role"],
                     "closed": a["closed"], "balance": _dollars(bal)})
    txns = []
    skipped = 0
    for t in _rows(data.get("transactions")):
        amt = _cents(t.get("amountCents")) if isinstance(t, dict) else None
        if not isinstance(t, dict) or amt is None or not _valid_date(t.get("date")) or not isinstance(t.get("accountId"), str):
            skipped += 1
            continue
        row = {
            "id": t.get("id") if isinstance(t.get("id"), str) else "",
            "accountId": t["accountId"],
            "date": t["date"],
            "description": t.get("description") if isinstance(t.get("description"), str) else "",
            "amount": _dollars(amt),
            "type": t.get("type") if isinstance(t.get("type"), str) else "transaction",
            "future": t["date"] > as_of,
        }
        if isinstance(t.get("transferId"), str):
            row["transferId"] = t["transferId"]
        if isinstance(t.get("note"), str):
            row["note"] = t["note"]
        txns.append(row)
    if skipped:
        warnings.append(f"{skipped} transaction(s) skipped: not a usable entry (bad amount, date or account)")
    return {
        "schemaVersion": 2,
        "asOf": as_of,
        "accounts": accounts,
        "accounts_meta": meta,
        "transactions": txns,
        "net_worth": _dollars(net),
        "warnings": warnings,
        "settings": data.get("settings") if isinstance(data.get("settings"), dict) else {},
        "fixedExpenses": data.get("fixedExpenses") if isinstance(data.get("fixedExpenses"), list) else [],
        "groceries": data.get("groceries") if isinstance(data.get("groceries"), dict) else {},
        "creditScores": data.get("creditScores") if isinstance(data.get("creditScores"), list) else [],
        "paychecks": data.get("paychecks") if isinstance(data.get("paychecks"), list) else [],
    }