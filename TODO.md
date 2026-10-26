# disinfo TODO

## Weather overlays on the aviator map (planned 2026-10-23)

Goal: satellite clouds + rain radar + wind (+ storms / alerts) as toggleable layers under the planes on the aviator radar
(`screens/aviator/`), same switches as the basemap layers on the web page. Home 48.8426,2.3916, map radius ≤ ~60 km up to
a zoomed-out France view.

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

### Plan

1. **Account & token (user)**: create Météo-France portal account, subscribe to Radar, Bulletin Vigilance (and AROME if wanted); token goes in `app_config` (`mf_token`), never in repo. Ask before installing deps.
2. **Poller** `screens/aviator/weather.py` in the data service next to `tasks.py` (own interval, not the 1 s plane job):
   - radar: every 5 min → mosaic cropped to the map's max box, reprojected to the flat km grid (same projection as `utils.py`), stored as a small RGBA PNG (+ timestamp) in Redis `di.weather.radar` (ex 900) + pubsub notify. Keep the last ~6 frames for a loop.
   - satellite: every 10 min → WMS `GetMap` with bbox = our box, EPSG:3857/4326, size ~512 px, `ir105_hrfi` first (works day and night) → greyscale→alpha cloud layer. Keep 3–6 frames.
   - wind: every hour → u/v on a ~10×10 grid (Open-Meteo multi-point) → Redis `di.weather.wind` JSON.
   - vigilance: every 30 min → the Paris-area level/phenomena → Redis `di.weather.alert`.
   - Each fetch failing must leave the old data and a "stale since" flag; nothing blocks the plane poller.
3. **Renderer** in the radar (`app.py`, drawn after `basemap.draw`, before planes), cairo only, no new deps:
   - raster layers: `cairo.ImageSurface` from the PNG, one transform with `basemap.view_matrix`, alpha per layer; radar recoloured to the existing palette (dark mode: low-alpha blue→violet, light mode deeper). Cross-fade between frames on change; **tag** the frame so the tag changes only when a new frame arrives (per user: per-frame changes must be tagged).
   - wind: not a per-frame redraw — pre-render a short loop of streak/particle frames (or arrows, thinner at the edge) from the grid; update at 1–5 fps with the existing 5 fps throttle; arrows+speed number as the cheap fallback.
   - storm/alert: a tinted frame edge or a small tile/pill when vigilance ≥ orange (orages / vent), and lightning dots from LI when available.
   - sky view: clouds only if cheap (cloud mask as haze over the roofline); otherwise leave the sky view alone.
4. **Switches**: add `weather` group to `basemap.layers`-style web toggles (`radar`, `clouds`, `wind`, `alerts`), per-session like `map_up`; default off; the display "Radar" button unchanged. Optional: auto-on `alerts` when vigilance ≥ orange, in the spirit of "background reacts to the stacks".
5. **Bench** every step with `disinfo/bench.py` (stdout dropped: HA token), log in `CHANGELOG.md`; watch the entry screen (266×160, server ~6.6× slower than PC) and the Guition fps.
6. **Tests**: parse fixtures of each source (saved responses), projection check (home pixel = centre; CDG/ORY pixels vs known km), stale-data behaviour.

### Order & open decisions (for the user)

- Start with **satellite IR via EUMETView (no account)** and **wind via Open-Meteo (no account)**: both work today without credentials → fastest visible result. Then radar (Météo-France token) and vigilance.
- Decide: radar from Météo-France (proper, needs account) or RainViewer first (quick, personal-use licence)?
- Decide: wind style — flowing streaks vs arrows; altitude (10 m vs 100–200 m, relevant for aircraft: pressure-level winds at ~FL100/FL300 are in AROME/ARPEGE too!).
- Decide: which screens get it (entry is the weak one for fps).
- To verify with real requests before coding: Météo-France radar output format + size; EUMETView natural-colour layer for MTG; Open-Meteo grid cost; vigilance JSON shape for dept 75.

