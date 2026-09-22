"""
Turning a Nominatim answer into something a person can read.

Separate from the client on purpose: this is the fiddly part -- the service
answers with whatever it happens to know, and every case has to land somewhere
sensible. Keeping it free of Home Assistant and aiohttp imports means it can be
tested with nothing installed but pytest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .const import CACHE_PRECISION

#: Where the house number goes before the street name rather than after it.
#:
#: "350 5th Avenue" in New York, "Pariser Platz 1" in Berlin -- and Nominatim
#: hands both over as separate fields, so the order is ours to get right.
#: Putting it the German way everywhere produced "5th Avenue 350, New York",
#: which no American would write and few would read twice.
#:
#: Countries not listed take the number after the street, which covers most of
#: Europe and South America. Adding one is a two-letter code.
HOUSE_NUMBER_FIRST: frozenset[str] = frozenset(
    {"us", "ca", "gb", "ie", "au", "nz", "fr", "in", "sg", "my", "hk", "ph", "th", "za"}
)


def street_head(street: str, house_number: str, country_code: str) -> str:
    """Street and house number in the order that country writes them."""
    if not street:
        return ""
    if not house_number:
        return street
    if country_code.lower() in HOUSE_NUMBER_FIRST:
        return f"{house_number} {street}"
    return f"{street} {house_number}"


def cache_key(latitude: float, longitude: float) -> str:
    """The key two nearby fixes share, so standing still costs one lookup."""
    return f"{latitude:.{CACHE_PRECISION}f},{longitude:.{CACHE_PRECISION}f}"


@dataclass(slots=True)
class Address:
    """The parts of an address the card and the sensors actually use."""

    label: str
    name: str = ""
    house_number: str = ""
    street: str = ""
    postcode: str = ""
    city: str = ""
    county: str = ""
    state: str = ""
    country: str = ""
    #: Two-letter code, kept because the order of street and house number
    #: depends on it.
    country_code: str = ""
    #: Whether this answer is the final one for these coordinates.
    #:
    #: False means a question could not be put -- the enclosing place was
    #: wanted but Overpass was busy -- so the label is the best guess for now
    #: and nothing may store it. Deliberately absent from `as_dict`: anything
    #: that made it into a cache is settled by definition, and a reconstructed
    #: entry gets the default.
    settled: bool = True

    def as_dict(self) -> dict[str, str]:
        return {
            "label": self.label,
            "name": self.name,
            "house_number": self.house_number,
            "street": self.street,
            "postcode": self.postcode,
            "city": self.city,
            "county": self.county,
            "state": self.state,
            "country": self.country,
            "country_code": self.country_code,
        }


def parse(payload: dict[str, Any]) -> Address:
    """
    Turn a Nominatim answer into one readable line plus its parts.

    Written against what the service actually returns rather than its schema: a
    footpath has no `road`, a shop has no house number, and a field in the middle
    of nowhere has neither. Each step falls back to the next thing a person would
    recognise, and the raw `display_name` is the last resort because it is long
    enough to break any layout.
    """
    address: dict[str, str] = payload.get("address") or {}

    street = (
        address.get("road")
        or address.get("pedestrian")
        or address.get("footway")
        or address.get("path")
        or ""
    )
    city = (
        address.get("village")
        or address.get("town")
        or address.get("city")
        or address.get("municipality")
        or ""
    )
    name = payload.get("name") or address.get("amenity") or address.get("shop") or ""
    house_number = address.get("house_number") or ""

    country_code = address.get("country_code") or ""

    if street:
        head = street_head(street, house_number, country_code)
    elif name:
        head = name
    else:
        head = city or address.get("county") or ""

    label = ", ".join(part for part in (head, city if head != city else "") if part)
    if not label:
        display = payload.get("display_name") or ""
        # Each part carries the space that followed the comma; joining them
        # again without stripping produces "Somewhere,  Somehow".
        label = ", ".join(part.strip() for part in display.split(",")[:2] if part.strip())

    return Address(
        label=label,
        name=name,
        house_number=house_number,
        street=street,
        postcode=address.get("postcode") or "",
        city=city,
        county=address.get("county") or "",
        state=address.get("state") or "",
        country=address.get("country") or "",
        country_code=country_code,
    )


def street_line(address: Address) -> str:
    """
    The postal address alone: street, house number, town.

    Deliberately built from the parts rather than from `label`. The label falls
    back to whatever Nominatim found nearest, and inside a shopping centre that
    is a shop -- so "Stadion Center (TEDi, Wien)" is what putting the label in
    brackets produces, which names the very thing the place was meant to
    replace.
    """
    head = street_head(address.street, address.house_number, address.country_code)
    if not head:
        return ""
    return ", ".join(part for part in (head, address.city) if part)


def merge_venue(address: Address | None, venue: str, with_address: bool = False) -> Address | None:
    """
    Let the enclosing place speak for the address it contains.

    Reverse geocoding answers "what is nearest", and inside a shopping centre
    that is a coffee bar, a bookshop, or the street the car park faces -- never
    the name on the building everybody uses. Where something encloses the fix,
    it is the better answer.

    `with_address` keeps the postal address too, in brackets after the name:
    the name says where somebody is, the address says how to get there, and
    which of the two a reader wants is not something this can know. Where no
    street is known the brackets are left off rather than filled with the
    nearest shop. The parts stay on the object either way, so the sensor
    attributes always carry street and postcode.
    """
    if not venue:
        return address
    if address is None:
        # No address at all, but a name for the place is an answer in itself.
        return Address(label=venue, name=venue)

    strasse = street_line(address) if with_address else ""
    if strasse:
        address.label = f"{venue} ({strasse})"
    else:
        address.label = ", ".join(part for part in (venue, address.city) if part)
    address.name = venue
    return address
