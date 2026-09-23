"""Setting the integration up from the interface, with no YAML involved."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

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
    KEEP_SUGGESTIONS,
)
from homeassistant.util import dt as dt_util

from .recorder_info import UNKNOWN, format_size
from .retention import format_keep, parse_keep, validate_keep


def _all_persons(hass: HomeAssistant) -> list[str]:
    return sorted(hass.states.async_entity_ids("person"))


def _form_defaults(hass: HomeAssistant, options: dict[str, Any]) -> dict[str, Any]:
    """
    What the form shows, which is not always what is stored.

    An empty person list is stored for "everyone", so that somebody added to
    Home Assistant later is included instead of quietly missing. Shown empty,
    though, it reads as "nobody". The form therefore ticks everybody instead.
    """
    defaults = dict(options)
    if not defaults.get(CONF_PERSONS):
        defaults[CONF_PERSONS] = _all_persons(hass)
    # A value from the list shows its translated label; a typed one such as
    # "40d" has none and is written out instead, so it reads "40 Tage".
    keep = defaults.get(CONF_KEEP)
    if not parse_keep(keep) and not isinstance(keep, str):
        keep = DEFAULT_KEEP
    if parse_keep(keep):
        defaults[CONF_KEEP] = (
            keep if keep in KEEP_SUGGESTIONS else format_keep(keep, hass.config.language)
        )
    return defaults


def _stored(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, Any]:
    """
    The reverse of `_form_defaults`: everybody ticked is stored as "everyone".

    Otherwise saving the form once would freeze today's household into the
    options, and the next person added would get no sensors.
    """
    options = dict(user_input)
    if set(options.get(CONF_PERSONS) or []) >= set(_all_persons(hass)):
        options[CONF_PERSONS] = []
    options[CONF_KEEP], _, _ = validate_keep(options.get(CONF_KEEP))
    return options


def _errors(user_input: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """
    What is wrong with the input, keyed by the field to show it under, and the
    placeholder that lets the message quote what was typed.
    """
    _, error, detail = validate_keep(user_input.get(CONF_KEEP))
    return ({CONF_KEEP: error} if error else {}), {"typed": detail}


async def _store_facts(hass: HomeAssistant, entry_id: str | None) -> dict[str, str]:
    """
    How much position history there is, for the text above the form.

    Before the first setup there is no store yet, and the dashes say so.
    """
    data = (hass.data.get(DOMAIN) or {}).get(entry_id) if entry_id else None
    store = data.get("store") if isinstance(data, dict) else None
    if store is None:
        return {"store_since": UNKNOWN, "store_size": UNKNOWN}
    oldest, size_mib = await store.async_stats()
    since = (
        dt_util.as_local(dt_util.utc_from_timestamp(oldest)).strftime("%d.%m.%Y")
        if oldest is not None
        else UNKNOWN
    )
    return {"store_since": since, "store_size": format_size(size_mib)}


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    """The options, in the order somebody reads them."""
    return vol.Schema(
        {
            vol.Optional(CONF_PERSONS, default=defaults.get(CONF_PERSONS, [])): selector.
            EntitySelector(
                selector.EntitySelectorConfig(domain="person", multiple=True)
            ),
            # One field for amount and unit: a list of the usual choices that
            # also takes anything typed, such as "40 Tage".
            vol.Required(CONF_KEEP, default=defaults[CONF_KEEP]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(KEEP_SUGGESTIONS),
                    custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="keep",
                )
            ),
            vol.Optional(CONF_GEOCODE, default=defaults.get(CONF_GEOCODE, True)): selector.
            BooleanSelector(),
            vol.Optional(CONF_EMAIL, default=defaults.get(CONF_EMAIL, "")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
            ),
            vol.Optional(
                CONF_MAX_ACCURACY, default=defaults.get(CONF_MAX_ACCURACY, DEFAULT_MAX_ACCURACY)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=10, max=2000, step=10, unit_of_measurement="m")
            ),
            vol.Optional(
                CONF_HOME_ZONE, default=defaults.get(CONF_HOME_ZONE, DEFAULT_HOME_ZONE)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="zone")),
        }
    )


class FamilyTrackingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Only one entry: the integration watches the whole household."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        typed: dict[str, str] = {"typed": ""}
        if user_input is not None:
            errors, typed = _errors(user_input)
            if not errors:
                return self.async_create_entry(
                    title="Family Tracking", data={}, options=_stored(self.hass, user_input)
                )

        facts = await _store_facts(self.hass, None) | typed
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(_form_defaults(self.hass, user_input or {})),
            description_placeholders=facts,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return FamilyTrackingOptionsFlow()


class FamilyTrackingOptionsFlow(OptionsFlow):
    """The same form again, so nothing has to be removed to be changed."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        typed: dict[str, str] = {"typed": ""}
        if user_input is not None:
            errors, typed = _errors(user_input)
            if not errors:
                return self.async_create_entry(data=_stored(self.hass, user_input))
        facts = await _store_facts(self.hass, self.config_entry.entry_id) | typed
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(
                _form_defaults(self.hass, user_input or dict(self.config_entry.options))
            ),
            description_placeholders=facts,
            errors=errors,
        )
