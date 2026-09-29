# stock_tools.py
# This is STOCK's data engine.
# It creates and manages two files:
#   - pantry.json      : everything Joey has at home
#   - grocery_list.json: everything Joey needs to buy
# This file never deletes data destructively — it only updates and appends.

import json
import os
from datetime import datetime

# ─── FILE PATHS ───────────────────────────────────────────────────────────────

PANTRY_PATH = r"D:\Projects\NEXUS SYSTEM\data\pantry.json"
GROCERY_PATH = r"D:\Projects\NEXUS SYSTEM\data\grocery_list.json"


# ─── SETUP ────────────────────────────────────────────────────────────────────

def _load_pantry():
    """Loads pantry.json from disk and returns it as a Python dictionary."""
    if not os.path.exists(PANTRY_PATH):
        return {"items": [], "last_updated": ""}
    with open(PANTRY_PATH, "r") as f:
        return json.load(f)


def _save_pantry(data):
    """Saves the pantry dictionary back to pantry.json on disk."""
    data["last_updated"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(PANTRY_PATH), exist_ok=True)
    with open(PANTRY_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _load_grocery():
    """Loads grocery_list.json from disk and returns it as a Python dictionary."""
    if not os.path.exists(GROCERY_PATH):
        return {"items": [], "last_cleared": ""}
    with open(GROCERY_PATH, "r") as f:
        return json.load(f)


def _save_grocery(data):
    """Saves the grocery dictionary back to grocery_list.json on disk."""
    os.makedirs(os.path.dirname(GROCERY_PATH), exist_ok=True)
    with open(GROCERY_PATH, "w") as f:
        json.dump(data, f, indent=2)


def initialize_data_files():
    """
    Creates pantry.json and grocery_list.json if they don't exist yet.
    Called once when STOCK starts up for the first time.
    """
    if not os.path.exists(PANTRY_PATH):
        _save_pantry({"items": [], "last_updated": ""})
        print("  Created pantry.json")

    if not os.path.exists(GROCERY_PATH):
        _save_grocery({"items": [], "last_cleared": ""})
        print("  Created grocery_list.json")


# ─── CONTAINER GROUP HELPERS ──────────────────────────────────────────────────
# A "container group" lets one item track multiple package sizes at once.
# Example: 2 bottles of milk, each 1 gallon, PLUS 1 bottle that's 0.5 gallon.
# Each group looks like:
#   {"count": 2, "container_label": "bottle", "size": 1, "size_unit": "gal"}
#
# Items that don't need this just have an empty container_groups list ([])
# and keep using the plain old "quantity" + "unit" fields like before.
# Nothing about old-style items changes.

def _format_container_groups(groups):
    """
    Turns a list of container groups into a readable string.
    Example: [{"count":2,"container_label":"bottle","size":1,"size_unit":"gal"}]
    becomes: "2 bottles (1 gal each)"

    Multiple groups are joined with commas:
    "2 bottles (1 gal each), 1 bottle (0.5 gal)"
    """
    if not groups:
        return ""

    parts = []
    for g in groups:
        count = g.get("count")
        label = g.get("container_label", "").strip()
        size = g.get("size")
        size_unit = g.get("size_unit", "").strip()

        # Pluralize the container word if count is not 1 (bottle -> bottles)
        if label:
            label_display = label if count == 1 else (label + "s" if not label.endswith("s") else label)
        else:
            label_display = ""

        count_part = f"{count} {label_display}".strip() if count is not None else label_display

        if size is not None and size_unit:
            if count == 1:
                size_part = f"({size} {size_unit})"
            else:
                size_part = f"({size} {size_unit} each)"
            parts.append(f"{count_part} {size_part}".strip())
        else:
            parts.append(count_part)

    return ", ".join(parts)


def get_total_quantity(item):
    """
    Sums up the total amount of an item across all its container groups,
    grouped by unit. Used by FLAME to know how much of something is
    actually available, regardless of how it's packaged.

    Returns a dict like: {"gal": 2.5, "ml": 200}
    If the item has no container_groups, falls back to its plain
    quantity/unit fields instead.

    Example: 2 bottles @ 1 gal + 1 bottle @ 0.5 gal -> {"gal": 2.5}
    """
    groups = item.get("container_groups") or []
    totals = {}

    if groups:
        for g in groups:
            count = g.get("count") or 0
            size = g.get("size") or 0
            unit = g.get("size_unit", "").strip()
            if not unit:
                continue
            totals[unit] = totals.get(unit, 0) + (count * size)
        return totals

    # No groups — fall back to the simple quantity/unit fields.
    qty = item.get("quantity")
    unit = item.get("unit", "").strip()
    if qty is not None and unit:
        totals[unit] = qty
    return totals


def _describe_item_amount(item):
    """
    Builds the display text for one item's amount —
    either the container group description, or the plain quantity/unit
    if there are no groups. Used by get_pantry() and get_grocery_list().
    """
    groups = item.get("container_groups") or []
    if groups:
        return _format_container_groups(groups)

    if item.get("quantity"):
        return f"{item['quantity']} {item.get('unit', '')}".strip()

    return ""


# ─── PANTRY FUNCTIONS ─────────────────────────────────────────────────────────

def log_pantry_item(name: str, quantity=None, unit: str = None, notes: str = "", container_groups=None):
    """
    Adds a new item to the pantry, or updates it if it already exists.

    name             — the ingredient name (e.g. "chicken breast")
    quantity         — how much Joey has (e.g. 2, 1.5) — optional, used when
                        there's just one simple amount (no container groups)
    unit             — the unit of measurement (e.g. "pieces", "liters") — optional
    notes            — any extra notes (e.g. "in the freezer") — optional
    container_groups — optional list of {"count","container_label","size","size_unit"}
                        dicts, used when an item has multiple package sizes
                        (e.g. 2 bottles at 1 gal each). Leave as None/empty
                        for simple items — they'll just use quantity/unit.
    """
    pantry = _load_pantry()

    # Check if this item already exists in the pantry (case-insensitive).
    existing = None
    for item in pantry["items"]:
        if item["name"].lower() == name.lower():
            existing = item
            break

    if existing:
        # Update the existing item.
        if quantity is not None:
            existing["quantity"] = quantity
        if unit:
            existing["unit"] = unit
        if notes:
            existing["notes"] = notes
        if container_groups is not None:
            existing["container_groups"] = container_groups
        existing["status"] = "in_stock"
        existing["last_updated"] = datetime.now().isoformat()
        result = f"Updated '{name}' in pantry."
    else:
        # Add a new item.
        pantry["items"].append({
            "name": name,
            "quantity": quantity,
            "unit": unit if unit else "",
            "container_groups": container_groups if container_groups else [],
            "status": "in_stock",
            "notes": notes,
            "added_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat()
        })
        result = f"Added '{name}' to pantry."

    _save_pantry(pantry)
    return result


def mark_out_of_stock(name: str):
    """
    Marks a pantry item as out of stock.
    The item stays in the pantry list but is flagged as out_of_stock.
    Clears both the plain quantity AND any container groups, since
    being "out of stock" means none of it is left, regardless of
    how it was packaged.
    It does NOT automatically go on the grocery list — Joey asks for that separately.

    name — the ingredient to mark as out (e.g. "milk")
    """
    pantry = _load_pantry()

    for item in pantry["items"]:
        if item["name"].lower() == name.lower():
            item["status"] = "out_of_stock"
            item["quantity"] = 0
            item["container_groups"] = []
            item["last_updated"] = datetime.now().isoformat()
            _save_pantry(pantry)
            return f"Marked '{name}' as out of stock."

    return f"'{name}' was not found in the pantry."


def remove_pantry_item(name: str):
    """
    Completely removes an item from the pantry.
    Used when something is no longer relevant (e.g. a one-time ingredient).

    name — the item to remove
    """
    pantry = _load_pantry()
    before = len(pantry["items"])
    pantry["items"] = [
        i for i in pantry["items"]
        if i["name"].lower() != name.lower()
    ]

    if len(pantry["items"]) < before:
        _save_pantry(pantry)
        return f"Removed '{name}' from pantry."
    return f"'{name}' was not found in the pantry."


def get_pantry():
    """
    Returns the full pantry contents as a readable summary string.
    Separates in-stock items from out-of-stock items.
    """
    pantry = _load_pantry()
    items = pantry["items"]

    if not items:
        return "The pantry is empty."

    in_stock = [i for i in items if i.get("status") == "in_stock"]
    out_of_stock = [i for i in items if i.get("status") == "out_of_stock"]

    lines = []

    if in_stock:
        lines.append("IN STOCK:")
        for item in in_stock:
            amount = _describe_item_amount(item)
            note = f" ({item['notes']})" if item.get("notes") else ""
            lines.append(f"  - {item['name']}" + (f": {amount}" if amount else "") + note)

    if out_of_stock:
        lines.append("\nOUT OF STOCK:")
        for item in out_of_stock:
            lines.append(f"  - {item['name']}")

    return "\n".join(lines)


# ============================================================
# IMAGE-BASED PANTRY EXTRACTION
# Sends a photo to local Gemma 3 12B (vision-capable) and asks it
# to identify every distinct food/grocery item it can see, returning
# structured data instead of a plain description. Used when Joey sends
# STOCK a pantry/fridge photo instead of typing out items by hand.
# ============================================================
import ollama
import json
import re


def extract_pantry_items_from_image(image_path: str) -> list:
    """
    Looks at a photo and returns a list of dicts, one per detected item:
      {"name": "...", "quantity": <number or None>, "unit": "...", "confidence": "high" or "low"}

    confidence is "low" when Gemma is genuinely unsure what something is
    (e.g. an unlabeled jar) — the name field will contain its best guess
    with a question mark, e.g. "unlabeled spice (possibly cinnamon?)"

    Returns an empty list if no food/grocery items are found, or if
    something goes wrong (bad image, Gemma error, etc.) — callers should
    treat an empty list as "nothing to do here," not as an error.
    """
    print(f"[PANTRY SCAN DEBUG] extract_pantry_items_from_image called with: {image_path}")
    prompt = (
        "Look at this photo of a pantry, fridge, or grocery items. "
        "Identify every distinct food or grocery item you can see.\n\n"
        "For each item, try to estimate a quantity and unit if it's "
        "visually obvious (e.g. '2' jars, '1' carton, '6' eggs). If you "
        "can't tell the quantity, leave it out.\n\n"
        "If something is unclear or unlabeled, still include it, but mark "
        "your best guess clearly with a question mark in the name, like "
        "'unlabeled spice jar (possibly cinnamon?)'.\n\n"
        "Respond with ONLY a JSON array, nothing else — no explanation, "
        "no markdown formatting, no code fences. Each item in the array "
        "must be an object with these exact keys: \"name\", \"quantity\", "
        "\"unit\", \"confidence\".\n\n"
        "\"confidence\" must be exactly \"high\" or \"low\" — use \"low\" "
        "whenever you marked the name with a question mark or you're "
        "genuinely guessing.\n\n"
        "If quantity is unknown, use null (not a string, not a guess).\n\n"
        "If unit is unknown or doesn't apply, use an empty string \"\".\n\n"
        "Example of the exact format expected:\n"
        '[{"name": "milk", "quantity": 1, "unit": "carton", "confidence": "high"}, '
        '{"name": "unlabeled spice jar (possibly cinnamon?)", "quantity": 1, "unit": "jar", "confidence": "low"}]\n\n'
        "If you see no food or grocery items at all, respond with an "
        "empty array: []"
    )

    try:
        print(f"[PANTRY SCAN DEBUG] about to call ollama.chat for vision...")
        response = ollama.chat(
            model="gemma3:12b",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [str(image_path)]
                }
            ],
            options={"num_predict": 1024}
        )
        print(f"[PANTRY SCAN DEBUG] ollama.chat returned successfully")
        raw_text = response["message"]["content"].strip()
        print(f"[PANTRY SCAN DEBUG] raw_text: {raw_text[:300]}")

        # Gemma sometimes wraps JSON in ```json ... ``` even when told not to.
        # Strip that off if it's there before trying to parse.
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)
        raw_text = raw_text.strip()

        items = json.loads(raw_text)

        # Safety check — make sure it's actually a list of dicts with the
        # fields we expect, and quietly skip anything malformed rather
        # than crashing the whole extraction over one bad entry.
        clean_items = []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("name"):
                    clean_items.append({
                        "name": str(item.get("name", "")).strip(),
                        "quantity": item.get("quantity"),
                        "unit": str(item.get("unit", "")).strip(),
                        "confidence": item.get("confidence", "high")
                    })
        return clean_items

    except Exception as e:
        print(f"[PANTRY IMAGE EXTRACTION ERROR] {str(e)}")
        return []

