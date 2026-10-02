"""
DRIVE TOOLS — read-only vehicle data engine (increment (a): core chat).

Rebuilt from reference/drive_tools.py. Everything that WRITES to
vehicle.json (log_maintenance, log_gas_fillup, log_issue, add_vehicle,
set/update_mileage, log_carfax_entry, log_wiper_fluid, and the recall
search that saves its result) is deliberately NOT here yet — that is
increment (b). Memory is increment (c). Photo/file support is deferred
(no image infrastructure in FORGE yet — same call as ATLAS). The old
duplicate SerpApi search is gone; DRIVE uses shared/web_search.py.

Real fixes vs the old code:
- The data path is an env var (VEHICLE_DATA_PATH), read at CALL time,
  defaulting to a FORGE-only file — never the old NEXUS SYSTEM's real
  vehicle.json.
- The file auto-creates if missing (same auto-create call as ATLAS),
  atomically under a lock, so simultaneous first-callers can't race
  (Lesson #4 — the old code had NO locking on vehicle.json at all).
- Every reader is shape-safe: the old code indexed vehicle['year'],
  vehicle['vin'] etc. directly and would KeyError on a malformed or
  partial entry; assumed data["vehicles"] always exists and is
  non-empty. All of that is now .get()-based with safe fallbacks
  (Lesson #5).
- Loading raises a clear RuntimeError on a real problem (corrupt JSON,
  wrong top-level shape, empty vehicles list) instead of crashing with
  a raw traceback, with one retry for a file caught mid-write
  (Lesson #12, same pattern as ATLAS).
"""
import json
import os
import time
from datetime import date, datetime

from dotenv import load_dotenv
from filelock import FileLock

load_dotenv(override=True)  # Lesson #12: .env must win over a stale system env var

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_VEHICLE_DATA_PATH = os.path.join(_REPO_ROOT, "data", "vehicle.json")

# Kept from the old code — the actual scheduling logic, not personal data.
MAINTENANCE_INTERVALS = {
    "oil_change":          {"miles": 5000,  "days": 180},
    "tire_rotation":       {"miles": 7500,  "days": 180},
    "air_filter":          {"miles": 15000, "days": 365},
    "cabin_filter":        {"miles": 15000, "days": 365},
    "wiper_blades":        {"miles": None,  "days": 365},
    "brake_inspection":    {"miles": 20000, "days": 365},
    "coolant_flush":       {"miles": 30000, "days": 730},
    "transmission_fluid":  {"miles": 30000, "days": 730},
    "spark_plugs":         {"miles": 30000, "days": 730},
    "tire_replacement":    {"miles": 50000, "days": None},
    "battery_replacement": {"miles": None,  "days": 1460},
}

SERVICE_DISPLAY_NAMES = {
    "oil_change":          "Oil Change",
    "tire_rotation":       "Tire Rotation",
    "air_filter":          "Air Filter Replacement",
    "cabin_filter":        "Cabin Air Filter Replacement",
    "wiper_blades":        "Wiper Blade Replacement",
    "brake_inspection":    "Brake Inspection",
    "brake_replacement":   "Brake Replacement",
    "coolant_flush":       "Coolant Flush",
    "transmission_fluid":  "Transmission Fluid Change",
    "spark_plugs":         "Spark Plug Replacement",
    "tire_replacement":    "Tire Replacement",
    "battery_replacement": "Battery Replacement",
    "wiper_fluid":         "Wiper Fluid Top-Off",
    "gas":                 "Gas Fill-Up",
    "other":               "Other Service",
}


def get_data_path() -> str:
    """Read at call time (not import time) so tests and .env changes work."""
    return os.path.abspath(os.getenv("VEHICLE_DATA_PATH") or DEFAULT_VEHICLE_DATA_PATH)


# ─────────────────────────────────────────────
# SECTION 1 — FILE SETUP AND LOADING
# ─────────────────────────────────────────────

