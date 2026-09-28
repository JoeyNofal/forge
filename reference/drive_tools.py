# D.R.I.V.E. — Tools & Data Engine
# Creates and manages vehicle.json
# Handles all maintenance logging, tracking, and web search

import json
import os
import uuid
import requests
import os
from dotenv import load_dotenv
load_dotenv(r"D:\Projects\NEXUS SYSTEM\.env", override=True)
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
from datetime import datetime, date

# ── File path for vehicle.json ───────────────────────────────────────────────
DATA_PATH = r"D:\Projects\NEXUS SYSTEM\data\vehicle.json"

# ── Default maintenance intervals ────────────────────────────────────────────
# These are the thresholds DRIVE uses to warn you when something is due
# All mileage values are in miles, all day values are calendar days
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

# ── Service type display names ───────────────────────────────────────────────
SERVICE_DISPLAY_NAMES = {
    "oil_change":          "Oil Change",
    "tire_rotation":       "Tire Rotation",
    "air_filter":          "Air Filter Replacement",
    "cabin_filter":        "Cabin Air Filter Replacement",
    "wiper_blades":        "Wiper Blade Replacement",
    "brake_inspection":    "Brake Inspection",
    "coolant_flush":       "Coolant Flush",
    "transmission_fluid":  "Transmission Fluid Change",
    "spark_plugs":         "Spark Plug Replacement",
    "tire_replacement":    "Tire Replacement",
    "battery_replacement": "Battery Replacement",
    "wiper_fluid":         "Wiper Fluid Top-Off",
    "gas":                 "Gas Fill-Up",
    "other":               "Other Service",
}


# ════════════════════════════════════════════════════════════════════════════
# VEHICLE.JSON — CREATE & LOAD
# ════════════════════════════════════════════════════════════════════════════

