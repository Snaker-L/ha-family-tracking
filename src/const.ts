export const CARD_VERSION = "0.9.0";

export const CARD_TAG = "family-tracking-card";
export const EDITOR_TAG = "family-tracking-card-editor";

/**
 * Tile styles. Everything here comes from ArcGIS Online and needs no API key.
 *
 * Two sources were tried and dropped, which is worth recording so they do not
 * come back. CARTO serves a real map but stamps "API KEY REQUIRED" across it --
 * light_all and dark_all included. That one is a warning about testing: the
 * watermarked tiles still differ from each other, so comparing bytes says
 * "fine". Only looking at the image finds it. `dev/probe-tiles.mjs` therefore
 * catches blank and blocked tiles, not watermarks; a new source needs one look
 * with human eyes.
 *
 * Home Assistant's own map card uses CARTO, so it currently shows that watermark
 * too -- copying "whatever Home Assistant uses" would inherit the problem. The
 * default is therefore Esri, which follows the theme and works worldwide.
 *
 * OpenStreetMap needed a second look: it is not the deprecated `{s}` subdomains
 * that get blocked, it is the missing referrer. See `TileSpec.referrerPolicy`.
 *
 * A style is a list of layers drawn in order: a base map, optionally overlays
 * with labels. `maxNativeZoom` is per layer because they run out at different
 * levels; Leaflet then upscales instead of showing nothing.
 */
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";
const BASEMAP_AT = "https://mapsneu.wien.gv.at/basemap";

const ESRI_ATTRIBUTION =
  "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors";
const ESRI_IMAGERY_ATTRIBUTION =
  "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics";
/** basemap.at is CC BY 4.0 and asks to be named. */
const BASEMAP_AT_ATTRIBUTION =
  'Data: <a href="https://www.basemap.at">basemap.at</a>';

export interface TileSpec {
  url: string;
  maxNativeZoom: number;
  /** Required for `{s}` URLs; Leaflet has no sensible default for them. */
  subdomains?: string;
  /**
   * Set on the tile `<img>`, overriding the page policy. Home Assistant sends
   * `Referrer-Policy: no-referrer`, and OpenStreetMap answers requests without
   * a referrer with its "Access blocked" image -- which is why OSM tiles look
   * broken inside Home Assistant while the same URL works elsewhere. Only set
   * this where the provider needs it: it reveals the instance host to them.
   */
  referrerPolicy?: ReferrerPolicy;
}

export interface TileStyle {
  label: string;
  attribution: string;
  /** Base map first, overlays after it. */
  layers: TileSpec[];
  /** Used when Home Assistant is in dark mode; falls back to `layers`. */
  darkLayers?: TileSpec[];
}

export const MAX_ZOOM = 20;

export const STREET_STYLES = {
  osm: {
    label: "OpenStreetMap",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    layers: [
      {
        url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        maxNativeZoom: 19,
        // Without this the tiles come back as "Access blocked"; see TileSpec.
        referrerPolicy: "origin",
      },
    ],
  },
  esri_gray: {
    label: "Esri Gray (follows your theme)",
    attribution: ESRI_ATTRIBUTION,
    layers: [
      { url: `${ESRI}/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`, maxNativeZoom: 16 },
      {
        url: `${ESRI}/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`,
        maxNativeZoom: 16,
      },
    ],
    darkLayers: [
      { url: `${ESRI}/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`, maxNativeZoom: 16 },
      {
        url: `${ESRI}/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`,
        maxNativeZoom: 16,
      },
    ],
  },
  esri_streets: {
    label: "Esri Streets",
    attribution: ESRI_ATTRIBUTION,
    layers: [{ url: `${ESRI}/World_Street_Map/MapServer/tile/{z}/{y}/{x}`, maxNativeZoom: 19 }],
  },
  esri_topo: {
    label: "Esri Topographic",
    attribution: ESRI_ATTRIBUTION,
    layers: [{ url: `${ESRI}/World_Topo_Map/MapServer/tile/{z}/{y}/{x}`, maxNativeZoom: 19 }],
  },
  esri_relief: {
    label: "Esri Hillshade (terrain)",
    attribution: ESRI_ATTRIBUTION,
    layers: [
      { url: `${ESRI}/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}`, maxNativeZoom: 16 },
      {
        url: `${ESRI}/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`,
        maxNativeZoom: 16,
      },
    ],
  },
  osm_hot: {
    label: "OpenStreetMap Humanitarian",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, ' +
      'Kacheln: <a href="https://www.hotosm.org/">HOT</a> &amp; ' +
      '<a href="https://openstreetmap.fr/">OSM France</a>',
    layers: [
      {
        url: "https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
        subdomains: "abc",
        maxNativeZoom: 19,
      },
    ],
  },
  opentopo: {
    label: "OpenTopoMap",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, ' +
      'SRTM, Kacheln: <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)',
    layers: [
      {
        url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        subdomains: "abc",
        maxNativeZoom: 17,
      },
    ],
  },
  basemap_at: {
    label: "basemap.at (Austria only)",
    attribution: BASEMAP_AT_ATTRIBUTION,
    layers: [
      { url: `${BASEMAP_AT}/geolandbasemap/normal/google3857/{z}/{y}/{x}.png`, maxNativeZoom: 20 },
    ],
  },
  basemap_at_gray: {
    label: "basemap.at Gray (Austria only)",
    attribution: BASEMAP_AT_ATTRIBUTION,
    layers: [
      { url: `${BASEMAP_AT}/bmapgrau/normal/google3857/{z}/{y}/{x}.png`, maxNativeZoom: 20 },
    ],
  },
} as const satisfies Record<string, TileStyle>;

