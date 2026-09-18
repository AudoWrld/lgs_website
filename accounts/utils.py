import re
import secrets

_WORDS = [
    "AMBER",
    "COPPER",
    "GOLD",
    "SILVER",
    "QUARTZ",
    "GRANITE",
    "BASALT",
    "TOPAZ",
    "ONYX",
    "CORAL",
    "IVORY",
    "PEARL",
    "EBONY",
    "RIVER",
    "VALLEY",
    "SUMMIT",
    "HARBOR",
    "MERIDIAN",
    "HORIZON",
    "FALCON",
    "TIGER",
    "EAGLE",
    "PANTHER",
    "COBALT",
    "CRIMSON",
]

_SAFE_DIGITS = "23456789"


def generate_temp_password():
    word = secrets.choice(_WORDS)
    digits = "".join(secrets.choice(_SAFE_DIGITS) for _ in range(4))
    return f"{word}{digits}"


def normalize_tz_phone(raw):
    if not raw:
        return raw

    digits_only = re.sub(r"\D", "", raw.strip())

    if digits_only.startswith("255") and len(digits_only) == 12:
        subscriber = digits_only[3:]
    elif digits_only.startswith("0") and len(digits_only) == 10:
        subscriber = digits_only[1:]
    elif len(digits_only) == 9:
        subscriber = digits_only
    else:
        return raw.strip()

    return f"+255{subscriber}"