### Sources
- Météo-France radar API: https://www.data.gouv.fr/dataservices/api-donnees-radar
- Météo-France portal: https://portail-api.meteofrance.fr/
- Vigilance API: https://www.data.gouv.fr/dataservices/api-bulletin-vigilance
- AROME data: https://data.gouv.fr/en/datasets/donnees-du-modele-atmospherique-arome-a-aire-limitee-a-haute-resolution
- EUMETView WMS capabilities: https://view.eumetsat.int/geoserver/wms?service=WMS&request=GetCapabilities
- EUMETSAT data policy: https://www.eumetsat.int/eumetsat-streamlines-its-data-and-service-policy-make-more-data-free-charge
- Open-Meteo Météo-France models: https://open-meteo.com/en/docs/meteofrance-api
- RainViewer API: https://www.rainviewer.com/api.html

## STATUS / hand-off notes for the next agent (weather overlays)

**2026-10-23, step 1 done: Météo-France radar fetch + decode works (tested on real data, not yet wired to anything).**
- Key: `meteo_france_api_key` (SecretStr, added to `config.py`; user put it in `.config-didesk.json`). Header `apikey: <key>`. One key = per *application*; it works for Radar.
- **Vigilance returns 403 "Resource forbidden"** on `DPVigilance/v1/cartevigilance/encours` with this key → ask the user to subscribe *Bulletin Vigilance* on the SAME application as the key (or make a second key `meteo_france_vigilance_key`). Not tested further.
- Radar endpoint (works): `GET https://public-api.meteofrance.fr/public/DPRadar/v1/mosaiques/METROPOLE/observations/LAME_D_EAU/produit?maille=500` → ODIM HDF5 (~2 MB, 3472² uint16, ACRR = mm in the 5 min, gain 0.01, 65534 undetect / 65535 nodata, `+proj=stere` polar stereographic, `where/UL_lat,UL_lon` corner). `maille=1000` gives BUFR.gz (needs eccodes: avoid). `REFLECTIVITY/produit` is 404 (wrong product name, not searched; LAME_D_EAU is enough).
- `screens/aviator/weather.py` (new): `fetch_radar`, `decode` (→ 300×300 uint8 grid, 1 km/px, ±150 km around home, row 0 north, level = mm/h × 4), `png_of`, `store` (Redis `di.weather.radar` JSON with base64 PNG, pubsub 'weather'), `radar_job`. Decode takes 0.15 s; looks right on a real frontal band (not yet checked against known rain position).
- **Needs new deps h5py, numpy, pyproj (+ pillow already): NOT added to pyproject/requirements: ask the user first.** Tested with `uv run --no-project --with h5py --with numpy --with pyproj --with pillow ... python -I`.
- NOT done yet: (a) DONE: `radar_task` (guarded wrapper) scheduled every 5 min in `drat/data_service.py`, prints "missing h5py" until deps are added (untested live); (b) renderer: load `di.weather.radar`, PNG→cairo surface, draw after `basemap.draw` in `app.py` (~line 265) with `basemap.view_matrix`, 1 px = 1 km at (-150..150), blue→violet palette like basemap styles, tag the frame by `at`; (c) web toggle `weather` layer (off by default) + credit "Météo-France" in the credit line; (d) satellite (EUMETView WMS, no key) and wind (Open-Meteo `/v1/meteofrance`, no key); (e) vigilance (blocked, above); (f) bench + CHANGELOG.

**2026-10-23, step 2 done: rain overlay drawn + web toggle (tested offline with a rendered PNG, not on a live display).**
- Keys renamed by the user: `meteo_france_api_key__radar` / `__vigil` (config.py; `.config-didesk.json` still has the old name). Vigilance key NOT tested yet (try the `DPVigilance/v1/cartevigilance/encours` GET with `apikey: <vigil key>`).
- Deps added (pyproject + requirements.txt, `uv sync` run): numpy, h5py, pyproj. `uv.lock` updated by uv sync.
- `weather.rain_doc()` (Redis read at most every 20 s) / `rain_surface` (ARGB, blue→violet→pink by mm/h, alpha 0.12–0.6, deeper in light mode, cached by timestamp) / `paint_rain`. Drawn at the end of `basemap.paint`, i.e. inside the cached basemap surface (key includes the radar timestamp), over the map features and under planes. Layer name `rain` in the web page's `names` (web/index.html): on by default, uncheck = hidden (the existing `off` list).
- Test script (scratchpad, not in repo): `DI_CONFIG_PATH=.config-diradar.json uv run python t_rain.py <outdir>` fetches the real mosaic and renders basemap with rain; result looked right (rain band east of Paris). Pixels are 1 km: visible blockiness when zoomed in; bilinear is on. Could resample at 0.5 km.
- Next: user deploys + restarts the data service (data_service runs `radar_task` every 5 min); check the first fetch in its log. Then: satellite (EUMETView), wind (Open-Meteo), vigilance, bench + CHANGELOG (the basemap cache key now changes every 5 min: one repaint, cheap).

