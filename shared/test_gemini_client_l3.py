"""
FORGE Gemini client - L3 (REAL Google calls: uses your real key and about 8 of your free requests).
Run with:  python -m shared.test_gemini_client_l3      (from D:\\Projects\\Forge)
Nothing is saved anywhere. Read the printed output: it shows which model answered, how fast, and any error text.
"""
import json, os, sys, time
sys.path.insert(0, os.path.abspath("."))
from google.genai import errors
from shared import model_client as mc

def ask(messages, system="You are a concise assistant. Answer in one or two sentences."):
    t0 = time.time(); first = None; parts = []
    for chunk in mc.stream_gemini(system, messages):
        if first is None: first = time.time() - t0
        parts.append(chunk)
    return "".join(parts), first, time.time() - t0

def show(label, fn):
    print(f"\n--- {label}")
    try:
        text, first, total = fn()
        print(f"model that answered: {mc.LAST_GEMINI_MODEL}   first text after {first:.1f}s, finished after {total:.1f}s")
        print("reply:", text.strip()[:400].replace("\n", " "))
        return text
    except errors.APIError as e:
        print(f"GOOGLE ERROR  code={e.code}  status={getattr(e, 'status', None)}")
        print("message:", str(e)[:600].replace("\n", " "))
    except Exception as e:
        print("OTHER ERROR:", type(e).__name__, str(e)[:400])
    return None

print(f"settings: GEMINI_MODEL={mc.GEMINI_MODEL}  GEMINI_FALLBACK_MODEL={mc.GEMINI_FALLBACK_MODEL!r}  GEMINI_THINKING_LEVEL={mc.GEMINI_THINKING_LEVEL}")
original_primary, original_fallback = mc.GEMINI_MODEL, mc.GEMINI_FALLBACK_MODEL

# A. each model on its own (fallback switched off) so we learn exactly what your key can use
for model in [mc.GEMINI_MODEL, original_fallback]:
    if not model: continue
    mc.GEMINI_MODEL, mc.GEMINI_FALLBACK_MODEL = model, ""
    mc._cooldown_until.clear()
    show(f"A. {model} on its own", lambda: ask([{"role": "user", "content": "Say hello and name the day of the week in one sentence."}]))
    time.sleep(2)

# B. the normal setup (first model, then fallback)
mc.GEMINI_MODEL, mc.GEMINI_FALLBACK_MODEL = original_primary, original_fallback
mc._cooldown_until.clear()
show("B. normal setup (first model, fallback ready)", lambda: ask([{"role": "user", "content": "In one sentence, what is a deload week in weightlifting?"}]))
time.sleep(2)

# C. multi-turn memory
reply = show("C. remembers an earlier turn", lambda: ask([
    {"role": "user", "content": "My favourite number is 42. Just say OK."},
    {"role": "assistant", "content": "OK."},
    {"role": "user", "content": "What is my favourite number?"}]))
print("CHECK C (reply contains 42):", "PASS" if reply and "42" in reply else "FAIL")
time.sleep(2)

# D. strict JSON (ATLAS plans, exercise how-tos and note reading all rely on this)
reply = show("D. strict JSON", lambda: ask(
    [{"role": "user", "content": 'Reply with ONLY this JSON, with 3 real gym exercises for legs: {"exercises": ["...", "...", "..."]}. No other text, no code fences.'}],
    system="You output only valid JSON."))
try:
    cleaned = (reply or "").strip()
    if cleaned.startswith("```"): cleaned = cleaned.strip("`").replace("json", "", 1).strip()
    data = json.loads(cleaned); ok = isinstance(data.get("exercises"), list) and len(data["exercises"]) == 3
    print("CHECK D (valid JSON with 3 exercises):", "PASS" if ok else "FAIL", "(wrapped in code fences)" if (reply or "").strip().startswith("```") else "")
except Exception as e:
    print("CHECK D (valid JSON with 3 exercises): FAIL", type(e).__name__)
time.sleep(2)

# E. the three thinking levels on a small puzzle: compare speed and answers
for level in ["minimal", "low", "medium"]:
    mc.GEMINI_THINKING_LEVEL = level
    show(f"E. thinking level {level}", lambda: ask([{"role": "user", "content": "A gym plan has 4 exercises of 3 sets each, plus 2 warmup exercises of 1 set each. How many sets in total? Give just the number."}]))
    time.sleep(2)
print("\nDone. Paste this whole output back to Claude.")