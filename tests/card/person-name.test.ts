import { deepStrictEqual, match, strictEqual } from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import { deviceNameUpdate, personDevices, personNames } from "../../src/person-name.ts";
import type { HassEntity, HomeAssistant } from "../../src/types.ts";

function entity(entity_id: string, attributes: Record<string, unknown>): HassEntity {
  return { entity_id, state: "", attributes, last_changed: "", last_updated: "" } as HassEntity;
}

function hass(nameByUser: string | null): Pick<HomeAssistant, "states" | "entities" | "devices"> {
  return {
    states: {
      "person.claudia": entity("person.claudia", { friendly_name: "Claudia Hruza Claudia" }),
      "person.admin": entity("person.admin", { friendly_name: "admin" }),
      "sensor.claudia_location": entity("sensor.claudia_location", {
        integration: "family_tracking",
        person_entity_id: "person.claudia",
      }),
      // Some other integration's sensor that happens to name a person.
      "sensor.other": entity("sensor.other", { person_entity_id: "person.admin" }),
    },
    entities: {
      "sensor.claudia_location": { entity_id: "sensor.claudia_location", device_id: "dev1" },
      "sensor.other": { entity_id: "sensor.other", device_id: "dev2" },
    },
    devices: {
      dev1: { id: "dev1", name: "Claudia Hruza Claudia", name_by_user: nameByUser },
      dev2: { id: "dev2", name: "Other", name_by_user: "Nicht verwenden" },
    },
  };
}

describe("Namen der Personen", () => {
  /* Ein Test mit selbst erfundenen Attributen beweist nichts, wenn der Sensor
     sie anders nennt -- genau so blieb der Stift im Editor einmal unsichtbar. */
  it("liest das Attribut, das der Sensor der Integration wirklich setzt", () => {
    const read = (file: string) =>
      readFileSync(new URL(`../../custom_components/family_tracking/${file}`, import.meta.url), "utf8");
    match(read("const.py"), /^ATTR_PERSON: Final = "person_entity_id"$/m);
    match(read("sensor.py"), /ATTR_PERSON: person\.person_id/);
    match(read("sensor.py"), /"integration": DOMAIN/);
  });

  it("findet das Gerät der Integration über den Standort-Sensor", () => {
    deepStrictEqual([...personDevices(hass(null))], [["person.claudia", "dev1"]]);
  });

  it("nimmt den am Gerät vergebenen Namen", () => {
    strictEqual(personNames(hass("Hruza Claudia")).get("person.claudia"), "Hruza Claudia");
  });

  it("bleibt beim Namen der Person, solange das Gerät nicht umbenannt ist", () => {
    strictEqual(personNames(hass(null)).get("person.claudia"), "Claudia Hruza Claudia");
    strictEqual(personNames(hass("  ")).get("person.claudia"), "Claudia Hruza Claudia");
  });

  it("lässt Geräte anderer Integrationen außer Acht", () => {
    strictEqual(personNames(hass(null)).get("person.admin"), "admin");
  });

  it("kommt ohne Registries aus", () => {
    const { states } = hass("Hruza Claudia");
    strictEqual(personNames({ states }).get("person.claudia"), "Claudia Hruza Claudia");
  });
});

describe("Gerät umbenennen", () => {
  const person = "Claudia Hruza Claudia";

  /* So kam bei Alexander ein Gerätename zustande, der nur den Personennamen
     wiederholte: Feld geöffnet, nichts geändert, verlassen. */
  it("speichert nichts, wenn der Name unverändert bleibt", () => {
    strictEqual(deviceNameUpdate(person, null, person), undefined);
    strictEqual(deviceNameUpdate(" Hruza Claudia ", "Hruza Claudia", person), undefined);
  });

  it("setzt einen neuen Namen", () => {
    deepStrictEqual(deviceNameUpdate("Hruza Claudia", null, person), { name_by_user: "Hruza Claudia" });
    deepStrictEqual(deviceNameUpdate("Mama", "Hruza Claudia", person), { name_by_user: "Mama" });
  });

  it("entfernt den eigenen Namen bei leerem Feld oder dem Namen der Person", () => {
    deepStrictEqual(deviceNameUpdate("", "Hruza Claudia", person), { name_by_user: null });
    deepStrictEqual(deviceNameUpdate(person, "Hruza Claudia", person), { name_by_user: null });
  });

  it("räumt einen Gerätenamen auf, der nur den Personennamen wiederholt", () => {
    deepStrictEqual(deviceNameUpdate("", person, person), { name_by_user: null });
  });
});
