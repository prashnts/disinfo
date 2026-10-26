# disinfo TODO

Consolidated 2026-10-26: done steps live in CHANGELOG.md, the code docstrings and the `di.*` Redis keys.

## Weather overlays on the aviator map (2026-10-23, built)

Built (all in `screens/aviator/weather.py` + data service jobs, cached by `data_service.cached(name, every, fn)`): Météo-France radar (5 min, `meteo_france_api_key__radar`, ODIM HDF5 → 300x300 grid, `di.weather.radar`) drawn at the end of `basemap.paint`; wind arrows (Open-Meteo AROME, 30 min, static, alpha 0.25: the user dropped streaks/pulses and vigilance-on-map); clouds (EUMETView WMS `mtg_fd:ir105_hrfi`, fallback `msg_fes:ir108`, 10 min); vigilance on the weather card as one scrolled line (`__vigil` key) + forecast lines; rain + clouds in the sky view (`sky.py`, wind skipped on purpose); sky colours (`skylook.py`: sun altitude, HA weather state, light sensor); deps numpy, h5py, pyproj added. Layers are web toggles, default off.

Still to do: credits line "Météo-France · EUMETSAT · Open-Meteo" (like planespotters in `fonts.exsmall`); lightning dots from MTG LI; vigilance frame/pill on the map (proposed, user dropped for now); an LLM telegram line from the vigilance text (only if the structured lines fall short). Tunable if clouds look wrong: `cloud*` constants in sky.py.

### Sources (free, France) — researched 2026-10-23, items marked ? still to verify by a real request

| Layer | Source | Access | Cadence | Notes |
|---|---|---|---|---|
| Rain radar | **Météo-France "API Données Radar"** (portail-api.meteofrance.fr, `DonneesPubliquesRadar`) | free account + token, 850 req / 5 min | 5 min, 20 h kept | mosaic metropole: reflectivity, lame d'eau; Licence Ouverte (credit "Météo-France"); format? (Swagger, probably GeoTIFF/PNG, check) |
| Rain radar (fallback) | RainViewer tiles | no key | 5 min | personal/educational use only, "may vanish"; ok for a home display, good quick start |
| Satellite clouds | **EUMETSAT EUMETView WMS** `view.eumetsat.int/geoserver/wms` | no key for WMS | 10–15 min | EPSG:4326/3857; layers seen: `mtg_fd:ir105_hrfi` (1 km IR, 10 min), `msg_fes:ir108`, `msg_fes:clm` cloud mask, `msg_fes:cth`, `mtg_fd:li_afa` (lightning flash area, 5 min), `msg_fes:h60b` / `mtg_fd:h40b` (precip); natural-colour / airmass RGB for MTG? (list was truncated; capabilities past char 100000 unread) |
| Satellite (full res) | EUMETSAT Data Store API (free EUMETSAT account) | token | 10 min | FCI L1C full disk is huge; only if WMS is not enough. Policy: hourly/derived free, full-res 15 min free after 3 h → ? check MTG |
| Wind (field) | **Open-Meteo** `/v1/meteofrance` (AROME France 2.5 km, HD 1.5 km, 15-min; ARPEGE Europe 0.1°) | no key, non-commercial, ~10k req/day | AROME 3 h (15-min models hourly) | wind 10..200 m + gusts, comma-separated lat/lon lists in one call → build a ~10×10 grid in one request; ? bounding-box/grid mode |
| Wind (field, raw) | Météo-France AROME/ARPEGE "Paquets" GRIB2 (portail-api, free account) | token | 3 h | U/V 10 m, heavy GRIB; only if Open-Meteo falls short (`meteole` python lib wraps it) |
| Alerts / storms | **Météo-France "Bulletin Vigilance"** API | free account + app token | per bulletin (~2×/day + updates) | JSON "carte" (per département, orages / vent violent / pluie-inondation, colour level) + PNG vignettes; Paris = dept 75 + neighbours; there was a June 2026 portal auth report, use private-window fix |
| Alerts (no key) | Meteoalarm (EU) feed | none | | optional; unverified |
| Lightning | EUMETSAT MTG LI (`mtg_fd:li_afa`) via WMS | none | 5 min | maybe Blitzortung (community, strict terms) — skip unless asked |

