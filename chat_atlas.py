"""Simple terminal chat with ATLAS (temporary, until the dashboard exists).

Run from the project folder:
    python chat_atlas.py            your REAL data (the files in the data folder)
    python chat_atlas.py --test     throwaway test files: your real data is never touched

Type  quit  to leave.

PASTING A WORKOUT LOG: just paste it. When the first line is "FORGE WORKOUT LOG", the script keeps
collecting lines until you type  END  on its own line and press Enter. (Typing  paste  first also works.)
"""
import os
import re
import sys
import tempfile

# --test points every ATLAS data file at throwaway files INSIDE this one run (nothing lingers in your
# terminal afterwards). It must happen before ATLAS is imported.
TEST_MODE = "--test" in sys.argv[1:]
if TEST_MODE:
    _tmp = tempfile.gettempdir()
    for _var, _name in (("TRAINING_PROFILE_PATH", "profile"), ("ATLAS_SETUP_STATE_PATH", "setup"), ("PENDING_ACTIONS_PATH", "pending"),
                        ("FITNESS_DATA_PATH", "fitness"), ("EXERCISE_LIBRARY_PATH", "library")):
        os.environ[_var] = os.path.join(_tmp, f"forge_chat_test_{_name}.json")

from agents.atlas import atlas_tools  # noqa: E402
from agents.atlas import training_profile  # noqa: E402
from agents.atlas.chat import stream_atlas  # noqa: E402

# A line that belongs INSIDE a workout log. If one arrives on its own, the log was pasted without its
# first line, and sending it to ATLAS line by line would just make ATLAS talk about every fragment.
LOG_PIECE = re.compile(r"^\s*(##\s|Exercise:|Prescribed:|Set\s+\d+:|RPE:|Notes:|Title:|Date:|Unit:|Program:|Day:)", re.IGNORECASE)


def banner() -> str:
    real_profile = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "training_profile.json"))
    using = os.path.abspath(training_profile.get_profile_path())
    if TEST_MODE:
        mode = "TEST MODE (throwaway files; your real data is not used)"
    elif using == real_profile:
        mode = "REAL DATA"
    else:
        mode = "WARNING: a TRAINING_PROFILE_PATH setting in this terminal is redirecting the profile to a different file"
    return f"{mode}\n  profile: {using}\n  fitness log: {os.path.abspath(atlas_tools.get_data_path())}"


def read_until_end() -> str:
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def read_message() -> str:
    first = input("\nYou: ").strip()
    if first.lower() == "paste":
        print("(Paste now, then type END on its own line and press Enter.)")
        return read_until_end()
    if first.upper().startswith("FORGE WORKOUT LOG"):
        print("(Workout log detected. Keep pasting; when the paste is finished, type END on its own line and press Enter.)")
        rest = read_until_end()
        return (first + "\n" + rest).strip()
    return first


def main() -> None:
    history = []
    print("ATLAS terminal chat. Type 'quit' to leave.")
    print(banner())
    while True:
        try:
            message = read_message()
        except (EOFError, KeyboardInterrupt):
            break
        if message.lower() in ("quit", "exit"):
            break
        if not message:
            continue
        if LOG_PIECE.match(message) and "\n" not in message:
            print("[not sent] That looks like one line of a workout log. Paste the WHOLE log starting from "
                  "'FORGE WORKOUT LOG v1', then type END on its own line.")
            continue
        print("\nATLAS: ", end="", flush=True)
        reply = ""
        try:
            for chunk in stream_atlas(message, history):
                print(chunk, end="", flush=True)
                reply += chunk
        except Exception as exc:  # show the problem, keep the chat alive
            print(f"\n[ERROR] {type(exc).__name__}: {exc}")
            continue
        print()
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()