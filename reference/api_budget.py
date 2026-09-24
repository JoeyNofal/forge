# ============================================================
# API_BUDGET.PY
# Tracks real dollar spend on Anthropic's Sonnet 5 API for
# NEXUS and CIPHER only. Handles the $10/day rollover-forever
# cap, 50/80/90% warnings against each day's flat $10, and the
# hard stop. Backed by three tables inside the existing
# chat_history.db:
#   api_balance   — single row, tracks the rolling dollar balance
#   api_usage     — one row per real API call, full history
#   app_settings  — generic key/value store for live-editable
#                   settings (daily cap override, agent default
#                   tiers) used by the Usage Tracker app
# ============================================================

import sqlite3
import json
from pathlib import Path
from datetime import date, datetime

DB_PATH = Path(__file__).parent / "chat_history.db"

DAILY_TOPUP = 10.0
WARNING_LEVELS = [50, 80, 90]

# Sonnet 5 pricing — per million tokens.
# Introductory rate through Aug 31, 2026, then the standard rate
# kicks in automatically — no manual date update needed later.
RATE_CHANGE_DATE = date(2026, 8, 31)
INTRO_INPUT_RATE = 2.0
INTRO_OUTPUT_RATE = 10.0
STANDARD_INPUT_RATE = 3.0
STANDARD_OUTPUT_RATE = 15.0


