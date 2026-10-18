"""Simple terminal chat with ATLAS (temporary, until the dashboard exists).

Run from the project folder:   python chat_atlas.py
Type  quit  to leave.
To paste a multi-line workout block: type  paste  and press Enter, paste the
block, then type  END  on its own line and press Enter.
"""
from agents.atlas.chat import stream_atlas


def read_message() -> str:
    first = input("\nYou: ").strip()
    if first.lower() != "paste":
        return first
    print("(Paste now, then type END on its own line and press Enter.)")
    lines = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


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