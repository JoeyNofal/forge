"""
DRIVE LOGGING — the ONLY place DRIVE writes to vehicle.json
(increment (b), Part 1). drive_tools.py stays read-only.

Two jobs:
1. NORMALIZE: turn whatever a model extracted (untrusted, possibly
   malformed) into a clean, exactly-shaped record, or raise a clear
   ValueError. (Lesson #5: never trust the shape.)
2. WRITE: add the clean record to the vehicle file under ONE lock for the
   whole read-modify-write (Lesson #4), via shared/file_store.update_json.
   If anything goes wrong inside, nothing is written at all.

Nothing in here talks to a model or to the approval queue — those are
separate, separately-tested parts (Parts 2 and 3).

Decisions baked in (all confirmed with Joey):
- Field names follow the DRIVE Tracker app: due_mileage / due_date,
  reported_date, severity low/medium/high. The readers in drive_tools.py
  accept the old agent's names too.
- Nothing is invented: unstated mileage / cost / severity / performed-by
  are saved as null (0 counts as "not stated"). A missing or future date
  becomes today.
- performed_by is "shop" or "diy" (dealership counts as shop).
- A service logged for an OLDER date never rewinds the next-due schedule.
- MPG comes from the nearest EARLIER fill-up by mileage.
- Current mileage only goes UP automatically (a service or fill-up at a
  higher reading raises it). Stating a mileage outright sets it, even if lower.
- Issues can be marked resolved; reopening is not done here.
"""
import re
import uuid
from datetime import datetime, timedelta

from shared.file_store import update_json
from agents.drive import issue_match
from agents.drive.drive_tools import (
    get_data_path, initialize_vehicle_data, get_active_vehicle,
    _starting_structure, MAINTENANCE_INTERVALS, SERVICE_DISPLAY_NAMES,
)

MAX_TEXT = 1000
MAX_LIST = 30
MAX_MILEAGE = 2_000_000
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# A generic word in the "shop" field is not a business name ("at the dealership").
_GENERIC_SHOP_WORDS = frozenset({
    "shop", "dealership", "dealer", "garage", "mechanic",
    "the shop", "the dealership", "the dealer", "the garage", "the mechanic",
    "a shop", "a dealership", "a garage", "a mechanic",
    "my shop", "my garage", "my mechanic",
})

# Brake work, worded differently by the real model every time ("brake pad replacement",
# "brake repair", "brakes replaced"). Lights/bulbs/fluid/lines are NOT brake replacement.
_BRAKE_WORK_WORDS = frozenset({"replacement", "replace", "replaced", "repair", "repaired",
                               "pad", "rotor", "caliper"})
_NOT_BRAKE_WORK = frozenset({"light", "bulb", "lamp", "fluid", "line", "hose", "sensor", "switch"})

# A service that restarts ANOTHER service's schedule: new brakes restart the brake-inspection clock.
SCHEDULE_RESETS = {"brake_replacement": "brake_inspection"}

PERFORMED_BY_ALIASES = {
    "shop": "shop", "dealership": "shop", "dealer": "shop",
    "mechanic": "shop", "garage": "shop",
    "diy": "diy", "self": "diy", "myself": "diy", "me": "diy", "owner": "diy",
}
SEVERITY_ALIASES = {
    "low": "low", "mild": "low", "minor": "low",
    "medium": "medium", "moderate": "medium",
    "high": "high", "severe": "high", "major": "high", "critical": "high",
}


# ─────────────────────────────────────────────
# SECTION 1 — NORMALIZERS (untrusted in, clean out, or ValueError)
# ─────────────────────────────────────────────

def _num(v, low, high, what):
    """Number in [low, high]; None/''/non-numeric -> 0 (= not stated); out of range -> ValueError."""
    if v is None or v == "" or isinstance(v, bool):
        return 0
    if isinstance(v, str):
        v = v.replace(",", "").replace("$", "").strip()
    try:
        n = float(v)
    except (TypeError, ValueError):
        return 0
    if n != n or n < low or n > high:   # n != n catches NaN
        raise ValueError(f"{what} out of range: {v!r}")
    return int(n) if n == int(n) else n


def _mileage(v):
    """A stated odometer reading as a whole number, or None if not stated."""
    n = _num(v, 0, MAX_MILEAGE, "mileage")
    return int(round(n)) if n else None


def _text(v) -> str:
    if v is None or isinstance(v, dict):
        return ""
    if isinstance(v, list):
        v = ", ".join(str(x) for x in v if x not in (None, ""))
    return str(v).strip()[:MAX_TEXT]


