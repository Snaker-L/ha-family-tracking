"""
Reverse geocoding, once for the whole household.

The card used to ask Nominatim straight from the browser. That works, but every
browser keeps its own cache, so the same street gets looked up again on the
phone, on the tablet and after every cleared browser storage -- and each of
those is a request against a service that asks for one per second, worldwide,
from everyone.

Doing it here means one cache for the whole instance, kept on disk across
restarts, and one queue that honours the rate limit no matter how many browsers
are open.

The cache lives in the integration's own database, next to the positions, and
is kept as long as they are: a month from half a year ago should come back with
its street names rather than a minute of queued lookups. It used to be a Home
Assistant `Store`, which is read once on the first start and then removed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

import aiohttp
from aiohttp import ClientError, ClientSession
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .address import Address, cache_key, merge_venue, parse
from .const import (
    CACHE_SCHEMA,
    MIN_REQUEST_INTERVAL,
    NOMINATIM_URL,
    OVERPASS_URLS,
    STORAGE_KEY,
    STORAGE_VERSION,
    VENUE_ATTEMPTS,
    VENUE_BACKOFF,
    VENUE_BUSY_STATUS,
    VENUE_CONNECT_TIMEOUT,
    VENUE_DEAD_FOR,
    VENUE_LIMIT_STATUS,
    VENUE_MIN_REQUEST_INTERVAL,
    VENUE_PAUSE,
    VENUE_TIMEOUT,
)
from .venue import build_query, covers, pick_name

if TYPE_CHECKING:
    from .track_store import TrackStore

_LOGGER = logging.getLogger(__name__)

# Re-exported so the rest of the integration keeps importing from one place.
__all__ = ["Address", "Geocoder", "cache_key", "merge_venue", "parse"]


class Geocoder:
    """One queue, one cache, one place that talks to Nominatim."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        email: str | None,
        store: TrackStore,
    ) -> None:
        self._hass = hass
        self._session = session
        self._email = email
        self._store = store
        #: The file the cache lived in before it moved into the database.
        self._legacy: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._cache: dict[str, dict[str, Any]] = {}
        #: Keys changed since the last write; only these go to the database.
        self._changed: set[str] = set()
        # Serialises the requests. Without it a dashboard opening with twelve
        # stays would fire twelve lookups in the same tick.
        self._lock = asyncio.Lock()
        self._last_request = 0.0
        self._last_venue = 0.0
        #: Monotonic time before which Overpass is not to be asked again.
        self._venue_quiet_until = 0.0
        #: Which instance answered last; the next lookup starts there.
        self._venue_first = 0
        #: Instances that could not be reached, and until when to skip them.
        self._venue_dead: dict[str, float] = {}
        self._save_handle: asyncio.TimerHandle | None = None

    async def async_load(self) -> None:
        """Read the cache from the database, taking over the old file once."""
        self._cache = {
            key: entry
            for key, entry in (await self._store.async_load_addresses()).items()
            if isinstance(entry, dict) and entry.get("schema") == CACHE_SCHEMA
        }
        legacy = await self._legacy.async_load()
        if legacy:
            ttl = self._store.address_ttl()
            now = time.time()
            taken = {
                key: entry
                for key, entry in (legacy.get("entries") or {}).items()
                if isinstance(entry, dict)
                and entry.get("schema") == CACHE_SCHEMA
                and now - entry.get("at", 0) < ttl
                and key not in self._cache
            }
            await self._store.async_save_addresses(taken)
            self._cache.update(taken)
            await self._legacy.async_remove()
            _LOGGER.info("Moved %d cached address(es) into %s", len(taken), self._store.path)
        _LOGGER.debug("Loaded %d cached addresses", len(self._cache))

    async def async_save(self) -> None:
        if not self._changed:
            return
        changed, self._changed = self._changed, set()
        await self._store.async_save_addresses(
            {key: self._cache[key] for key in changed if key in self._cache}
        )

    def cached(self, latitude: float, longitude: float) -> Address | None:
        entry = self._cache.get(cache_key(latitude, longitude))
        if not entry:
            return None
        return merge_venue(Address(**entry["address"]), entry.get("venue") or "")

    async def async_resolve(
        self,
        latitude: float,
        longitude: float,
        language: str | None = None,
        places: bool = True,
        with_address: bool = False,
    ) -> Address | None:
        """
        What to call a position, from the cache where possible.

        The address and the name of the enclosing place are stored side by side
        rather than as one finished line. They answer different questions, the
        caller decides which it wants, and a dashboard that asks for one must
        not leave the other permanently unavailable to the next caller.
        """
        key = cache_key(latitude, longitude)
        entry = self._cache.get(key)
        if entry is not None and (not places or "venue" in entry):
            return self._compose(entry, places, with_address)

        async with self._lock:
            # Someone else may have filled it in while this call queued.
            entry = self._cache.get(key)
            if entry is not None and (not places or "venue" in entry):
                return self._compose(entry, places, with_address)

            wanted = []
            if entry is None:
                wanted.append(self._nominatim(latitude, longitude, language))
            if places:
                wanted.append(self._venue(latitude, longitude))
            # Both go to different services, so asking them at the same time
            # costs the longer of the two waits rather than their sum.
            answers = list(await asyncio.gather(*wanted))

        address = Address(**entry["address"]) if entry is not None else answers.pop(0)
        venue = answers.pop(0) if places else (entry or {}).get("venue")

        if address is None and not venue:
            return None

        stored: dict[str, Any] = {
            "address": (address or Address(label="")).as_dict(),
            "at": time.time(),
            "schema": CACHE_SCHEMA,
        }
        # `None` means the question could not be put, which is not the same as
        # "nothing is there". Storing it would freeze the street address in
        # place for months over one busy moment at the other end.
        if venue is not None:
            stored["venue"] = venue
        elif entry is not None and "venue" in entry:
            stored["venue"] = entry["venue"]

        if address is not None:
            self._cache[key] = stored
            self._changed.add(key)
            self._schedule_save()

        endgueltig = merge_venue(address, venue or "", with_address)
        if endgueltig is not None and places and venue is None:
            # Overpass could not be asked. The address goes back as a usable
            # line, but marked so that nothing downstream stores it -- the
            # browser keeps its own copy for a month, which would outlive the
            # busy moment by a long way.
            endgueltig.settled = False
        return endgueltig

    @staticmethod
    def _compose(entry: dict[str, Any], places: bool, with_address: bool = False) -> Address:
        address = Address(**entry["address"])
        if not places:
            return address
        return merge_venue(address, entry.get("venue") or "", with_address)

    async def _nominatim(
        self, latitude: float, longitude: float, language: str | None
    ) -> Address | None:
        # The rate limit lives here rather than around the call, because the two
        # services are now asked at the same time and each has its own pace to
        # keep. Nominatim's usage policy is one request per second.
        wait = self._last_request + MIN_REQUEST_INTERVAL - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = time.monotonic()

        params = {
            "format": "jsonv2",
            "lat": f"{latitude}",
            "lon": f"{longitude}",
            "zoom": "18",
            "addressdetails": "1",
        }
        if language:
            params["accept-language"] = language
        if self._email:
            params["email"] = self._email

        try:
            async with self._session.get(
                NOMINATIM_URL,
                params=params,
                headers={"User-Agent": "home-assistant-family-tracking"},
                timeout=15,
            ) as response:
                if response.status != 200:
                    _LOGGER.debug("Nominatim answered %s", response.status)
                    return None
                payload = await response.json(content_type=None)
        except (ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Nominatim unreachable: %s", err)
            return None

        address = parse(payload)
        return address if address.label else None

    async def _venue(self, latitude: float, longitude: float) -> str | None:
        """
        The name of the place this coordinate is inside.

        Three outcomes, and the difference between the last two matters: a name,
        `""` for "nothing encloses this spot", and `None` for "could not ask".
        Overpass is donated capacity and answers a burst with 429; treating that
        like an empty result would write the street address into a cache that
        holds for months, and the shopping centre would stay misnamed long after
        the service was happy again.
        """
        if time.monotonic() < self._venue_quiet_until:
            # Told to slow down recently. Asking anyway is how a busy signal
            # turns into a block.
            return None

        query = build_query(latitude, longitude)

        # Each instance gets the full round of attempts before the next one is
        # tried. A rate limit ends that instance's turn immediately -- asking
        # again is the one thing it just told us not to do.
        reihenfolge = [
            OVERPASS_URLS[(self._venue_first + i) % len(OVERPASS_URLS)]
            for i in range(len(OVERPASS_URLS))
        ]

        for stelle, url in enumerate(reihenfolge):
            if time.monotonic() < self._venue_dead.get(url, 0.0):
                continue
            gedrosselt = False
            for versuch in range(1, VENUE_ATTEMPTS + 1):
                wait = self._last_venue + VENUE_MIN_REQUEST_INTERVAL - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last_venue = time.monotonic()

                try:
                    async with self._session.post(
                        url,
                        data={"data": query},
                        headers={"User-Agent": "home-assistant-family-tracking"},
                        timeout=aiohttp.ClientTimeout(
                            total=VENUE_TIMEOUT, sock_connect=VENUE_CONNECT_TIMEOUT
                        ),
                    ) as response:
                        if response.status in VENUE_LIMIT_STATUS:
                            _LOGGER.debug("%s is rate limiting (%s)", url, response.status)
                            gedrosselt = True
                            break
                        if response.status in VENUE_BUSY_STATUS:
                            _LOGGER.debug(
                                "%s is busy (%s), attempt %d of %d",
                                url, response.status, versuch, VENUE_ATTEMPTS,
                            )
                            continue
                        if response.status != 200:
                            _LOGGER.debug("%s answered %s", url, response.status)
                            break
                        # Overpass reports its own errors as XML with a 200, so
                        # the content type is not something to insist on here
                        # -- but then the body will not parse, which lands in
                        # the same place as any other failure.
                        payload = await response.json(content_type=None)
                except (ClientError, asyncio.TimeoutError, ValueError) as err:
                    _LOGGER.debug("Could not reach %s: %s", url, err)
                    self._venue_dead[url] = time.monotonic() + VENUE_DEAD_FOR
                    break

                if not covers(payload):
                    # It answered, but it has no data for this part of the
                    # world. Believing it would cache "nothing here" as fact.
                    _LOGGER.debug("%s holds no data around this fix", url)
                    break

                # Worth starting here next time.
                self._venue_first = (self._venue_first + stelle) % len(OVERPASS_URLS)
                return pick_name(payload)

            if gedrosselt and stelle == len(reihenfolge) - 1:
                # Every instance turned us away. That is about us, not them.
                self._venue_quiet_until = time.monotonic() + VENUE_BACKOFF
                return None

        # Nobody answered usefully. A short pause, not the long one.
        self._venue_quiet_until = time.monotonic() + VENUE_PAUSE
        return None

    def _schedule_save(self) -> None:
        """Write at most once every half minute rather than per lookup."""
        if self._save_handle is not None:
            return

        def _write() -> None:
            self._save_handle = None
            self._hass.async_create_task(self.async_save())

        self._save_handle = self._hass.loop.call_later(30, _write)