export const SATELLITE_STYLES = {
  esri_imagery: {
    label: "Esri Imagery",
    attribution: ESRI_IMAGERY_ATTRIBUTION,
    layers: [{ url: `${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`, maxNativeZoom: 19 }],
  },
  esri_hybrid: {
    label: "Esri Imagery with labels",
    attribution: ESRI_IMAGERY_ATTRIBUTION,
    layers: [
      { url: `${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`, maxNativeZoom: 19 },
      {
        url: `${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`,
        maxNativeZoom: 16,
      },
      {
        url: `${ESRI}/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}`,
        maxNativeZoom: 19,
      },
    ],
  },
  basemap_at_ortho: {
    label: "basemap.at Orthophoto 30 cm (Austria only)",
    attribution: BASEMAP_AT_ATTRIBUTION,
    layers: [
      {
        url: `${BASEMAP_AT}/bmaporthofoto30cm/normal/google3857/{z}/{y}/{x}.jpeg`,
        maxNativeZoom: 20,
      },
    ],
  },
  basemap_at_ortho_labels: {
    label: "basemap.at Orthophoto with labels (Austria only)",
    attribution: BASEMAP_AT_ATTRIBUTION,
    layers: [
      {
        url: `${BASEMAP_AT}/bmaporthofoto30cm/normal/google3857/{z}/{y}/{x}.jpeg`,
        maxNativeZoom: 20,
      },
      { url: `${BASEMAP_AT}/bmapoverlay/normal/google3857/{z}/{y}/{x}.png`, maxNativeZoom: 20 },
    ],
  },
} as const satisfies Record<string, TileStyle>;

export type StreetStyleId = keyof typeof STREET_STYLES;
export type SatelliteStyleId = keyof typeof SATELLITE_STYLES;

export const DEFAULT_STREET_STYLE: StreetStyleId = "esri_gray";
export const DEFAULT_SATELLITE_STYLE: SatelliteStyleId = "esri_imagery";

export type MapLayerId = "street" | "satellite";

/**
 * Fallback colours for persons that have none configured. Picking by a hash of
 * the entity id rather than by list position keeps a person's colour stable when
 * somebody else is added or removed.
 */
export const PERSON_PALETTE = [
  "#7c4dff",
  "#00b894",
  "#2d7ff9",
  "#ff7043",
  "#e91e63",
  "#00acc1",
  "#8d6e63",
  "#fbc02d",
] as const;

/**
 * What the colour picker offers.
 *
 * The eight person colours first, because those are the ones already in use on
 * the map, then eight that sit well beside them. A palette rather than a free
 * wheel: on a map that has to stay readable, most of the colour space is a bad
 * answer, and the hex field is there for the rest.
 */
export const COLOR_CHOICES = [
  ...PERSON_PALETTE,
  "#ef5350",
  "#ab47bc",
  "#5c6bc0",
  "#26a69a",
  "#9ccc65",
  "#ffa726",
  "#78909c",
  "#455a64",
] as const;

/**
 * A hex colour the card can use, or nothing.
 *
 * Accepts what people actually type: with or without the hash, upper or lower
 * case, and the three-digit short form that CSS allows. Anything else is not
 * guessed at -- a half-typed colour must not repaint the map on every
 * keystroke.
 */
