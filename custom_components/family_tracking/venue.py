"""
Working out what to call the place a fix is in.

Reverse geocoding answers "what is nearest", which is the wrong question
indoors. Standing in the Donauzentrum, Nominatim offers the A1 shop a few
metres away; in the Q19 a Nespresso, in the Stadion Center a Thalia. None of
those is where a person would say they are, and the street address is no
better -- nobody arranges to meet at Wagramer Straße 94.

Containment is a different question, and Overpass answers it: `is_in` returns
every area a coordinate falls within. Two things were learned by trying it:

  * A stay is the centre of many samples, and indoors those scatter. Forty
    metres out is normal and puts the point outside the outline, so a small
    search around it catches what containment misses.
  * Filtering areas by a regular expression over *keys* is not indexed and
    times the service out. One statement per key is, and answers in seconds.

Kept free of aiohttp and Home Assistant imports so it can be tested with
nothing installed but pytest; the client lives in geocode.py next to the
Nominatim one.
"""

from __future__ import annotations

from typing import Any

#: Keys that make a named area a place worth showing rather than geography.
#:
#: Administrative boundaries are deliberately absent: every fix is inside a
#: district, a city and a country, and none of those is an answer to "where is
#: she". What is here is the kind of outline that has a door and a sign.
VENUE_KEYS: tuple[str, ...] = (
    "shop",
    "amenity",
    "leisure",
    "tourism",
    "aeroway",
    "healthcare",
    "office",
    "landuse",
    "building",
)

#: Places that contain other places, most telling first.
#:
#: Inside a shopping centre the fix is inside the centre *and* inside whatever
#: unit it happens to sit in, and both come back. This decides which of the two
#: a person means, and the answer is almost always the bigger one.
CONTAINERS: tuple[tuple[str, str], ...] = (
    ("shop", "mall"),
    ("shop", "department_store"),
    ("landuse", "retail"),
    ("aeroway", "aerodrome"),
    ("amenity", "hospital"),
    ("amenity", "university"),
    ("amenity", "school"),
    ("amenity", "marketplace"),
    ("leisure", "stadium"),
    ("tourism", "theme_park"),
    ("tourism", "zoo"),
)

#: What the search around the point may return. Only containers, and only the
#: retail ones: a café fifty metres away is somewhere else, but a shopping
#: centre fifty metres away is almost certainly the building you are standing
#: in with a scattered fix.
NEARBY: tuple[tuple[str, str], ...] = (
    ("shop", "mall"),
    ("shop", "department_store"),
    ("landuse", "retail"),
)

#: How far from the fix a container still counts. Chosen from what indoor
#: scatter actually looks like, not from what sounds tidy.
NEARBY_RADIUS = 50


def build_query(latitude: float, longitude: float, radius: int = NEARBY_RADIUS) -> str:
    """The Overpass query for both questions at once: inside what, and near what."""
    where = f"{latitude:.6f},{longitude:.6f}"

    inside = "".join(f'area.a[name]["{key}"];out tags;' for key in VENUE_KEYS)

    grouped: dict[str, list[str]] = {}
    for key, value in NEARBY:
        grouped.setdefault(key, []).append(value)
    nearby = "".join(
        f'nwr(around:{radius},{where})[name]["{key}"~"^({"|".join(values)})$"];out tags;'
        for key, values in grouped.items()
    )

    return f"[out:json][timeout:25];is_in({where})->.a;{inside}{nearby}"


def _rank(element: dict[str, Any]) -> tuple[int, int]:
    """
    Lower sorts first: whether it encloses the fix, then how telling its tags are.

    An area came back from `is_in` and therefore contains the point; anything
    else was merely close by, and only counts when nothing contains it.
    """
    tags = element.get("tags") or {}
    encloses = 0 if element.get("type") == "area" else 1
    for position, (key, value) in enumerate(CONTAINERS):
        if tags.get(key) == value:
            return (encloses, position)
    return (encloses, len(CONTAINERS))


def pick_name(payload: dict[str, Any]) -> str:
    """
    The name to show, out of everything the query returned.

    Several places can answer at once -- a unit inside a centre, a building and
    the retail ground it stands on. The order in `CONTAINERS` decides, and
    something that actually contains the fix always beats something that is
    only nearby.
    """
    best: tuple[int, int] | None = None
    name = ""

    for element in payload.get("elements") or []:
        candidate = (element.get("tags") or {}).get("name") or ""
        if not candidate:
            continue
        rank = _rank(element)
        if best is None or rank < best:
            best, name = rank, candidate

    return name