RainViewer (checked 2026-10-23): `api.rainviewer.com/public/weather-maps.json`, past 2 h only in 10 min steps (no nowcast listed), tiles z≤7 (~5 km/px at z7: coarse next to a 60 km map; fine for France-wide), 256/512 px, colour scheme id + smooth/snow options, coverage mask endpoint; rate limits/terms page not read. Source-only/docker distribution is not "commercial", but the licence says personal/educational, so ship it as an optional provider, off by default, and make Météo-France the default radar.

Not found: any free Météo-France *wind-observation* mosaic (the "profils de vent" products are paid). Use model wind (AROME) = fine for a display.
Licences: Météo-France = Licence Ouverte 2.0 (credit "Météo-France"), EUMETSAT = credit "EUMETSAT", Open-Meteo = CC-BY 4.0 credit, RainViewer = credit asked. Add to the credit line in `fonts.exsmall` like planespotters.

## Camera and view cases (2026-10-23)

Map (`aviator/app.py radar()`): 1) rest = `view(focus, radius)` (home slice, 40 km default, or an airport with ≥ `queue_min` low planes); 2) a card on top for a plane overhead/tapped: one 4 s zoom sweep (2.5x), then `held` until it leaves the clear box (`framed()`); 3) no card but a plane overhead: the nearest is framed the same way, no sweep, haloed (`following()` fallback, `_near`). "Overhead" (tasks.py): `reach` ≤ `overhead_km` (8) now or at closest approach within `lookahead` (150 s), reach = hypot(distance, altitude/2); `overhead_at` keeps it 60 s. The first rule had a plane overhead 100 % of the time on the live feed: retuned after the user's maindev run. Sky (`sky.py look/aim`): rest = mean bearing of the watched planes, followed = centred in the clear box. Tunables if it still misses: `overhead_km` (12 catches more), `lookahead`, `max_watched`, `framed()`. Not done: choosing by interest (airline, type), the solar view.

## Daylight (2026-10-25..26, built; see memory disinfo-daylight)

`aviator/daylight.py`: `task` every minute (log `di.daylight.log`, 14 days), `sky_task` every 15 min (Open-Meteo cover + radiation). The east window can't see the sun in the afternoon, so with the sun outside `aviator_window` `sun`/`cloud` come from the model; the desk sensor (telemetry `rgbc`, fresh within 60 s) is the most reliable and tells artificial light (`room_dark/room_bright` 100/10000 counts are a first guess: check at night with the lamps). First production night 2026-10-26 (`~/limn-shot/daylight-*.json*`): the morning matches Open-Meteo. Lamp fix done (`signatures` takes a day row when the lamps are < 5 % of the counts).

## Sky state: one fused picture (2026-10-26, built, uncommitted: the user deploys the data service + renderers)

