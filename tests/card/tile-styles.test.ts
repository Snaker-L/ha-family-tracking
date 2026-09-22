import { deepStrictEqual, ok, strictEqual } from "node:assert/strict";
import { describe, it } from "node:test";

import {
  COLOR_CHOICES,
  DEFAULTS,
  DEFAULT_SATELLITE_STYLE,
  DEFAULT_STREET_STYLE,
  DEFAULT_ZONE_COLOR,
  DEFAULT_ZONE_ICON,
  editedLayer,
  EDITOR_SCHEMA,
  FILL_HEIGHT,
  MAX_MAP_HEIGHT,
  MAX_STAY_MINUTES,
  MAX_STAY_RADIUS,
  MIN_MAP_HEIGHT,
  MIN_STAY_MINUTES,
  MIN_STAY_RADIUS,
  normalizeHex,
  OBSOLETE_KEYS,
  PERSON_PALETTE,
  resolveMapHeight,
  resolveStayMinutes,
  resolveStayRadius,
  MAX_ZOOM,
  resolveStyle,
  sanitizeStyles,
  SATELLITE_STYLES,
  toReferrerPolicy,
  STREET_STYLES,
  type SatelliteStyleId,
  zoneGeometry,
  zoneVisual,
  type StreetStyleId,
  type TileStyle,
} from "../../src/const";

const allStyles: [string, TileStyle][] = [
  ...Object.entries(STREET_STYLES),
  ...Object.entries(SATELLITE_STYLES),
];

describe("tile styles", () => {
  it("offers more than one choice per layer", () => {
    ok(Object.keys(STREET_STYLES).length > 1);
    ok(Object.keys(SATELLITE_STYLES).length > 1);
  });

  it("has a default that exists", () => {
    ok(DEFAULT_STREET_STYLE in STREET_STYLES);
    ok(DEFAULT_SATELLITE_STYLE in SATELLITE_STYLES);
  });

  /**
   * The whole point of the picker: two choices must not render the same map.
   * The comparison covers every layer, not just the base: the two satellite
   * styles share one aerial image and differ only in the labels above it.
   */
  it("makes every style render differently", () => {
    const signatures = allStyles.map(([, style]) => style.layers.map((l) => l.url).join(" "));
    deepStrictEqual(new Set(signatures).size, signatures.length);
  });

  it("carries a label, an attribution and at least one layer", () => {
    for (const [id, style] of allStyles) {
      ok(style.label.length > 0, `${id} has no label`);
      ok(style.attribution.length > 0, `${id} has no attribution`);
      ok(style.layers.length > 0, `${id} has no layers`);
    }
  });

  it("keeps every layer within the zoom the tiles actually reach", () => {
    for (const [id, style] of allStyles) {
      for (const layer of [...style.layers, ...(style.darkLayers ?? [])]) {
        ok(layer.url.includes("{z}"), `${id} has a layer without a zoom placeholder`);
        ok(
          layer.maxNativeZoom > 0 && layer.maxNativeZoom <= MAX_ZOOM,
          `${id} has an implausible maxNativeZoom`
        );
      }
    }
  });

  it("uses the same layer count light and dark, so a theme flip cannot lose labels", () => {
    for (const [id, style] of allStyles) {
      if (!style.darkLayers) continue;
      strictEqual(style.darkLayers.length, style.layers.length, `${id} differs between themes`);
    }
  });
});

const defaults = { street: DEFAULT_STREET_STYLE, satellite: DEFAULT_SATELLITE_STYLE };

describe("resolveStyle", () => {
  /**
   * The map only swaps layers when this key changes. If two picks produced the
   * same key, the picker would silently do nothing -- which is exactly the bug
   * this guards against.
   */
  it("gives every street pick its own key", () => {
    const keys = (Object.keys(STREET_STYLES) as StreetStyleId[]).map(
      (street) => resolveStyle("street", false, { ...defaults, street }).key
    );
    strictEqual(new Set(keys).size, keys.length);
  });

  it("gives every satellite pick its own key", () => {
    const keys = (Object.keys(SATELLITE_STYLES) as SatelliteStyleId[]).map(
      (satellite) => resolveStyle("satellite", false, { ...defaults, satellite }).key
    );
    strictEqual(new Set(keys).size, keys.length);
  });

  it("returns the layers of the style that was picked", () => {
    const resolved = resolveStyle("street", false, { ...defaults, street: "esri_streets" });
    deepStrictEqual(resolved.layers, STREET_STYLES.esri_streets.layers);
    strictEqual(resolved.label, STREET_STYLES.esri_streets.label);
  });

  it("switches to the dark layers only where the style has them", () => {
    const gray = resolveStyle("street", true, { ...defaults, street: "esri_gray" });
    deepStrictEqual(gray.layers, STREET_STYLES.esri_gray.darkLayers);
    ok(gray.key.endsWith(":dark"));

    // No dark variant: the light layers must stay, and the key must not claim dark.
    const topo = resolveStyle("street", true, { ...defaults, street: "esri_topo" });
    deepStrictEqual(topo.layers, STREET_STYLES.esri_topo.layers);
    ok(topo.key.endsWith(":light"));
  });

  it("keeps the two layers apart", () => {
    const street = resolveStyle("street", false, defaults);
    const satellite = resolveStyle("satellite", false, defaults);
    ok(street.key !== satellite.key);
  });
});

