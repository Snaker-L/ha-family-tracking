/**
 * Reverse geocoding via Nominatim (OpenStreetMap).
 *
 * Their usage policy allows this only under strict conditions: at most one
 * request per second, results must be cached, and the client has to identify
 * itself. A browser cannot set `User-Agent` (the header is forbidden by fetch),
 * so identification falls back to the Referer the browser sends automatically,
 * optionally strengthened by the `email` parameter Nominatim documents for
 * exactly this case.
 */

const ENDPOINT = "https://nominatim.openstreetmap.org/reverse";
const MIN_REQUEST_GAP_MS = 1100;
/*
 * The `:2` is a version, and bumping it throws the stored labels away.
 *
 * Needed the moment the integration learned to name a shopping centre instead
 * of the street around it: this cache is consulted before anything is asked,
 * so a stay resolved last week would go on reading "Grinzinger Straße 112"
 * for a month no matter what the integration now answers.
 *
 * Raised to 3 for a second helping of the same problem. The integration takes
 * care not to store an address it only fell back to while the lookup service
 * was busy -- and this cache stored it anyway, which is how a stay at the
 * Bauhaus went on reading "Jägerstraße 82" after the fix was already in.
 */
const CACHE_KEY = "family-tracking-card:geocode:3";
const CACHE_TTL_MS = 30 * 24 * 60 * 60 * 1000;
/** ~11 m at the equator: fine enough for a stay, coarse enough to reuse. */
const CACHE_PRECISION = 4;

export interface GeocodeOptions {
  /** Contact address forwarded to Nominatim, see their usage policy. */
  email?: string;
  language?: string;
  /**
   * Whether to ask what the coordinate lies inside. With it, a stay in a
   * shopping centre reads as the centre rather than as the street beside it or
   * whichever shop happens to be nearest. Off, nothing is asked of the second
   * service at all.
   */
  places?: boolean;
  /**
   * Whether to keep the address as well, in brackets after the name. Part of
   * the cache key for the same reason `places` is: the same coordinate has
   * more than one right answer, and a stored one from the other setting would
   * make the switch look broken.
   */
  placeAddress?: boolean;
  /**
   * Home Assistant's websocket call. When the Family Tracking integration is
   * installed it answers `family_tracking/geocode`, and then the lookup belongs
   * there: one cache for every browser in the house instead of one per device,
   * one queue honouring the rate limit, and results that survive a cleared
   * browser storage. Without the integration the card asks Nominatim itself,
   * exactly as before.
   */
  callWS?: <T>(message: Record<string, unknown>) => Promise<T>;
}

/** The instance-wide settings of the integration that the card follows. */
export interface ServerSettings {
  /** `false` when lookups are switched off for the whole instance. */
  geocode?: boolean;
  /** Fixes reporting a worse accuracy than this, in metres, are left out. */
  maxAccuracy?: number;
}

/**
 * Asks the integration for its settings.
 *
 * Every field is `undefined` when there is no integration to ask or it could
 * not answer: the card then decides on its own, as it always did.
 */
export async function fetchServerSettings(
  callWS: GeocodeOptions["callWS"]
): Promise<ServerSettings> {
  if (!callWS) return {};
  try {
    const result = await callWS<{ geocode?: unknown; max_accuracy?: unknown } | null>({
      type: "family_tracking/settings",
    });
    const maxAccuracy = Number(result?.max_accuracy);
    return {
      geocode: typeof result?.geocode === "boolean" ? result.geocode : undefined,
      maxAccuracy: Number.isFinite(maxAccuracy) && maxAccuracy > 0 ? maxAccuracy : undefined,
    };
  } catch {
    return {};
  }
}

/**
 * Whether the integration lets this instance resolve addresses at all.
 *
 * Only an explicit `false` means the editor's lookup switches have no effect.
 */
export async function serverGeocodeEnabled(
  callWS: GeocodeOptions["callWS"]
): Promise<boolean | undefined> {
  return (await fetchServerSettings(callWS)).geocode;
}

/** Remembers a missing integration, so the card asks once and not per stay. */
let serverGeocoding: boolean | undefined;

/**
 * Remembers that the instance switched lookups off.
 *
 * Kept apart from `serverGeocoding`, because the two lead opposite ways: a
 * missing integration means fall back to Nominatim, a switched-off one means
 * do not.
 */
