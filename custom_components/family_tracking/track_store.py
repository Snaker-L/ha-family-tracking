"""
The integration's own record of where everybody was.

The card's timeline used to show whatever the recorder kept, and the recorder
keeps ten days unless somebody edits `configuration.yaml`. How long that is
belongs to the whole installation, and an integration has no business changing
it: the setting covers every energy meter and thermostat as well. So this keeps
its own copy of just the positions, for as long as the options say, and leaves
the recorder alone.

A separate SQLite file rather than a Home Assistant `Store`: five years of a
family's positions are millions of rows, which a JSON file rewritten on every
save cannot carry. SQLite with one index answers a month's range for one person
in milliseconds at that size, whatever database the recorder itself runs on.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_time_change, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DEFAULT_KEEP
from .retention import cutoff_for, parse_keep

_LOGGER = logging.getLogger(__name__)

FILENAME = "family_tracking.db"

#: Addresses were always kept for ninety days, and keeping positions for less
#: than that is no reason to ask Nominatim again sooner.
ADDRESS_MIN_TTL = 90 * 24 * 60 * 60

#: Positions are written in batches. A crash loses at most this much, and the
#: recorder still has it, so the next start fills the gap back in.
FLUSH_INTERVAL = timedelta(seconds=30)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    entity_id TEXT NOT NULL,
    ts        REAL NOT NULL,
    state     TEXT,
    latitude  REAL NOT NULL,
    longitude REAL NOT NULL,
    accuracy  REAL,
    source    TEXT,
    PRIMARY KEY (entity_id, ts)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS addresses (
    key  TEXT PRIMARY KEY,
    at   REAL NOT NULL,
    data TEXT NOT NULL
) WITHOUT ROWID;
"""

Row = tuple[str, float, str | None, float, float, float | None, str | None]


