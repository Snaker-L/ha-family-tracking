"""Shared names and defaults for the Family Tracking integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "family_tracking"

# --- configuration keys -----------------------------------------------------

CONF_PERSONS: Final = "persons"
CONF_EMAIL: Final = "geocode_email"
CONF_LANGUAGE: Final = "language"
CONF_MAX_ACCURACY: Final = "max_accuracy"
CONF_HOME_ZONE: Final = "home_zone"
CONF_GEOCODE: Final = "geocode"

# --- defaults ---------------------------------------------------------------

#: A fix reported as worse than this many metres says more about the radio
#: conditions than about where somebody is, so it is not allowed to move them.
DEFAULT_MAX_ACCURACY: Final = 100

#: Zero accuracy is not a perfect fix. Several trackers report it when they have
#: no fix at all, which is the opposite of what the number says.
ZERO_ACCURACY_IS_UNKNOWN: Final = True

DEFAULT_HOME_ZONE: Final = "zone.home"

#: How long a person stays marked as just arrived or just left. Long enough to
#: drive an automation from it, short enough not to lie about the present.
TRANSITION_SECONDS: Final = 180

# --- presence ---------------------------------------------------------------

PRESENCE_HOME: Final = "home"
PRESENCE_JUST_ARRIVED: Final = "just_arrived"
PRESENCE_JUST_LEFT: Final = "just_left"
PRESENCE_AWAY: Final = "away"
PRESENCE_UNKNOWN: Final = "unknown"

# --- attributes exposed on the location sensor ------------------------------

ATTR_SOURCE: Final = "source"
ATTR_PERSON: Final = "person_entity_id"
ATTR_PRESENCE: Final = "presence"
ATTR_ZONE: Final = "zone"
ATTR_DISTANCE: Final = "distance_from_home"
ATTR_DIRECTION: Final = "direction"
ATTR_BEARING: Final = "bearing"
ATTR_UPDATED: Final = "location_updated"
ATTR_REASON: Final = "last_decision"

# --- reverse geocoding ------------------------------------------------------

NOMINATIM_URL: Final = "https://nominatim.openstreetmap.org/reverse"

#: Their usage policy allows one request per second. Staying a little under it
#: costs nothing and keeps the card working for everybody else too.
MIN_REQUEST_INTERVAL: Final = 1.1

#: Coordinates are rounded to this many decimals before they become a cache
#: key. Four is about eleven metres -- fine enough to tell two addresses apart,
#: coarse enough that standing still does not produce a new lookup every minute.
CACHE_PRECISION: Final = 4

CACHE_TTL_DAYS: Final = 90
STORAGE_KEY: Final = f"{DOMAIN}.geocode_cache"
STORAGE_VERSION: Final = 1

#: Bumped whenever a stored label would come out differently today. Entries
#: written under an older schema are dropped on load rather than migrated:
#: they are a convenience, and keeping them would hide the very change that
#: raised the number -- a shopping centre visited last week would go on
#: reading as the street outside it.
CACHE_SCHEMA: Final = 4

# --- enclosing places -------------------------------------------------------

#: Asked in order, and only instances that hold the whole planet.
#:
#: A mirror carrying one country is worse than no mirror: it answers "200,
#: nothing found" for everywhere else, which reads exactly like "nothing
#: encloses this fix" and would be cached as fact. `venue.covers()` catches
#: that now, but a regional instance still has no business in this list -- it
#: would fail every lookup outside its country and delay the real answer.
#:
#: The order is a preference, not a ranking: whichever answered last is tried
#: first next time, so an instance that a particular network cannot reach stops
#: costing a timeout on every lookup. Several of these publish AAAA records
#: only, which is fine where there is IPv6 and a dead end where there is not.
OVERPASS_URLS: Final = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)

#: Overpass is donated capacity, and containment queries are cheap only for the
#: person asking. One every two seconds, on top of a cache that holds for
#: months, keeps this well inside what the service asks of a client.
VENUE_MIN_REQUEST_INTERVAL: Final = 2.0

#: Containment queries are answered in about a second, but the public instance
#: sometimes queues them. Waiting is free -- the label appears when it appears,
#: and nothing in the card is blocked on it.
VENUE_TIMEOUT: Final = 30

#: How long to wait for the connection itself.
#:
#: Short on purpose, and separate from the one above. Several instances publish
#: AAAA records only, and on a network without IPv6 they do not refuse the
#: connection -- they swallow it. Thirty seconds of that per instance, per
#: lookup, is how a fallback chain becomes slower than having none.
VENUE_CONNECT_TIMEOUT: Final = 8

#: How long an instance that could not be reached is left out of the rotation.
#:
#: A network either routes to an instance or it does not, and that rarely
#: changes within an hour. Trying a dead one on every lookup costs the connect
#: timeout each time and delays the answer that would have worked.
VENUE_DEAD_FOR: Final = 1800

#: "Our servers are struggling." Worth another ask a couple of seconds later:
#: measured against the public instance, the same query answers 504 and then
#: 200 within seconds -- it load-balances across backends and some of them time
#: out. Four of ten succeed first time, three of four within three tries.
VENUE_BUSY_STATUS: Final = frozenset({502, 503, 504})

#: "You are asking too much." A different message entirely, and asking again is
#: precisely the wrong answer to it. One of these stops the round and buys a
#: long silence.
VENUE_LIMIT_STATUS: Final = frozenset({429})

#: How often to ask one instance through a busy signal before moving to the
#: next. Two, not three: with three instances in the rotation that is already
#: six chances, and a single attempt succeeds about four times in ten.
VENUE_ATTEMPTS: Final = 2

#: How long to leave Overpass alone after it says *we* are the problem.
#:
#: Learned the hard way: a burst of queries earns a 429, and carrying on
#: regardless earns a block that outlasts the session. A dashboard opening with
#: a dozen unresolved stays is exactly such a burst.
VENUE_BACKOFF: Final = 600

#: The shorter pause after the service itself was struggling. Not our fault and
#: usually over quickly, so a dashboard full of stays should not be written off
#: for ten minutes because one of them was unlucky.
VENUE_PAUSE: Final = 60

# --- frontend ---------------------------------------------------------------

CARD_FILENAME: Final = "family-tracking-card.js"
CARD_URL_BASE: Final = f"/{DOMAIN}"
