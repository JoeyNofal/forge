# pending_tasks.py
#
# This file manages "pending_tasks.json" — the list of build tasks that
# are currently PAUSED, waiting on Joey to click yes/no before they can
# continue. Think of it as a waiting room: a task goes in, sits there,
# and only leaves once Joey resolves it.

import json
import os
import uuid
from datetime import datetime
from filelock import FileLock

PENDING_TASKS_PATH = r"D:\Projects\NEXUS SYSTEM\data\pending_tasks.json"
REMINDERS_PATH = r"D:\Projects\NEXUS SYSTEM\data\reminders.json"

# Lock files - these are just empty marker files filelock uses to coordinate
# between processes/threads. They don't contain any real data themselves.
PENDING_TASKS_LOCK = PENDING_TASKS_PATH + ".lock"
REMINDERS_LOCK = REMINDERS_PATH + ".lock"


def _load_all():
    """
    Reads pending_tasks.json from disk and returns its contents.
    If the file doesn't exist yet, returns an empty starting structure
    instead of crashing - this is what "creates the file automatically
    on first use" actually means in practice.
    """
    if not os.path.exists(PENDING_TASKS_PATH):
        return {"tasks": []}

    with open(PENDING_TASKS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_all(data):
    """
    Writes the given data back to pending_tasks.json, creating the
    data folder first if it somehow doesn't exist.
    """
    os.makedirs(os.path.dirname(PENDING_TASKS_PATH), exist_ok=True)
    with open(PENDING_TASKS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_pending_tasks(chat_id=None):
    """
    Returns all currently pending (unresolved) tasks.
    If chat_id is given, only returns pending tasks belonging to that chat.
    This is what NEXUS calls at the start of every message to check
    "is there something we're already waiting on?"
    """
    data = _load_all()
    pending = [t for t in data["tasks"] if t["status"] == "pending"]

    if chat_id is not None:
        pending = [t for t in pending if t["chat_id"] == chat_id]

    return pending

def mark_task_mentioned(task_id):
    """
    Flips a task's mentioned_to_user flag to True, so NEXUS knows not
    to bring this specific task up again until Joey either resolves it
    or explicitly asks about it himself.
    """
    lock = FileLock(PENDING_TASKS_LOCK, timeout=10)
    with lock:
        data = _load_all()

        for task in data["tasks"]:
            if task["id"] == task_id:
                task["mentioned_to_user"] = True
                _save_all(data)
                return True

        return False

def create_pending_task(chat_id, tier, description, waiting_on_text, extra_context=""):
    """
    Creates a new pending task and saves it to disk. This is called the
    moment NEXUS or CIPHER needs to pause and wait for Joey's approval.

    chat_id          — which chat this task belongs to
    tier             — "tier1" (plan approval) or "tier2" (command approval)
    description      — plain English summary of the overall task
                        (e.g. "Add a dark mode toggle to STOCK Tracker")
    waiting_on_text  — the EXACT thing being asked right now
                        (e.g. "Run: npm install some-css-library")
    extra_context    — anything else worth remembering for when this
                        task resumes later (optional, defaults to blank)

    Returns the new task's unique ID, so the caller can reference it
    later (for example, to put it in a chat bubble's approval button).
    """
    lock = FileLock(PENDING_TASKS_LOCK, timeout=10)
    with lock:
        data = _load_all()

        new_task = {
            "id": str(uuid.uuid4()),
            "chat_id": chat_id,
            "tier": tier,
            "description": description,
            "waiting_on_text": waiting_on_text,
            "extra_context": extra_context,
            "status": "pending",          # pending, approved, denied
            "mentioned_to_user": False,   # flips to True after NEXUS brings it up once
            "created_at": datetime.now().isoformat(),
            "resolved_at": None
        }

        data["tasks"].append(new_task)
        _save_all(data)

    _create_approval_reminder(new_task["id"], description, tier)

    return new_task["id"]

def _create_approval_reminder(task_id, description, tier):
    """
    Creates a matching entry in reminders.json whenever a new pending
    task is created, so it shows up as a popup on the dashboard.
    This reminder is purely informational - clicking its buttons just
    dismisses or snoozes the NOTIFICATION. The actual yes/no approval
    buttons live in the chat itself, not on this reminder.

    task_id      — the pending task's unique ID (stored for reference,
                    not currently used to link anywhere)
    description  — plain English summary of what the task is
    tier         — "tier1" or "tier2", used to word the reminder text
    """
    lock = FileLock(REMINDERS_LOCK, timeout=10)
    with lock:
        if os.path.exists(REMINDERS_PATH):
            with open(REMINDERS_PATH, "r", encoding="utf-8") as f:
                reminders = json.load(f)
        else:
            reminders = []

        if tier == "tier1":
            title = "NEXUS needs your approval"
            message = f"NEXUS is waiting on you to approve a plan: {description}"
        else:
            title = "NEXUS needs your approval"
            message = f"NEXUS is waiting on you to approve a command for: {description}"

        new_reminder = {
            "id": f"reminder_{uuid.uuid4().hex}",
            "title": title,
            "message": message,
            "remind_at": "general",
            "created_at": datetime.now().isoformat(),
            "status": "active",
            "related_task_id": task_id
        }

        reminders.append(new_reminder)

        with open(REMINDERS_PATH, "w", encoding="utf-8") as f:
            json.dump(reminders, f, indent=2)

def resolve_task(task_id, approved):
    """
    Marks a pending task as approved or denied, based on Joey's click.

    task_id   — the unique ID of the task being resolved
    approved  — True if Joey clicked yes, False if Joey clicked no

    Returns the full task dictionary so the caller can see what it was
    waiting on (needed to actually continue the work afterward).
    Returns None if no task with that ID was found.
    """
    lock = FileLock(PENDING_TASKS_LOCK, timeout=10)
    with lock:
        data = _load_all()

        for task in data["tasks"]:
            if task["id"] == task_id:
                task["status"] = "approved" if approved else "denied"
                task["resolved_at"] = datetime.now().isoformat()
                _save_all(data)
                found_task = task
                break
        else:
            return None

    _dismiss_reminder_for_task(task_id)
    return found_task


def _dismiss_reminder_for_task(task_id):
    """
    Finds any reminder(s) linked to this task via related_task_id and
    marks them dismissed, so resolving a task in chat also clears its
    popup notification automatically — no manual "Mark as Read" needed.
    """
    lock = FileLock(REMINDERS_LOCK, timeout=10)
    with lock:
        if not os.path.exists(REMINDERS_PATH):
            return

        with open(REMINDERS_PATH, "r", encoding="utf-8") as f:
            reminders = json.load(f)

        for r in reminders:
            if r.get("related_task_id") == task_id:
                r["status"] = "dismissed"

        with open(REMINDERS_PATH, "w", encoding="utf-8") as f:
            json.dump(reminders, f, indent=2)


def get_task_by_id(task_id):
    """
    Looks up a single task by its ID, regardless of status.
    Useful for checking details without resolving it.
    """
    data = _load_all()
    for task in data["tasks"]:
        if task["id"] == task_id:
            return task
    return None