**2026-10-23, step 2b: CHANGELOG entry + bench of the rain layer done** (+0.3 ms per basemap repaint, 5.7 ms per 5-min update). Order the user chose next: wind (Open-Meteo), then satellite (EUMETView).

**2026-10-23, step 3 done: wind arrows** (`weather.wind_job` every 30 min → Redis `di.weather.wind`, `paint_wind` in `basemap.paint`, layer `wind`, CHANGELOG + bench: +5 ms per repaint at 800x480, a Python loop: vectorise or cache by view if it matters). Open-Meteo `/v1/meteofrance` takes 49 points in one call, `current=wind_speed_10m,wind_direction_10m`, m/s. Credit "Open-Meteo (CC-BY 4.0), Météo-France AROME" not yet shown anywhere. Possible later: pressure-level wind at flight altitude, streak animation. Next: satellite (EUMETView WMS), then vigilance.

**2026-10-23, step 4 done: clouds** (`weather.sat_job` every 10 min → Redis `di.weather.sat`; EUMETView WMS 1.3.0 EPSG:4326 (bbox lat first), `mtg_fd:ir105_hrfi` first, falls back to `msg_fes:ir108` (the MTG layer answered 503 once, retry works); grey = brighter is colder, stretched from 90 to translucent white; `paint_sat` is drawn FIRST in `basemap.paint`; layer `clouds`). CHANGELOG + bench done (all three layers: +0.8 ms at 266x160, +5.7 ms at 800x480 per repaint, 0.1 ms at rest). Looks subtle on the dark map; tune `sat_alpha`/`sat_floor` in weather.py after seeing it live.
Still to do: (1) credits line "Météo-France · EUMETSAT · Open-Meteo" somewhere visible (user showed planespotters credit in `fonts.exsmall`); (2) vigilance (`meteo_france_api_key__vigil` untested); (3) user deploys, restarts data service, checks its log for "weather ..." errors; (4) NEW LAYERS ARE ON BY DEFAULT: uncheck in the web page if cluttered; (5) wind arrows: vectorise if fps matters on big screens; (6) not tested on a live display.

**2026-10-23, step 5 done: vigilance on the weather card.** `GET https://public-api.meteofrance.fr/public/DPVigilance/v1/cartevigilance/encours` (header `apikey`, 180 KB JSON, works with the `__vigil` key; `textesvigilance/encours` works too: 120 KB, national bulletin only, text under `product.text_bloc_items[].bloc_items[].text_items[].term_items[].subdivision_text[]`, French, verbose). `screens/weather/vigilance.py`: `job` (data service, 15 min) → Redis `di.weather.vigil` {phenomena: id → [[begin, end, color_id epoch s]]}, `lines(now)` → [(color, 'Vent orange → 16h')]; `weather/app.py` `vigil_lines` appended to the card's vstack (grows down). Phenomenon ids: 1 vent, 2 pluie-inondation, 3 orages, 4 crues, 5 neige-verglas, 6 canicule, 7 grand froid, 8 avalanches, 9 vagues; color_id 1 green, 2 yellow, 3 orange, 4 red. Cared (from yellow): 2, 5, 7; others from orange. Today (storm "AUSTEN"): Paris wind orange until 16h.
Ideas not built: (a) an LLM line like the news highlights (`apps/news_highlights.py`: pydantic_ai Agent + `oai_base_url`, gpt-oss-20b) fed the national/IdF text → 1–2 telegram lines, only worth it when the structured lines are not enough; (b) show the vigilance on the radar map (tint/pill when orange); (c) a cold/rain line from AROME for the next hours (the user cares about rain and cold: "pluie 15h-17h, 4°"), from Open-Meteo hourly `precipitation,temperature_2m`; (d) long lines (`Neige/verglas orange 14h → 22h`) may be wider than the card (~68 px for one short line) → shorten or wrap if it clips. Not tested on a live card (HA needed); `vigil_lines` rendered alone is 68x7 px.

