"""
What the recorder still holds, read out so the card's limits are visible.

The timeline can only show what the recorder kept. That makes the database part
of this integration's interface rather than a detail of the installation:
somebody who picks last month in the calendar and gets an empty map is looking
at `purge_keep_days`, not at a bug.

Nothing here changes anything. `purge_keep_days` belongs to `configuration.yaml`
and the nightly purge is global -- an integration can shorten the retention of
its own entities through `recorder.purge_entities`, but it can never extend it
beyond what the recorder keeps. Reporting the truth, with the numbers that
decide when a different database is due, is what this integration can honestly
do about it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

#: Beyond this, SQLite starts to make history queries slow enough to notice and
#: a server-backed database is the better home. The figure is a rule of thumb
#: from the Home Assistant documentation, not a hard limit.
SQLITE_MIGRATION_HINT_MIB = 2048

#: Shown wherever a value could not be read, so the form never says "None".
UNKNOWN = "—"


def format_size(mib: float | None) -> str:
    """
    A size somebody can read.

    Whole megabytes are right for a database that has been running a while, but
    a fresh one then reads "0 MiB", which looks like a failed measurement rather
    than an empty database.
    """
    if mib is None:
        return UNKNOWN
    if mib >= 1024:
        return f"{mib / 1024:.2f} GiB"
    if mib < 1:
        return f"{max(1, round(mib * 1024))} KiB"
    return f"{mib:.1f} MiB" if mib < 100 else f"{mib:.0f} MiB"


@dataclass(frozen=True)
class RecorderFacts:
    """The handful of numbers that answer "how far back does this go?"."""

    engine: str | None = None
    version: str | None = None
    size_mib: float | None = None
    keep_days: int | None = None
    oldest: datetime | None = None

    @property
    def history_days(self) -> float | None:
        """Days between the oldest surviving run and now."""
        if self.oldest is None:
            return None
        oldest = dt_util.as_utc(self.oldest) if self.oldest.tzinfo else self.oldest.replace(
            tzinfo=dt_util.UTC
        )
        return max(0.0, (dt_util.utcnow() - oldest).total_seconds() / 86400)

    @property
    def outgrown_sqlite(self) -> bool:
        """True once SQLite holds more than it comfortably should."""
        return (
            self.engine == "sqlite"
            and self.size_mib is not None
            and self.size_mib >= SQLITE_MIGRATION_HINT_MIB
        )

    def placeholders(self) -> dict[str, str]:
        """The values as the config flow wants them: strings, never None."""
        days = self.history_days
        return {
            "db_engine": self.engine or UNKNOWN,
            "db_version": self.version or UNKNOWN,
            "db_size": format_size(self.size_mib),
            "db_keep_days": str(self.keep_days) if self.keep_days is not None else UNKNOWN,
            "db_oldest": dt_util.as_local(self.oldest).strftime("%d.%m.%Y")
            if self.oldest is not None
            else UNKNOWN,
            "db_days": f"{days:.1f}" if days is not None else UNKNOWN,
        }


def _from_system_health(info: dict[str, Any]) -> dict[str, Any]:
    """
    Picks the fields out of what the recorder reports to the system health page.

    That page is the same source the user sees under Settings > System, so the
    numbers here and there cannot drift apart. The size arrives pre-formatted as
    "3205.78 MiB"; only the number is wanted.
    """
    size = None
    raw = info.get("estimated_db_size")
    if isinstance(raw, str) and raw.endswith("MiB"):
        try:
            size = float(raw.removesuffix("MiB").strip())
        except ValueError:
            size = None
    return {
        "engine": info.get("database_engine"),
        "version": str(info.get("database_version")) if info.get("database_version") else None,
        "size_mib": size,
        "oldest": info.get("oldest_recorder_run"),
    }


async def async_recorder_facts(hass: HomeAssistant) -> RecorderFacts:
    """
    Reads the recorder, and returns empty facts rather than failing.

    This is decoration on a form and a diagnostic sensor. A recorder that is
    absent, still starting, or one version further along than expected must
    never keep the integration from setting up, so every step is optional.
    """
    try:
        from homeassistant.components.recorder import get_instance
    except ImportError:
        return RecorderFacts()

    try:
        instance = get_instance(hass)
    except (KeyError, RuntimeError):
        # No recorder configured, or it has not reached `hass.data` yet.
        return RecorderFacts()

    keep_days = getattr(instance, "keep_days", None)
    values: dict[str, Any] = {}

    try:
        from homeassistant.components.recorder.system_health import system_health_info

        values = _from_system_health(await system_health_info(hass))
    except Exception:  # noqa: BLE001 - diagnostics must not break setup
        # Fall back to what the instance exposes directly. The size needs a
        # query per dialect and is simply left out here.
        dialect = getattr(instance, "dialect_name", None)
        engine = getattr(instance, "database_engine", None)
        runs = getattr(instance, "recorder_runs_manager", None)
        values = {
            "engine": getattr(dialect, "value", None),
            "version": str(engine.version) if engine is not None else None,
            "size_mib": None,
            "oldest": getattr(getattr(runs, "first", None), "start", None),
        }

    return RecorderFacts(
        engine=values.get("engine"),
        version=values.get("version"),
        size_mib=values.get("size_mib"),
        keep_days=int(keep_days) if isinstance(keep_days, (int, float)) else None,
        oldest=values.get("oldest"),
    )
