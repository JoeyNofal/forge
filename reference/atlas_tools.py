# atlas_tools.py
# A.T.L.A.S. data engine
# Creates, reads, and manages fitness.json
# Also handles web search for fitness research

import json
import os
import re
import uuid
import requests
from filelock import FileLock
import ollama
import os
from dotenv import load_dotenv
load_dotenv(r"D:\Projects\NEXUS SYSTEM\.env", override=True)
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
from datetime import datetime

# Path to the fitness data file
FITNESS_DATA_PATH = r"D:\Projects\NEXUS SYSTEM\data\fitness.json"


# ─────────────────────────────────────────────
# SECTION 1 — FITNESS.JSON SETUP
# Creates the file if it doesn't exist yet
# ─────────────────────────────────────────────

def initialize_fitness_data():
    """
    Creates fitness.json with a clean starting structure if it doesn't exist.
    Safe to call every time — does nothing if the file already exists.
    """
    if os.path.exists(FITNESS_DATA_PATH):
        return  # File already exists, leave it alone

    starting_structure = {
        "profile": {
            "name": "Joey",
            "units": "imperial",
            "notes": "Former competitive swimmer. Specialized in breaststroke, IM, and long-distance freestyle. Also did open water. Currently training casually to get back in shape."
        },
        "workouts": [],
        "body_metrics": [],
        "injuries": [
            {
                "id": str(uuid.uuid4()),
                "date_logged": datetime.now().isoformat(),
                "description": "No injuries currently on file. Add as needed.",
                "status": "none"
            }
        ],
        "plans": []
    }

    with open(FITNESS_DATA_PATH, "w") as f:
        json.dump(starting_structure, f, indent=2)

    print("fitness.json created successfully.")


def load_fitness_data() -> dict:
    """
    Loads and returns the entire fitness.json file as a Python dictionary.
    Initializes the file first if it doesn't exist.
    """
    initialize_fitness_data()
    with open(FITNESS_DATA_PATH, "r") as f:
        return json.load(f)


