"""
SHARED: turning a local model's answer into a dict, and the ONE error type for
"the model call failed or its answer wasn't usable JSON".

WHY ONE COPY (Lesson #9): atlas_extract.py and drive_extract.py each carried an identical
ExtractionError and _parse_model_json, drive_remember.py reached into drive_extract for the
private copy, and the "model call failed" wrapper was pasted in three places. STOCK, FLAME
and the rest reuse this instead of becoming copy number four.

Note: the model CALL itself stays in each extractor (many tests replace
complete_ollama_json on that module). Only parsing and the error live here.
"""
import json
import re


class ExtractionError(Exception):
    """The local model call failed or its answer wasn't usable JSON."""


def model_call_failed(e: Exception) -> ExtractionError:
    """The one wording for 'the model call itself failed' (Ollama down, timeout, bad response)."""
    return ExtractionError(f"the local model call failed ({type(e).__name__}: {e})")


def parse_model_json(text) -> dict:
    """Model text -> dict, or ExtractionError. Tolerates ```json fences; nothing else."""
    if not isinstance(text, str) or not text.strip():
        raise ExtractionError("the local model returned nothing")
    cleaned = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.S | re.I)
    if fenced:
        cleaned = fenced.group(1)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"the local model's answer wasn't valid JSON ({e.msg})") from e
    except RecursionError as e:
        raise ExtractionError("the local model's answer was nested too deeply to read") from e
    if not isinstance(data, dict):
        raise ExtractionError(f"expected a JSON object, got {type(data).__name__}")
    return data