def _row_of(state: State) -> Row | None:
    """A state as one stored position, or nothing if it has no coordinates."""
    attributes = state.attributes
    try:
        latitude = float(attributes["latitude"])
        longitude = float(attributes["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    accuracy = attributes.get("gps_accuracy")
    try:
        accuracy = float(accuracy) if accuracy is not None else None
    except (TypeError, ValueError):
        accuracy = None
    source = attributes.get("source")
    return (
        state.entity_id,
        state.last_updated.timestamp(),
        state.state,
        latitude,
        longitude,
        accuracy,
        str(source) if source is not None else None,
    )


class TrackStore:
    """Records every `person` position and answers range queries for the card."""

    def __init__(self, hass: HomeAssistant, keep: str) -> None:
        self.hass = hass
        self.keep = keep if parse_keep(keep) else DEFAULT_KEEP
        self.path = hass.config.path(FILENAME)
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None
        self._pending: list[Row] = []
        self._unsubscribe: list[Callable[[], None]] = []

    # -- lifecycle -----------------------------------------------------------

    async def async_start(self) -> None:
        await self.hass.async_add_executor_job(self._open)
        await self.async_purge()
        self._unsubscribe.append(
            self.hass.bus.async_listen(
                EVENT_STATE_CHANGED, self._handle_change, event_filter=_is_person
            )
        )
        self._unsubscribe.append(
            async_track_time_interval(self.hass, self._async_flush_timer, FLUSH_INTERVAL)
        )
        # Nightly, like the recorder's own purge, and at an hour nobody looks.
        self._unsubscribe.append(
            async_track_time_change(self.hass, self._async_purge_timer, hour=4, minute=17, second=0)
        )

    async def async_stop(self) -> None:
        for remove in self._unsubscribe:
            remove()
        self._unsubscribe.clear()
        await self.async_flush()
        await self.hass.async_add_executor_job(self._close)

    def _open(self) -> None:
        # Opened for use from whichever executor thread comes along; the lock
        # below is what keeps two of them from interleaving.
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def _close(self) -> None:
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None

    # -- recording -----------------------------------------------------------

    @callback
    def _handle_change(self, event: Event[EventStateChangedData]) -> None:
        state = event.data["new_state"]
        if state is None:
            return
        row = _row_of(state)
        if row is not None:
            self._pending.append(row)

    async def _async_flush_timer(self, _now: datetime) -> None:
        await self.async_flush()

    async def async_flush(self) -> None:
        if not self._pending:
            return
        rows, self._pending = self._pending, []
        await self.hass.async_add_executor_job(self._insert, rows)

    def _insert(self, rows: list[Row]) -> None:
        with self._lock:
            if self._db is None:
                return
            # The key is entity and timestamp, so a position the recorder import
            # already brought in is simply not written twice.
            self._db.executemany(
                "INSERT OR IGNORE INTO positions VALUES (?, ?, ?, ?, ?, ?, ?)", rows
            )
            self._db.commit()

    # -- purging -------------------------------------------------------------

    def cutoff(self) -> datetime:
        return cutoff_for(self.keep, dt_util.utcnow())

    async def _async_purge_timer(self, _now: datetime) -> None:
        await self.async_purge()

    async def async_purge(self) -> None:
        removed = await self.hass.async_add_executor_job(self._purge, self.cutoff().timestamp())
        if removed:
            _LOGGER.info("Removed %s position(s) older than %s", removed, self.keep)
        expired = await self.hass.async_add_executor_job(
            self._purge_addresses, dt_util.utcnow().timestamp() - self.address_ttl()
        )
        if expired:
            _LOGGER.info("Removed %s address(es) looked up too long ago", expired)

    def _purge(self, cutoff: float) -> int:
        with self._lock:
            if self._db is None:
                return 0
            cursor = self._db.execute("DELETE FROM positions WHERE ts < ?", (cutoff,))
            self._db.commit()
            return cursor.rowcount

    # -- addresses -----------------------------------------------------------

    def address_ttl(self) -> float:
        """
        How long a looked-up address is kept, in seconds.

        As long as the positions, so a month from half a year ago still has its
        street names when somebody opens it, and never less than the ninety
        days the cache always held: an address is no less true for the
        positions around it being short-lived.
        """
        kept = (dt_util.utcnow() - self.cutoff()).total_seconds()
        return max(ADDRESS_MIN_TTL, kept)

    async def async_load_addresses(self) -> dict[str, dict]:
        cutoff = dt_util.utcnow().timestamp() - self.address_ttl()
        return await self.hass.async_add_executor_job(self._load_addresses, cutoff)

    def _load_addresses(self, cutoff: float) -> dict[str, dict]:
        with self._lock:
            if self._db is None:
                return {}
            rows = self._db.execute(
                "SELECT key, data FROM addresses WHERE at >= ?", (cutoff,)
            ).fetchall()
        entries: dict[str, dict] = {}
        for key, data in rows:
            try:
                entries[key] = json.loads(data)
            except ValueError:
                continue
        return entries

    async def async_save_addresses(self, entries: dict[str, dict]) -> None:
        """Writes the given entries, replacing older answers for the same place."""
        if entries:
            await self.hass.async_add_executor_job(self._save_addresses, entries)

    def _save_addresses(self, entries: dict[str, dict]) -> None:
        rows = [
            (key, float(entry.get("at", 0)), json.dumps(entry, ensure_ascii=False))
            for key, entry in entries.items()
        ]
        with self._lock:
            if self._db is None:
                return
            self._db.executemany("INSERT OR REPLACE INTO addresses VALUES (?, ?, ?)", rows)
            self._db.commit()

    def _purge_addresses(self, cutoff: float) -> int:
        with self._lock:
            if self._db is None:
                return 0
            cursor = self._db.execute("DELETE FROM addresses WHERE at < ?", (cutoff,))
            self._db.commit()
            return cursor.rowcount

    # -- importing from the recorder ------------------------------------------

    async def async_import_recorder(self) -> None:
        """
        Copies what the recorder still holds and this store does not.

        On the first start that is everything the recorder kept, so the
        timeline does not begin empty. Later it closes two kinds of gap: the
        time before the oldest stored position, which appears when the setting
        was raised, and the last day, which covers a crash or a period with the
        integration switched off.
        """
        try:
            from homeassistant.components.recorder import get_instance, history
        except ImportError:
            return
        try:
            instance = get_instance(self.hass)
        except (KeyError, RuntimeError):
            return
        if not await instance.async_db_ready:
            return

        oldest, newest = await self.hass.async_add_executor_job(self._bounds)
        now = dt_util.utcnow()
        cutoff = self.cutoff()
        ranges: list[tuple[datetime, datetime]] = []
        if oldest is None:
            ranges.append((cutoff, now))
        else:
            ranges.append((cutoff, dt_util.utc_from_timestamp(oldest)))
            ranges.append((max(cutoff, dt_util.utc_from_timestamp(newest) - timedelta(days=1)), now))

        person_ids = self.hass.states.async_entity_ids("person")
        imported = 0
        for start, end in ranges:
            if start >= end:
                continue
            for person_id in person_ids:
                changes = await instance.async_add_executor_job(
                    lambda pid=person_id, s=start, e=end: history.state_changes_during_period(
                        self.hass,
                        s,
                        e,
                        entity_id=pid,
                        no_attributes=False,
                        # Otherwise the state at `start` comes back stamped with
                        # `start` and would be stored as a second, invented row.
                        include_start_time_state=False,
                    )
                )
                rows = [row for state in changes.get(person_id, []) if (row := _row_of(state))]
                if rows:
                    await self.hass.async_add_executor_job(self._insert, rows)
                    imported += len(rows)
        if imported:
            _LOGGER.info("Took over %s position(s) from the recorder", imported)

    # -- reading -------------------------------------------------------------

    def _bounds(self) -> tuple[float | None, float | None]:
        with self._lock:
            if self._db is None:
                return None, None
            return self._db.execute("SELECT MIN(ts), MAX(ts) FROM positions").fetchone()

    async def async_positions(
        self, entity_id: str, start: datetime, end: datetime
    ) -> list[dict[str, object]]:
        """
        One person's positions in a range, in the recorder's compressed form.

        The same shape as `history/history_during_period`, so the card parses
        both with one function. The last position before the range comes along
        stamped with the range's start, as the recorder does, so a track begins
        where the person was rather than wherever they next moved.
        """
        await self.async_flush()
        rows = await self.hass.async_add_executor_job(
            self._range, entity_id, start.timestamp(), end.timestamp()
        )
        return [
            {
                "s": state,
                "a": {
                    "latitude": latitude,
                    "longitude": longitude,
                    **({"gps_accuracy": accuracy} if accuracy is not None else {}),
                    **({"source": source} if source is not None else {}),
                },
                "lu": ts,
            }
            for ts, state, latitude, longitude, accuracy, source in rows
        ]

    def _range(self, entity_id: str, start: float, end: float) -> list[tuple]:
        with self._lock:
            if self._db is None:
                return []
            before = self._db.execute(
                "SELECT ts, state, latitude, longitude, accuracy, source FROM positions"
                " WHERE entity_id = ? AND ts < ? ORDER BY ts DESC LIMIT 1",
                (entity_id, start),
            ).fetchone()
            rows = self._db.execute(
                "SELECT ts, state, latitude, longitude, accuracy, source FROM positions"
                " WHERE entity_id = ? AND ts >= ? AND ts <= ? ORDER BY ts",
                (entity_id, start, end),
            ).fetchall()
        if before is not None:
            rows.insert(0, (start, *before[1:]))
        return rows

    async def async_stats(self) -> tuple[float | None, float]:
        """The oldest stored position as a timestamp, and the file size in MiB."""
        oldest, _ = await self.hass.async_add_executor_job(self._bounds)
        size = await self.hass.async_add_executor_job(self._size_mib)
        return oldest, size

    def _size_mib(self) -> float:
        try:
            return os.path.getsize(self.path) / (1024 * 1024)
        except OSError:
            return 0.0


@callback
def _is_person(event_data: EventStateChangedData) -> bool:
    return event_data["entity_id"].startswith("person.")
