"""
Standardized, locked read-modify-write for shared JSON data files.
Pulls the working FileLock pattern already proven in the old
pending_tasks.py / atlas_tools.py into one reusable function, instead
of it being re-copy-pasted (and potentially re-broken) per file.
"""
import json
import os
from filelock import FileLock

def load_json(path: str, default):
    """Reads a JSON file. Returns `default` if the file doesn't exist yet."""
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def update_json(path: str, update_fn, default, timeout: int = 10):
    """
    Locked read-modify-write. update_fn takes the current data and
    returns the new data to save — the lock is held for the entire
    read+modify+write, so two simultaneous callers can never silently
    stomp on each other (Lesson #4).

    path      — full path to the JSON file
    update_fn — function: (current_data) -> new_data
    default   — starting value if the file doesn't exist yet
    timeout   — seconds to wait for the lock before giving up

    Returns the new data that was saved.
    """
    lock_path = path + ".lock"
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with FileLock(lock_path, timeout=timeout):
        current = load_json(path, default)
        new_data = update_fn(current)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)
        return new_data