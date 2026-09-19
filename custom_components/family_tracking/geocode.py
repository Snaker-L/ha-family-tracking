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
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from aiohttp import ClientError, ClientSession
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .address import Address, cache_key, merge_venue, parse
from .const import (
    CACHE_SCHEMA,
    CACHE_TTL_DAYS,
    MIN_REQUEST_INTERVAL,
    NOMINATIM_URL,
    OVERPASS_URL,
    STORAGE_KEY,
    STORAGE_VERSION,
    VENUE_BACKOFF,
    VENUE_MIN_REQUEST_INTERVAL,
    VENUE_RETRY_STATUS,
    VENUE_TIMEOUT,
)
from .venue import build_query, pick_name

_LOGGER = logging.getLogger(__name__)

# Re-exported so the rest of the integration keeps importing from one place.
__all__ = ["Address", "Geocoder", "cache_key", "merge_venue", "parse"]

_TTL_SECONDS = CACHE_TTL_DAYS * 24 * 60 * 60


class Geocoder:
    """One queue, one cache, one place that talks to Nominatim."""

    def __init__(self, hass: HomeAssistant, session: ClientSession, email: str | None) -> None:
        self._hass = hass
        self._session = session
        self._email = email
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._cache: dict[str, dict[str, Any]] = {}
        # Serialises the requests. Without it a dashboard opening with twelve
        # stays would fire twelve lookups in the same tick.
        self._lock = asyncio.Lock()
        self._last_request = 0.0
        self._last_venue = 0.0
        #: Monotonic time before which Overpass is not to be asked again.
        self._venue_quiet_until = 0.0
        self._save_handle: asyncio.TimerHandle | None = None
        self._dirty = False

    async def async_load(self) -> None:
        """Read the cache from disk and drop whatever has gone stale."""
        stored = await self._store.async_load() or {}
        now = time.time()
        entries: dict[str, dict[str, Any]] = stored.get("entries", {})
        self._cache = {
            key: entry
            for key, entry in entries.items()
            if isinstance(entry, dict)
            and now - entry.get("at", 0) < _TTL_SECONDS
            and entry.get("schema") == CACHE_SCHEMA
        }
        _LOGGER.debug("Loaded %d cached addresses", len(self._cache))

    async def async_save(self) -> None:
        if not self._dirty:
            return
        await self._store.async_save({"entries": self._cache})
        self._dirty = False

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
            return self._compose(entry, places)

        async with self._lock:
            # Someone else may have filled it in while this call queued.
            entry = self._cache.get(key)
            if entry is not None and (not places or "venue" in entry):
                return self._compose(entry, places)

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
            self._dirty = True
            self._schedule_save()

        return merge_venue(address, venue or "")

    @staticmethod
    def _compose(entry: dict[str, Any], places: bool) -> Address:
        address = Address(**entry["address"])
        return merge_venue(address, entry.get("venue") or "") if places else address

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

        # One retry. The commonest failure is a busy moment -- 429 or 504 --
        # and the instance is usually fine seconds later. Beyond that it is not
        # worth pressing: the address is already a usable line, and the next fix
        # at this spot asks again.
        for attempt in (1, 2):
            wait = self._last_venue + VENUE_MIN_REQUEST_INTERVAL - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_venue = time.monotonic()

            try:
                async with self._session.post(
                    OVERPASS_URL,
                    data={"data": query},
                    headers={"User-Agent": "home-assistant-family-tracking"},
                    timeout=VENUE_TIMEOUT,
                ) as response:
                    if response.status in VENUE_RETRY_STATUS:
                        if attempt == 1:
                            _LOGGER.debug(
                                "Overpass is busy (%s), asking once more", response.status
                            )
                            continue
                        _LOGGER.debug(
                            "Overpass is busy (%s), leaving it alone for %d s",
                            response.status,
                            VENUE_BACKOFF,
                        )
                        self._venue_quiet_until = time.monotonic() + VENUE_BACKOFF
                        return None
                    if response.status != 200:
                        _LOGGER.debug("Overpass answered %s", response.status)
                        return None
                    # Overpass reports its own errors as XML with a 200, so the
                    # content type is not something to insist on here -- but
                    # then the body will not parse, which lands in the same
                    # place as any other failure.
                    payload = await response.json(content_type=None)
            except (ClientError, asyncio.TimeoutError, ValueError) as err:
                _LOGGER.debug("Could not ask what encloses the fix: %s", err)
                self._venue_quiet_until = time.monotonic() + VENUE_BACKOFF
                return None

            return pick_name(payload)

        return None

    def _schedule_save(self) -> None:
        """Write at most once every half minute rather than per lookup."""
        if self._save_handle is not None:
            return

        def _write() -> None:
            self._save_handle = None
            self._hass.async_create_task(self.async_save())

        self._save_handle = self._hass.loop.call_later(30, _write)