def _starting_structure() -> dict:
    """Joey's real car, confirmed current — same as the old system's default."""
    return {
        "vehicles": [
            {
                "id": "vehicle_001",
                "active": True,
                "make": "Honda",
                "model": "Civic",
                "year": 2016,
                "vin": "19XFC2F57GE016309",
                "current_mileage": None,
                "mileage_last_updated": None,
                "notes": "Purchased used. Previous owner history available on Carfax.",
                "maintenance_log": [],
                "upcoming_maintenance": [],
                "gas_log": [],
                "issues": [],
                "recalls": []
            }
        ],
        "created_at": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat()
    }


def initialize_vehicle_data() -> bool:
    """
    Creates the data file with the starting structure if it doesn't exist.
    Safe to call any number of times, from any number of threads.
    Returns True only if THIS call created the file.
    """
    path = get_data_path()
    if os.path.exists(path):
        return False

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with FileLock(path + ".lock", timeout=10):
        if os.path.exists(path):  # someone else created it while we waited
            return False
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(_starting_structure(), f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)  # atomic: a reader never sees half a file
        return True


def load_data() -> dict:
    """
    Returns the whole vehicle file as a dict. Auto-creates it if missing.
    Raises RuntimeError with a specific message on a real problem.
    """
    initialize_vehicle_data()
    path = get_data_path()

    data = None
    last_error = None
    for attempt in range(2):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            break
        except json.JSONDecodeError as e:
            last_error = e
            if attempt == 0:
                time.sleep(0.3)  # a mid-write read; retry once
        except OSError as e:
            raise RuntimeError(f"Could not read the vehicle data file at {path}: {e}")
    else:
        raise RuntimeError(
            f"The vehicle data file at {path} is malformed (not valid JSON): {last_error}"
        )

    if not isinstance(data, dict):
        raise RuntimeError(
            f"The vehicle data file at {path} has the wrong shape "
            f"(expected a JSON object, found {type(data).__name__})."
        )
    return data


def get_active_vehicle(data: dict) -> dict:
    """
    Returns the active vehicle dict. Raises RuntimeError if there truly
    is no usable vehicle on file (the old code would KeyError/IndexError
    on an empty or malformed list instead).
    """
    vehicles = data.get("vehicles")
    if not isinstance(vehicles, list) or not vehicles:
        raise RuntimeError("No vehicle is on file (vehicles list is missing or empty).")
    dict_vehicles = [v for v in vehicles if isinstance(v, dict)]
    if not dict_vehicles:
        raise RuntimeError("The vehicle data file has no valid vehicle entries.")
    for v in dict_vehicles:
        if v.get("active"):
            return v
    return dict_vehicles[0]


# ─────────────────────────────────────────────
# SECTION 2 — SAFE HELPERS (Lesson #5: never trust the shape)
# ─────────────────────────────────────────────

def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _show(v):
    return "unknown" if v is None or v == "" else v


def _entries(vehicle: dict, key: str) -> list:
    v = vehicle.get(key)
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _first(item: dict, *keys):
    """First non-None value among several possible field names. The DRIVE Tracker
    and the old agent named some fields differently (due_mileage vs next_due_miles,
    reported_date vs date_reported), so readers accept either."""
    for k in keys:
        if item.get(k) is not None:
            return item.get(k)
    return None


def _vehicle_label(vehicle: dict) -> str:
    year = _show(vehicle.get("year"))
    make = vehicle.get("make") or ""
    model = vehicle.get("model") or ""
    label = f"{year} {make} {model}".strip()
    return label or "Unknown vehicle"


# ─────────────────────────────────────────────
# SECTION 3 — READING AND ANALYSIS (read-only)
# ─────────────────────────────────────────────

def get_vehicle_info() -> str:
    vehicle = get_active_vehicle(load_data())
    mileage = vehicle.get("current_mileage")
    mil_str = f"{mileage:,} miles" if isinstance(mileage, (int, float)) else "not yet recorded"
    return (
        f"{_vehicle_label(vehicle)}\n"
        f"VIN: {_show(vehicle.get('vin'))}\n"
        f"Current mileage: {mil_str}"
    )