export function normalizeHex(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const raw = value.trim().replace(/^#/, "").toLowerCase();
  if (/^[0-9a-f]{3}$/.test(raw)) {
    return `#${raw[0]}${raw[0]}${raw[1]}${raw[1]}${raw[2]}${raw[2]}`;
  }
  return /^[0-9a-f]{6}$/.test(raw) ? `#${raw}` : undefined;
}

export function fallbackPersonColor(entityId: string): string {
  let hash = 0;
  for (let i = 0; i < entityId.length; i += 1) {
    hash = (hash * 31 + entityId.charCodeAt(i)) >>> 0;
  }
  return PERSON_PALETTE[hash % PERSON_PALETTE.length];
}

/**
 * Zones.
 *
 * Home Assistant already gives every zone an icon, so the card follows that by
 * default and only stores what the user actually overrode. A single neutral
 * colour is the default rather than one per zone: the person palette carries
 * the meaning on this map, and zones tinted in eight colours would compete with
 * it. Anyone who wants a green shop and a blue school can set them.
 */
export const DEFAULT_ZONE_COLOR = "#727272";
export const DEFAULT_ZONE_ICON = "mdi:map-marker-radius";

export interface ZoneStyleConfig {
  zone_icons?: Record<string, string>;
  zone_colors?: Record<string, string>;
}

export interface ZoneVisual {
  icon: string;
  color: string;
}

/** Icon and colour for one zone: the override first, then Home Assistant's. */
export function zoneVisual(
  entityId: string,
  attributes: Record<string, any>,
  config: ZoneStyleConfig
): ZoneVisual {
  return {
    icon: config.zone_icons?.[entityId] || attributes.icon || DEFAULT_ZONE_ICON,
    color: config.zone_colors?.[entityId] || DEFAULT_ZONE_COLOR,
  };
}

export interface ZoneGeometry {
  lat: number;
  lon: number;
  radius: number;
}

/**
 * The circle to draw, or `undefined` when the zone has none.
 *
 * Not every `zone.*` entity can be drawn: Home Assistant also exposes zones
 * without coordinates, and a radius of zero would be an invisible circle with a
 * marker floating at its centre. Those are skipped rather than drawn wrong.
 */
export function zoneGeometry(attributes: Record<string, any>): ZoneGeometry | undefined {
  const lat = Number(attributes.latitude);
  const lon = Number(attributes.longitude);
  const radius = Number(attributes.radius);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return undefined;
  if (!Number.isFinite(radius) || radius <= 0) return undefined;
  return { lat, lon, radius };
}

/**
 * Map height.
 *
 * `fill` lets the card take whatever height it is given instead of a fixed
 * number of pixels, which is what a panel view is for -- there the dashboard
 * hands the card the whole screen and a fixed 480 px leaves most of it empty.
 * It needs a container with a height to fill, so in a masonry view, where the
 * card is only as tall as its contents, a number is the right answer.
 */
export const FILL_HEIGHT = "fill";

/** Below this the map is unusable, above it no screen follows anyway. */
export const MIN_MAP_HEIGHT = 160;
export const MAX_MAP_HEIGHT = 2000;

/**
 * What still counts as standing still, and for how long.
 *
 * Below 10 m every GPS wobble becomes its own stay; above 500 m a stay would
 * swallow a whole neighbourhood. One minute is the shortest wait worth a line
 * in the list, and beyond twelve hours a day has no stays left to show.
 *
 * The lower bound sits below the default on purpose: a setting that cannot be
 * turned down from where it starts is not a setting.
 */
export const MIN_STAY_RADIUS = 10;
export const MAX_STAY_RADIUS = 500;
export const MIN_STAY_MINUTES = 1;
export const MAX_STAY_MINUTES = 720;

/**
 * The stay setting a config asks for, kept sane.
 *
 * Three cases, and they are not the same. Nothing at all -- an empty field, a
 * key the config never had -- means the default. A number outside the range is
 * pulled to the nearest end rather than thrown away, because somebody typing
 * 5 into a metre field meant "small", not "give me 120". And anything that is
 * not a number falls back to the default.
 *
 * `Number("")` and `Number(null)` are both 0, which is why the first case has
 * to be settled before the arithmetic starts.
 */
function resolveNumber(value: unknown, fallback: number, min: number, max: number): number {
  if (value === undefined || value === null || value === "") return fallback;
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, Math.round(n)));
}

export const resolveStayRadius = (value: unknown): number =>
  resolveNumber(value, DEFAULTS.stay_radius, MIN_STAY_RADIUS, MAX_STAY_RADIUS);

export const resolveStayMinutes = (value: unknown): number =>
  resolveNumber(value, DEFAULTS.stay_min_duration, MIN_STAY_MINUTES, MAX_STAY_MINUTES);

/**
 * The window the card opens on: the current day from midnight, not the last 24
 * hours. Asked "where was everyone today", a rolling window answers with half of
 * yesterday, and the stay list then starts mid-evening for no reason anybody can
 * see. Midnight is the boundary people actually mean.
 */
