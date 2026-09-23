"""
Where "keep three months" ends, kept free of Home Assistant so it can be tested.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .const import DEFAULT_KEEP, KEEP_UNITS, MAX_KEEP_MONTHS


def subtract_months(moment: datetime, months: int) -> datetime:
    """
    The same day `months` earlier, clamped to the end of a shorter month.

    Calendar months rather than 30 days, so "1 year" really means a year and
    31 March minus one month is the last day of February, not early March.
    """
    month_index = moment.year * 12 + (moment.month - 1) - months
    year, month = divmod(month_index, 12)
    month += 1
    for day in (moment.day, 30, 29, 28):
        try:
            return moment.replace(year=year, month=month, day=day)
        except ValueError:
            continue
    raise ValueError(f"cannot go back {months} months from {moment}")


def parse_keep(keep: object) -> tuple[int, str] | None:
    """ "40d" as (40, "d"), or nothing for anything that is not a valid setting."""
    # Digits only: `int()` alone would also take " 2" and store "2 y".
    if not isinstance(keep, str) or keep[-1:] not in KEEP_UNITS or not keep[:-1].isdigit():
        return None
    amount = int(keep[:-1])
    return (amount, keep[-1]) if amount >= 1 else None


#: Every word for a unit somebody might type, in the languages the integration
#: speaks. Matched case-insensitively and without a trailing full stop.
UNIT_WORDS: dict[str, str] = {
    **dict.fromkeys(("d", "t", "tag", "tage", "tagen", "day", "days"), "d"),
    **dict.fromkeys(("m", "mo", "mon", "monat", "monate", "monaten", "month", "months"), "m"),
    **dict.fromkeys(("y", "j", "jahr", "jahre", "jahren", "year", "years", "yr", "yrs"), "y"),
}

#: How a setting reads in the field, per language and unit: singular, plural.
UNIT_NAMES: dict[str, dict[str, tuple[str, str]]] = {
    "de": {"d": ("Tag", "Tage"), "m": ("Monat", "Monate"), "y": ("Jahr", "Jahre")},
    "en": {"d": ("day", "days"), "m": ("month", "months"), "y": ("year", "years")},
}


def format_keep(keep: str, language: str | None) -> str:
    """ "40d" as "40 Tage" -- for a typed value, which has no translated label."""
    amount, unit = parse_keep(keep) or parse_keep(DEFAULT_KEEP)
    names = UNIT_NAMES.get((language or "en").split("-")[0], UNIT_NAMES["en"])[unit]
    return f"{amount} {names[0] if amount == 1 else names[1]}"


def validate_keep(text: object) -> tuple[str | None, str | None, str]:
    """
    What was picked or typed, as a stored setting -- or what is wrong with it.

    Accepts a value from the list ("3m"), or a number and a unit, short or
    written out ("40 T", "18 Monate", "3 J."). A bare number means days, the
    unit the field starts out in.

    Returns the setting, the translation key of the error, and the part of the
    input the error is about, so the message can quote what was typed instead
    of repeating the rules.
    """
    if not isinstance(text, str) or not text.strip():
        return None, "keep_no_number", ""
    text = text.strip()
    if parse_keep(text):
        keep = text
    else:
        match = re.fullmatch(r"(-?[0-9.,]*)\s*(.*)", text)
        number, word = match.group(1), match.group(2).strip()
        if not number.strip("-"):
            return None, "keep_no_number", ""
        if "." in number or "," in number:
            return None, "keep_whole_number", number
        value = int(number)
        if value < 1:
            return None, "keep_no_number", ""
        unit = UNIT_WORDS.get(word.rstrip(".").lower()) if word else "d"
        if unit is None:
            return None, "keep_unknown_unit", word
        keep = f"{value}{unit}"
    amount, unit = parse_keep(keep)
    months = amount / 30.44 if unit == "d" else amount * (12 if unit == "y" else 1)
    if months > MAX_KEEP_MONTHS:
        return None, "keep_too_long", ""
    return keep, None, ""


def cutoff_for(keep: str, now: datetime) -> datetime:
    """The oldest moment still kept for a setting such as "10d", "3m" or "2y"."""
    amount, unit = parse_keep(keep) or parse_keep(DEFAULT_KEEP)
    if unit == "d":
        return now - timedelta(days=amount)
    return subtract_months(now, amount * (12 if unit == "y" else 1))
