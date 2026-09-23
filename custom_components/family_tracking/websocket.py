"""
The command the card uses instead of talking to Nominatim itself.

Moving the lookup here is the whole point of the integration for the card: one
cache for every browser in the house, one queue that respects the rate limit,
and a result that survives clearing browser storage.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .geocode import Geocoder


@callback
def async_register(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, _handle_geocode)
    websocket_api.async_register_command(hass, _handle_settings)
    websocket_api.async_register_command(hass, _handle_history)


def _active(hass: HomeAssistant) -> tuple[Geocoder | None, bool]:
    """The geocoder to use, and whether it is allowed to ask anybody."""
    for data in (hass.data.get(DOMAIN) or {}).values():
        if not isinstance(data, dict):
            continue
        geocoder = data.get("geocoder")
        if geocoder is not None:
            coordinator = data.get("coordinator")
            return geocoder, bool(getattr(coordinator, "geocode_enabled", True))
    return None, True


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/geocode",
        vol.Required("latitude"): vol.Coerce(float),
        vol.Required("longitude"): vol.Coerce(float),
        vol.Optional("language"): vol.Any(str, None),
        vol.Optional("places", default=True): bool,
        vol.Optional("address", default=False): bool,
    }
)
@websocket_api.async_response
async def _handle_geocode(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    geocoder, enabled = _active(hass)
    if geocoder is None:
        connection.send_error(msg["id"], "not_ready", "Family Tracking is not set up")
        return

    if not enabled:
        # A plain result rather than an error, and that distinction is the
        # whole point. An error tells the card the integration cannot answer,
        # and it then asks Nominatim from the browser -- which is exactly the
        # traffic this setting was turned off to stop. `disabled` says the
        # instance decided against lookups, and the card drops the idea.
        connection.send_result(msg["id"], {"disabled": True})
        return

    address = await geocoder.async_resolve(
        msg["latitude"],
        msg["longitude"],
        msg.get("language"),
        places=msg["places"],
        with_address=msg["address"],
    )
    connection.send_result(
        msg["id"],
        {**address.as_dict(), "settled": address.settled} if address else None,
    )


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings"})
@callback
def _handle_settings(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """
    The instance-wide settings a card editor has to respect.

    Without this the editor offers switches the integration then overrules:
    "Resolve coordinates" stays on and clickable while nothing is looked up.
    And the card's timeline would draw every fix the live position refuses.
    """
    for data in (hass.data.get(DOMAIN) or {}).values():
        coordinator = data.get("coordinator") if isinstance(data, dict) else None
        if coordinator is not None:
            connection.send_result(
                msg["id"],
                {
                    "geocode": coordinator.geocode_enabled,
                    "max_accuracy": coordinator.max_accuracy,
                },
            )
            return
    connection.send_error(msg["id"], "not_ready", "Family Tracking is not set up")


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/history",
        vol.Required("entity_id"): str,
        vol.Required("start_time"): str,
        vol.Required("end_time"): str,
    }
)
@websocket_api.async_response
async def _handle_history(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """
    One person's stored positions, for ranges the recorder no longer holds.

    Answered in the recorder's compressed form, so the card merges the two
    sources with the parser it already has.
    """
    store = None
    for data in (hass.data.get(DOMAIN) or {}).values():
        if isinstance(data, dict) and data.get("store") is not None:
            store = data["store"]
            break
    if store is None:
        connection.send_error(msg["id"], "not_ready", "Family Tracking is not set up")
        return

    start = dt_util.parse_datetime(msg["start_time"])
    end = dt_util.parse_datetime(msg["end_time"])
    if start is None or end is None:
        connection.send_error(msg["id"], "invalid_format", "start_time and end_time must be ISO")
        return
    connection.send_result(
        msg["id"],
        await store.async_positions(msg["entity_id"], dt_util.as_utc(start), dt_util.as_utc(end)),
    )