**2026-10-23, step 6:** weather card warnings now ONE scrolled line (`HScroller(size=card width)`, `weather/app.py` `vigil_lines(now, tick, width)`) = vigilance lines + `vigilance.forecast_lines` (next rain span / lowest temp ≤ 5° in 12 h, Open-Meteo hourly `precipitation,temperature_2m` via `forecast_job` every 30 min → Redis `di.weather.forecast`). Not seen live on the card (needs HA). Compass: `aviator/app.py compass()`, drawn last on the cairo surface, bottom right, rotated by −map_up (tested up=0/270). It may sit under the bottom card stack on some screens.
Proposed for the map (not built, user asked how): a thin coloured frame/glow on the map's edge in the vigilance colour when orange or red (rain/cold/wind/storm), a small pill by the compass with the phenomenon letters (e.g. "V" wind, "P" rain, "F" cold, "O" storms), and the radar rain layer unchanged. Hide for green/yellow-non-cared. Data already in Redis `di.weather.vigil`.

**2026-10-23, step 7: wind animated.** `weather.paint_flow` (stateless streaks, seeds on a golden-ratio sequence, phase per streak, life 6 s) replaces the static arrows (`paint_wind` and the wind part of `basemap.draw`'s cache key removed). `app.py` calls it after `basemap.draw`; `throttled()` redraws every `weather.flow_every` = 0.2 s while `weather.flow_active(off)` (layer `wind` on + data). WATCH: radar frames now change 5×/s: check the entry/Guition fps, and the data churn (transport regions); if too heavy raise `flow_every` to 0.33–0.5 or cut `flow_cell_px` density; at low fps the streak steps (~3 px at 5 fps) read as dashes, it's fine. Not seen live.

**2026-10-23, step 7b (replaces 7): wind = arrows with heads, pulsed.** User dropped vigilance-on-map and the continuous streaks. `weather.paint_flow` now draws the arrow grid; pulses every `pulse_every` 2.5 s (fade in, nudge `pulse_px` forward during `pulse_for` 1 s, hold, fade out); `app.py throttled()` redraws at `flow_every` 0.2 s only while `weather.flow_moving(now)`, else the usual 1 s: 2.6 redraws/s vs 5/s. Further savings if needed: `pulse_for` 0.6 and `flow_every` 0.33, or `pulse_every` 4. Arrows cost 3.7 ms at 800x480 per frame (Python loop, ~330 arrows).

**2026-10-23, step 7c (final for wind): no animation.** User: more transparent, no pulsing. `weather.paint_wind` (alpha 0.25, arrows with heads on a 34 px screen grid) is back inside `basemap.draw`'s cached image (key has the wind's timestamp); `paint_flow`, `flow_*` and the app.py throttle changes are removed. No extra redraws.

**2026-10-23, step 8: rain + clouds in the sky view** (`aviator/sky.py` `clouds()`/`rain()`, `weather.sky_profile/polar/along`; wind skipped on purpose). Profiles per update: 120 bearings x bins (rain 8,18,32,50,80 km; clouds 10,30,60,100 km). Tunables: `cloud_alpha`, cover gain 2.5, `cloud_base_km` 4, `rain_weights`, alpha 1.4 cap 0.6. Clouds are from the IR (cold tops only): thin/low cloud won't show. Tested only on a bare cairo surface with yaw 90/270, not in the full sky frame (needs fs + state). Verify `OpenedStateManager().get_state(fs).off` is the same list the basemap uses (it is: `opened_state.off`).

**2026-10-23: data service cache.** `data_service.cached(name, every, fn)` wraps radar/wind/sat/vigil/forecast; tasks now return True on success (False/None otherwise: not recorded). Only the startup `run_all` is skipped when fresh (`starting` flag). To force a refetch: `redis-cli del di.dataservice.ran.<name>` (names: radar, wind, sat, vigil, forecast).