# ─── GROCERY LIST FUNCTIONS ───────────────────────────────────────────────────

def add_to_grocery_list(name: str, quantity=None, unit: str = None, notes: str = "", container_groups=None):
    """
    Adds an item to the grocery list.
    If it's already on the list, updates it instead of duplicating.

    name             — what to buy (e.g. "olive oil")
    quantity         — how much (e.g. 1) — optional
    unit             — unit of measurement (e.g. "bottle") — optional
    notes            — any extra notes (e.g. "any brand is fine") — optional
    container_groups — optional list of package-size groups, same format
                        as log_pantry_item()
    """
    grocery = _load_grocery()

    # Check if it's already on the list.
    existing = None
    for item in grocery["items"]:
        if item["name"].lower() == name.lower() and item["status"] == "needed":
            existing = item
            break

    if existing:
        if quantity is not None:
            existing["quantity"] = quantity
        if unit:
            existing["unit"] = unit
        if notes:
            existing["notes"] = notes
        if container_groups is not None:
            existing["container_groups"] = container_groups
        existing["last_updated"] = datetime.now().isoformat()
        result = f"Updated '{name}' on the grocery list."
    else:
        grocery["items"].append({
            "name": name,
            "quantity": quantity,
            "unit": unit if unit else "",
            "container_groups": container_groups if container_groups else [],
            "status": "needed",
            "notes": notes,
            "added_at": datetime.now().isoformat()
        })
        result = f"Added '{name}' to the grocery list."

    _save_grocery(grocery)
    return result