let serverDisabled = false;

/** Test helper: forget whether the integration answered. */
export function resetServerGeocoding(): void {
  serverGeocoding = undefined;
  serverDisabled = false;
}

/** What the integration answered: the label, and whether it is the final one. */
interface ServerAnswer {
  label?: string;
  settled: boolean;
  /** The instance resolves no addresses at all; do not go around it. */
  disabled?: boolean;
}

async function viaServer(
  lat: number,
  lon: number,
  options: GeocodeOptions
): Promise<ServerAnswer | null> {
  if (!options.callWS || serverGeocoding === false) return null;
  if (serverDisabled) return { settled: true, disabled: true };
  try {
    const result = await options.callWS<{
      label?: string;
      settled?: boolean;
      disabled?: boolean;
    } | null>({
      type: "family_tracking/geocode",
      latitude: lat,
      longitude: lon,
      language: options.language,
      places: options.places !== false,
      address: options.placeAddress === true,
    });
    serverGeocoding = true;
    if (result?.disabled) {
      serverDisabled = true;
      return { settled: true, disabled: true };
    }
    // `settled: false` means the integration wanted to name the place and
    // could not ask -- the label is an address standing in for a name that is
    // not available this minute.
    return { label: result?.label || undefined, settled: result?.settled !== false };
  } catch (err) {
    // Not the same thing twice. `unknown_command` means the integration is not
    // installed, and then asking again for every stay only costs a round trip
    // each time. Anything else -- most often "not_ready" while Home Assistant
    // is still starting up -- is over in a minute, and giving up on it for the
    // rest of the page would hand back the worse answer all evening.
    if ((err as { code?: string } | undefined)?.code === "unknown_command") {
      serverGeocoding = false;
    }
    return null;
  }
}

interface CacheEntry {
  label: string;
  at: number;
  /**
   * Set when the label came from asking Nominatim directly rather than from
   * the integration. Those answers know nothing about shopping centres, so
   * they are kept for this page and no longer: written to storage, a lookup
   * made while Home Assistant was still starting would outlive the reason it
   * was ever needed.
   */
  direct?: boolean;
}

export const cacheKeyFor = (lat: number, lon: number): string =>
  `${lat.toFixed(CACHE_PRECISION)},${lon.toFixed(CACHE_PRECISION)}`;

/**
 * The cache key for one lookup.
 *
 * The setting is part of it. The same coordinate has two right answers -- the
 * place and the address -- and without this, turning the option off would go
 * on showing the place it had already stored, which reads like the switch does
 * nothing.
 */
const entryKeyFor = (lat: number, lon: number, places: boolean, withAddress: boolean): string => {
  const base = cacheKeyFor(lat, lon);
  if (!places) return `${base}|addr`;
  return withAddress ? `${base}|both` : base;
};

/**
 * Where the house number goes before the street name rather than after it.
 *
 * "350 5th Avenue" in New York, "Pariser Platz 1" in Berlin -- and Nominatim
 * hands both over as separate fields, so the order is ours to get right.
 * Countries not listed take the number after the street, which covers most of
 * Europe and South America. Kept in step with `HOUSE_NUMBER_FIRST` in
 * `custom_components/family_tracking/address.py`.
 */
const HOUSE_NUMBER_FIRST = new Set([
  "us", "ca", "gb", "ie", "au", "nz", "fr", "in", "sg", "my", "hk", "ph", "th", "za",
]);

/** Street and house number in the order that country writes them. */
export function streetHead(street: string, houseNumber?: string, countryCode?: string): string {
  if (!street) return "";
  if (!houseNumber) return street;
  return HOUSE_NUMBER_FIRST.has((countryCode ?? "").toLowerCase())
    ? `${houseNumber} ${street}`
    : `${street} ${houseNumber}`;
}

/**
 * Condenses a Nominatim address object into one readable line.
 * Pure function, kept separate so it can be tested without network access.
 */
export function shortLabel(result: any): string | undefined {
  const address = result?.address ?? {};
  const street = address.road ?? address.pedestrian ?? address.footway ?? address.path;
  const place =
    address.village ?? address.town ?? address.city ?? address.municipality ?? address.county;

  if (street) {
    const head = streetHead(street, address.house_number, address.country_code);
    return place ? `${head}, ${place}` : head;
  }
  const named = result?.name || address.amenity || address.shop || address.building;
  if (named) return place ? `${named}, ${place}` : named;
  if (place) return place;
  return typeof result?.display_name === "string"
    ? result.display_name.split(",").slice(0, 2).join(",").trim()
    : undefined;
}

