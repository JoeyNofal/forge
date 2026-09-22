# This file gives NEXUS four real abilities on Joey's laptop:
# Tool 1 — Open apps (Financial Tracker, standard Windows apps)
# Tool 2 — Browse the web and summarize results with sources
# Tool 3 — Set reminders (saved locally to a file)
# Tool 4 — Read, move, and organize files and folders

import os
import json
import subprocess  # Lets Python run commands on Windows, like opening apps
import requests
import os
from dotenv import load_dotenv
load_dotenv(r"D:\Projects\NEXUS SYSTEM\.env", override=True)
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
from datetime import datetime

# The root of the NEXUS project
NEXUS_ROOT = r"D:\Projects\NEXUS SYSTEM"

# Where reminders are saved
REMINDERS_FILE = os.path.join(NEXUS_ROOT, "data", "reminders.json")

# Known apps NEXUS can open
# Each entry has a name and how to open it
KNOWN_APPS = {
    "financial tracker": {
        "type": "electron",
        "path": r"D:\Projects\Financial Tracker\FinancialTracker\Files",
        "command": "electron ."
    },
    "notepad": {
        "type": "windows",
        "command": "notepad"
    },
    "calculator": {
        "type": "windows",
        "command": "calc"
    },
    "chrome": {
        "type": "windows",
        "command": "start chrome"
    },
    "explorer": {
        "type": "windows",
        "command": "explorer"
    },
    "task manager": {
        "type": "windows",
        "command": "taskmgr"
    }
}


# ==============================================================================
# TOOL 1 — OPEN APPS
# ==============================================================================

def open_app(app_name):
    """
    Opens an app on Joey's laptop by name.
    
    app_name — the name of the app to open (example: "financial tracker")
    """
    # Convert to lowercase so "Financial Tracker" and "financial tracker" both work
    app_key = app_name.lower().strip()

    if app_key not in KNOWN_APPS:
        available = ", ".join(KNOWN_APPS.keys())
        return f"I don't know how to open '{app_name}'. Apps I can open: {available}"

    app = KNOWN_APPS[app_key]

    try:
        if app["type"] == "electron":
            # For Electron apps, we need to open a terminal in the app's folder
            # and run the command there
            subprocess.Popen(
                app["command"],
                cwd=app["path"],  # cwd means "current working directory" — run from this folder
                shell=True        # shell=True lets us run it like a terminal command
            )
            return f"Opening {app_name}... launching from {app['path']}"

        elif app["type"] == "windows":
            # For standard Windows apps, just run the command directly
            subprocess.Popen(app["command"], shell=True)
            return f"Opening {app_name}..."

    except Exception as e:
        return f"Failed to open {app_name}: {str(e)}"


# ==============================================================================
# TOOL 2 — WEB SEARCH WITH SOURCES
# ==============================================================================