**2026-10-23, step 9: sky colours** (`aviator/skylook.py`: `look(sun_alt, cond, gain)`, `paint`; `sky.py` calls it where the gradient was). Inputs: sun altitude (suncalc), HA `weather_entity` state (`conditions` table), `ambient_light_sensor` lux. Not done: the satellite's cloud cover as a fallback when HA has no weather state, cpt-city palettes (phillips.shef.ac.uk returned 500 on 2026-10-23; `rafi/` is its sky collection), a sunset reflection on the roofs' windows (only a glow under the horizon now), stars. Seen at 13:00/19:05/07:40 in a full `sky()` frame (HA live): fine; the glow only shows when the sun is within 30 degrees of the view. Font note: bitocra7 lacks → and ° (checked in the .bdf); use ASCII.

## Camera and view cases (2026-10-23, after the user's "we keep missing planes above or near us")

Map (`aviator/app.py radar()`), in this order:
1. **Rest** (nothing followed): `view(focus, radius)`: `focus` = 'home' (the window's slice around home out to `radius`, 40 km default, web slider) when any plane is watched; else an airport with >= `queue_min` low planes climbing/descending (CDG, ORY, LBG, sticky); else the same home slice. x the web zoom, then `drift` (wander + breathe).
2. **A card on top** for a plane overhead or tapped (`follow()` from the stack): first time per plane a 4 s zoom sweep (2.5x), then `held`: still while the plane is in the clear box (the part the cards leave free), re-framed when it leaves: `framed()` = between home and the plane if both fit at the resting scale, else on the plane (a tapped far plane is followed anywhere, 90 s).
3. **NEW, no card on top but a plane overhead**: the nearest overhead plane is framed the same way, no sweep, haloed, kept while it is overhead (`following()` fallback, `_near`). So the home slice never hides a plane passing near while the tile is on top.
4. What "overhead" is (tasks.py): `reach` <= `overhead_km` (8) now or at the closest approach within `lookahead` (150 s); reach = hypot(distance, altitude/2) (km). Old rule was elevation >= 60 degrees. `overhead_at` keeps it 60 s after. Sorted nearest first, they go first in `watched` (cards, max `max_watched` 2 unless more overhead).
Sky (`sky.py look/aim`): rest = the mean bearing of the watched planes within the window, held until they move a quarter view; followed (case 2/3) = centred in the clear box, same sweep. Layers: `planes`, `info`, `clouds`, `rain`, `wind` and the map's.
Tunables if it still misses: `overhead_km` (8; 12 catches more), `lookahead` (150 s), `max_watched`, `framed()`'s requirement that home stays in. Not done: choosing by the plane's interest (airline, type), the solar view.
Stars/moon/roof sunset/cloud fallback done (astro.py). cpt-city palettes: the site was down (HTTP 500) on 2026-10-23, own palette in skylook.py instead; its sky collection is `rafi/`.

**2026-10-23 fix after the user's run (maindev):** the first overhead rule (reach <= 8 km, altitude half, lookahead 150 s, 60 s after) had a plane overhead 100% of the time on the live feed (CDG/ORY traffic): cards always there, so the radar was always the background (no solar view) and the cards/view rotated between planes. Now reach counts the altitude a quarter, `overhead_km` 3.5, `lookahead` 90 s, `passed_for` 30 s; `tasks.watched` keeps the order of overhead planes (no swap as they move). Measured live: 3.5 gives about the old rate (old rule: 15-57% of the time with >= 1 plane overhead, depending on the traffic). If it is still too often: 3 (or 2.5); too rare: 4-5. Test script idea (scratchpad t_over.py): sample `tasks.update` on the live feed every 3 s and count planes with `nearness <= T`.

**2026-10-25: the light by the window (`aviator/daylight.py`).** Data service: `daylight.task` every minute (log row in `di.daylight.log`, 14 days; estimate in `di.daylight`), `sky_task` every 15 min (Open-Meteo cover low/mid/high + radiation, `di.weather.sky`), desk telemetry from `di.pubsub.telemetry` (node `daylight_node`). Once a day (thread, ~25 s): Sensei's envelope from HA's history (p90 over the floor by sun bearing, 5° bins), the desk's lamp model (night least squares on the lamps' brightness; HA doesn't record the lights, so only from the log), desk envelope after 2 days, usual colour (log r/b) after a few. Force: `redis-cli del di.daylight.env`. HA sensors `sensor.distudy_clear/daylight/sky_cloud` (not in devmode). Desk client: APDS auto range (64x/712 ms .. 1x/50 ms), counts as at 4x/712 ms, `rgbc` + `range` in telemetry; deployed on the desk 2026-10-25 (backup `~/di_remote.py.bak-2026-10-25`).
Seen on 14 days of Sensei: log10(lux over the envelope) tracks the model's low cloud (>= -0.3 clear-ish, -1..-0.6 overcast, < -1 dark); 15-min variability didn't separate cloud types (Sensei updates too slowly?), `broken` is a guess; the shutter = under 4% of the envelope with a bright model sky (morning before ~9:20). East window: direct sun on the sensors in the morning (3400 lx, UV 1000). Not done: UV (weak through glass), lamp steps in daytime to learn the lamps faster, `light_gain` still reads `sensor.radar_salon_light`, which is `unknown` in HA (the room gain is 1.0 everywhere). Tune after a few days with the desk: `shutter_b`, the cloud/dark/sun ramps in `estimate`, `cirrus_*`.
Later the same day: the east window can't see the sun in the afternoon, and a clear sky across is no brighter than a bright overcast (live: Sensei at 34% of its envelope under a clear sky, model kt 0.86). With the sun outside `aviator_window`, `sun` and `cloud` come from the model's kt; the light only says when it's dark (log b < -0.8). Facades lit by day (`roofs(daylit=)`: facing the sun, by `sun` or 1 - cloud). `daylight.model()` reads Open-Meteo's fetch directly (cirrus with no light estimate). The job writes Nones when HA or an entity is missing. The desk logger was stopped (it had died at 14:16 anyway): no lamp-only night recorded; the job's own log builds the lamp model.
Then (user: the desk sensor is the most reliable, it can tell artificial light): `skylook.light_gain` uses the screen's own sensor first (telemetry `rgbc`, fresh within 60 s; `room_dark/room_bright` 100/10000 counts are a first guess: check at night with the lamps), then `ambient_light_sensor` (the `radar_*` ones need engineering mode: unreliable), then 1.0. The desk counts twice in the daylight ratio. `daylight.signatures`: the lamps' colour (night) and the daylight's (day, HA lamps off), per clear count; `desk_daylight` takes the known lamps off by brightness, then splits the rest by colour (a lamp HA doesn't know). Not seen on the real sensor yet: if the two colours are within 0.03 it stays off (`envs['sig']` None). Telemetry: the light sensor now updates on any change of the client's `updated_at` (it went stale after a client restart: monotonic clock starts over); then all parts (remote, encoder, user, tof, ircam), and the timer: the encoder's position seen first or after a client restart is no turn, the 5 s pause on the client's clock (it compared it with the server's). Tests in `tests/test_telemetry.py`.
**2026-10-26: first night of the production log** (dump in `~/limn-shot/daylight-*.json*`, 1206 rows, no gaps). The morning matches Open-Meteo (mid+high 100 %, direct ~0 until 10h): cloud ~1, dark 0.8-0.99 at 08:10-08:40, b 0.36 when the direct radiation came back at 10h. The desk lamps left+right toggle together ~12 times a night (+~1500 clear counts, warm r/c 0.47); `lamp_model` fits on this log (the server's env predates it: refresh ~14:14). **`light.ikea_e27_study_desklamp` is on at 232 in every row** → `signatures` never sees "all lamps off" by day → no colour split; with it ignored: 728 night / 48 day rows, lamp 0.51/0.32/0.26 vs day 0.41/0.34/0.34 (separable). Ask the user if that lamp is really on (night floor 135 counts, reddish: it, or the display's own glow). Room gain: lamps off 135 → 0.58, on ~1640 → 0.82, day 10-24k → 1.0.