def _str_list(v) -> list:
    """List of short strings from a list OR a comma-separated string."""
    if v is None or v == "":
        return []
    if isinstance(v, str):
        v = v.split(",")
    if not isinstance(v, list):
        return []
    out = []
    for x in v:
        if isinstance(x, dict):
            x = x.get("description") or x.get("name") or ""
        s = str(x).strip()
        if s:
            out.append(s[:200])
    return out[:MAX_LIST]


def _date(v) -> str:
    """A real, non-future YYYY-MM-DD, else today."""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        d = datetime.strptime(str(v).strip()[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return today
    return d if d <= today else today


def _require_dict(raw, kind):
    if not isinstance(raw, dict):
        raise ValueError(f"{kind}: expected an object, got {type(raw).__name__}")


def _service(raw):
    """(service_type, display_name). A known service becomes its snake_case key;
    anything else is kept as the text Joey gave."""
    text = _text(raw.get("service_type") or raw.get("service") or raw.get("display_name"))
    if not text:
        raise ValueError("maintenance: no service stated")
    key = re.sub(r"[\s\-]+", "_", text.lower()).strip("_")
    if key == "gas":
        raise ValueError("maintenance: gas fill-ups are logged as fill-ups, not maintenance")
    if key in SERVICE_DISPLAY_NAMES:
        return key, SERVICE_DISPLAY_NAMES[key]
    words = issue_match.content_words(text)
    if "brake" in words and words & _BRAKE_WORK_WORDS and not words & _NOT_BRAKE_WORK:
        return "brake_replacement", SERVICE_DISPLAY_NAMES["brake_replacement"]
    if "_" in text and " " not in text:        # a model echoing snake_case: "turbo_swap"
        text = text.replace("_", " ")
    return text, text


def normalize_mileage(raw) -> dict:
    _require_dict(raw, "mileage update")
    m = _mileage(raw.get("mileage"))
    if m is None:
        raise ValueError("mileage update: no mileage stated")
    return {"mileage": m}


def normalize_maintenance(raw) -> dict:
    _require_dict(raw, "maintenance")
    service_type, display_name = _service(raw)
    cost = _num(raw.get("cost"), 0, 1_000_000, "cost")
    shop_text = _text(raw.get("shop"))
    generic_shop = shop_text.lower() in _GENERIC_SHOP_WORDS
    performed_by = PERFORMED_BY_ALIASES.get(_text(raw.get("performed_by")).lower())
    if performed_by is None and generic_shop:
        performed_by = "shop"        # he did say a shop did it; what he said about WHO did it always wins
    return {
        "service_type": service_type,
        "display_name": display_name,
        "date": _date(raw.get("date")),
        "mileage": _mileage(raw.get("mileage")),
        "shop": None if generic_shop else (shop_text or None),
        "cost": cost or None,
        "notes": _text(raw.get("notes")),
        "performed_by": performed_by,
        "parts_used": _str_list(raw.get("parts_used")),
    }


def normalize_fillup(raw) -> dict:
    _require_dict(raw, "fill-up")
    gallons = _num(raw.get("gallons"), 0, 100, "gallons")
    ppg = _num(raw.get("price_per_gallon"), 0, 50, "price per gallon")
    total = _num(raw.get("total_cost"), 0, 1000, "total cost")
    if not gallons and not total:
        raise ValueError("fill-up: state the gallons or the total cost")
    if not total and gallons and ppg:
        total = round(gallons * ppg, 2)
    if not ppg and gallons and total:
        ppg = round(total / gallons, 3)
    return {
        "date": _date(raw.get("date")),
        "mileage": _mileage(raw.get("mileage")),
        "gallons": gallons or None,
        "price_per_gallon": ppg or None,
        "total_cost": total or None,
    }


def normalize_issue(raw) -> dict:
    _require_dict(raw, "issue")
    description = _text(raw.get("description"))
    if not description:
        raise ValueError("issue: no description stated")
    return {
        "description": description,
        "severity": SEVERITY_ALIASES.get(_text(raw.get("severity")).lower()),   # None = not stated
        "date": _date(raw.get("date") or raw.get("reported_date")),
        "notes": _text(raw.get("notes")),
    }


def normalize_issue_update(raw) -> dict:
    _require_dict(raw, "issue update")
    issue_id = _text(raw.get("issue_id"))
    if not issue_id:
        raise ValueError("issue update: no issue id")
    status = _text(raw.get("new_status")).lower()
    if status != "resolved":
        raise ValueError(f"issue update: new_status must be 'resolved', got {status!r}")
    return {
        "issue_id": issue_id,
        "new_status": status,
        "resolution_notes": _text(raw.get("resolution_notes") or raw.get("notes")),
        "date": _date(raw.get("date")),
    }


# ─────────────────────────────────────────────
# SECTION 2 — LOCKED WRITERS
# ─────────────────────────────────────────────

def _modify_vehicle(change_fn):
    """
    Locked read-modify-write on the ACTIVE vehicle.
    change_fn(vehicle) -> (changed: bool, value). If it raises, NOTHING is written.
    Returns `value`.
    """
    initialize_vehicle_data()
    out = {}

    def _modify(data):
        if not isinstance(data, dict):
            raise RuntimeError("vehicle file has the wrong shape (expected an object)")
        vehicle = get_active_vehicle(data)     # raises RuntimeError if no usable vehicle
        changed, value = change_fn(vehicle)
        out["value"] = value
        if changed:
            data["last_updated"] = datetime.now().isoformat()
        return data

    update_json(get_data_path(), _modify, default=_starting_structure())
    return out["value"]


def _list_for_append(vehicle: dict, key: str) -> list:
    """The vehicle's list at `key`, created if missing/null; refuses to overwrite a non-list."""
    current = vehicle.get(key)
    if current is None:
        vehicle[key] = []
    elif not isinstance(current, list):
        raise RuntimeError(f"vehicle file: '{key}' is not a list — refusing to overwrite it")
    return vehicle[key]


def _maybe_raise_mileage(vehicle: dict, mileage) -> bool:
    """Raise current_mileage if `mileage` is higher (or none is recorded). Never lowers it."""
    if mileage is None:
        return False
    current = vehicle.get("current_mileage")
    if isinstance(current, bool) or not isinstance(current, (int, float)) or mileage > current:
        vehicle["current_mileage"] = mileage
        vehicle["mileage_last_updated"] = datetime.now().isoformat()
        return True
    return False


def _update_schedule(vehicle: dict, m: dict):
    """
    After a service is logged, work out the next-due entry.
    Returns (status, entry): 'updated' / 'kept' (an equal-or-newer service is already
    on the schedule, so an older one never rewinds it) / 'none' (no schedule for this service).
    """
    key = SCHEDULE_RESETS.get(m["service_type"], m["service_type"])
    interval = MAINTENANCE_INTERVALS.get(key)
    if not interval:
        return "none", None

    upcoming = vehicle.get("upcoming_maintenance")
    if upcoming is None:
        upcoming = []
    elif not isinstance(upcoming, list):
        raise RuntimeError("vehicle file: 'upcoming_maintenance' is not a list — refusing to overwrite it")

    same = [u for u in upcoming if isinstance(u, dict) and u.get("service_type") == key]
    done_dates = [str(u.get("last_done_date")) for u in same
                  if _ISO_DATE.match(str(u.get("last_done_date") or ""))]
    newest_done = max(done_dates, default="")
    if newest_done and m["date"] < newest_done:
        return "kept", None

    due_mileage = None
    if m["mileage"] and interval.get("miles"):
        due_mileage = m["mileage"] + interval["miles"]
    due_date = None
    if interval.get("days"):
        due_date = (datetime.strptime(m["date"], "%Y-%m-%d")
                    + timedelta(days=interval["days"])).strftime("%Y-%m-%d")

    entry = {
        "service_type": key,
        "display_name": SERVICE_DISPLAY_NAMES.get(key, key),
        "last_done_mileage": m["mileage"],
        "last_done_date": m["date"],
        "due_mileage": due_mileage,
        "due_date": due_date,
    }
    others = [u for u in upcoming if not (isinstance(u, dict) and u.get("service_type") == key)]
    vehicle["upcoming_maintenance"] = others + [entry]
    return "updated", entry


def _compute_mpg(gas_log: list, f: dict):
    """(mpg, reason). Uses the nearest EARLIER fill-up by mileage (not list order)."""
    if not f["mileage"] or not f["gallons"]:
        return None, "it needs both a mileage and the gallons"
    prev = None
    for g in gas_log:
        if not isinstance(g, dict):
            continue
        pm = g.get("mileage")
        if isinstance(pm, bool) or not isinstance(pm, (int, float)):
            continue
        if pm < f["mileage"] and (prev is None or pm > prev):
            prev = pm
    if prev is None:
        return None, "there is no earlier fill-up with a lower mileage on file"
    mpg = round((f["mileage"] - prev) / f["gallons"], 1)
    if mpg < 1 or mpg > 150:
        return None, "the result looked implausible"
    return mpg, ""


def log_mileage(raw) -> str:
    m = normalize_mileage(raw)

    def change(vehicle):
        old = vehicle.get("current_mileage")
        vehicle["current_mileage"] = m["mileage"]
        vehicle["mileage_last_updated"] = datetime.now().isoformat()
        return True, old

    old = _modify_vehicle(change)
    text = f"Mileage updated to {m['mileage']:,} miles."
    if isinstance(old, (int, float)) and not isinstance(old, bool) and m["mileage"] < old:
        text += f" (This is LOWER than the previous {old:,.0f}.)"
    return text


def log_maintenance(raw) -> str:
    m = normalize_maintenance(raw)
    record = {
        "id": str(uuid.uuid4()),
        "source": "owner",
        "service_type": m["service_type"],
        "display_name": m["display_name"],
        "date": m["date"],
        "logged_at": datetime.now().isoformat(),
        "mileage": m["mileage"],
        "shop": m["shop"],
        "cost": m["cost"],
        "notes": m["notes"],
        "performed_by": m["performed_by"],
        "parts_used": m["parts_used"],
    }

    def change(vehicle):
        _list_for_append(vehicle, "maintenance_log").append(record)
        raised = _maybe_raise_mileage(vehicle, m["mileage"])
        status, entry = _update_schedule(vehicle, m)
        return True, (raised, status, entry)

    raised, status, entry = _modify_vehicle(change)
    mil = f" at {m['mileage']:,} miles" if m["mileage"] else ""
    msg = f"Maintenance logged: {m['display_name']} on {m['date']}{mil}."
    if status == "updated":
        parts = []
        if entry["due_mileage"]:
            parts.append(f"{entry['due_mileage']:,} miles")
        if entry["due_date"]:
            parts.append(entry["due_date"])
        if parts:
            label = "" if entry["service_type"] == m["service_type"] else f" for {entry['display_name']}"
            msg += f" Next due{label}: " + " / ".join(parts) + "."
    elif status == "kept":
        msg += " (The upcoming schedule already reflects a newer service, so it was left alone.)"
    if raised:
        msg += f" Current mileage raised to {m['mileage']:,}."
    return msg


def log_fillup(raw) -> str:
    f = normalize_fillup(raw)

    def change(vehicle):
        gas = _list_for_append(vehicle, "gas_log")
        mpg, note = _compute_mpg(gas, f)
        gas.append({
            "id": str(uuid.uuid4()),
            "date": f["date"],
            "logged_at": datetime.now().isoformat(),
            "mileage": f["mileage"],
            "gallons": f["gallons"],
            "price_per_gallon": f["price_per_gallon"],
            "total_cost": f["total_cost"],
            "mpg": mpg,
        })
        raised = _maybe_raise_mileage(vehicle, f["mileage"])
        return True, (mpg, note, raised)

    mpg, note, raised = _modify_vehicle(change)
    parts = []
    if f["gallons"]:
        parts.append(f"{f['gallons']} gal")
    if f["price_per_gallon"]:
        parts.append(f"${f['price_per_gallon']}/gal")
    if f["total_cost"]:
        parts.append(f"${f['total_cost']:.2f} total")
    mil = f" at {f['mileage']:,} miles" if f["mileage"] else ""
    msg = f"Fill-up logged: {', '.join(parts)} on {f['date']}{mil}."
    msg += f" MPG this tank: {mpg}." if mpg else f" MPG not calculated ({note})."
    if raised:
        msg += f" Current mileage raised to {f['mileage']:,}."
    return msg


def log_issue(raw) -> str:
    i = normalize_issue(raw)
    record = {
        "id": str(uuid.uuid4()),
        "description": i["description"],
        "severity": i["severity"],
        "status": "open",
        "reported_date": i["date"],
        "logged_at": datetime.now().isoformat(),
        "notes": i["notes"],
        "resolved_date": None,
        "resolution_notes": None,
    }

    def change(vehicle):
        _list_for_append(vehicle, "issues").append(record)
        return True, None

    _modify_vehicle(change)
    return f"Issue logged: {i['description']} (severity: {i['severity'] or 'not stated'})."


def update_issue_status(raw) -> tuple:
    """
    Marks ONE issue (matched by exact id) as resolved. Returns (ok, message).
    Never guesses: unknown id / already resolved -> (False, message), nothing changed.
    Choosing WHICH issue Joey means is the extraction step's job (Part 3).
    """
    u = normalize_issue_update(raw)

    def change(vehicle):
        issues = vehicle.get("issues")
        if not isinstance(issues, list):
            return False, (False, "No issues are on file, so nothing was changed.")
        match = [x for x in issues if isinstance(x, dict) and x.get("id") == u["issue_id"]]
        if not match:
            return False, (False, f"No issue with id {u['issue_id']} is on file. Nothing was changed.")
        issue = match[0]
        current = issue.get("status") or "open"
        if current == u["new_status"]:
            return False, (False, f"That issue is already {current}. Nothing was changed.")
        issue["status"] = "resolved"
        issue["resolved_date"] = u["date"]
        issue["resolution_notes"] = u["resolution_notes"] or None
        return True, (True, f"Issue marked resolved: {issue.get('description') or 'no description'}.")

    return _modify_vehicle(change)



# ─────────────────────────────────────────────
# SECTION 3 — RESOLVE SEVERAL ISSUES AT ONCE ("everything is fixed")
# ─────────────────────────────────────────────

MAX_BULK_ISSUES = 50


def normalize_issues_update(raw) -> dict:
    _require_dict(raw, "issues update")
    ids = raw.get("issue_ids")
    if not isinstance(ids, list):
        raise ValueError("issues update: issue_ids must be a list")
    clean_ids = []
    for x in ids:
        s = _text(x)
        if s and s not in clean_ids:
            clean_ids.append(s)
    if not clean_ids:
        raise ValueError("issues update: no issue ids given")
    if len(clean_ids) > MAX_BULK_ISSUES:
        raise ValueError(f"issues update: too many issues at once (max {MAX_BULK_ISSUES})")
    status = _text(raw.get("new_status")).lower()
    if status != "resolved":
        raise ValueError(f"issues update: new_status must be 'resolved', got {status!r}")
    return {
        "issue_ids": clean_ids,
        "new_status": status,
        "resolution_notes": _text(raw.get("resolution_notes") or raw.get("notes")),
        "date": _date(raw.get("date")),
    }


def update_issues_status(raw) -> tuple:
    """
    Marks every listed issue that is still unresolved as resolved, all under ONE
    lock. Unknown or already-resolved ids are skipped and reported. Returns
    (ok, message); if nothing could be resolved, nothing is changed.
    """
    u = normalize_issues_update(raw)

    def change(vehicle):
        issues = vehicle.get("issues")
        if not isinstance(issues, list):
            return False, (False, "No issues are on file, so nothing was changed.")
        by_id = {x["id"]: x for x in issues if isinstance(x, dict) and isinstance(x.get("id"), str)}
        done, skipped = [], 0
        for iid in u["issue_ids"]:
            issue = by_id.get(iid)
            if issue is None or (issue.get("status") or "open") == "resolved":
                skipped += 1
                continue
            issue["status"] = "resolved"
            issue["resolved_date"] = u["date"]
            issue["resolution_notes"] = u["resolution_notes"] or None
            done.append(str(issue.get("description") or "no description"))
        if not done:
            return False, (False, "None of those issues were still open, so nothing was changed.")
        msg = f"Marked {len(done)} issue(s) resolved: " + "; ".join(done) + "."
        if skipped:
            msg += f" ({skipped} skipped: not found or already resolved.)"
        return True, (True, msg)

    return _modify_vehicle(change)



# ─────────────────────────────────────────────
# SECTION 4 — THE BRAKE REMINDER (one approved entry)
# ─────────────────────────────────────────────

def has_brake_schedule(vehicle) -> bool:
    """True if a brake inspection is already on this vehicle's schedule."""
    if not isinstance(vehicle, dict):
        return False
    upcoming = vehicle.get("upcoming_maintenance")
    return isinstance(upcoming, list) and any(
        isinstance(u, dict) and u.get("service_type") == "brake_inspection" for u in upcoming)


def log_brake_reminder() -> tuple:
    """
    Adds ONE 'Brake Inspection, due today' schedule entry so it sorts first on the tracker
    until Joey logs brake work (which replaces it with the normal interval). Under the lock,
    refuses to add a second one. Returns (ok, message).
    """
    today = datetime.now().strftime("%Y-%m-%d")

    def change(vehicle):
        upcoming = vehicle.get("upcoming_maintenance")
        if upcoming is None:
            upcoming = []
        elif not isinstance(upcoming, list):
            raise RuntimeError("vehicle file: 'upcoming_maintenance' is not a list — refusing to overwrite it")
        if has_brake_schedule(vehicle):
            return False, (False, "A brake inspection is already on your schedule, so nothing was added.")
        vehicle["upcoming_maintenance"] = upcoming + [{
            "service_type": "brake_inspection",
            "display_name": SERVICE_DISPLAY_NAMES["brake_inspection"],
            "last_done_mileage": None,
            "last_done_date": None,
            "due_mileage": None,
            "due_date": today,
        }]
        return True, (True, f"Brake reminder added: Brake Inspection is due {today}, so it shows up first "
                            "until you log a brake inspection or a brake replacement.")

    return _modify_vehicle(change)