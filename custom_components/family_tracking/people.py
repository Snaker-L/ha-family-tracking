"""
Who to follow, decided without Home Assistant so it can be tested on its own.

A person counts as known when Home Assistant has a state for them *or* an entry
in its entity registry. The registry is the part that survives a restart. A
person can be missing from the states for a while after Home Assistant starts:
one supplied by another instance through Remote Home Assistant only appears
once that connection is up. Judging by the states alone treated such a person
as gone -- no sensors, and the device with its name and area removed.
"""

from __future__ import annotations

from collections.abc import Iterable


def persons_to_follow(
    configured: list[str] | None,
    present: Iterable[str],
    registered: Iterable[str],
) -> list[str]:
    """
    The persons to follow: the configured ones Home Assistant knows, otherwise
    every one it knows.

    Defaulting to all of them means a person added later shows up by itself
    instead of quietly going missing. A configured person Home Assistant does
    not know at all -- deleted, or renamed to another entity id -- is left out.
    """
    known = set(present) | set(registered)
    if configured:
        return [person_id for person_id in configured if person_id in known]
    return sorted(known)