def mark_grocery_bought(name: str, quantity=None, unit: str = None, container_groups=None):
    """
    Marks a grocery list item as bought and moves it into the pantry.
    This is how Joey updates the pantry after shopping — one item at a time.

    Container groups carry over from the grocery list entry into the
    pantry automatically, unless new ones are passed in here.

    name             — what was bought
    quantity         — how much was bought (optional, can update from list)
    unit             — unit of measurement (optional)
    container_groups — optional override for package-size groups; if not
                        given, whatever was on the grocery list entry
                        carries over to the pantry as-is
    """
    grocery = _load_grocery()

    found = False
    final_qty = quantity
    final_unit = unit
    final_groups = container_groups

    for item in grocery["items"]:
        if item["name"].lower() == name.lower() and item["status"] == "needed":
            item["status"] = "bought"
            item["bought_at"] = datetime.now().isoformat()
            found = True

            # Use the quantity/unit/groups from the grocery list if not specified now.
            final_qty = quantity if quantity is not None else item.get("quantity")
            final_unit = unit if unit else item.get("unit", "")
            final_groups = container_groups if container_groups is not None else item.get("container_groups", [])
            break

    if not found:
        return f"'{name}' was not found on the grocery list."

    _save_grocery(grocery)

    # Now add it to the pantry, carrying the container groups over.
    pantry_result = log_pantry_item(name, final_qty, final_unit, container_groups=final_groups)
    return f"Marked '{name}' as bought. {pantry_result}"