## Sky state: one fused picture of the sky, the weather and the time (proposal, 2026-10-26)

The user: the window light worked well; next, outside sources for confidence (not to rely on them), one data structure with
the whole state for visualisations, the planes' temperatures (ADS-B), and soon an indoor half-sky camera to plug in.

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

**Order proposed:** (1) the E27 fix; (2) `SkyState` + the fusion with today's sources (light, AROME cover, satellite,
HA state, radar, vigilance), `sky.py`/`skylook` reading it instead of each source; (3) the planes' profile (freezing level,
contrails); (4) the camera as a source when it exists.

**2026-10-26, built (uncommitted; user deploys the data service + renderers):**
- Lamp fix: `daylight.signatures(rows, coef)` takes a day row when the lamp model puts the lamps under 5 % of its counts,
  and takes them off first (`refresh` fits the lamps before the signatures). On the production log: lamp
  0.51/0.32/0.26 vs day 0.41/0.34/0.34. `estimate` now says `window` (the sun in its view).
- `aviator/aloft.py`: `add(now, aircraft)` from `tasks.adsbx_task` (one sample per plane a minute, 150 km, 30 min),
  `profile()` (1000 ft bins of pressure altitude, a plane once per bin, >= 3 planes, a bin 6 °C off the line through its
  neighbours dropped), `derived()` (freezing level above the sea, lapse 1.5-9 km, inversion under 3 km, jet, `contrail_m`
  by Schmidt-Appleman). Live 2026-10-26: freezing 3.1-3.3 km (model 2.96), jet 55 m/s 309° at FL355, model 1.4 °C warm.