def create_empty_vehicle_json():
    """Creates a fresh vehicle.json with Joey's car pre-loaded."""
    data = {
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
    save_data(data)
    return data


def load_data() -> dict:
    """Loads vehicle.json from disk. Creates it if it doesn't exist."""
    if not os.path.exists(DATA_PATH):
        return create_empty_vehicle_json()
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data: dict):
    """Saves vehicle.json to disk."""
    data["last_updated"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_active_vehicle(data: dict) -> dict:
    """Returns the currently active vehicle from vehicle.json."""
    for v in data["vehicles"]:
        if v.get("active"):
            return v
    return data["vehicles"][0]


# ════════════════════════════════════════════════════════════════════════════
# FIRST STARTUP — MILEAGE & CARFAX SETUP
# ════════════════════════════════════════════════════════════════════════════

def is_first_startup() -> bool:
    """Returns True if no mileage has been recorded yet."""
    data = load_data()
    vehicle = get_active_vehicle(data)
    return vehicle["current_mileage"] is None


def set_initial_mileage(mileage: int):
    """Sets the car's mileage for the first time."""
    data = load_data()
    vehicle = get_active_vehicle(data)
    vehicle["current_mileage"] = mileage
    vehicle["mileage_last_updated"] = datetime.now().isoformat()
    save_data(data)
    return f"Current mileage set to {mileage:,} miles."


def update_mileage(mileage: int):
    """Updates the car's current mileage."""
    data = load_data()
    vehicle = get_active_vehicle(data)
    vehicle["current_mileage"] = mileage
    vehicle["mileage_last_updated"] = datetime.now().isoformat()
    save_data(data)
    return f"Mileage updated to {mileage:,} miles."


# ════════════════════════════════════════════════════════════════════════════
# CARFAX HISTORY — MANUAL ENTRY
# ════════════════════════════════════════════════════════════════════════════

def log_carfax_entry(
    service_type: str,
    date_str: str,
    mileage: int = None,
    shop: str = None,
    cost: float = None,
    notes: str = None
) -> str:
    """
    Logs a historical maintenance entry from Carfax.
    date_str format: YYYY-MM-DD (example: 2024-03-15)
    """
    data = load_data()
    vehicle = get_active_vehicle(data)

    entry = {
        "id": str(uuid.uuid4()),
        "source": "carfax",
        "service_type": service_type,
        "display_name": SERVICE_DISPLAY_NAMES.get(service_type, service_type),
        "date": date_str,
        "logged_at": datetime.now().isoformat(),
        "mileage": mileage,
        "shop": shop,
        "cost": cost,
        "notes": notes,
        "performed_by": "previous_owner"
    }

    vehicle["maintenance_log"].append(entry)
    save_data(data)

    name = SERVICE_DISPLAY_NAMES.get(service_type, service_type)
    mil = f" at {mileage:,} miles" if mileage else ""
    return f"✅ Carfax entry logged: {name} on {date_str}{mil}."


# ════════════════════════════════════════════════════════════════════════════
# MAINTENANCE LOGGING
# ════════════════════════════════════════════════════════════════════════════

def log_maintenance(
    service_type: str,
    mileage: int,
    date_str: str = None,
    date: str = None,
    shop: str = None,
    cost: float = None,
    notes: str = None,
    performed_by: str = "dealership",
    parts_used: str = None
) -> str:
    # Accept either 'date' or 'date_str' — LLaMA sometimes uses either
    if date_str is None and date is not None:
        date_str = date
    """
    Logs a maintenance event.
    performed_by: 'dealership', 'shop', 'diy'
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    data = load_data()
    vehicle = get_active_vehicle(data)

    # Update current mileage if this is higher than what we have
    if vehicle["current_mileage"] is None or mileage > vehicle["current_mileage"]:
        vehicle["current_mileage"] = mileage
        vehicle["mileage_last_updated"] = datetime.now().isoformat()

    entry = {
        "id": str(uuid.uuid4()),
        "source": "owner",
        "service_type": service_type,
        "display_name": SERVICE_DISPLAY_NAMES.get(service_type, service_type),
        "date": date_str,
        "logged_at": datetime.now().isoformat(),
        "mileage": mileage,
        "shop": shop,
        "cost": cost,
        "notes": notes,
        "performed_by": performed_by,
        "parts_used": parts_used
    }

    vehicle["maintenance_log"].append(entry)

    # Update upcoming maintenance schedule after logging
    _update_upcoming_maintenance(vehicle, service_type, mileage, date_str)

    save_data(data)

    name = SERVICE_DISPLAY_NAMES.get(service_type, service_type)
    return f"✅ Logged: {name} on {date_str} at {mileage:,} miles."


def log_gas_fillup(
    mileage: int,
    gallons: float,
    price_per_gallon: float,
    date_str: str = None,
    date: str = None
) -> str:
    """Logs a gas fill-up and calculates MPG from the previous fill-up."""
    # Accept either 'date' or 'date_str' — LLaMA sometimes uses either
    if date_str is None and date is not None:
        date_str = date
    # If date is missing, "current", "today", or otherwise invalid — use today
    if not date_str or date_str.lower() in ["current", "today", "now", ""]:
        date_str = datetime.now().strftime("%Y-%m-%d")
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        date_str = datetime.now().strftime("%Y-%m-%d")

    data = load_data()
    vehicle = get_active_vehicle(data)

    # Update current mileage
    if vehicle["current_mileage"] is None or mileage > vehicle["current_mileage"]:
        vehicle["current_mileage"] = mileage
        vehicle["mileage_last_updated"] = datetime.now().isoformat()

    # Calculate MPG from previous fill-up
    mpg = None
    gas_log = vehicle.get("gas_log", [])
    if gas_log:
        last = gas_log[-1]
        miles_driven = mileage - last["mileage"]
        if miles_driven > 0 and last.get("gallons"):
            mpg = round(miles_driven / last["gallons"], 1)

    total_cost = round(gallons * price_per_gallon, 2)

    entry = {
        "id": str(uuid.uuid4()),
        "date": date_str,
        "logged_at": datetime.now().isoformat(),
        "mileage": mileage,
        "gallons": gallons,
        "price_per_gallon": price_per_gallon,
        "total_cost": total_cost,
        "mpg": mpg
    }

    vehicle["gas_log"].append(entry)
    save_data(data)

    mpg_str = f" MPG this tank: {mpg}" if mpg else " (MPG will calculate on next fill-up)"
    return f"✅ Gas logged: {gallons} gal @ ${price_per_gallon}/gal = ${total_cost:.2f} on {date_str}.{mpg_str}"

# ════════════════════════════════════════════════════════════════════════════
# UPCOMING MAINTENANCE SCHEDULE
# ════════════════════════════════════════════════════════════════════════════

def _update_upcoming_maintenance(vehicle: dict, service_type: str, done_at_mileage: int, done_on_date: str):
    """
    After a service is logged, calculates the next due date/mileage
    and saves it to upcoming_maintenance.
    Internal function — called automatically by log_maintenance().
    """
    if service_type not in MAINTENANCE_INTERVALS:
        return

    interval = MAINTENANCE_INTERVALS[service_type]
    upcoming = vehicle.get("upcoming_maintenance", [])

    # Remove old entry for this service type if it exists
    upcoming = [u for u in upcoming if u["service_type"] != service_type]

    next_miles = None
    next_date = None

    if interval["miles"]:
        next_miles = done_at_mileage + interval["miles"]

    if interval["days"]:
        done_date_obj = datetime.strptime(done_on_date, "%Y-%m-%d").date()
        from datetime import timedelta
        next_date_obj = done_date_obj + timedelta(days=interval["days"])
        next_date = next_date_obj.isoformat()

    upcoming.append({
        "service_type": service_type,
        "display_name": SERVICE_DISPLAY_NAMES.get(service_type, service_type),
        "last_done_mileage": done_at_mileage,
        "last_done_date": done_on_date,
        "next_due_miles": next_miles,
        "next_due_date": next_date
    })

    vehicle["upcoming_maintenance"] = upcoming


def get_upcoming_maintenance() -> str:
    """
    Returns a plain-English summary of what maintenance is coming due soon.
    Warns if within 500 miles or 30 days of due date.
    """
    data = load_data()
    vehicle = get_active_vehicle(data)
    current_mileage = vehicle.get("current_mileage")
    upcoming = vehicle.get("upcoming_maintenance", [])

    if not upcoming:
        return "No upcoming maintenance scheduled yet. Log a service to start tracking."

    today = date.today()
    warnings = []
    schedule = []

    for item in upcoming:
        name = item["display_name"]
        due_miles = item.get("next_due_miles")
        due_date = item.get("next_due_date")

        parts = []
        urgent = False

        if due_miles and current_mileage:
            miles_away = due_miles - current_mileage
            parts.append(f"due at {due_miles:,} miles ({miles_away:,} miles away)")
            if miles_away <= 500:
                urgent = True

        if due_date:
            due_date_obj = datetime.strptime(due_date, "%Y-%m-%d").date()
            days_away = (due_date_obj - today).days
            parts.append(f"due by {due_date} ({days_away} days away)")
            if days_away <= 30:
                urgent = True

        line = f"{'⚠️ ' if urgent else '• '}{name}: {' / '.join(parts)}"
        if urgent:
            warnings.append(line)
        else:
            schedule.append(line)

    result = ""
    if warnings:
        result += "COMING DUE SOON:\n" + "\n".join(warnings) + "\n\n"
    if schedule:
        result += "UPCOMING SCHEDULE:\n" + "\n".join(schedule)

    return result.strip() or "All maintenance is up to date."


# ════════════════════════════════════════════════════════════════════════════
# READING & SUMMARIZING DATA
# ════════════════════════════════════════════════════════════════════════════

def get_recent_maintenance(limit: int = 5) -> str:
    """Returns the most recent maintenance entries as a readable summary."""
    data = load_data()
    vehicle = get_active_vehicle(data)
    log = vehicle.get("maintenance_log", [])

    if not log:
        return "No maintenance history logged yet."

    # Sort by date, most recent first
    sorted_log = sorted(log, key=lambda x: x.get("date", ""), reverse=True)
    recent = sorted_log[:limit]

    lines = []
    for entry in recent:
        name = entry.get("display_name", entry.get("service_type", "Service"))
        date_str = entry.get("date", "unknown date")
        mileage = entry.get("mileage")
        shop = entry.get("shop", "")
        cost = entry.get("cost")
        by = entry.get("performed_by", "")
        source = entry.get("source", "owner")

        mil_str = f" at {mileage:,} miles" if mileage else ""
        shop_str = f" — {shop}" if shop else ""
        cost_str = f" (${cost:.2f})" if cost else ""
        by_str = f" [{by}]" if by and by != "dealership" else ""
        carfax_str = " [Carfax]" if source == "carfax" else ""

        lines.append(f"• {name} on {date_str}{mil_str}{shop_str}{cost_str}{by_str}{carfax_str}")

    return "\n".join(lines)


def get_full_maintenance_history() -> str:
    """Returns the complete maintenance log as a readable summary."""
    data = load_data()
    vehicle = get_active_vehicle(data)
    log = vehicle.get("maintenance_log", [])

    if not log:
        return "No maintenance history logged yet."

    sorted_log = sorted(log, key=lambda x: x.get("date", ""))
    lines = [f"Full maintenance history — {len(sorted_log)} entries:\n"]

    for entry in sorted_log:
        name = entry.get("display_name", entry.get("service_type", "Service"))
        date_str = entry.get("date", "unknown date")
        mileage = entry.get("mileage")
        shop = entry.get("shop", "")
        cost = entry.get("cost")
        by = entry.get("performed_by", "")
        notes = entry.get("notes", "")
        source = entry.get("source", "owner")

        mil_str = f" at {mileage:,} miles" if mileage else ""
        shop_str = f" — {shop}" if shop else ""
        cost_str = f" (${cost:.2f})" if cost else ""
        by_str = f" [{by}]" if by else ""
        carfax_str = " [Carfax]" if source == "carfax" else ""
        notes_str = f"\n  Notes: {notes}" if notes else ""

        lines.append(f"• {name} on {date_str}{mil_str}{shop_str}{cost_str}{by_str}{carfax_str}{notes_str}")

    return "\n".join(lines)


def get_gas_summary() -> str:
    """Returns a summary of gas fill-up history and average MPG."""
    data = load_data()
    vehicle = get_active_vehicle(data)
    gas_log = vehicle.get("gas_log", [])

    if not gas_log:
        return "No gas fill-ups logged yet."

    total_gallons = sum(e.get("gallons", 0) for e in gas_log)
    total_spent = sum(e.get("total_cost", 0) for e in gas_log)
    mpg_entries = [e["mpg"] for e in gas_log if e.get("mpg")]
    avg_mpg = round(sum(mpg_entries) / len(mpg_entries), 1) if mpg_entries else None

    lines = [f"Gas log — {len(gas_log)} fill-ups:"]
    lines.append(f"Total gallons: {total_gallons:.1f}")
    lines.append(f"Total spent: ${total_spent:.2f}")
    if avg_mpg:
        lines.append(f"Average MPG: {avg_mpg}")

    lines.append("\nRecent fill-ups:")
    for entry in sorted(gas_log, key=lambda x: x.get("date", ""), reverse=True)[:5]:
        mpg_str = f" | MPG: {entry['mpg']}" if entry.get("mpg") else ""
        lines.append(
            f"• {entry['date']} — {entry['gallons']} gal @ "
            f"${entry['price_per_gallon']}/gal = ${entry['total_cost']:.2f}{mpg_str}"
        )

    return "\n".join(lines)


def get_vehicle_info() -> str:
    """Returns basic vehicle info as a readable string."""
    data = load_data()
    vehicle = get_active_vehicle(data)

    mileage = vehicle.get("current_mileage")
    mil_str = f"{mileage:,} miles" if mileage else "not yet recorded"

    return (
        f"{vehicle['year']} {vehicle['make']} {vehicle['model']}\n"
        f"VIN: {vehicle['vin']}\n"
        f"Current mileage: {mil_str}"
    )


def get_data_summary_for_llm() -> str:
    """
    Builds a full plain-English summary of all vehicle data.
    This is injected into LLaMA's context before every response
    so DRIVE always knows the current state of the car.
    """
    data = load_data()
    vehicle = get_active_vehicle(data)

    mileage = vehicle.get("current_mileage")
    mil_str = f"{mileage:,} miles" if mileage else "not yet recorded"

    summary = f"""=== VEHICLE DATA SUMMARY ===
Vehicle: {vehicle['year']} {vehicle['make']} {vehicle['model']}
VIN: {vehicle['vin']}
Current mileage: {mil_str}

RECENT MAINTENANCE:
{get_recent_maintenance(5)}

GAS LOG:
{get_gas_summary()}

UPCOMING MAINTENANCE:
{get_upcoming_maintenance()}
=== END OF VEHICLE DATA ==="""

    return summary


# ════════════════════════════════════════════════════════════════════════════
# WEB SEARCH — RECALLS & BULLETINS
# ════════════════════════════════════════════════════════════════════════════

def search_automotive_web(query: str) -> str:
    """Searches the web for automotive information using SerpApi."""
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
            return "No results found for that search."

        output = f"Web search results for '{query}':\n\n"
        for r in results:
            title = r.get("title", "No title")
            snippet = r.get("snippet", "No description available")
            link = r.get("link", "")
            output += f"- {title}\n  {snippet}\n  {link}\n\n"

        return output.strip()

    except Exception as e:
        return f"Web search failed: {str(e)}"


def search_recalls() -> str:
    """Searches for Honda Civic 2016 recall notices."""
    query = "2016 Honda Civic recall notice NHTSA safety"
    result = search_automotive_web(query)

    data = load_data()
    vehicle = get_active_vehicle(data)

    # Save the recall search result to vehicle.json
    recall_entry = {
        "searched_at": datetime.now().isoformat(),
        "query": query,
        "result": result
    }
    vehicle["recalls"].append(recall_entry)
    save_data(data)

    return result


# ════════════════════════════════════════════════════════════════════════════
# ISSUE / PROBLEM TRACKING
# ════════════════════════════════════════════════════════════════════════════

def log_wiper_fluid(date_str: str = None, date: str = None, notes: str = None) -> str:
    """Logs a wiper fluid top-off using the car's current mileage."""
    # Accept either 'date' or 'date_str' — LLaMA sometimes uses either
    if date_str is None and date is not None:
        date_str = date
    data = load_data()
    vehicle = get_active_vehicle(data)
    mileage = vehicle.get("current_mileage") or 0
    return log_maintenance(
        service_type="wiper_fluid",
        mileage=mileage,
        date_str=date_str,
        notes=notes
    )

def log_issue(description: str, severity: str = "mild", date_str: str = None, date: str = None, notes: str = "") -> str:
    """
    Logs a car problem or issue to watch.
    severity: 'mild', 'moderate', 'severe'
    """
    if date_str is None and date is not None:
        date_str = date
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    data = load_data()
    vehicle = get_active_vehicle(data)

    entry = {
        "id": str(uuid.uuid4()),
        "description": description,
        "severity": severity,
        "date_reported": date_str,
        "logged_at": datetime.now().isoformat(),
        "status": "open",
        "notes": notes,
        "resolved_date": None,
        "resolution_notes": None
    }

    vehicle["issues"].append(entry)
    save_data(data)

    return f"✅ Issue logged: {description} (severity: {severity})"


def get_open_issues() -> str:
    """Returns all open (unresolved) issues."""
    data = load_data()
    vehicle = get_active_vehicle(data)
    issues = [i for i in vehicle.get("issues", []) if i.get("status") == "open"]

    if not issues:
        return "No open issues."

    lines = [f"Open issues ({len(issues)}):"]
    for issue in issues:
        lines.append(f"• [{issue['severity'].upper()}] {issue['description']} — reported {issue['date_reported']}")

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════
# MULTI-VEHICLE SUPPORT
# ════════════════════════════════════════════════════════════════════════════

def add_vehicle(make: str, model: str, year: int, vin: str = None) -> str:
    """Adds a new vehicle and sets it as active. Marks the old one as inactive."""
    data = load_data()

    # Mark all existing vehicles as inactive
    for v in data["vehicles"]:
        v["active"] = False

    new_vehicle = {
        "id": f"vehicle_{str(uuid.uuid4())[:8]}",
        "active": True,
        "make": make,
        "model": model,
        "year": year,
        "vin": vin or "",
        "current_mileage": None,
        "mileage_last_updated": None,
        "notes": "",
        "maintenance_log": [],
        "upcoming_maintenance": [],
        "gas_log": [],
        "issues": [],
        "recalls": []
    }

    data["vehicles"].append(new_vehicle)
    save_data(data)

    return f"✅ New vehicle added: {year} {make} {model}. This is now your active vehicle."


def list_vehicles() -> str:
    """Lists all vehicles in vehicle.json."""
    data = load_data()
    lines = []

    for v in data["vehicles"]:
        active_str = " [ACTIVE]" if v.get("active") else " [archived]"
        mileage = v.get("current_mileage")
        mil_str = f" — {mileage:,} miles" if mileage else ""
        lines.append(f"• {v['year']} {v['make']} {v['model']}{mil_str}{active_str}")

    return "\n".join(lines) if lines else "No vehicles on file."


# ════════════════════════════════════════════════════════════════════════════
# TEST — run this file directly to confirm everything works
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Testing DRIVE tools...\n")

    # Check if vehicle.json was created
    data = load_data()
    vehicle = get_active_vehicle(data)
    print(f"Vehicle loaded: {vehicle['year']} {vehicle['make']} {vehicle['model']}")
    print(f"VIN: {vehicle['vin']}\n")

    # Set initial mileage
    print(set_initial_mileage(45000))

    # Log a Carfax entry
    print(log_carfax_entry(
        service_type="oil_change",
        date_str="2025-06-01",
        mileage=38000,
        shop="Honda Dealership",
        cost=89.99,
        notes="Full synthetic 0W-20"
    ))

    # Log a gas fill-up
    print(log_gas_fillup(
        mileage=45000,
        gallons=11.2,
        price_per_gallon=3.45
    ))

    # Log a second gas fill-up to trigger MPG calculation
    print(log_gas_fillup(
        mileage=45350,
        gallons=10.8,
        price_per_gallon=3.50
    ))

    # Show gas summary (should show MPG now)
    print("\n" + get_gas_summary())

    # Show upcoming maintenance
    print("\n" + get_upcoming_maintenance())

    # Show full data summary
    print("\n" + get_data_summary_for_llm())

    print("\nDRIVE tools test complete.")