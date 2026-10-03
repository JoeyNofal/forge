"""
DRIVE RECALL — the recall check (increment (b), Part 6b).

When Joey asks about recalls:
  1. BEFORE DRIVE answers: look up the official NHTSA recalls for HIS vehicle (year/make/model come from
     his vehicle file, never from what he typed) and hand the model a clearly labeled block
     (shared/nhtsa.py). If the lookup fails, the model is told it failed and not to guess (Lessons #2/#12).
  2. AFTER DRIVE answers: offer to save a dated snapshot through the usual approval step — only if the
     list of recalls changed since the last saved one.
Nothing is saved here. A failed lookup is never saved and never presented as "no recalls".
"""
from typing import Optional

from shared import nhtsa
from shared.keyword_gate import contains_keyword
from shared.agent_topics import DRIVE_RECALL_WORDS
from agents.drive import drive_actions
from agents.drive.drive_tools import load_data, get_active_vehicle


def is_recall_question(message) -> bool:
    return isinstance(message, str) and contains_keyword(message, DRIVE_RECALL_WORDS)


def _vehicle_details() -> tuple:
    """(make, model, year) of the ACTIVE vehicle, from the data file. RuntimeError if it can't be read."""
    vehicle = get_active_vehicle(load_data())
    year = vehicle.get("year")
    if isinstance(year, str) and year.strip().isdigit():
        year = int(year.strip())
    return vehicle.get("make"), vehicle.get("model"), year


def prepare_recall_context(message):
    """
    Called BEFORE the reply. Returns (context_block, result):
      (None, None)          not a recall question
      (failure note, None)  the lookup failed: the model is told so, and nothing will be offered for saving
      (labeled block, dict) success; the dict is what may be offered for saving afterwards
    Never raises.
    """
    if not is_recall_question(message):
        return None, None
    try:
        make, model, year = _vehicle_details()
        result = nhtsa.lookup_recalls(make, model, year)
    except (RuntimeError, nhtsa.NHTSAError) as e:
        return nhtsa.failure_note(e), None
    return nhtsa.format_for_context(result), result


def recall_footer(result) -> Optional[str]:
    """
    A FIXED reminder shown after DRIVE's reply whenever a recall list was used. Written by Python, not the
    model: the real local model ignored the 'model year, not VIN' caveat in its context block.
    """
    if not isinstance(result, dict):
        return None
    return (f"Reminder: NHTSA's list covers ALL {result.get('model_year')} {result.get('make')} {result.get('model')} "
            "vehicles, not your VIN specifically. Some of these may not apply to your exact car or may already be "
            "repaired — check your VIN at nhtsa.gov/recalls to see what is actually open.")


def propose_recall_snapshot_note(result) -> Optional[str]:
    """Called AFTER the reply, only with a successful result. A plain note for Joey, or None."""
    if result is None:
        return None
    return drive_actions.propose_recall_snapshot(result)[1]