def get_recent_maintenance(limit: int = 5) -> str:
    vehicle = get_active_vehicle(load_data())
    log = _entries(vehicle, "maintenance_log")
    if not log:
        return "No maintenance history logged yet."

    recent = sorted(log, key=lambda e: str(e.get("date") or ""), reverse=True)[:limit]
    lines = []
    for e in recent:
        name = e.get("display_name") or SERVICE_DISPLAY_NAMES.get(e.get("service_type"), e.get("service_type") or "Service")
        d = e.get("date") or "unknown date"
        mileage = e.get("mileage")
        mil_str = f" at {mileage:,} miles" if isinstance(mileage, (int, float)) else ""
        shop = e.get("shop")
        shop_str = f" — {shop}" if shop else ""
        cost = e.get("cost")
        cost_str = f" (${cost:.2f})" if isinstance(cost, (int, float)) else ""
        by = e.get("performed_by")
        by_str = f" [{by}]" if by and by != "dealership" else ""
        carfax_str = " [Carfax]" if e.get("source") == "carfax" else ""
        lines.append(f"• {name} on {d}{mil_str}{shop_str}{cost_str}{by_str}{carfax_str}")
    return "\n".join(lines)


def get_full_maintenance_history() -> str:
    vehicle = get_active_vehicle(load_data())
    log = _entries(vehicle, "maintenance_log")
    if not log:
        return "No maintenance history logged yet."

    sorted_log = sorted(log, key=lambda e: str(e.get("date") or ""))
    lines = [f"Full maintenance history — {len(sorted_log)} entries:\n"]
    for e in sorted_log:
        name = e.get("display_name") or SERVICE_DISPLAY_NAMES.get(e.get("service_type"), e.get("service_type") or "Service")
        d = e.get("date") or "unknown date"
        mileage = e.get("mileage")
        mil_str = f" at {mileage:,} miles" if isinstance(mileage, (int, float)) else ""
        shop = e.get("shop")
        shop_str = f" — {shop}" if shop else ""
        cost = e.get("cost")
        cost_str = f" (${cost:.2f})" if isinstance(cost, (int, float)) else ""
        by = e.get("performed_by")
        by_str = f" [{by}]" if by else ""
        carfax_str = " [Carfax]" if e.get("source") == "carfax" else ""
        notes = e.get("notes")
        notes_str = f"\n  Notes: {notes}" if notes else ""
        lines.append(f"• {name} on {d}{mil_str}{shop_str}{cost_str}{by_str}{carfax_str}{notes_str}")
    return "\n".join(lines)


def get_gas_summary() -> str:
    vehicle = get_active_vehicle(load_data())
    gas_log = _entries(vehicle, "gas_log")
    if not gas_log:
        return "No gas fill-ups logged yet."

    total_gallons = sum(_num(e.get("gallons")) or 0 for e in gas_log)
    total_spent = sum(_num(e.get("total_cost")) or 0 for e in gas_log)
    mpg_entries = [m for m in (_num(e.get("mpg")) for e in gas_log) if m]
    avg_mpg = round(sum(mpg_entries) / len(mpg_entries), 1) if mpg_entries else None

    lines = [f"Gas log — {len(gas_log)} fill-ups:", f"Total gallons: {total_gallons:.1f}",
             f"Total spent: ${total_spent:.2f}"]
    if avg_mpg:
        lines.append(f"Average MPG: {avg_mpg}")

    lines.append("\nRecent fill-ups:")
    for e in sorted(gas_log, key=lambda x: str(x.get("date") or ""), reverse=True)[:5]:
        gallons = _num(e.get("gallons"))
        price = _num(e.get("price_per_gallon"))
        cost = _num(e.get("total_cost"))
        mpg = _num(e.get("mpg"))
        mpg_str = f" | MPG: {mpg}" if mpg else ""
        lines.append(
            f"• {e.get('date', 'unknown date')} — {_show(gallons)} gal @ "
            f"${_show(price)}/gal = ${cost:.2f}" + (mpg_str if mpg else "")
            if cost is not None else
            f"• {e.get('date', 'unknown date')} — incomplete entry{mpg_str}"
        )
    return "\n".join(lines)


