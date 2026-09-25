"""
Tracks real dollar spend on Sonnet 5 (Paid Cloud tier) for FORGE.
Ported from the old NEXUS SYSTEM's proven dashboard/api_budget.py
(carries over as-is per the Rebuild Plan — no rebuilding needed) with
one change: the database lives in FORGE's own new folder, so this
starts a fresh $10/day pool, separate from the old system's.

Handles the $10/day rollover-forever cap, 50/80/90% warnings against
each day's flat cap, and the hard stop. Backed by three tables:
  api_balance   - single row, tracks the rolling dollar balance
  api_usage     - one row per real API call, full history
  app_settings  - generic key/value store (daily cap override,
                  agent default tiers)
"""

import sqlite3
import json
import os
from pathlib import Path
from datetime import date, datetime

DB_PATH = Path(os.getenv("FORGE_DB_PATH", r"D:\Projects\forge\data\chat_history.db"))

DAILY_TOPUP = 10.0
WARNING_LEVELS = [50, 80, 90]

# Sonnet 5 pricing - per million tokens.
# Introductory rate through Aug 31, 2026, then the standard rate
# kicks in automatically - no manual date update needed later.
RATE_CHANGE_DATE = date(2026, 8, 31)
INTRO_INPUT_RATE = 2.0
INTRO_OUTPUT_RATE = 10.0
STANDARD_INPUT_RATE = 3.0
STANDARD_OUTPUT_RATE = 15.0


def _get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def _init_tables():
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS api_balance (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            balance REAL,
            last_reset_date TEXT,
            warned_levels TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            date TEXT,
            agent TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost REAL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    try:
        c.execute("ALTER TABLE api_balance ADD COLUMN hard_stop_notified INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # column already exists - fine, this just makes the file safe to re-run
    try:
        c.execute("ALTER TABLE api_usage ADD COLUMN cache_creation_tokens INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE api_usage ADD COLUMN cache_read_tokens INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    c.execute("SELECT COUNT(*) FROM api_balance WHERE id = 1")
    if c.fetchone()[0] == 0:
        c.execute(
            "INSERT INTO api_balance (id, balance, last_reset_date, warned_levels) VALUES (1, ?, ?, '')",
            (DAILY_TOPUP, date.today().isoformat())
        )
    conn.commit()
    conn.close()

_init_tables()


# ============================================================
# GENERIC SETTINGS STORAGE
# ============================================================

def get_setting(key: str, default=None):
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key: str, value: str):
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value))
    )
    conn.commit()
    conn.close()


# ============================================================
# LIVE DAILY CAP OVERRIDE
# ============================================================

def get_daily_topup() -> float:
    override = get_setting("daily_cap_override")
    if override:
        try:
            return float(override)
        except ValueError:
            pass
    return DAILY_TOPUP


def set_daily_topup(new_value: float):
    set_setting("daily_cap_override", str(new_value))


def get_current_rates():
    """Returns (input_rate, output_rate) per million tokens, based on today's real date."""
    if date.today() >= RATE_CHANGE_DATE:
        return STANDARD_INPUT_RATE, STANDARD_OUTPUT_RATE
    return INTRO_INPUT_RATE, INTRO_OUTPUT_RATE

CACHE_WRITE_1H_MULTIPLIER = 2.0
CACHE_READ_MULTIPLIER = 0.1

def get_cache_rates():
    input_rate, _ = get_current_rates()
    return input_rate * CACHE_WRITE_1H_MULTIPLIER, input_rate * CACHE_READ_MULTIPLIER

def _ensure_today_state():
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT balance, last_reset_date FROM api_balance WHERE id = 1")
    balance, last_reset_date = c.fetchone()
    today_str = date.today().isoformat()
    if last_reset_date != today_str:
        balance += get_daily_topup()
        c.execute(
            "UPDATE api_balance SET balance = ?, last_reset_date = ?, warned_levels = '', hard_stop_notified = 0 WHERE id = 1",
            (balance, today_str)
        )
        conn.commit()
    conn.close()


def get_balance() -> float:
    _ensure_today_state()
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT balance FROM api_balance WHERE id = 1")
    balance = c.fetchone()[0]
    conn.close()
    return balance