**Shape: sources → observations → fusion → `SkyState`.**
- Each source (a job, or another device) writes its observations to Redis `di.sky.obs.<source>`: `{at, quantities: {name:
  [value, sigma]}, notes}`. A source says only what it can see (the window light: cloud by day; the satellite: cold tops;
  the planes: the air aloft; the camera: cover in its view, the sun's disc, sky colour). New source = a new key, nothing else.
- The fusion job (today's `daylight.task` grows into it, every minute) combines each quantity: the model is the prior,
  observations weigh by 1/sigma², sigma grows with age, and disagreement between sources lowers the confidence instead of
  being averaged away. Each quantity comes out as `{v, conf, by: {source: v}}`: a visualisation can show only what's sure
  (cirrus only above 0.6, say) and debugging shows who said what.
- `SkyState` in Redis `di.sky` (+ pubsub), read like `daylight.doc()`: 
  - `time`: now, sun {alt, az, phase night/astronomical/nautical/civil/golden/day, next rise/set}, moon {alt, az, phase}.
  - `sky`: cover total/low/mid/high, sun_visible (the direct beam), brightness, dark, broken, haze, warmth, sky colour
    (zenith/horizon, from the camera when there is one: it could drive the palette directly).
  - `precip`: rate, type (rain/snow/mix: from the freezing level, below), radar ring, next rain span.
  - `air`: surface temp (AROME), the profile aloft [{alt, t, wind}], freezing level, lapse rate, inversion, jet (wind at
    FL300), contrails {form, persist}.
  - `alerts`: vigilance. `sources`: {name: {at, ok}} (a dead source shows as such, not as clear sky).
  - `trend`: the last 3 h and the next 6 h of the main quantities (model forward, observations back): "clearing", "rain
    in 40 min" for animations.
  - The room (lamps, shutter, each screen's gain) stays out: it's per screen and indoor. The fusion uses it (lamps off the
    desk counts, the shutter = the window blind), the visualisation applies the gain.

**Planes as weather balloons (checked live 2026-10-26: readsb gives `oat`, `tat`, `wd`, `ws` for 41 of 107 aircraft,
from BDS 5,0/6,0).** 0 °C at ~8750 ft, -40 °C at ~31000 ft, wind 280-320° 20 kt low → 100 kt at FL310. Noisy (derived
from Mach and TAS, ±3-7 °C between planes at one level: DLV494 -37 vs GAF300 -30 at FL270): median per 1000 ft bin over
20-30 min, drop outliers, the low bins come only from CDG/ORY approaches. Uses:
- Freezing level → snow vs rain (better than skylook's surface-temperature ramp; melting layer ~300 m under it).
- Contrails: Schmidt-Appleman (T under ~-40 °C) from the planes, persistence from AROME's humidity at 300/250 hPa (ice
  supersaturation) → draw trails behind the high planes in the sky view, long-lived ones spreading into cirrus.
- Cloud drift: low cloud moves with the 850 hPa wind, cirrus with the jet: direction and speed for the cloud layers.
- Inversion (warmer above than below) → haze/smog at the horizon.
- Confidence for the model: compare with Open-Meteo `temperature_850hPa/700/500/300hPa`; a big miss → the model's sigma up.

**Half-sky camera (indoor, through the east window).** A source like the others, its processing on its own device:
window mask once (sky vs frame/buildings), azimuth/elevation map fitted on the sun's track over a day, then per frame: cover
by red/blue ratio (cloud ~1, blue sky lower), the sun's disc visible, sky colour at zenith and horizon, stars at night
(clear vs cloud), drops on the glass. Indoor issues: the lamps reflect in the glass at night (the lamp state is known: mask
or skip), the shutter (dark frame = shutter, not night). Reuse the limn camera lib's capture/ladder ideas.

**Fix now, whatever the rest:** the E27 desk lamp is sometimes forgotten on → `signatures` never sees all lamps off by
day. Take a day row when the lamps' share of its counts (from `lamp_model`) is under 5 %, not only when all are off.

**Built:** `aviator/aloft.py` (planes' temperature/wind profile from ADS-B in 1000 ft bins, freezing level, jet, contrails by Schmidt-Appleman; live: freezing 3.1-3.3 km vs model 2.96), `aviator/skystate.py` (`task` every minute → Redis `di.sky` + `di.sky.log`, sigmas/`stale`/`quantities` tunables at the top, `doc()` / `v()`), renderer `skylook.seen(fs)` → `Seen` (replaces `measured`/`wetness`/...; without `di.sky` it falls back to HA's state), sky view `contrails()` and `puff()`/`lobes()` heaps (800x480 sky frame 6.4 → 8.1 ms). Tests `test_seen`, `test_fuse`, `test_sky_state`, `test_aloft`, `test_contrails_and_puffs`. Renders in `~/limn-shot/sky-state/`. Watch the night look: the deck now also comes from the model at night.
Not done: cloud drift by the wind (`air.wind_low`/`wind_high` are there), the haze band from an inversion, a trend view (`trend.hours`/`seen`), alerts in the sky view.

**The half-sky camera as a source (contract, nothing to change in skystate):** write Redis `di.sky.obs.camera` =
`{"at": epoch s, "q": {"cover": [v, sigma], "deck": [...], "high": [...], "sun": [...], "dark": [...], "haze": [...]},
"notes": {...}}` with an expiry (`SET ... EX 600`), or `skystate.observe('camera', q, ttl)` from Python. Names outside
`quantities` are ignored (add them there first: e.g. `zenith_rgb`, `stars`). Its staleness is `stale_other` (900 s)
unless added to `stale`. A good camera deserves sigma ~0.1 for cover/sun by day.
Not done: drawing cloud drift by the wind (`air.wind_low`/`wind_high` are there), the haze band from an inversion, a
trend view (`trend.hours`/`seen`), alerts in the sky view.