def get_upcoming_maintenance() -> str:
    vehicle = get_active_vehicle(load_data())
    current_mileage = vehicle.get("current_mileage")
    upcoming = _entries(vehicle, "upcoming_maintenance")
    if not upcoming:
        return "No upcoming maintenance scheduled yet. Log a service to start tracking."

    today = date.today()
    warnings, schedule = [], []
    for item in upcoming:
        name = item.get("display_name") or item.get("service_type") or "Service"
        due_miles = _first(item, "due_mileage", "next_due_miles")
        due_date = _first(item, "due_date", "next_due_date")
        parts, urgent = [], False

        if isinstance(due_miles, (int, float)) and isinstance(current_mileage, (int, float)):
            miles_away = due_miles - current_mileage
            parts.append(f"due at {due_miles:,.0f} miles ({miles_away:,.0f} miles away)")
            if miles_away <= 500:
                urgent = True

        if isinstance(due_date, str):
            try:
                due_date_obj = datetime.strptime(due_date, "%Y-%m-%d").date()
                days_away = (due_date_obj - today).days
                parts.append(f"due by {due_date} ({days_away} days away)")
                if days_away <= 30:
                    urgent = True
            except ValueError:
                parts.append(f"due by {due_date} (date unclear)")

        line = f"{'⚠️ ' if urgent else '• '}{name}: {' / '.join(parts) if parts else 'schedule unclear'}"
        (warnings if urgent else schedule).append(line)

    result = ""
    if warnings:
        result += "COMING DUE SOON:\n" + "\n".join(warnings) + "\n\n"
    if schedule:
        result += "UPCOMING SCHEDULE:\n" + "\n".join(schedule)
    return result.strip() or "All maintenance is up to date."


def get_open_issues() -> str:
    vehicle = get_active_vehicle(load_data())
    issues = [i for i in _entries(vehicle, "issues") if i.get("status") == "open"]
    if not issues:
        return "No open issues."
    lines = [f"Open issues ({len(issues)}):"]
    for i in issues:
        sev = str(i.get("severity") or "unknown").upper()
        lines.append(f"• [{sev}] {_show(i.get('description'))} — reported {_show(_first(i, 'reported_date', 'date_reported'))}")
    return "\n".join(lines)


def list_vehicles() -> str:
    data = load_data()
    vehicles = [v for v in data.get("vehicles", []) if isinstance(v, dict)]
    if not vehicles:
        return "No vehicles on file."
    lines = []
    for v in vehicles:
        active_str = " [ACTIVE]" if v.get("active") else " [archived]"
        mileage = v.get("current_mileage")
        mil_str = f" — {mileage:,} miles" if isinstance(mileage, (int, float)) else ""
        lines.append(f"• {_vehicle_label(v)}{mil_str}{active_str}")
    return "\n".join(lines)


def get_data_summary_for_llm() -> str:
    """
    Plain-English summary of the vehicle data, used as DRIVE's context
    before it responds. Every number here is the ONLY number DRIVE may
    quote (its prompt forbids inventing any).
    """
    vehicle = get_active_vehicle(load_data())
    mileage = vehicle.get("current_mileage")
    mil_str = f"{mileage:,} miles" if isinstance(mileage, (int, float)) else "not yet recorded"

    return f"""=== VEHICLE DATA SUMMARY ===
Vehicle: {_vehicle_label(vehicle)}
VIN: {_show(vehicle.get('vin'))}
Current mileage: {mil_str}

RECENT MAINTENANCE:
{get_recent_maintenance(5)}

GAS LOG:
{get_gas_summary()}

UPCOMING MAINTENANCE:
{get_upcoming_maintenance()}

OPEN ISSUES:
{get_open_issues()}
=== END OF VEHICLE DATA ===""".strip()