def search_web(query):
    """
    Searches the web using SerpApi and returns results with sources.

    query — what to search for

    IMPORTANT: a real failure (timeout, network error, bad response)
    returns a string starting with "[WEB SEARCH FAILED]" — callers
    must treat this differently from a legitimate empty-results case.
    Collapsing the two together previously let NEXUS quietly fill the
    gap with unrelated memory content and state it as fact.
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
            return f"[Web search ran successfully but found no results for '{query}'.]"

        output = f"Search results for: '{query}'\n"
        output += "=" * 40 + "\n"
        for r in results:
            title = r.get("title", "No title")
            snippet = r.get("snippet", "No description available")
            link = r.get("link", "")
            output += f"- {title}\n  {snippet}\n  {link}\n\n"

        return output.strip()

    except Exception as e:
        print(f"[WEB SEARCH ERROR] query={query!r} | {type(e).__name__}: {e}")
        return (
            f"[WEB SEARCH FAILED] The search itself failed and returned "
            f"no data ({type(e).__name__}). Do not use memory or prior "
            f"knowledge to answer as if the search had succeeded — "
            f"plainly tell the user the search failed and that you "
            f"don't have current information to answer confidently."
        )


# ==============================================================================
# TOOL 3 — REMINDERS
# ==============================================================================

def set_reminder(title, message, remind_at=None):
    """
    Saves a reminder to a local file.
    The dashboard will display these as pop-ups later.
    
    title     — short name for the reminder (example: "Gym session")
    message   — the full reminder text
    remind_at — optional date/time string (example: "2024-12-25 09:00")
                if not provided, saves as a general reminder
    """
    # Load existing reminders if the file exists
    if os.path.exists(REMINDERS_FILE):
        with open(REMINDERS_FILE, "r") as f:
            reminders = json.load(f)
    else:
        reminders = []

    # Create the new reminder
    new_reminder = {
        "id": f"reminder_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "title": title,
        "message": message,
        "remind_at": remind_at if remind_at else "general",
        "created_at": datetime.now().isoformat(),
        "status": "active"
    }

    reminders.append(new_reminder)

    # Save back to file
    with open(REMINDERS_FILE, "w") as f:
        json.dump(reminders, f, indent=2)

    if remind_at:
        return f"Reminder set: '{title}' at {remind_at}"
    else:
        return f"Reminder saved: '{title}'"

def snooze_reminder(reminder_id, snooze_until_iso):
    """
    Marks a reminder as snoozed until a specific future time, instead
    of dismissing it permanently. The reminder will reappear once that
    time has passed.

    reminder_id      — the ID of the reminder to snooze
    snooze_until_iso — an ISO-format timestamp string for when the
                        reminder should come back (example:
                        "2026-06-28T09:00:00")
    """
    if not os.path.exists(REMINDERS_FILE):
        return "No reminders file found."

    with open(REMINDERS_FILE, "r") as f:
        reminders = json.load(f)

    found = False
    for r in reminders:
        if r["id"] == reminder_id:
            r["status"] = "snoozed"
            r["snoozed_until"] = snooze_until_iso
            found = True
            break

    if not found:
        return f"Reminder {reminder_id} not found."

    with open(REMINDERS_FILE, "w") as f:
        json.dump(reminders, f, indent=2)

    return f"Reminder {reminder_id} snoozed until {snooze_until_iso}"

def list_reminders():
    """
    Returns all active reminders.
    """
    if not os.path.exists(REMINDERS_FILE):
        return "No reminders saved yet."

    with open(REMINDERS_FILE, "r") as f:
        reminders = json.load(f)

    active = [r for r in reminders if r["status"] == "active"]

    if not active:
        return "No active reminders."

    output = f"Active reminders ({len(active)}):\n"
    output += "=" * 40 + "\n"
    for r in active:
        output += f"- [{r['id']}] {r['title']}\n"
        output += f"  {r['message']}\n"
        if r['remind_at'] != "general":
            output += f"  Scheduled: {r['remind_at']}\n"
        output += "\n"

    return output


# ==============================================================================
# TOOL 4 — FILE SYSTEM
# ==============================================================================

def read_file(full_path):
    """
    Reads and returns the contents of any file on the laptop.
    
    full_path — the complete path to the file

    Tries a few different text encodings before giving up (some files
    aren't saved as plain UTF-8), and if the file genuinely isn't
    readable text at all (an icon, an .exe, a compiled file, etc.),
    reports that clearly instead of crashing.
    """
    if not os.path.exists(full_path):
        return f"ERROR: File not found — {full_path}"

    if os.path.isdir(full_path):
        return f"ERROR: {full_path} is a folder, not a file — use LIST_FOLDER to see what's inside it."

    encodings_to_try = ["utf-8", "utf-8-sig", "utf-16", "cp1252"]

    for encoding in encodings_to_try:
        try:
            with open(full_path, "r", encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception as e:
            return f"ERROR: Could not read {full_path} — {str(e)}"

    return f"ERROR: {full_path} doesn't look like a readable text file (tried several text encodings, none worked) — it's likely a binary file such as an image, executable, or compiled file."


def move_file(source_path, destination_path):
    """
    Moves a file from one location to another.
    
    source_path      — where the file currently is
    destination_path — where to move it
    """
    if not os.path.exists(source_path):
        return f"ERROR: Source file not found — {source_path}"

    # Create the destination folder if it doesn't exist
    os.makedirs(os.path.dirname(destination_path), exist_ok=True)

    os.rename(source_path, destination_path)
    return f"File moved: {source_path} → {destination_path}"


def list_folder(full_path):
    """
    Lists all files and folders inside a directory.
    
    full_path — the complete path to the folder
    """
    if not os.path.exists(full_path):
        return f"ERROR: Folder not found — {full_path}"

    output = f"Contents of: {full_path}\n"
    output += "=" * 40 + "\n"

    for item in os.listdir(full_path):
        item_path = os.path.join(full_path, item)
        if os.path.isdir(item_path):
            output += f"  [folder] {item}/\n"
        else:
            output += f"  [file]   {item}\n"

    return output


# ==============================================================================
# TEST BLOCK
# ==============================================================================
if __name__ == "__main__":
    print("Testing NEXUS tools...\n")

    # Test 1 — Set a reminder
    print("TEST 1 — Set a reminder:")
    result = set_reminder(
        title="Test Reminder",
        message="This is a test reminder from NEXUS.",
        remind_at="2026-12-25 09:00"
    )
    print(result)

    # Test 2 — List reminders
    print("\nTEST 2 — List reminders:")
    print(list_reminders())

    # Test 3 — List the NEXUS folder
    print("\nTEST 3 — List NEXUS folder:")
    print(list_folder(NEXUS_ROOT))

    # Test 4 — Web search
    print("\nTEST 4 — Web search:")
    print(search_web("Python programming language"))

    # Test 5 — Open app (we'll just verify it's recognized, not actually open it)
    print("\nTEST 5 — App recognition:")
    for app in KNOWN_APPS:
        print(f"  Known app: {app}")