def _get_conn():
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
        pass  # column already exists — fine, this just makes the file safe to re-run
    try:
        c.execute("ALTER TABLE api_usage ADD COLUMN cache_creation_tokens INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # column already exists — fine, this just makes the file safe to re-run
    try:
        c.execute("ALTER TABLE api_usage ADD COLUMN cache_read_tokens INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # column already exists — fine, this just makes the file safe to re-run
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
# Small key/value store used for anything that needs to be
# editable at runtime without a restart — the daily cap override
# and each agent's default model tier live here, and future
# settings can reuse this same pair of functions rather than
# needing a new table every time.
# ============================================================

def get_setting(key: str, default=None):
    """Returns the raw string value for a setting, or `default`
    if that key has never been set."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key: str, value: str):
    """Writes (or overwrites) one setting. Value is always stored
    as a string — callers convert to/from str, int, float, or JSON
    as needed."""
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
    """The LIVE daily cap. Reads an override from app_settings if
    the Usage Tracker app has set one; otherwise falls back to the
    hardcoded DAILY_TOPUP constant above. This is what actually
    gets used everywhere in this file from now on — DAILY_TOPUP
    itself is now just the fallback default."""
    override = get_setting("daily_cap_override")
    if override:
        try:
            return float(override)
        except ValueError:
            pass
    return DAILY_TOPUP


def set_daily_topup(new_value: float):
    """Called by the Usage Tracker app to change the daily cap.
    Takes effect on the very next balance check — no restart."""
    set_setting("daily_cap_override", new_value)


def get_current_rates():
    """Returns (input_rate, output_rate) per million tokens, based on today's real date."""
    if date.today() >= RATE_CHANGE_DATE:
        return STANDARD_INPUT_RATE, STANDARD_OUTPUT_RATE
    return INTRO_INPUT_RATE, INTRO_OUTPUT_RATE

# Prompt caching pricing multipliers, applied to the base input rate.
# 1-hour cache writes cost 2x normal input price; cache reads cost
# just 0.1x — this is where the savings come from on every message
# after the first one in a session.
CACHE_WRITE_1H_MULTIPLIER = 2.0
CACHE_READ_MULTIPLIER = 0.1

def get_cache_rates():
    """Returns (cache_write_rate, cache_read_rate) per million tokens."""
    input_rate, _ = get_current_rates()
    return input_rate * CACHE_WRITE_1H_MULTIPLIER, input_rate * CACHE_READ_MULTIPLIER

def _ensure_today_state():
    """
    If today is a new calendar day compared to the last recorded date,
    tops the balance up by the LIVE daily cap (rollover-forever —
    whatever was left over just stays, no ceiling) and resets which
    warning levels have already been shown today.
    """
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
    and checks whether a new 50/80/90% warning threshold (measured
    against today's LIVE daily cap, not the rolling balance) was just
    crossed. Returns a warning message string if one should be shown
    right now, or "" if nothing new to warn about.

    cache_creation_tokens and cache_read_tokens come from Anthropic's
    prompt caching feature — most calls will have 0 for both unless
    the tier is paid_cloud and caching actually fired.
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


def get_usage_summary(days: int = 7) -> str:
    """
    Plain-English breakdown of spend by agent over the last N days.
    Not wired into anything yet this milestone — available for a
    future dashboard usage panel.
    """
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT agent, COUNT(*), SUM(cost)
        FROM api_usage
        WHERE date >= date('now', ?)
        GROUP BY agent
    """, (f"-{days} days",))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return "No API usage recorded yet."
    lines = [f"Usage over the last {days} days:"]
    for agent, count, total_cost in rows:
        lines.append(f"  {agent.upper()}: {count} calls, ${total_cost:.4f}")
    return "\n".join(lines)

def check_and_notify_hard_stop() -> bool:
    """
    Called every time the hard stop fires. Returns True only the FIRST
    time today — that's the signal to actually create a reminder popup.
    Every call after that today returns False, so we don't queue up a
    new popup for every single message sent while maxed out.
    """
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

# ============================================================
# STRUCTURED USAGE DATA — for the Usage Tracker app
# Unlike get_usage_summary() above (which returns a plain-English
# string), these return real lists/dicts of numbers so a chart or
# table can actually plot them.
# ============================================================

def get_usage_by_agent(days: int = 7) -> list:
    """Returns [{"agent": "nexus", "calls": 12, "cost": 1.2345}, ...]
    for the last N days, sorted highest spend first."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT agent, COUNT(*), SUM(cost)
        FROM api_usage
        WHERE date >= date('now', ?)
        GROUP BY agent
        ORDER BY SUM(cost) DESC
    """, (f"-{days} days",))
    rows = c.fetchall()
    conn.close()
    return [
        {"agent": agent, "calls": count, "cost": round(total_cost or 0, 4)}
        for agent, count, total_cost in rows
    ]


def get_usage_by_day(days: int = 7) -> list:
    """Returns one row per agent per day:
    [{"date": "2026-07-16", "agent": "nexus", "calls": 3, "cost": 0.4512}, ...]
    ordered oldest to newest — the natural shape for a line chart."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT date, agent, COUNT(*), SUM(cost)
        FROM api_usage
        WHERE date >= date('now', ?)
        GROUP BY date, agent
        ORDER BY date ASC
    """, (f"-{days} days",))
    rows = c.fetchall()
    conn.close()
    return [
        {"date": d, "agent": agent, "calls": count, "cost": round(total_cost or 0, 4)}
        for d, agent, count, total_cost in rows
    ]


def get_budget_overview() -> dict:
    """One-shot snapshot for the top of the Usage Tracker screen:
    current rolling balance, what's been spent today, the live
    daily cap, and what percent of today's cap is used."""
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
# their hardcoded default — chat_streaming.py's own
# AGENT_DEFAULT_TIERS_DEFAULT dict is still the fallback for any
# agent that's never been touched here.
# ============================================================

def get_agent_default_tiers() -> dict:
    """Returns a dict of ONLY the agent → tier overrides that have
    been explicitly set (e.g. {"stock": "local"}). An agent with no
    override simply won't be a key in this dict — the caller falls
    back to its own hardcoded default in that case."""
    raw = get_setting("agent_default_tiers")
    if raw:
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            pass
    return {}


def set_agent_default_tier(agent: str, tier: str):
    """Updates ONE agent's default tier, merging with whatever
    overrides already exist for the other agents so they aren't
    wiped out. tier must be one of: local, free_cloud, paid_cloud."""
    current = get_agent_default_tiers()
    current[agent] = tier
    set_setting("agent_default_tiers", json.dumps(current))

def get_usage_all_time_by_agent() -> list:
    """Same shape as get_usage_by_agent(), but with NO date filter —
    full history since the very first API call ever made. Powers the
    all-time bar graph."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT agent, COUNT(*), SUM(cost)
        FROM api_usage
        GROUP BY agent
        ORDER BY SUM(cost) DESC
    """)
    rows = c.fetchall()
    conn.close()
    return [
        {"agent": agent, "calls": count, "cost": round(total_cost or 0, 4)}
        for agent, count, total_cost in rows
    ]