export const TODAY = "today";

/** A rolling window in hours, or the calendar day so far. */
export type TimeRange = number | typeof TODAY;

/**
 * Fixed behaviour of the card. Only `time_ranges`, `show_stays`, `show_zones`
 * and `geocode` are still configurable; the rest was removed from the config on
 * purpose, to keep the editor down to the handful of things that actually get
 * changed.
 */
export const DEFAULTS = {
  range: TODAY as TimeRange,
  zoom: 13,
  // Hours rather than days: how a day went is the question actually asked here.
  // Anything longer is what the calendar is for, and the recorder keeps only ten
  // days by default anyway.
  time_ranges: [1, 4, 6, 8, 12, 16, 18, 20, 22, 24],
  map_layer: "street" as MapLayerId,
  map_height: 480 as number | typeof FILL_HEIGHT,
  // Tight on purpose. A wide radius turns a walk through a shopping street
  // into one circle and the track loses the shape of the day; three minutes
  // is long enough that waiting at a light does not earn a line of its own.
  stay_radius: 20,
  stay_min_duration: 3,
  show_stays: true,
  // Off by default: an existing card must not suddenly grow circles on its map.
  show_zones: false,
  geocode: true,
  // On by default: a name beats an address wherever there is one, and the
  // lookup is cached for the whole household.
  places: true,
  // Off by default: the name is the answer to "where is she". The address is
  // the answer to "how do I get there", which is a different question and not
  // the one the stay list is usually asked.
  place_address: false,
};

/** A tile source entered by hand, in the spirit of map-card's tile_layer_url. */
export interface CustomTileLayer {
  url: string;
  /** Needed when the URL contains `{s}`, for example `abc`. */
  subdomains?: string;
  attribution?: string;
  max_zoom?: number;
  /** See `TileSpec.referrerPolicy`; `origin` is what OpenStreetMap needs. */
  referrer_policy?: string;
}

export const CUSTOM_STYLE = "custom";

/** The values the browser accepts; anything else would be silently ignored. */
const REFERRER_POLICIES: ReferrerPolicy[] = [
  "",
  "no-referrer",
  "no-referrer-when-downgrade",
  "origin",
  "origin-when-cross-origin",
  "same-origin",
  "strict-origin",
  "strict-origin-when-cross-origin",
  "unsafe-url",
];

/** Config comes from YAML, so a typo must not end up on the image element. */
export function toReferrerPolicy(value: string | undefined): ReferrerPolicy | undefined {
  return value && (REFERRER_POLICIES as string[]).includes(value)
    ? (value as ReferrerPolicy)
    : undefined;
}

export interface ResolvedStyle {
  /** Identifies the exact layer set; two different choices must never match. */
  key: string;
  /** The style id, e.g. `esri_gray`. Used to look up its translated name. */
  id: string;
  label: string;
  attribution: string;
  layers: readonly TileSpec[];
}

/**
 * Turns "which layer, which theme, which styles" into the concrete tile set.
 *
 * Pure on purpose: the map swaps layers only when the key changes, so a bug
 * here shows up as "the picker does nothing". That is worth a test, and a test
 * needs this out of the Leaflet code.
 */
export interface StyleChoice {
  street: StreetStyleId | typeof CUSTOM_STYLE;
  satellite: SatelliteStyleId | typeof CUSTOM_STYLE;
  customStreet?: CustomTileLayer;
  customSatellite?: CustomTileLayer;
}

export function resolveStyle(layer: MapLayerId, dark: boolean, styles: StyleChoice): ResolvedStyle {
  const id = layer === "street" ? styles.street : styles.satellite;

  if (id === CUSTOM_STYLE) {
    const custom = layer === "street" ? styles.customStreet : styles.customSatellite;
    // An empty URL would leave a blank map with no way back, so fall through to
    // the built-in default until something is actually entered.
    if (custom?.url) {
      return {
        key: `${layer}:custom:${custom.url}`,
        id: CUSTOM_STYLE,
        label: "Custom URL",
        attribution: custom.attribution ?? "",
        layers: [
          {
            url: custom.url,
            maxNativeZoom: custom.max_zoom ?? 19,
            ...(custom.subdomains ? { subdomains: custom.subdomains } : {}),
            ...(toReferrerPolicy(custom.referrer_policy)
              ? { referrerPolicy: toReferrerPolicy(custom.referrer_policy) }
              : {}),
          },
        ],
      };
    }
  }

  const streetId = id === CUSTOM_STYLE ? DEFAULT_STREET_STYLE : (id as StreetStyleId);
  const satelliteId = id === CUSTOM_STYLE ? DEFAULT_SATELLITE_STYLE : (id as SatelliteStyleId);
  const style: TileStyle = layer === "street" ? STREET_STYLES[streetId] : SATELLITE_STYLES[satelliteId];
  const useDark = dark && style.darkLayers !== undefined;
  const resolvedId = layer === "street" ? streetId : satelliteId;
  return {
    key: `${layer}:${resolvedId}:${useDark ? "dark" : "light"}`,
    id: resolvedId,
    label: style.label,
    attribution: style.attribution,
    layers: useDark ? style.darkLayers! : style.layers,
  };
}

