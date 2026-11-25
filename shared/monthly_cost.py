"""
MONTHLY COST OF FIXED EXPENSES (shared, pure Python)

The ONE rule for "what do my fixed bills cost per month", copied from the Financial
Tracker's own apps/financial-tracker/bills.js (monthlyAmount / monthlyTotal) and
checked against it by shared/test_monthly_cost.py, which runs the real JavaScript.

  monthly   amount as it is          weekly     amount x 4.33
  biweekly  amount x 26 / 12         quarterly  amount / 3
  yearly    amount / 12              anything else: 0 (never guessed)

An expense whose end date is BEFORE today is finished and does not count (an end date
of today still counts). One that has not started yet still counts (the owner wants to
plan for it). Entries that are not objects, and amounts that are not numbers, count as 0.

Differences from the JavaScript, on purpose, for junk only: true/false as an amount is 0
here (JavaScript would read true as 1), and an end date written with a time of day is
ignored here (the tracker only ever writes plain YYYY-MM-DD dates).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

WEEKS_PER_MONTH = 4.33
_MAX_ITEMS = 100000   # same cap as bills.js
_NUM_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)$")


def _valid_date(s: Any) -> bool:
    if not isinstance(s, str) or len(s) != 10:
        return False
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return False
    return d.strftime("%Y-%m-%d") == s and 1900 <= d.year <= 2200


def _number(x: Any) -> float | None:
    """A finite number from a real number or a plain decimal string; anything else is None."""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        v = float(x)
    elif isinstance(x, str) and _NUM_RE.match(x.strip()):
        v = float(x.strip())
    else:
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def monthly_amount(e: Any) -> float:
    """What one fixed expense costs per month (0 for anything unusable)."""
    if not isinstance(e, dict):
        return 0.0
    a = _number(e.get("amount"))
    if a is None:
        return 0.0
    f = e.get("frequency")
    if f == "monthly":
        return a
    if f == "biweekly":
        return a * 26 / 12
    if f == "weekly":
        return a * WEEKS_PER_MONTH
    if f == "quarterly":
        return a / 3
    if f == "yearly":
        return a / 12
    return 0.0


def monthly_total(expenses: Any, today: Any) -> float:
    """All fixed expenses per month as of `today` (a date or 'YYYY-MM-DD')."""
    if hasattr(today, "strftime") and not isinstance(today, str):
        today = today.strftime("%Y-%m-%d")
    if not _valid_date(today):
        raise ValueError(f"today must be a real date like 2026-11-24, got {today!r}")
    if not isinstance(expenses, list):
        return 0.0
    total = 0.0
    for e in expenses[:_MAX_ITEMS]:
        if not isinstance(e, dict):
            continue
        end = e.get("endDate")
        if isinstance(end, str) and _valid_date(end) and end < today:
            continue
        total += monthly_amount(e)
    return total