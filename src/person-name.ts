import type { HomeAssistant } from "./types";

const DOMAIN = "family_tracking";

type Registries = Pick<HomeAssistant, "states" | "entities" | "devices">;

/**
 * The device the integration created for each person it follows, keyed by the
 * person entity. Found through the location sensor: it names its person in
 * `person_entity_id` (ATTR_PERSON in the integration's const.py), and the
 * entity registry knows which device the sensor belongs to.
 */
export function personDevices(hass: Registries): Map<string, string> {
  const result = new Map<string, string>();
  if (!hass.entities) return result;
  for (const [id, entity] of Object.entries(hass.states)) {
    if (!id.startsWith("sensor.")) continue;
    const { integration, person_entity_id: person } = entity.attributes;
    if (integration !== DOMAIN || typeof person !== "string" || result.has(person)) continue;
    const deviceId = hass.entities[id]?.device_id;
    if (deviceId) result.set(person, deviceId);
  }
  return result;
}

/**
 * The name to show for every person: the name given to the person's device
 * under Settings → Devices if there is one, otherwise the person's own name.
 * That is the same name the device page shows, so both always agree.
 */
export function personNames(hass: Registries): Map<string, string> {
  const devices = personDevices(hass);
  const result = new Map<string, string>();
  for (const [id, entity] of Object.entries(hass.states)) {
    if (!id.startsWith("person.")) continue;
    const deviceId = devices.get(id);
    const renamed = deviceId ? hass.devices?.[deviceId]?.name_by_user?.trim() : undefined;
    result.set(id, renamed || entity.attributes.friendly_name || id.split(".")[1]);
  }
  return result;
}

/**
 * What to store as the device's own name when the editor is given `value`.
 * Undefined means there is nothing to change. A name equal to the person's
 * own is stored as no name at all: the device page then shows it greyed out,
 * as a default, instead of an override that merely repeats it.
 */
export function deviceNameUpdate(
  value: string,
  current: string | null | undefined,
  personName: string
): { name_by_user: string | null } | undefined {
  const trimmed = value.trim();
  const next = trimmed && trimmed !== personName ? trimmed : null;
  return next === (current || null) ? undefined : { name_by_user: next };
}