/** The part of the card config that decides which tiles are drawn. */
export interface StyleConfig {
  street_style?: string;
  satellite_style?: string;
  custom_street?: CustomTileLayer;
  custom_satellite?: CustomTileLayer;
}

/** Falls back when a config names a style that no longer exists. */
export function sanitizeStyles(config: StyleConfig): StyleChoice {
  const street = config.street_style;
  const satellite = config.satellite_style;
  return {
    street:
      street === CUSTOM_STYLE
        ? CUSTOM_STYLE
        : street && street in STREET_STYLES
          ? (street as StreetStyleId)
          : DEFAULT_STREET_STYLE,
    satellite:
      satellite === CUSTOM_STYLE
        ? CUSTOM_STYLE
        : satellite && satellite in SATELLITE_STYLES
          ? (satellite as SatelliteStyleId)
          : DEFAULT_SATELLITE_STYLE,
    customStreet: config.custom_street,
    customSatellite: config.custom_satellite,
  };
}

/**
 * Which of the two tile pickers was just touched, if either. The editor preview
 * uses it to show the style that was chosen: selecting a satellite map and then
 * still having to press "Satellit" over the preview to see it is a step nobody
 * expects. The custom URLs count as part of their side.
 */
export function editedLayer(previous: StyleConfig, next: StyleConfig): MapLayerId | undefined {
  const before = sanitizeStyles(previous);
  const after = sanitizeStyles(next);

  if (
    before.satellite !== after.satellite ||
    JSON.stringify(before.customSatellite) !== JSON.stringify(after.customSatellite)
  ) {
    return "satellite";
  }
  if (
    before.street !== after.street ||
    JSON.stringify(before.customStreet) !== JSON.stringify(after.customStreet)
  ) {
    return "street";
  }
  return undefined;
}

/**
 * The `ha-form` schema of the editor. Pure data, and here rather than next to
 * the editor so a test can reach it without a DOM.
 *
 * The empty grid name is the load-bearing part. `ha-form` reads a named group
 * from `data[name]` and writes it straight back there, so `name: "toggles"`
 * quietly stored the switches as `toggles: { show_zones: true }` -- a key the
 * card never looks at. The switch then showed its own nested value and looked
 * perfectly on while nothing happened, and the stray `toggles` and `layers`
 * objects in existing configurations are the fossils of exactly that. A grid
 * with an empty name hands the whole object down and keeps the keys flat.
 */
/**
 * What is left for `ha-form`: the title, and nothing else.
 *
 * The switches used to live here too, in a grid. Two of them then needed an
 * info icon, which a form label -- a plain string -- cannot carry, and the two
 * that moved out ended up with a different spacing from the two that stayed.
 * Drawing all four by hand is what makes the rhythm even.
 */
export const EDITOR_SCHEMA = [{ name: "title", selector: { text: {} } }] as const;

/**
 * Keys no configuration should still carry.
 *
 * `toggles` and `layers` were written by a bug and mirror real option names, so
 * leaving them in place means a configuration that permanently reads as if it
 * said something it does not. `geocode_email` was real once: it identified the
 * card to Nominatim back when the card asked Nominatim itself. The integration
 * does the asking now and carries its own contact address, so the field only
 * offered somewhere to type an address that nothing would read.
 */
export const OBSOLETE_KEYS = ["toggles", "layers", "geocode_email"] as const;

/**
 * The map height a config asks for, or the default when it asks for nonsense.
 * Config comes from YAML, so "480px", an empty string and a negative number all
 * have to land somewhere sensible rather than on the element.
 */
export function resolveMapHeight(value: unknown): number | typeof FILL_HEIGHT {
  if (value === FILL_HEIGHT) return FILL_HEIGHT;
  const height = Number(value);
  if (!Number.isFinite(height)) return DEFAULTS.map_height;
  if (height < MIN_MAP_HEIGHT || height > MAX_MAP_HEIGHT) return DEFAULTS.map_height;
  return height;
}