describe("sanitizeStyles", () => {
  it("passes valid ids through", () => {
    const sanitized = sanitizeStyles({ street_style: "esri_topo", satellite_style: "esri_hybrid" });
    strictEqual(sanitized.street, "esri_topo");
    strictEqual(sanitized.satellite, "esri_hybrid");
  });

  it("falls back when a style was removed or misspelled", () => {
    for (const config of [{ street_style: "gibt_es_nicht" }, {}]) {
      const sanitized = sanitizeStyles(config);
      strictEqual(sanitized.street, defaults.street);
      strictEqual(sanitized.satellite, defaults.satellite);
    }
  });
});

describe("eigene Kachel-URL", () => {
  const custom = { url: "https://{s}.tile.example.org/{z}/{x}/{y}.png", subdomains: "abc" };

  it("uses the entered URL instead of a built-in style", () => {
    const resolved = resolveStyle("street", false, {
      street: "custom",
      satellite: DEFAULT_SATELLITE_STYLE,
      customStreet: custom,
    });
    strictEqual(resolved.layers[0].url, custom.url);
    strictEqual(resolved.layers[0].subdomains, "abc");
  });

  /** An empty URL would leave a blank map and no obvious way back. */
  it("falls back to the default while no URL is entered", () => {
    const resolved = resolveStyle("street", false, {
      street: "custom",
      satellite: DEFAULT_SATELLITE_STYLE,
    });
    deepStrictEqual(resolved.layers, STREET_STYLES[DEFAULT_STREET_STYLE].layers);
  });

  it("keeps the key tied to the URL, so editing it swaps the layer", () => {
    const a = resolveStyle("street", false, { street: "custom", satellite: DEFAULT_SATELLITE_STYLE, customStreet: custom });
    const b = resolveStyle("street", false, {
      street: "custom",
      satellite: DEFAULT_SATELLITE_STYLE,
      customStreet: { url: "https://anders.example.org/{z}/{x}/{y}.png" },
    });
    ok(a.key !== b.key);
  });

  it("survives a custom id in the config", () => {
    const sanitized = sanitizeStyles({ street_style: "custom", custom_street: custom });
    strictEqual(sanitized.street, "custom");
    deepStrictEqual(sanitized.customStreet, custom);
  });
});

describe("Referrer-Richtlinie", () => {
  /**
   * Home Assistant sends `Referrer-Policy: no-referrer`, and OpenStreetMap
   * answers referrer-less requests with its "Access blocked" tile. The override
   * on the tile element is the only thing that makes those tiles load.
   */
  it("keeps the override on the OpenStreetMap style", () => {
    strictEqual(STREET_STYLES.osm.layers[0].referrerPolicy, "origin");
  });

  it("passes a valid policy through from a custom source", () => {
    const resolved = resolveStyle("street", false, {
      street: "custom",
      satellite: DEFAULT_SATELLITE_STYLE,
      customStreet: { url: "https://x.example/{z}/{x}/{y}.png", referrer_policy: "origin" },
    });
    strictEqual(resolved.layers[0].referrerPolicy, "origin");
  });

  it("drops a value the browser would not accept", () => {
    strictEqual(toReferrerPolicy("quatsch"), undefined);
    strictEqual(toReferrerPolicy(undefined), undefined);
    strictEqual(toReferrerPolicy("origin"), "origin");
  });
});

/**
 * The editor preview follows the picker that was just used, so choosing a
 * satellite style shows it without a second click on the layer button.
 */
