"""
DRIVE UNITS — the unit words and conversion factors, in one tiny pure module.

WHY: DRIVE's extraction prompt used to tell the local model to convert liters and
kilometers itself ("1 L = 0.264 gal"). A local model doing its own arithmetic (or
guessing a unit nobody stated) is the same bug that turned ATLAS's "at 50" into
110.23 lbs. Now the model only reports the number exactly as Joey said it, plus a
unit word only if he wrote one; PYTHON converts (drive_logging.py), and
drive_extract.py only keeps a unit the message really contains.

No imports and no logic beyond word lookup and the two multiplications, so both
drive_extract.py (which must not import drive_logging) and drive_logging.py can use it.
"""

LITERS_TO_GALLONS = 0.264172      # US gallons
KM_TO_MILES = 0.621371

_FAMILIES = {
    "miles": ("mi", "mile", "miles"),
    "km": ("km", "kms", "kilometer", "kilometers", "kilometre", "kilometres"),
    "gallons": ("gal", "gals", "gallon", "gallons"),
    "liters": ("l", "liter", "liters", "litre", "litres"),
}


def unit_family(unit_text) -> str:
    """'miles' / 'km' / 'gallons' / 'liters' for a unit word the model reported, else ''. Never raises."""
    if not isinstance(unit_text, str):
        return ""
    word = unit_text.strip().lower()
    for family, words in _FAMILIES.items():
        if word in words:
            return family
    return ""


def km_to_miles(km: float) -> float:
    return km * KM_TO_MILES


def liters_to_gallons(liters: float) -> float:
    return liters * LITERS_TO_GALLONS