let memoryCache: Map<string, CacheEntry> | undefined;

function cache(): Map<string, CacheEntry> {
  if (memoryCache) return memoryCache;
  memoryCache = new Map();
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (raw) {
      const now = Date.now();
      for (const [key, entry] of Object.entries(JSON.parse(raw) as Record<string, CacheEntry>)) {
        if (entry && now - entry.at < CACHE_TTL_MS) memoryCache.set(key, entry);
      }
    }
  } catch {
    // A corrupt or unavailable localStorage must not break the card.
  }
  return memoryCache;
}

let persistHandle: number | undefined;

function persist(): void {
  if (persistHandle !== undefined) return;
  persistHandle = window.setTimeout(() => {
    persistHandle = undefined;
    try {
      const lasting = [...cache()].filter(([, entry]) => !entry.direct);
      window.localStorage.setItem(CACHE_KEY, JSON.stringify(Object.fromEntries(lasting)));
    } catch {
      // Quota exceeded or private mode: the in-memory cache still works.
    }
  }, 1000);
}

/** Serialises all lookups and keeps at least MIN_REQUEST_GAP_MS between them. */
let queue: Promise<unknown> = Promise.resolve();
let lastRequestAt = 0;

function schedule<T>(task: () => Promise<T>): Promise<T> {
  const run = queue.then(async () => {
    const wait = lastRequestAt + MIN_REQUEST_GAP_MS - Date.now();
    if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
    lastRequestAt = Date.now();
    return task();
  });
  queue = run.catch(() => undefined);
  return run;
}

/**
 * Resolves coordinates to a readable address. Returns `undefined` when the
 * lookup fails; the caller is expected to fall back to the raw coordinates.
 */
export async function reverseGeocode(
  lat: number,
  lon: number,
  options: GeocodeOptions = {}
): Promise<string | undefined> {
  const key = entryKeyFor(lat, lon, options.places !== false, options.placeAddress === true);
  const hit = cache().get(key);
  if (hit) return hit.label;

  const server = await viaServer(lat, lon, options);
  // Switched off instance-wide. Returning here rather than falling through is
  // the point of the setting: the queue below would otherwise ask Nominatim
  // from the browser and undo the decision.
  if (server?.disabled) return undefined;
  if (server !== null) {
    // The server has its own cache; keeping a copy here saves the round trip
    // for the stays already on screen. An unsettled answer is kept only for
    // this page: the integration deliberately did not store it, and writing it
    // to browser storage for a month would undo that -- a shopping centre
    // would go on reading as the street outside it long after the lookup
    // service was willing again.
    if (server.label) {
      cache().set(key, {
        label: server.label,
        at: Date.now(),
        direct: !server.settled,
      });
    }
    persist();
    return server.label;
  }

  return schedule(async () => {
    // A second lookup may have filled the cache while this one was queued.
    const queued = cache().get(key);
    if (queued) return queued.label;

    const params = new URLSearchParams({
      format: "jsonv2",
      lat: String(lat),
      lon: String(lon),
      zoom: "18",
      addressdetails: "1",
    });
    if (options.language) params.set("accept-language", options.language);
    if (options.email) params.set("email", options.email);

    try {
      const response = await fetch(`${ENDPOINT}?${params.toString()}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return undefined;
      const label = shortLabel(await response.json());
      if (!label) return undefined;
      cache().set(key, { label, at: Date.now(), direct: true });
      persist();
      return label;
    } catch {
      return undefined;
    }
  });
}

/** Test/debug helper: forgets every cached address. */
export function clearGeocodeCache(): void {
  memoryCache = undefined;
  // A write may already be queued, and it would put the cleared content
  // straight back. Dropping the handle also lets the next lookup queue one of
  // its own -- without this, the first write of a session was the last.
  if (persistHandle !== undefined) {
    try {
      window.clearTimeout(persistHandle);
    } catch {
      // A browser that cannot cancel it will still write nothing worth keeping.
    }
    persistHandle = undefined;
  }
  try {
    window.localStorage.removeItem(CACHE_KEY);
  } catch {
    // ignored
  }
}