describe("welche Ebene gerade bearbeitet wurde", () => {
  it("folgt der Satellitenauswahl", () => {
    strictEqual(editedLayer({}, { satellite_style: "esri_hybrid" }), "satellite");
  });

  it("folgt der Straßenauswahl", () => {
    strictEqual(editedLayer({}, { street_style: "opentopo" }), "street");
  });

  it("meldet nichts, wenn beide Stile gleich bleiben", () => {
    const config = { street_style: "opentopo", satellite_style: "esri_hybrid" };
    strictEqual(editedLayer(config, { ...config, title: "neu" } as typeof config), undefined);
  });

  it("ignoriert einen Stil, den es nicht gibt -- beide fallen auf denselben Standard", () => {
    strictEqual(editedLayer({ street_style: "gibtsnicht" }, { street_style: "auchnicht" }), undefined);
  });

  it("erkennt eine geänderte eigene Kachel-URL", () => {
    strictEqual(
      editedLayer(
        { satellite_style: "custom", custom_satellite: { url: "https://a.example/{z}/{x}/{y}.png" } },
        { satellite_style: "custom", custom_satellite: { url: "https://b.example/{z}/{x}/{y}.png" } }
      ),
      "satellite"
    );
  });

  it("nennt die Satellitenseite zuerst, wenn beide zugleich wechseln", () => {
    strictEqual(
      editedLayer({}, { street_style: "opentopo", satellite_style: "esri_hybrid" }),
      "satellite"
    );
  });
});

describe("Zonen-Darstellung", () => {
  it("nimmt das Icon von Home Assistant, solange keines gesetzt ist", () => {
    const visual = zoneVisual("zone.home", { icon: "mdi:home" }, {});
    strictEqual(visual.icon, "mdi:home");
    strictEqual(visual.color, DEFAULT_ZONE_COLOR);
  });

  it("fällt auf ein Standard-Icon zurück, wenn die Zone keines hat", () => {
    strictEqual(zoneVisual("zone.x", {}, {}).icon, DEFAULT_ZONE_ICON);
  });

  it("bevorzugt Icon und Farbe aus der Konfiguration", () => {
    const visual = zoneVisual(
      "zone.schule",
      { icon: "mdi:home" },
      { zone_icons: { "zone.schule": "mdi:school" }, zone_colors: { "zone.schule": "#ff0000" } }
    );
    strictEqual(visual.icon, "mdi:school");
    strictEqual(visual.color, "#ff0000");
  });

  it("lässt eine fremde Zone unberührt", () => {
    const config = { zone_icons: { "zone.andere": "mdi:school" } };
    strictEqual(zoneVisual("zone.home", { icon: "mdi:home" }, config).icon, "mdi:home");
  });

  /* Nicht jede zone-Entität lässt sich zeichnen; ein Kreis ohne Radius wäre
     ein unsichtbarer Kreis mit einem Icon in der Mitte. */
  it("liefert die Geometrie einer vollständigen Zone", () => {
    deepStrictEqual(zoneGeometry({ latitude: 48.2, longitude: 16.3, radius: 100 }), {
      lat: 48.2,
      lon: 16.3,
      radius: 100,
    });
  });

  it("überspringt Zonen ohne Koordinaten oder Radius", () => {
    strictEqual(zoneGeometry({}), undefined);
    strictEqual(zoneGeometry({ latitude: 48.2, longitude: 16.3 }), undefined);
    strictEqual(zoneGeometry({ latitude: 48.2, longitude: 16.3, radius: 0 }), undefined);
    strictEqual(zoneGeometry({ latitude: 48.2, longitude: 16.3, radius: -5 }), undefined);
    strictEqual(zoneGeometry({ latitude: "x", longitude: 16.3, radius: 100 }), undefined);
  });

  it("nimmt Zahlen auch als Zeichenkette an, so wie sie aus YAML kommen", () => {
    deepStrictEqual(zoneGeometry({ latitude: "48.2", longitude: "16.3", radius: "100" }), {
      lat: 48.2,
      lon: 16.3,
      radius: 100,
    });
  });
});

/*
 * `ha-form` reads a named group from `data[name]` and writes it back there. A
 * grid called "toggles" therefore stored the switches as
 * `toggles: { show_zones: true }`, which the card never reads -- the switch
 * showed its own nested value and looked on while nothing happened.
 *
 * The switches have since left the form altogether: they needed info icons a
 * label cannot carry, and half in and half out gave them two different row
 * spacings. Only the title is left, and it must stay flat for the same reason
 * the grid had to.
 */
describe("Editor-Schema", () => {
  it("enthält nur noch den Titel", () => {
    deepStrictEqual(
      EDITOR_SCHEMA.map((entry) => entry.name),
      ["title"]
    );
  });

  it("verschachtelt nichts", () => {
    // A group would nest its values under its own name, and the card reads the
    // keys flat. Nothing here has a type at all, so nothing can.
    for (const entry of EDITOR_SCHEMA) {
      strictEqual((entry as { type?: string }).type, undefined);
    }
  });

  it("nennt die Altlasten, die beim Speichern entfernt werden", () => {
    // `geocode_email` was a real option once: it identified the card to
    // Nominatim back when the card asked Nominatim itself. The integration
    // does the asking now, so the field only offered somewhere to type an
    // address that nothing would read.
    deepStrictEqual([...OBSOLETE_KEYS], ["toggles", "layers", "geocode_email"]);
  });
});