def save_fitness_data(data: dict):
    """
    Saves the entire fitness dictionary back to fitness.json.
    Called after any change is made.
    """
    with open(FITNESS_DATA_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ─────────────────────────────────────────────
# SECTION 2 — WORKOUT LOGGING
# ─────────────────────────────────────────────

def log_swim_workout(
    total_distance_yards: float,
    duration_minutes: int,
    strokes: list,
    sets: list,
    difficulty: int,
    form_notes: str,
    weaknesses: str,
    coach_notes: str,
    date: str = None
) -> str:
    """
    Logs a swim workout to fitness.json.

    total_distance_yards — total yards swum in the session
    duration_minutes     — how long the session lasted
    strokes              — list of strokes used, e.g. ["breaststroke", "freestyle"]
    sets                 — list of sets, each a dict: {"description": "4x50 free", "distance_yards": 200}
    difficulty           — self-rated difficulty 1-10
    form_notes           — what good form things were noticed
    weaknesses           — what needs improvement
    coach_notes          — ATLAS's coaching observations or feedback
    date                 — optional, defaults to today
    """
    lock = FileLock(FITNESS_DATA_PATH + ".lock", timeout=10)
    with lock:
        data = load_fitness_data()

        workout = {
            "id": str(uuid.uuid4()),
            "type": "swim",
            "date": date if date else datetime.now().strftime("%Y-%m-%d"),
            "logged_at": datetime.now().isoformat(),
            "total_distance_yards": total_distance_yards,
            "duration_minutes": duration_minutes,
            "strokes": strokes,
            "sets": sets,
            "difficulty_1_to_10": difficulty,
            "form_notes": form_notes,
            "weaknesses": weaknesses,
            "coach_notes": coach_notes
        }

        data["workouts"].append(workout)
        save_fitness_data(data)

    return f"Swim workout logged: {total_distance_yards} yards in {duration_minutes} minutes on {workout['date']}."


def log_gym_workout(
    exercises: list,
    duration_minutes: int,
    difficulty: int,
    form_notes: str,
    weaknesses: str,
    coach_notes: str,
    date: str = None
) -> str:
    """
    Logs a gym workout to fitness.json.

    exercises        — list of exercises, each a dict:
                       {"name": "bench press", "sets": 3, "reps": 8, "weight_lbs": 135, "notes": "felt strong"}
    duration_minutes — how long the session lasted
    difficulty       — self-rated difficulty 1-10
    form_notes       — what good form things were noticed
    weaknesses       — what needs improvement
    coach_notes      — ATLAS's coaching observations or feedback
    date             — optional, defaults to today
    """
    lock = FileLock(FITNESS_DATA_PATH + ".lock", timeout=10)
    with lock:
        data = load_fitness_data()

        workout = {
            "id": str(uuid.uuid4()),
            "type": "gym",
            "date": date if date else datetime.now().strftime("%Y-%m-%d"),
            "logged_at": datetime.now().isoformat(),
            "exercises": exercises,
            "duration_minutes": duration_minutes,
            "difficulty_1_to_10": difficulty,
            "form_notes": form_notes,
            "weaknesses": weaknesses,
            "coach_notes": coach_notes
        }

        data["workouts"].append(workout)
        save_fitness_data(data)

    return f"Gym workout logged: {len(exercises)} exercise(s) in {duration_minutes} minutes on {workout['date']}."


def log_injury(description: str, severity: str = "mild", date_str: str = None, notes: str = "", status: str = "active") -> str:
    """
    Logs or updates an injury record.

    description — what the injury is (e.g. "left shoulder strain")
    severity    — "mild", "moderate", "severe"
    date_str    — optional date string, defaults to today
    notes       — optional additional notes
    status      — "active", "recovering", or "resolved"
    """
    lock = FileLock(FITNESS_DATA_PATH + ".lock", timeout=10)
    with lock:
        data = load_fitness_data()

        injury = {
            "id": str(uuid.uuid4()),
            "date_logged": date_str if date_str else datetime.now().strftime("%Y-%m-%d"),
            "description": description,
            "severity": severity,
            "notes": notes,
            "status": status
        }

        data["injuries"].append(injury)
        save_fitness_data(data)

    return f"Injury logged: {description} — Severity: {severity} — Status: {status}"


# ─────────────────────────────────────────────
# SECTION 3 — READING AND ANALYSIS
# ─────────────────────────────────────────────

def get_recent_workouts(limit: int = 10) -> str:
    """
    Returns the most recent workouts as a readable summary.
    limit — how many to return (default: 10)
    """
    data = load_fitness_data()
    workouts = [w for w in data.get("workouts", []) if isinstance(w, dict)]

    if not workouts:
        return "No workouts logged yet."

    # Sort by date, most recent first
    sorted_workouts = sorted(workouts, key=lambda w: w["date"], reverse=True)
    recent = sorted_workouts[:limit]

    lines = [f"Last {min(limit, len(recent))} workout(s):\n"]
    for w in recent:
        if w["type"] == "swim":
            lines.append(
                f"  [{w['date']}] SWIM — {w['total_distance_yards']} yards, "
                f"{w['duration_minutes']} min, difficulty {w['difficulty_1_to_10']}/10"
            )
        elif w["type"] == "gym":
            exercise_names = [
                e["name"] if isinstance(e, dict) else str(e)
                for e in w.get("exercises", [])
            ]
            lines.append(
                f"  [{w['date']}] GYM — {', '.join(exercise_names)}, "
                f"{w['duration_minutes']} min, difficulty {w['difficulty_1_to_10']}/10"
            )

    return "\n".join(lines)


def _safe_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0


def get_swim_history() -> str:
    """
    Returns a full summary of all swim workouts ever logged.
    """
    data = load_fitness_data()
    workouts = [w for w in data.get("workouts", []) if isinstance(w, dict) and w.get("type") == "swim"]

    if not workouts:
        return "No swim workouts logged yet."

    total_yards = sum(_safe_num(w.get("total_distance_yards", 0)) for w in workouts)
    total_sessions = len(workouts)
    avg_yards = total_yards / total_sessions if total_sessions > 0 else 0

    sorted_workouts = sorted(workouts, key=lambda w: w["date"])

    lines = [
        f"Swim history: {total_sessions} session(s), {total_yards:,.0f} total yards, "
        f"avg {avg_yards:,.0f} yards/session\n"
    ]
    for w in sorted_workouts:
        lines.append(
            f"  [{w['date']}] {w['total_distance_yards']} yards — "
            f"Strokes: {', '.join(w.get('strokes', []))} — "
            f"Difficulty: {w['difficulty_1_to_10']}/10"
        )
        if w.get("weaknesses"):
            lines.append(f"    Weaknesses: {w['weaknesses']}")

    return "\n".join(lines)


def get_gym_history() -> str:
    """
    Returns a full summary of all gym workouts ever logged.
    """
    data = load_fitness_data()
    workouts = [w for w in data.get("workouts", []) if isinstance(w, dict) and w.get("type") == "gym"]

    if not workouts:
        return "No gym workouts logged yet."

    total_sessions = len(workouts)
    sorted_workouts = sorted(workouts, key=lambda w: w["date"])

    lines = [f"Gym history: {total_sessions} session(s)\n"]
    for w in sorted_workouts:
        exercise_names = [
            e["name"] if isinstance(e, dict) else str(e)
            for e in w.get("exercises", [])
        ]
        lines.append(
            f"  [{w['date']}] {', '.join(exercise_names)} — "
            f"{w['duration_minutes']} min — Difficulty: {w['difficulty_1_to_10']}/10"
        )
        if w.get("weaknesses"):
            lines.append(f"    Weaknesses: {w['weaknesses']}")

    return "\n".join(lines)


def get_injury_history() -> str:
    """
    Returns all logged injuries and their current status.
    """
    data = load_fitness_data()
    injuries = data.get("injuries", [])

    # Filter out the default placeholder entry
    real_injuries = [i for i in injuries if i.get("status") != "none"]

    if not real_injuries:
        return "No injuries on record."

    lines = ["Injury history:\n"]
    for i in real_injuries:
        date_str = i.get("date_logged", "")[:10]
        lines.append(f"  [{date_str}] {i['description']} — Status: {i['status']}")

    return "\n".join(lines)


def get_data_summary_for_llm() -> str:
    """
    Builds a full plain-English summary of Joey's fitness data.
    This gets passed to LLaMA so ATLAS has full context before responding.
    """
    data = load_fitness_data()
    workouts = [w for w in data.get("workouts", []) if isinstance(w, dict)]
    swim_workouts = [w for w in workouts if w.get("type") == "swim"]
    gym_workouts = [w for w in workouts if w.get("type") == "gym"]

    recent = get_recent_workouts(5)
    injuries = get_injury_history()

    summary = f"""
=== ATLAS DATA SUMMARY ===
Profile: {data['profile']['name']} — {data['profile']['notes']}

Total workouts logged: {len(workouts)}
  Swim sessions: {len(swim_workouts)}
  Gym sessions: {len(gym_workouts)}

{recent}

{injuries}
=========================
"""
    return summary.strip()


# ─────────────────────────────────────────────
# SECTION 3.5 — WORKOUT PHOTO EXTRACTION
# Reads a whiteboard workout plan or smartwatch summary screen photo
# ─────────────────────────────────────────────

def extract_workout_items_from_image(image_path: str) -> list:
    """
    Looks at a photo of a whiteboard workout plan, a smartwatch/fitness
    app summary screen, or a handwritten training log, and returns a
    list of dicts -- one per distinct workout session detected:

    Swim workout dict:
      {"workout_type": "swim", "total_distance_yards": <number or None>,
       "duration_minutes": <number or None>, "difficulty": <1-10 or None>,
       "date": "YYYY-MM-DD" or None, "strokes": [list of strings],
       "form_notes": "", "weaknesses": "", "coach_notes": "",
       "confidence": "high" or "low"}

    Gym workout dict:
      {"workout_type": "gym", "duration_minutes": <number or None>,
       "difficulty": <1-10 or None>, "date": "YYYY-MM-DD" or None,
       "exercises": [{"name": "...", "sets": <n or None>, "reps": <n or None>,
                       "weight_lbs": <n or None>, "notes": ""}],
       "form_notes": "", "weaknesses": "", "coach_notes": "",
       "confidence": "high" or "low"}

    confidence is "low" when handwriting/screen content is genuinely
    hard to read -- still include your best guess, just flag it.

    Returns an empty list if no workout content is found, or if
    something goes wrong (bad image, model error, etc.) -- callers
    should treat an empty list as "nothing to do here," not an error.
    """
    print(f"[WORKOUT SCAN DEBUG] extract_workout_items_from_image called with: {image_path}")
    prompt = (
        "Look at this photo. It may be a whiteboard workout plan, a "
        "smartwatch or fitness app summary screen, or a handwritten "
        "training log. Identify every distinct workout session shown.\n\n"
        "For each session, decide if it's a SWIM workout or a GYM workout.\n\n"
        "For a SWIM workout, extract: total_distance_yards, duration_minutes, "
        "difficulty (1-10 if shown, otherwise null), date (YYYY-MM-DD if "
        "visible, otherwise null), and strokes (a list of strings, e.g. "
        "[\"freestyle\", \"breaststroke\"]).\n\n"
        "For a GYM workout, extract: duration_minutes, difficulty (1-10 if "
        "shown, otherwise null), date (YYYY-MM-DD if visible, otherwise "
        "null), and exercises -- a list of objects, each shaped exactly "
        "like {\"name\": \"bench press\", \"sets\": 3, \"reps\": 8, "
        "\"weight_lbs\": 135, \"notes\": \"\"}. If sets/reps/weight aren't "
        "shown for an exercise, use null for that field.\n\n"
        "If a field genuinely isn't visible in the photo, use null. Do not "
        "guess numbers that aren't there.\n\n"
        "Respond with ONLY a JSON array, nothing else -- no explanation, "
        "no markdown, no code fences. Each item must include a "
        "\"workout_type\" key set to exactly \"swim\" or \"gym\", and a "
        "\"confidence\" key set to exactly \"high\" or \"low\" -- use "
        "\"low\" whenever the handwriting or screen is hard to read.\n\n"
        "Example of the exact format expected:\n"
        '[{"workout_type": "swim", "total_distance_yards": 2000, '
        '"duration_minutes": 60, "difficulty": 7, "date": "2026-03-01", '
        '"strokes": ["freestyle"], "confidence": "high"}]\n\n'
        "If you see no workout content at all, respond with an empty "
        "array: []"
    )

    try:
        print(f"[WORKOUT SCAN DEBUG] about to call ollama.chat for vision...")
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
        print(f"[WORKOUT SCAN DEBUG] ollama.chat returned successfully")
        raw_text = response["message"]["content"].strip()
        print(f"[WORKOUT SCAN DEBUG] raw_text: {raw_text[:300]}")

        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)
        raw_text = raw_text.strip()

        # Robustness: if the model added prose before/after the array
        # despite instructions not to, pull out just the outermost
        # [...] block instead of failing outright.
        first_bracket = raw_text.find("[")
        last_bracket = raw_text.rfind("]")
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            raw_text = raw_text[first_bracket:last_bracket + 1]

        items = json.loads(raw_text)

        clean_items = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                wtype = item.get("workout_type")
                if wtype not in ("swim", "gym"):
                    continue

                base = {
                    "workout_type": wtype,
                    "duration_minutes": item.get("duration_minutes"),
                    "difficulty": item.get("difficulty"),
                    "date": item.get("date"),
                    "form_notes": "",
                    "weaknesses": "",
                    "coach_notes": "",
                    "confidence": item.get("confidence", "high")
                }

                if wtype == "swim":
                    base["total_distance_yards"] = item.get("total_distance_yards")
                    strokes = item.get("strokes", [])
                    base["strokes"] = strokes if isinstance(strokes, list) else []
                else:
                    exercises_raw = item.get("exercises", [])
                    clean_exercises = []
                    if isinstance(exercises_raw, list):
                        for ex in exercises_raw:
                            if isinstance(ex, dict) and ex.get("name"):
                                clean_exercises.append({
                                    "name": str(ex.get("name", "")).strip(),
                                    "sets": ex.get("sets"),
                                    "reps": ex.get("reps"),
                                    "weight_lbs": ex.get("weight_lbs"),
                                    "notes": str(ex.get("notes", "")).strip()
                                })
                    base["exercises"] = clean_exercises

                clean_items.append(base)

        return clean_items

    except Exception as e:
        print(f"[WORKOUT SCAN EXTRACTION ERROR] {str(e)}")
        return []


