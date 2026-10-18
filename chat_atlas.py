"""Simple terminal chat with ATLAS (temporary, until the dashboard exists).

Run from the project folder:   python chat_atlas.py
Type  quit  to leave.

PASTING A WORKOUT LOG: just paste it. When the first line is "FORGE WORKOUT LOG", the script keeps
collecting lines until you type  END  on its own line and press Enter. (Typing  paste  first also works.)
"""
import re

from agents.atlas.chat import stream_atlas

# A line that belongs INSIDE a workout log. If one arrives on its own, the log was pasted without its
# first line, and sending it to ATLAS line by line would just make ATLAS talk about every fragment.
LOG_PIECE = re.compile(r"^\s*(##\s|Exercise:|Prescribed:|Set\s+\d+:|RPE:|Notes:|Title:|Date:|Unit:|Program:|Day:)", re.IGNORECASE)


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