def get_today_spent() -> float:
    conn = _get_conn()
    c = conn.cursor()
    today_str = date.today().isoformat()
    c.execute("SELECT COALESCE(SUM(cost), 0) FROM api_usage WHERE date = ?", (today_str,))
    total = c.fetchone()[0]
    conn.close()
    return total


def record_usage(agent: str, input_tokens: int, output_tokens: int, cache_creation_tokens: int = 0, cache_read_tokens: int = 0) -> str:
    """
    Logs a real API call's cost, subtracts it from the rolling balance,
    and checks whether a new 50/80/90% warning threshold was just
    crossed. Returns a warning message string, or "" if nothing new.
    """
    input_rate, output_rate = get_current_rates()
    cache_write_rate, cache_read_rate = get_cache_rates()
    cost = (
        (input_tokens / 1_000_000 * input_rate)
        + (output_tokens / 1_000_000 * output_rate)
        + (cache_creation_tokens / 1_000_000 * cache_write_rate)
        + (cache_read_tokens / 1_000_000 * cache_read_rate)
    )

    conn = _get_conn()
    c = conn.cursor()
    now_str = datetime.now().isoformat()
    today_str = date.today().isoformat()
    c.execute(
        "INSERT INTO api_usage (timestamp, date, agent, input_tokens, output_tokens, cost, cache_creation_tokens, cache_read_tokens) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (now_str, today_str, agent, input_tokens, output_tokens, cost, cache_creation_tokens, cache_read_tokens)
    )

    c.execute("SELECT balance, warned_levels FROM api_balance WHERE id = 1")
    balance, warned_levels = c.fetchone()
    balance -= cost
    c.execute("UPDATE api_balance SET balance = ? WHERE id = 1", (balance,))
    conn.commit()

    daily_cap = get_daily_topup()
    today_spent = get_today_spent()
    warned_list = warned_levels.split(",") if warned_levels else []
    percent_used = (today_spent / daily_cap) * 100

    newly_crossed = [lvl for lvl in WARNING_LEVELS if percent_used >= lvl and str(lvl) not in warned_list]

    warning_message = ""
    if newly_crossed:
        for lvl in newly_crossed:
            warned_list.append(str(lvl))
        highest = max(newly_crossed)
        warning_message = (
            f"⚠️ Heads up — we've now used {highest}% of today's ${daily_cap:.0f} "
            f"Sonnet 5 budget (${today_spent:.2f} spent so far today)."
        )
        c.execute("UPDATE api_balance SET warned_levels = ? WHERE id = 1", (",".join(warned_list),))
        conn.commit()

    conn.close()
    return warning_message


def check_and_notify_hard_stop() -> bool:
    """Returns True only the FIRST time today the hard stop fires."""
    _ensure_today_state()
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT hard_stop_notified FROM api_balance WHERE id = 1")
    notified = c.fetchone()[0]
    if notified:
        conn.close()
        return False
    c.execute("UPDATE api_balance SET hard_stop_notified = 1 WHERE id = 1")
    conn.commit()
    conn.close()
    return True


def get_budget_overview() -> dict:
    """One-shot snapshot: current balance, today's spend, live daily cap, percent used."""
    balance = get_balance()
    today_spent = get_today_spent()
    daily_cap = get_daily_topup()
    percent_used = round((today_spent / daily_cap) * 100, 1) if daily_cap else 0
    return {
        "balance": round(balance, 4),
        "today_spent": round(today_spent, 4),
        "daily_cap": daily_cap,
        "percent_used_today": percent_used,
    }


# ============================================================
# LIVE AGENT DEFAULT-TIER OVERRIDES
# Stores ONLY the agents that have actually been changed from
# their hardcoded default - shared.model_client's own
# AGENT_DEFAULT_TIERS_DEFAULT dict is the fallback.
# ============================================================

def get_agent_default_tiers() -> dict:
    raw = get_setting("agent_default_tiers")
    if raw:
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            pass
    return {}


def set_agent_default_tier(agent: str, tier: str):
    current = get_agent_default_tiers()
    current[agent] = tier
    set_setting("agent_default_tiers", json.dumps(current))