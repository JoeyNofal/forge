"""
FORGE Gemini client - L1 (static) + L2 (mocked: no network, no key) + L4 (sustained / concurrent) + L5 (extreme).
Covers: model names and settings, no temperature, thinking level, the "last turn must be the user's" guard,
and the primary -> fallback behaviour (429 / 503 before any text; never mixed output; never silent).
Run with:  python -m shared.test_gemini_client      (from the forge folder)
"""
import ast, os, re, sys, tempfile, threading
sys.path.insert(0, os.path.abspath("."))
os.environ["FORGE_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="forge_gem_test_"), "chat_history.db")

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond: passed += 1
    else:
        failed += 1
        print(f"FAIL: {name}" + (f"  -> {detail}" if detail else ""))

from google.genai import errors as E, types
from shared import model_client as mc

SRC = open("shared/model_client.py", encoding="utf-8").read()
fn_src = SRC[SRC.index("def stream_gemini("):SRC.index("def stream_ollama(")]

# ---------------- L1 static
check("L1 model_client.py parses", bool(ast.parse(SRC)))
check("L1 default models are 3.6 Flash with 3.5 Flash-Lite as the fallback, and 2.5 Flash is gone",
      'or "gemini-3.6-flash"' in SRC and '"gemini-3.5-flash-lite"' in SRC and "gemini-2.5" not in SRC)
check("L1 no temperature is sent to Gemini any more", "temperature" not in fn_src.replace("No temperature", ""))
check("L1 the role conversion to Gemini's 'model' still lives only inside stream_gemini (Lesson 11)", SRC.count('"model" if') == 1)
check("L1 settings come from the environment (GEMINI_MODEL, GEMINI_FALLBACK_MODEL, GEMINI_THINKING_LEVEL)", all(k in SRC for k in ["GEMINI_MODEL", "GEMINI_FALLBACK_MODEL", "GEMINI_THINKING_LEVEL"]))

# ---------------- fake Gemini client
class Chunk:
    def __init__(self, t): self.text = t
def api_err(code):
    cls = E.ServerError if code >= 500 else E.ClientError
    return cls(code, {"error": {"code": code, "message": "m", "status": "X"}})

class FakeModels:
    def __init__(self, script): self.script = script; self.calls = []; self.lock = threading.Lock()
    def generate_content_stream(self, model, contents, config):
        with self.lock: self.calls.append({"model": model, "contents": contents, "config": config})
        plan = self.script.get(model, ["ok from " + model])
        if plan == "raise_at_call": raise api_err(429)
        def gen():
            for item in plan:
                if isinstance(item, Exception): raise item
                yield Chunk(item)
        return gen()
class FakeClient:
    def __init__(self, script): self.models = FakeModels(script)

clock = [1000.0]
def setup(script, primary="P-model", fallback="F-model", level="low"):
    mc.GEMINI_MODEL, mc.GEMINI_FALLBACK_MODEL, mc.GEMINI_THINKING_LEVEL = primary, fallback, level
    mc._cooldown_until.clear(); mc.LAST_GEMINI_MODEL = None
    clock[0] = 1000.0; mc._now = lambda: clock[0]
    fc = FakeClient(script); mc.get_gemini_client = lambda: fc
    return fc
_DEFAULT = object()
def run(msgs=_DEFAULT, **kw):
    return "".join(mc.stream_gemini("SYSTEM", [{"role": "user", "content": "hi"}] if msgs is _DEFAULT else msgs, **kw))  # pyright: ignore[reportArgumentType]
U = lambda t="hi": {"role": "user", "content": t}
A = lambda t="yo": {"role": "assistant", "content": t}

# ---------------- L2 request shape
fc = setup({})
out = run([U("first"), A("answer"), U("second")], location="South Bend")
c = fc.models.calls[0]
check("L2 normal call: the answer comes back, from the first model", out == "ok from P-model" and mc.LAST_GEMINI_MODEL == "P-model" and [x["model"] for x in fc.models.calls] == ["P-model"])
check("L2 roles: user stays user, assistant becomes model, text intact, order kept", [(x.role, x.parts[0].text) for x in c["contents"]] == [("user", "first"), ("model", "answer"), ("user", "second")])
cfg = c["config"]
check("L2 config: system prompt + date + location, 8192 output cap", "SYSTEM" in cfg.system_instruction and "Current date and time" in cfg.system_instruction and "South Bend" in cfg.system_instruction and cfg.max_output_tokens == 8192)
check("L2 config: NO temperature / top_p / top_k", cfg.temperature is None and cfg.top_p is None and cfg.top_k is None)
check("L2 config: thinking level LOW", cfg.thinking_config.thinking_level == types.ThinkingLevel.LOW and cfg.thinking_config.thinking_budget is None)
for lvl, enum in [("minimal", "MINIMAL"), ("medium", "MEDIUM"), ("high", "HIGH")]:
    fc = setup({}, level=lvl); run()
    check(f"L2 thinking level {lvl} reaches the request", fc.models.calls[0]["config"].thinking_config.thinking_level == types.ThinkingLevel[enum])
fc = setup({}, level="turbo")
try: run(); raised = False
except ValueError as e: raised = "GEMINI_THINKING_LEVEL" in str(e)
check("L2 level 'turbo': ValueError naming the setting, and no request was sent", raised and fc.models.calls == [])

# ---------------- L2 history guard
for name, msgs in [("empty list", []), ("last turn is the assistant", [U(), A()]), ("only an assistant turn", [A()]), ("not a list", "hello"), ("None", None),
                   ("a bad role", [{"role": "system", "content": "x"}, U()]), ("a non-dict item", [U(), "x"])]:
    fc = setup({})
    try: run(msgs); ok = False
    except ValueError: ok = True
    check(f"L2 guard: {name} -> ValueError and nothing sent", ok and fc.models.calls == [])

# ---------------- L2 fallback
fc = setup({"P-model": "raise_at_call"})
check("L2 429 when the call starts -> the fallback answers", run() == "ok from F-model" and [x["model"] for x in fc.models.calls] == ["P-model", "F-model"] and mc.LAST_GEMINI_MODEL == "F-model")
fc = setup({"P-model": [api_err(429)]})
check("L2 429 on the first read (how the real SDK raises it) -> the fallback answers", run() == "ok from F-model")
check("L2 the SAME request (history, system text, settings) goes to the fallback", fc.models.calls[0]["contents"] is fc.models.calls[1]["contents"] and fc.models.calls[0]["config"] is fc.models.calls[1]["config"])
fc = setup({"P-model": [api_err(503)]})
check("L2 503 (overloaded) also falls back", run() == "ok from F-model")
import logging
class Cap(logging.Handler):
    def __init__(self): super().__init__(); self.records = []
    def emit(self, record): self.records.append(record.getMessage())
cap = Cap(); logging.getLogger("forge.model_client").addHandler(cap)
fc = setup({"P-model": [api_err(429)]}); run()
check("L2 a fallback is never silent: a warning is logged naming both models", any("fallback" in m and "F-model" in m and "P-model" in m for m in cap.records), str(cap.records))

# cooldown
fc = setup({"P-model": [api_err(429)]}); run(); fc.models.calls.clear()
fc.models.script["P-model"] = ["P back"]
clock[0] += 60
check("L2 cooldown: for the next 5 minutes the resting model is not even tried", run() == "ok from F-model" and [x["model"] for x in fc.models.calls] == ["F-model"])
fc.models.calls.clear(); clock[0] += 400
check("L2 after the cooldown the first model is tried again and answers", run() == "P back" and [x["model"] for x in fc.models.calls] == ["P-model"] and mc.LAST_GEMINI_MODEL == "P-model")

# no mixing, no hiding
fc = setup({"P-model": ["partial ", api_err(429)]})
try: run(); raised = False
except E.APIError: raised = True
check("L2 an error AFTER text has started is raised, and the fallback is NOT used (no mixed answers)", raised and [x["model"] for x in fc.models.calls] == ["P-model"])
for code in (400, 401, 403, 404):
    fc = setup({"P-model": [api_err(code)]})
    try: run(); raised = False
    except E.APIError as e: raised = e.code == code
    check(f"L2 a {code} error is raised as it is (a wrong key or model name must not hide behind the fallback)", raised and len(fc.models.calls) == 1)
fc = setup({"P-model": [RuntimeError("boom")]})
try: run(); raised = False
except RuntimeError: raised = True
check("L2 a non-Google error is raised as it is", raised and len(fc.models.calls) == 1)
fc = setup({"P-model": [api_err(429)], "F-model": [api_err(429)]})
try: run(); raised = False
except E.APIError as e: raised = e.code == 429
check("L2 both models out of requests -> the error is raised (fail loudly), after trying both", raised and [x["model"] for x in fc.models.calls] == ["P-model", "F-model"])
fc.models.calls.clear()
try: run(); raised = False
except E.APIError: raised = True
check("L2 while BOTH are resting it still tries them (in order) instead of giving up without asking", raised and [x["model"] for x in fc.models.calls] == ["P-model", "F-model"])
fc = setup({"P-model": [api_err(429)]}, fallback="")
try: run(); raised = False
except E.APIError: raised = True
check("L2 fallback switched off (empty setting): a 429 is raised", raised and len(fc.models.calls) == 1)
fc = setup({"Same": [api_err(429)]}, primary="Same", fallback="Same")
try: run(); raised = False
except E.APIError: raised = True
check("L2 fallback equal to the first model is not tried twice", raised and len(fc.models.calls) == 1)

# ---------------- L4 sustained + concurrent
fc = setup({}); ok = True
for i in range(100):
    if run([U(f"q{i}")]) != "ok from P-model": ok = False; break
check("L4 100 sequential calls, all answered, none lost", ok and len(fc.models.calls) == 100)
fc = setup({"P-model": [api_err(429)]}); results = []; errs = []
def worker(i):
    try: results.append("".join(mc.stream_gemini("S", [U(f"m{i}")])))
    except Exception as e: errs.append(repr(e))
ts = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
[t.start() for t in ts]; [t.join() for t in ts]
check("L4 20 simultaneous calls while the first model is out: every one answered by the fallback, no errors", not errs and len(results) == 20 and set(results) == {"ok from F-model"}, str(errs[:2]))
check("L4 the cooldown record is a single clean entry (no corruption under threads)", list(mc._cooldown_until) == ["P-model"])

# ---------------- L5 extreme
fc = setup({}); big = "x" * 50000
check("L5 a 50,000-character message goes through whole", run([U(big)]) == "ok from P-model" and fc.models.calls[0]["contents"][0].parts[0].text == big)
fc = setup({}); uni = "héllo 😀 日本語 \u0000 \u202e"
check("L5 unicode, emoji and control characters go through untouched", run([U(uni)]) == "ok from P-model" and fc.models.calls[0]["contents"][0].parts[0].text == uni)
fc = setup({"P-model": [""]}); out = run()
check("L5 a model that returns only empty text gives an empty answer, no crash", out == "")
fc = setup({"P-model": [api_err(429)]}); mc.get_gemini_client = lambda: (_ for _ in ()).throw(ValueError("GEMINI_API_KEY is not set"))
try: run(); raised = False
except ValueError as e: raised = "GEMINI_API_KEY" in str(e)
check("L5 a missing API key still fails loudly (never falls back or hides)", raised)

print(f"{passed}/{passed + failed} passed")
sys.exit(1 if failed else 0)