describe("Kartenhöhe", () => {
  it("nimmt eine vernünftige Zahl", () => {
    strictEqual(resolveMapHeight(700), 700);
    strictEqual(resolveMapHeight("700"), 700);
  });

  it("erkennt das Füllen", () => {
    strictEqual(resolveMapHeight(FILL_HEIGHT), FILL_HEIGHT);
  });

  /* Die Konfiguration kommt aus YAML, also darf auch Unsinn darin stehen. */
  it("fällt bei Unsinn auf den Standard zurück", () => {
    strictEqual(resolveMapHeight(undefined), DEFAULTS.map_height);
    strictEqual(resolveMapHeight(""), DEFAULTS.map_height);
    strictEqual(resolveMapHeight("480px"), DEFAULTS.map_height);
    strictEqual(resolveMapHeight(-100), DEFAULTS.map_height);
    strictEqual(resolveMapHeight(0), DEFAULTS.map_height);
    strictEqual(resolveMapHeight(99999), DEFAULTS.map_height);
  });

  it("lässt die Grenzen selbst zu", () => {
    strictEqual(resolveMapHeight(MIN_MAP_HEIGHT), MIN_MAP_HEIGHT);
    strictEqual(resolveMapHeight(MAX_MAP_HEIGHT), MAX_MAP_HEIGHT);
  });
});

/*
 * Aufenthaltsradius und Mindestdauer kommen jetzt aus der Konfiguration. Beide
 * landen über ein Zahlenfeld dort, und YAML kennt ohnehin keine Grenzen -- also
 * muss jeder Unsinn irgendwo sinnvoll landen statt in einer leeren Karte.
 */
describe("Aufenthaltseinstellungen", () => {
  it("nimmt vernünftige Werte unverändert", () => {
    strictEqual(resolveStayRadius(40), 40);
    strictEqual(resolveStayMinutes(10), 10);
  });

  it("hält sie in den Grenzen", () => {
    strictEqual(resolveStayRadius(5), MIN_STAY_RADIUS);
    strictEqual(resolveStayRadius(9000), MAX_STAY_RADIUS);
    strictEqual(resolveStayMinutes(0), MIN_STAY_MINUTES);
    strictEqual(resolveStayMinutes(10000), MAX_STAY_MINUTES);
  });

  it("nimmt bei leerem Feld die Vorgabe", () => {
    // Nichts eingetragen heißt "wie bisher", nicht "so klein wie möglich" --
    // Number("") und Number(null) sind beide 0 und lägen sonst am Minimum.
    for (const leer of [undefined, null, ""]) {
      strictEqual(resolveStayRadius(leer), DEFAULTS.stay_radius);
      strictEqual(resolveStayMinutes(leer), DEFAULTS.stay_min_duration);
    }
  });

  it("fällt bei Unsinn auf die Vorgabe zurück", () => {
    for (const unsinn of ["viel", NaN, {}]) {
      strictEqual(resolveStayRadius(unsinn), DEFAULTS.stay_radius);
      strictEqual(resolveStayMinutes(unsinn), DEFAULTS.stay_min_duration);
    }
  });

  it("rundet, weil Meter und Minuten keine Nachkommastellen brauchen", () => {
    strictEqual(resolveStayRadius("47.6"), 48);
    strictEqual(resolveStayMinutes("5.4"), 5);
  });
});

describe("Farbwerte", () => {
  it("nimmt die gängigen Schreibweisen", () => {
    strictEqual(normalizeHex("#7C4DFF"), "#7c4dff");
    strictEqual(normalizeHex("7c4dff"), "#7c4dff");
    strictEqual(normalizeHex("  #7c4dff "), "#7c4dff");
  });

  it("versteht die Kurzform", () => {
    strictEqual(normalizeHex("#f0a"), "#ff00aa");
    strictEqual(normalizeHex("abc"), "#aabbcc");
  });

  it("rät bei halb Getipptem nicht", () => {
    // Sonst färbt sich die Karte bei jedem Tastendruck um.
    for (const halb of ["#7c4d", "#", "", "rot", "#gggggg", undefined, null, 42]) {
      strictEqual(normalizeHex(halb), undefined);
    }
  });

  it("bietet die Personenfarben zuerst an", () => {
    deepStrictEqual([...COLOR_CHOICES].slice(0, PERSON_PALETTE.length), [...PERSON_PALETTE]);
    strictEqual(new Set(COLOR_CHOICES).size, COLOR_CHOICES.length);
    ok(COLOR_CHOICES.every((c) => normalizeHex(c) === c));
  });
});