# ─────────────────────────────────────────────
# SECTION 4 — WEB SEARCH
# ─────────────────────────────────────────────

def search_fitness_web(query: str) -> str:
    """
    Searches the web for fitness, swimming technique, or recovery science info.
    Uses SerpApi to query Google search results reliably.
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
            return "Web search returned no results. Try rephrasing or ask ATLAS to answer from its training knowledge."

        output = f"Web search results for '{query}':\n\n"
        for r in results:
            title = r.get("title", "No title")
            snippet = r.get("snippet", "No description available")
            link = r.get("link", "")
            output += f"- {title}\n  {snippet}\n  {link}\n\n"

        return output.strip()

    except Exception as e:
        return f"Web search failed: {str(e)}"


# ─────────────────────────────────────────────
# RUN THIS FILE DIRECTLY TO TEST IT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("Initializing fitness.json...")
    initialize_fitness_data()

    print("\nLogging a test swim workout...")
    result = log_swim_workout(
        total_distance_yards=2000,
        duration_minutes=60,
        strokes=["breaststroke", "freestyle"],
        sets=[
            {"description": "400 warm-up freestyle", "distance_yards": 400},
            {"description": "8x100 breaststroke on 2:00", "distance_yards": 800},
            {"description": "4x200 freestyle steady", "distance_yards": 800}
        ],
        difficulty=7,
        form_notes="Breaststroke pullout felt strong. Good hip rotation on freestyle.",
        weaknesses="Breaststroke kick timing is off. Breathing too early.",
        coach_notes="Focus on delayed breath in breaststroke. Kick should finish before breath."
    )
    print(result)

    print("\nLogging a test gym workout...")
    result = log_gym_workout(
        exercises=[
            {"name": "bench press", "sets": 3, "reps": 8, "weight_lbs": 135, "notes": "felt solid"},
            {"name": "pull-ups", "sets": 3, "reps": 6, "weight_lbs": 0, "notes": "bodyweight"},
            {"name": "lat pulldown", "sets": 3, "reps": 10, "weight_lbs": 100, "notes": "good range of motion"}
        ],
        duration_minutes=50,
        difficulty=6,
        form_notes="Good depth on pull-ups.",
        weaknesses="Upper back rounds slightly on bench.",
        coach_notes="Cue: retract scapula before bench press."
    )
    print(result)

    print("\nRecent workouts:")
    print(get_recent_workouts())

    print("\nData summary for LLaMA:")
    print(get_data_summary_for_llm())