def remove_from_grocery_list(name: str):
    """
    Removes an item from the grocery list entirely.
    Used when something on the list is no longer needed.

    name — the item to remove
    """
    grocery = _load_grocery()
    before = len(grocery["items"])
    grocery["items"] = [
        i for i in grocery["items"]
        if not (i["name"].lower() == name.lower() and i["status"] == "needed")
    ]

    if len(grocery["items"]) < before:
        _save_grocery(grocery)
        return f"Removed '{name}' from the grocery list."
    return f"'{name}' was not found on the grocery list."


def get_grocery_list():
    """
    Returns only the currently needed items on the grocery list.
    Already-bought items are not shown.
    """
    grocery = _load_grocery()
    needed = [i for i in grocery["items"] if i["status"] == "needed"]

    if not needed:
        return "The grocery list is empty."

    lines = ["GROCERY LIST:"]
    for item in needed:
        amount = _describe_item_amount(item)
        note = f" — {item['notes']}" if item.get("notes") else ""
        lines.append(f"  - {item['name']}" + (f": {amount}" if amount else "") + note)

    return "\n".join(lines)


# ─── CONTEXT FOR LLAMA ────────────────────────────────────────────────────────

def get_data_summary_for_llm():
    """
    Builds a plain-English summary of the pantry and grocery list.
    This is injected into LLaMA's context before every response
    so it always knows what Joey has and what he needs.
    """
    pantry_summary = get_pantry()
    grocery_summary = get_grocery_list()

    return f"""=== CURRENT PANTRY STATE ===
{pantry_summary}

=== CURRENT GROCERY LIST ===
{grocery_summary}
"""