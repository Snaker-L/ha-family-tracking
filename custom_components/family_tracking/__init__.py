"""
Family Tracking: one integration for the map card and the data behind it.

The card alone could only work with what the browser could reach: it asked
Nominatim itself, cached the answers per device, and had no way to tell which of
a person's trackers was worth believing. All three belong on the server, where
there is one cache, one queue and one view of every tracker -- which is why this
integration exists and why it ships the card with it.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.start import async_at_started
from homeassistant.loader import async_get_integration

from . import websocket
from .const import (
    CONF_EMAIL,
    CONF_GEOCODE,
    CONF_HOME_ZONE,
    CONF_KEEP,
    CONF_MAX_ACCURACY,
    CONF_PERSONS,
    DEFAULT_HOME_ZONE,
    DEFAULT_KEEP,
    DEFAULT_MAX_ACCURACY,
    DOMAIN,
)
from .coordinator import FamilyTrackingCoordinator
from .frontend import async_register_card, async_remove_resource
from .geocode import Geocoder
from .track_store import TrackStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def _version(hass: HomeAssistant) -> str:
    """
    The version from the manifest Home Assistant has already read.

    Reading the file here would be a blocking call inside the event loop, which
    Home Assistant rightly complains about: everything else waits while the disk
    is touched. The loader hands out the parsed manifest for free.
    """
    integration = await async_get_integration(hass, DOMAIN)
    return str(integration.version or "0")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    options = dict(entry.options)

    # First, because the address cache lives in the same database.
    store = TrackStore(hass, options.get(CONF_KEEP) or DEFAULT_KEEP)
    await store.async_start()

    geocoder = Geocoder(
        hass,
        async_get_clientsession(hass),
        (options.get(CONF_EMAIL) or "").strip() or None,
        store,
    )
    await geocoder.async_load()

    coordinator = FamilyTrackingCoordinator(
        hass,
        geocoder,
        person_ids=options.get(CONF_PERSONS) or None,
        max_accuracy=float(options.get(CONF_MAX_ACCURACY) or DEFAULT_MAX_ACCURACY),
        home_zone=options.get(CONF_HOME_ZONE) or DEFAULT_HOME_ZONE,
        # Addresses follow the language Home Assistant is set to. An address
        # language stored by an older version is ignored on purpose: the field
        # is gone, so nobody could see or change it any more.
        language=hass.config.language,
        geocode=options.get(CONF_GEOCODE, True),
    )
    await coordinator.async_start()

    async def _import(_hass: HomeAssistant) -> None:
        # In the background: on a first start this copies weeks of recorder
        # history, and setup must not wait for that.
        entry.async_create_background_task(
            hass, store.async_import_recorder(), "family_tracking recorder import"
        )

    entry.async_on_unload(async_at_started(hass, _import))

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "geocoder": geocoder,
        "store": store,
    }

    websocket.async_register(hass)
    await async_register_card(hass, await _version(hass))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _prune_devices(hass, entry, coordinator)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


def _wanted_identifiers(entry: ConfigEntry, coordinator: FamilyTrackingCoordinator) -> set[str]:
    """
    Everything this entry should own a device for right now.

    One per followed person, plus the entry itself for the service device the
    diagnostics hang on.
    """
    return set(coordinator.person_ids) | {entry.entry_id}


def _prune_devices(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: FamilyTrackingCoordinator
) -> None:
    """
    Drops the devices of persons this entry no longer follows.

    Renaming a person in Home Assistant changes its entity id, and the device
    here is keyed by that id. Without this, the old device stays behind with its
    two sensors and the integration page fills up with pairs -- "Alex" next to
    "Hruza Alexander" -- that describe the same person. Deselecting somebody
    left the same litter.

    Only devices belonging to this entry are touched, and only those whose
    identifier names nothing we still follow.
    """
    registry = dr.async_get(hass)
    wanted = _wanted_identifiers(entry, coordinator)
    stale = [
        device
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
        if not ({ident for domain, ident in device.identifiers if domain == DOMAIN} & wanted)
    ]
    for device in stale:
        # A device belongs to exactly one entry, so dropping it from this one
        # means removing it outright.
        registry.async_remove_device(device.id)
    if stale:
        _LOGGER.info(
            "Removed %s device(s) for persons no longer followed: %s",
            len(stale),
            ", ".join(sorted(device.name or device.id for device in stale)),
        )


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> bool:
    """
    Lets the delete button work for a device whose person is gone.

    Home Assistant hides the button unless an integration answers this. A
    device that is still followed must stay, otherwise it would reappear at the
    next reload and the deletion would look broken.
    """
    data = (hass.data.get(DOMAIN) or {}).get(entry.entry_id)
    if data is None:
        return True
    wanted = _wanted_identifiers(entry, data["coordinator"])
    return not ({ident for domain, ident in device.identifiers if domain == DOMAIN} & wanted)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["coordinator"].async_stop()
        # Write the cache out now rather than losing whatever the delayed save
        # was still holding -- and before the database it goes to is closed.
        await data["geocoder"].async_save()
        await data["store"].async_stop()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Leave nothing behind: a resource pointing at a path that stopped being
    served would break every dashboard using the card."""
    await async_remove_resource(hass)


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
