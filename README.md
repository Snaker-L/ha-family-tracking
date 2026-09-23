# Family Tracking

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?logo=home-assistant&logoColor=white)](https://hacs.xyz/docs/faq/custom_repositories)
[![Version](https://img.shields.io/github/v/release/Snaker-L/ha-family-tracking?label=version&color=orange)](https://github.com/Snaker-L/ha-family-tracking/releases)
[![Last commit](https://img.shields.io/github/last-commit/Snaker-L/ha-family-tracking?label=last%20commit&color=teal)](https://github.com/Snaker-L/ha-family-tracking/commits/main)
[![License](https://img.shields.io/github/license/Snaker-L/ha-family-tracking?label=license&color=green)](LICENSE)

A Home Assistant integration that works out where each person actually is — and
a map card, shipped with it, that shows the day as a readable list of stays
instead of raw coordinates.

<p>
  <img src="https://raw.githubusercontent.com/Snaker-L/ha-family-tracking/main/docs/screenshot-card.png?v=0.9.0" alt="The card: person chips, the range menu, a map with a track, and the stay list below" width="355">
  <img src="https://raw.githubusercontent.com/Snaker-L/ha-family-tracking/main/docs/screenshot-satellite.jpg?v=0.9.0" alt="The same card on satellite tiles, with the view unchanged" width="355">
</p>
<p>
  <img src="https://raw.githubusercontent.com/Snaker-L/ha-family-tracking/main/docs/screenshot-editor.png?v=0.9.0" alt="The card editor: the two lookup switches, map height, tile styles, a colour per person and an icon per zone" width="355">
</p>

**One install, nothing to register.** The integration serves the card and keeps
its Lovelace resource up to date by itself, including after an upgrade.

## What it does

**Picks the tracker worth believing.** A person usually carries several — the
companion app, iCloud, a router that sees the phone on WLAN, a beacon — and they
disagree constantly. Averaging them puts the person where nobody is; taking the
newest makes them teleport. Each report is judged instead: a fix reported as
accurate to 0 m is refused (several trackers mean "no fix" by that), so is one
worse than your threshold, and so is one older than what we already have. A
tracker that sees a zone boundary crossed wins regardless of its accuracy;
otherwise the one being followed keeps the lead until another is measurably
better. The reason is on the sensor, so a tracker that never wins can be found.

**Says where that is.** Outside a zone the position is reverse geocoded through
Nominatim — once for the whole household, cached on disk across restarts, and
queued to one request per second. Inside a zone you get the name you gave it,
because "School" says more than the road it sits on.

**Presence that is not a yes/no.** `home` and `away` are useless in the two
minutes that matter, so arriving and leaving get their own states for a few
minutes: `just_arrived` and `just_left`.

**Distance and direction from home**, so an automation can act before somebody
pulls into the driveway.

**The map card**: everyone at once in their own colour, a range menu from the
current day down to a single hour plus a month calendar for anything else,
street and satellite tiles, zones as circles with their own icon, and the stay
list underneath. It opens on today.

## Install

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Snaker-L&repository=ha-family-tracking&category=integration)

The button adds this repository to HACS on your own instance; then click
**Download** and restart Home Assistant. By hand: HACS → ⋮ → *Custom
repositories* → URL `https://github.com/Snaker-L/ha-family-tracking`,
category **Integration**.

Then Settings → Devices & services → **Add integration** → *Family Tracking*.
Leaving the people empty follows everyone, so somebody added later is included
by themselves.

Add the card to a dashboard from the card picker — it is already there, no
resource needed.

### Coming from 0.3.0 or earlier

Those versions were a dashboard card. Remove it in HACS, delete the
`/local/family-tracking-card.js` resource under Settings → Dashboards → ⋮ →
Resources, then install this. **Leaving the old resource in place breaks the
card**: the element would be defined twice. Your card configuration is
unaffected.

## Entities

Per person, one device with:

| Entity | State | Notable attributes |
|---|---|---|
| `sensor.<name>_location` | zone name, the enclosing place, or the address | `presence`, `source`, `latitude`, `longitude`, `gps_accuracy`, `distance_from_home`, `direction`, `bearing`, `street`, `city`, `postcode`, `country`, `last_decision`, `last_rejected` |
| `sensor.<name>_distance_from_home` | kilometres | `direction`, `bearing` |

`direction` is how the person is moving relative to home (`towards home`,
`away from home`, `stationary`); `bearing` is where they are from it (`N`, `SE`,
…). Two different questions, so two attributes.

`last_decision` says why the current fix was accepted (`first-fix`,
`zone-change`, `same-source`, `more-accurate`) and `last_rejected` why the most
recent report was not (`accuracy-zero`, `accuracy-poor`, `stale`,
`less-accurate`).

## Integration options

Set at install and changeable afterwards under *Configure*:

| Option | Default | Meaning |
|---|---|---|
| People with their own sensors | everyone | Which `person` entities get location and distance sensors; everyone ticked includes people added later |
| Keep position history for | 10 days | Any number of days, months or years (up to 20 years); kept by the integration in `family_tracking.db`, independent of the recorder |
| Resolve addresses | on | Reverse geocode positions outside a zone |
| Contact address | – | Passed to Nominatim, as their usage policy asks |
| Ignore fixes worse than | 100 m | Above this a fix says more about the radio than the person; applies to the live position, the sensors and the timeline, zone changes always count |
| Home zone | `zone.home` | Used for distance and direction |

## Card options

| Option | Type | Default | Meaning |
|---|---|---|---|
| `title` | string | – | Card header |
| `time_ranges` | list | `[1, 4, 6, 8, 12, 16, 18, 20, 22, 24]` | Entries of the range menu, in hours. *Today* heads the menu and the calendar sits beside it; neither can be configured away |
| `map_height` | number \\| `fill` | `480` | Height in pixels, or fill the space the card is given |
| `street_style` / `satellite_style` | see below | `esri_gray` / `esri_imagery` | Tiles |
| `custom_street` / `custom_satellite` | map | – | Own tile URL, when the style is `custom` |
| `person_colors` | map | palette | Colour per entity id |
| `hidden_persons` | list | `[]` | People the card leaves out entirely |
| `show_stays` | boolean | `true` | Stay list below the map |
| `show_zones` | boolean | `false` | Draw zones as circles with their icon |
| `zone_icons` / `zone_colors` | map | – | Icon and colour per zone |
| `hidden_zones` | list | `[]` | Zones the card leaves out |
| `geocode` | boolean | `true` | Turn the coordinates of a stay into a readable address |
| `places` | boolean | `true` | Show the name of the place a stay is in, where it has one, instead of its address |
| `place_address` | boolean | `false` | Keep the street address too, in brackets after the name |
| `stay_radius` | number | `20` | How far somebody may wander and still count as staying put, in metres (10–500) |
| `stay_min_duration` | number | `3` | How long a pause has to last to earn a line of its own, in minutes (1–720) |

`hidden_persons` and `hidden_zones` store what is *excluded*, so anything added
later shows up instead of going missing.

Tile styles — `street_style`: `osm`, `esri_gray` (follows your theme),
`esri_streets`, `esri_topo`, `esri_relief`, `osm_hot`, `opentopo`,
`basemap_at`, `basemap_at_gray`, `custom`. `satellite_style`:
`esri_imagery`, `esri_hybrid`, `basemap_at_ortho`,
`basemap_at_ortho_labels`, `custom`. The `basemap_at` ones cover Austria only.

## Good to know

- **The timeline reaches back as far as the integration keeps positions** —
  10 days unless set otherwise. It stores them in its own file,
  `family_tracking.db` in the config folder, so the recorder's retention for
  everything else stays untouched. On its first start it takes over what the
  recorder still holds; older days cannot be brought back.
- **Addresses are kept as long as the positions**, at least 90 days, in the same
  file — so an old month opens with its street names instead of a queue of
  lookups at one per second.
- **The timeline uses today's zones.** Which zone a past position lies in is
  worked out from its coordinates and the zones as they are set up now, so a
  renamed zone reads the same everywhere, a deleted one gives way to the
  address, and a new one applies to earlier visits too.
- **A stay inside a zone is exact** — arrival and departure come from the state
  changes. Only the parts outside any zone are clustered.
- **A stay is one circle, not a tangle of points.** Three hours of wandering a
  city centre would otherwise draw a knot that says nothing, so the samples
  inside a stay become its marker. None are discarded, and `stay_radius` and
  `stay_min_duration` decide where the line gives way to a circle. If the track
  looks coarser than you expect, that is usually the recorder rather than the
  card: Home Assistant stores a position when the phone reports one, which for
  the companion app is every couple of minutes by default.
- **The calendar takes two clicks.** One day picks that day; a second makes it
  a span; a third starts over. Whole days, no clocks — a map is asked about
  days, not about office hours. The week starts on the day that locale starts
  it on.
- **The card opens on today, not on the last 24 hours.** Asked where everyone
  has been, a rolling window answers with half of yesterday; midnight is the
  boundary people mean. *Today* heads the range menu, so it is one pick away
  again.
- **The map re-frames only when you change who is on it.** A new time range,
  incoming positions and switching to satellite leave your view alone.
- **Addresses are written the way that country writes them.** Nominatim hands
  the street and the house number over as separate fields, so the order is the
  integration's to get right: `350 5th Avenue` in New York, `Pariser Platz 1`
  in Berlin. Countries not on the list take the number after the street, which
  covers most of Europe and South America; adding one is a two-letter code in
  [`address.py`](custom_components/family_tracking/address.py).
- **A place is named, not addressed.** Reverse geocoding answers "what is
  nearest", which in the Donauzentrum is a phone shop and in the Q19 a coffee
  bar — and the street outside is no better, because nobody arranges to meet at
  Wagramer Straße 94. So the integration also asks Overpass what the fix falls
  *inside*: a shopping centre, a hospital, a university, a station. Where two
  answer at once — the centre and the unit within it — the larger one wins.
  Administrative areas never count; every fix is inside a district and a city,
  and neither says where somebody is.
- **A stay is the middle of many samples, and indoors they scatter.** Forty
  metres out is ordinary and puts the point outside the building, so the
  integration also looks a short way around it — but only for the kind of place
  that contains others. A café fifty metres away is somewhere else; a shopping
  centre fifty metres away is the building you are standing in.
- **Two services, one lookup.** Nominatim allows one request per second and
  asks for caching; Overpass is donated capacity. The integration keeps to
  both, asks them at the same time rather than one after the other, and caches
  the result for the whole household. Where Overpass cannot be reached the
  address is still shown — but it is not cached, so the place is named as soon
  as the service answers again.
- **Three Overpass instances, in rotation.** A busy one is asked twice and then
  left for the next; an explicit rate limit ends its turn at once, because
  asking again is the one thing it just said not to do. Whichever answered last
  is tried first next time, and one that a network cannot route to at all is
  left out for half an hour rather than costing a timeout on every lookup. Only
  instances holding the whole planet are listed: several public mirrors carry a
  single country and answer "nothing found" for everywhere else, which reads
  exactly like "nothing here". Every answer carries a count of the areas
  enclosing the fix, and a zero there means the instance has no data for this
  part of the world.
- **Both speak your language.** English and German are translated; anything else
  falls back to English. A language is one table in
  [`src/localize.ts`](src/localize.ts) and one file under
  [`custom_components/family_tracking/translations/`](custom_components/family_tracking/translations/).
- **Person pictures** come from the person entity; without one you get initials.
- **The integration brings its own icon.** Home Assistant 2026.3 and newer read
  it from `custom_components/family_tracking/brand/`; older versions show a
  placeholder instead.

## License

MIT — see [LICENSE](LICENSE).