- `aviator/skystate.py`: `task()` every minute in the data service → Redis `di.sky` (15 min expiry) + `di.sky.log`
  (row a minute, 14 days: [t, cover, deck, high, sun, dark, mm, conf]) + pubsub `weather`/`sky`. Sources: model
  (`daylight.fetch_sky` now also hourly -3..+6 h with 850-250 hPa temperature/RH/wind), light, sat (reports high cloud
  only when it sees cold tops: thin cirrus is warm in IR, it said 0.01 under 100 % cirrus), ha, radar, planes, and
  `di.sky.obs.<source>` keys. Tunables at the top: sigmas in each `*_obs`, `stale` (sigma doubles at that age, dropped at
  3x), `quantities` (the spread that halves the confidence). Shape in the module's docstring; read with `doc()` / `v()`.
- Renderer: `skylook.seen(fs)` → `Seen` (cond, deck, high, sun, dark, broken, warmth, wet, snow, trails); replaces
  `measured`/`wetness`/`weather_state`/`temperature` and `sky.overhead_cover`. Deck and cirrus are scaled by
  `min(1, 0.4 + conf)`; the darkening uses 0.6 x dark. Without `di.sky` (data service down): HA's state alone, no deck.
  Deck now comes from the model too (at night as well), not only from the light: watch the night look.
- Sky view: `contrails()` behind planes above `form_m` (25 s in dry air → 10 min, wider, at ice saturation; old parts
  drift with the FL300 wind). `puff()`/`lobes()`: tiers of heaps on a flat base (fixes the notch: arcs without
  `new_sub_path`). 800x480 sky frame 6.4 → 8.1 ms (the heaps), 128x128 ~3 ms unchanged.
- Tests: `test_seen`, `test_fuse`, `test_sky_state`, `test_aloft`, `test_contrails_and_puffs`, lamp-left-on in
  `test_daylight`. Renders in `~/limn-shot/sky-state/`.

**The half-sky camera as a source (contract, nothing to change in skystate):** write Redis `di.sky.obs.camera` =
`{"at": epoch s, "q": {"cover": [v, sigma], "deck": [...], "high": [...], "sun": [...], "dark": [...], "haze": [...]},
"notes": {...}}` with an expiry (`SET ... EX 600`), or `skystate.observe('camera', q, ttl)` from Python. Names outside
`quantities` are ignored (add them there first: e.g. `zenith_rgb`, `stars`). Its staleness is `stale_other` (900 s)
unless added to `stale`. A good camera deserves sigma ~0.1 for cover/sun by day.
Not done: drawing cloud drift by the wind (`air.wind_low`/`wind_high` are there), the haze band from an inversion, a
trend view (`trend.hours`/`seen`), alerts in the sky view.
