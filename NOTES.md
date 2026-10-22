# Notes

Running notes: the state of things, findings, decisions. The hand-off on top is the current state.

## Hand-off: layouts, the grid and screens that move (2026-10-22)

Uncommitted. CHANGELOG (Unreleased, Added: Screen layouts, Grid layout; Performance) has the details and numbers.

### Grid (`discore.layouts.grid`)

- `grid(elements, nrows, ncols, gap, anchor, masonry, width, height)`, next to `hstack`/`vstack`. One of
  `nrows`/`ncols` given, the other follows from the count; both, the overflow takes rows; none, about square.
- Rows: each column as wide as its widest, each row as tall as its tallest, `anchor` places an element in its
  cell. `masonry=True`: no rows, each element under the shortest column (columns as wide as their widest).
- `width`/`height`: the columns (rows) share it evenly; growers (`Grow`, a `Box` with `grow`) fill their cell;
  the rest is clipped, touch targets too (`_clipped`). Without them it's the natural size.
- It's a function returning a `Frame`, not a `Box` like `Flex`: a grid can't be a grower inside a flex row yet.
- Users: the entry's buttons (`screens/entry.py` `controls`: masonry, 3 columns, fewer till it fits the width),
  the flex demo's grid tab (`apps/flex_demo.py`: shapes, rows vs masonry, width, anchors). Tests: `test_grid_*`.
- Gotcha met on the way: a `div` around a `Box` (`DivBox`) puts its content top left whatever the `anchor`
  (deliberate, its comment says). The entry's buttons render their content to a `Frame` first to get it centered.

### Screens that move (`discore.screen`)

The idea: the items of a screen (stacks, time, date, buttons) move between a few allowed places, away from what
has to stay in sight and from the spots they've lit longest (burn-in), on average on their designed side.

- **Setup, in code, like a widget**: `Screen(name, choices, compose, ..., covering, stacked)`. `choices` is a list
  of lists of `Option`s, an arrangement takes one option of each list. An `Option` puts items on `Spot`s
  (`anchor`, `dx`/`dy`, `jitter` rolled inwards at each relayout), with a `penalty` and an optional `when`
  (offered only while the composer says that condition holds, e.g. `'calm'`). The first option of the first list
  is the designated layout (`common.across` reads its side).
- **Each frame**: `layout = screen.arrange(fs, items, focus, when, relayout)` with the drawn item frames (`None`:
  not shown, ignored); then `layout.place(item, frame, dest, frost)` and `layout.clear` (the largest box the
  items leave free; the radar keeps the followed plane in it). The composer reads `screen.spot(item)` before
  drawing for what depends on the side (the stack's `align`, the time's `align`).
- **Scoring**, once a second, every allowed arrangement, on a 4 px grid (`cell`); about 0-1 each, weighed by the
  module constants:
  - focus (`focus_weight` 3): the share of the `Focus` under the `covering` items. `Focus.disk(x, y, r, weight)`,
    each disk weighs its weight in all. The focus can be a function of the arrangement's spots (the solar clock
    moves with the side stack, so each arrangement gets its own).
  - overlap (2): per item, its share under the others; `stacked` items may share a corner (the two stacks did
    in the original layouts). Masks are on/off: a frosted card counts whole (its alpha hid overlaps at first).
  - off screen (2), the options' penalties.
  - heat (1): per item, how long its cells have been lit, against the most worn cell or an hour at least.
    Fades by half over 12 h (`heat_half_life`), saved every 5 min in Redis `di.screen.heat.<screen>`
    (`common.heat_store`).
- **When it moves**: on `relayout` (the composer passes `motion(fs)`: someone came), every `every_s` (15 min,
  jitter re-rolled too), when the current option isn't allowed any more (calm ended), or any time the current
  arrangement is worse than the best by `anytime_margin` (0.3) for `anytime_s` (30 s: cards cycle and slide; it
  swapped sides every few seconds on the desk without it). A `Focus(follows=True)` (the planes: drawn for the current
  arrangement, the radar re-frames after a move) counts only on relayout, else it ping-pongs. On relayout the best wins
  if better by `switch_margin` (0.05). Items slide from where they were (`move_s` 0.8, cubic in-out).

### The screens

- `compositor.big_screen(name, side, time_side=None, compose=None)`: the salon (`disalon`, left), the desk
  (`distudy`, right) and the T4-S3 (`di_pcstate`, left, `compose_display_frame`, no date). Choices: side stack
  `m<side>` with the time and date in a top corner (one list: the time across from the stack is free, on the
  stack's side +0.3, the stack on its other side +0.5, the bottom corners +0.2 and only `calm`), and the bottom
  stack `bl`. `time_side='left'|'right'` keeps the time on that side. `compositor.DATE_BESIDE` (the desk): the date may go in the
  time's row (item `timedate`, +1.2: over the burn-in heat, which favors one item less), chosen when its own spot below the time would be under the cards. `covering` and `stacked`: the two stacks.
- The entry, `screens/entry.py` `screen`: the side stack `tl` (`tr` +0.5), the time across (+0.3 on the stack's
  side), the bottom stack and the buttons fixed (`bl`, `br`: hands expect them). Not dimmed-asleep aware: it's
  dark then anyway (`compositor.compose_entry`).
- `compositor.SCREENS` and `screen_for(name)` (a left `big_screen` for any other name); `compose()` goes through
  `screen.compose`, except `picowpanel` (`compose_small_frame`, untouched).
- `calm` = nobody there or a plane's card on top (the bottom stack: the time at the bottom is then fine).
- The solar clock: where it was designed (salon/desk cx 75, display w/2+22, entry w/2+60), mirrored while the side
  stack is on its other side (`common.across`). Its small random offset (`p_stack_offset`) is the last left.
- Plane focus: `aviator.app.plane_marks(fs)` reads the last radar/sky frame's touch targets (`aviator.open`):
  followed 8, numbered 4, others 1 (protect as many as possible, those most).

### Checking

- Tests: `libs/discore/tests/test_core.py` (`test_screen_*`, `test_grid_*`), `tests/test_screens.py`.
- **A screen over days**: `DI_CONFIG_PATH=.config.json python -m disinfo.sim_layout 72 8 2>&1 >/dev/null`
  (hours, asleep hours a day): its real items and focus, a fake clock, the time per side and corner and the
  moves. Last run, 3 days: a move every ~40 min; side stack off its side 22 % salon, 42 % desk, 24 % display,
  23 % entry; time and date in all four corners while asleep. The first day moves more (no history yet).
- To see why an arrangement wins, print `screen.costs` (arrangement -> cost) after a compose, and the parts by hand
  (the `_cost` body; a script did that per component: penalty, overlap per item, off, focus).
- Bench as before (`disinfo.bench --at "2026-10-19 17:00"`): `arrange` 0.3 ms a frame, 0.7 ms with the scoring.
- Test renders save heat into the PC's Redis: `redis-cli --scan --pattern 'di.screen.heat.*' | xargs -r redis-cli del`.

### Open, ideas

- The weights and margins are tuned on simulations only; watch the real panels (moves too often? the side too
  long on the other side?). Penalties are the knob for "on average on the designated side".
- `motion(fs)` is stateful: call it once a frame (the composers do, and pass it as `relayout`).
- Costs use the items' frames of the scoring second and no jitter; a stack that scrolls a card under the time is
  caught by `anytime_margin` if it stays there 30 s.
- Heat counts the items only (static, bright), not the background (the solar clock's dial and the sky are
  lit too, and the clock doesn't move except across).
- The solar clock could follow `layout.clear` (centered in the free space) instead of two fixed places; it'd need
  easing so it doesn't jump when cards resize.
- `picowpanel` has no screen. The entry's buttons never move (a jitter could, small).
- Name clash: `web/server.py` also has a `Screen` (the server's frame store), unrelated.
- The grid could become a `Box` (grow/shrink inside flex) and a screen could use it for a cards area.

## Hand-off: the client-server model (2026-10-19)

Nothing below is committed yet: disinfo since `024a6f0` (flex), esp-displays since `02d7a74`. CHANGELOG
(Unreleased) has each change with numbers; esp-displays has its own CHANGELOG and NOTES.md (firmware side).

### How a frame gets to a display

- **Renderer** (`renderers/background.py`): `compositor.compose(fs)` -> a `Frame` (image + touch targets).
  `publish_frame`: raw RGB + zlib on Redis `di.frames.raw` when it changed (and every 1 s, for a server that just
  started); the touch targets and `awake` (the screen's presence sensors, `should_turn_on_display`) as JSON on
  `di.pubsub.targets`, on change. `di.frames.raw` is outside `di.pubsub.*` on purpose: `PubSubManager` json-decodes
  everything there and a binary message would kill its thread.
- **Server** (`web/server.py`): a `Screen` per screen: the newest frame (`seq`, `rgbz`), each encoding made once per
  frame, the 8 before it (`prev`) for regions. One server process serves every screen.
  - `/ws2/<screen>?fmt=rgbz|png|rgb565z`: pushed. Whole frames, then the regions that changed since the frame the
    client has (16x16 tiles merged into boxes, all in one message; whole again past 50% or 8 frames behind). Format
    in `transport.py`'s docstring. Text out: `{"display": {"on"}}` (on change, and first), `{"acts"}`,
    `{"alive"}` every 2 s, `{"time"}` first (displays without NTP set their clock). Text in: `{"touch": [x, y, "down|move|up"]}` (frame px), `{"resync": 1}`, telemetry
    `{"_node", "telemetry": "<json string>"}` (also sent to Home Assistant, below).
  - `/ws/<screen>`: v1, a JSON + base64 PNG per request; the HUB75 panels still on it. `/png/<screen>` (snapshot),
    `/display/<screen>/stream.mjpg|buttons|press` (esp-displays' MJPEG fallback).
- **Clients**: the web page (`web/index.html`: canvases, PNG regions, touch), the HUB75 client
  (`clients/websocket-rpi-matrix`, `"protocol": "v2"`, `frames.py` puts frames together), esp-displays' viewer
  (`ws2.c`: RGB565 regions composed and redrawn alone, touches, its board's sensors as telemetry).

### Touch

- `discore`: `Frame.targets` (`Target`: a box in the frame's px, an action, a payload), carried by the layouts:
  stacks, flex, div, `composite_at`, `place_at`, crops and scales, scrollers (the ones in view), a transition's once
  it's settled (none while it moves). `discore.button`: a styled div, touchable all over, with a pressed style.
- Server `touched()`: the topmost target under a down is held (published on `di.pubsub.touch`: the renderer's
  `TouchStateManager` draws it pressed), a move off it lets go, an up on it does its action: `ha.call` (a Home
  Assistant service, called from the server: one server, many renderers) or else a remote action
  (`di.pubsub.remote`, as the web page's buttons).
- Clients report raw touches only; buttons are drawn and placed by disinfo, and can change any time.

### Sensors and presence

- An ESP display's sensors come as telemetry over `/ws2`; `utils/ha_states.py` sets them as Home Assistant states
  (REST, `/api/states`): `sensor.<screen>_<reading>`, or the ids a display had (`KNOWN`: the Guition keeps
  ESPHome's `sensor.guiton_*`, so their history and statistics go on). The BME680's -1 °C offset is applied there.
- The backlight: `{"display": {"on": false}}` when the screen's presence sensors say no one's there; a display
  follows it only with its config `presence` (the Guition yes, the T4-S3 no); a touch lights it 30 s.

### Screens and devices

| Screen | Size | Where | Client |
|---|---|---|---|
| distudy | 128x128 | desk Pi `pi@10.0.1.157` (HUB75) | prod `/ws/distudy`, v1 |
| disalon | 128x192 | salon Pi `pi@10.0.1.91` (HUB75) | prod `/ws2/disalon`, v2 |
| di_pcstate | 200x150 | T4-S3 on this PC's USB (192.168.7.1) | MJPEG or `/ws2` |
| dientry | 400x240, 2x | Guition 5" (10.0.1.246, reserved), T4-S3's "Entry" (as big as fits: 1.5x) | `/ws2` |

`screens/entry.py` is `dientry`: the solar clock behind, the flip clock, weather, moon and music (the 128 px
cards at 2x, `big()`), the scenes lumos/dodo/soir/nuit and the mirror's light along the bottom. The music card
shows any player that's playing, with play/pause and next.

Test source on this PC (until the server has `dientry`): `~/.local/state/disinfo-entry/run.sh` starts the renderer
and a server on :4201 (`.config-dientry.json`, git-ignored: a copy of the pcstate config, name/size/presence set),
logs next to it. The PC's Redis is its own (localhost).

### Deploying dientry on the server

1. Deploy this code (renderer and server together: the renderer no longer publishes PNGs on `di.pubsub.frames`).
2. In `/home/noop/run/disinfo`, the entry config from the study's, the rest unchanged:
   `python3 -c "import json; c = json.load(open('.config-study.json')); c.update(name='dientry', width=400, height=240, presence_sensors=['binary_sensor.radar_entree_presence']); json.dump(c, open('.config-entry.json', 'w'), indent=2)"`
3. `config/di2_entry.conf` into supervisor's conf.d, `supervisorctl reread && supervisorctl update`, then
   `supervisorctl restart diserver di2pcstate_server didataservice di2study di2salon di2pcstate`: `update` only starts the new program, the server
   kept its old code (2026-10-20: `/ws2` frames but no touches, no `{"time"}`/`{"display"}`, no sensors to HA).
   Check: the first message on `wss://disinfo.nb.malow.im/ws2/dientry` is `{"time": ...}`.
4. The display to it: `cd ~/repo/esp-displays && uv run displays.py src Entry https://disinfo.nb.malow.im/display/dientry --host http://10.0.1.246`
   (or on the display: a tap along its top edge shows its controls; the source's name opens the sources).
   `https` becomes `wss://.../ws2/dientry` by itself.

### Checking and measuring

- Tests: `tests/test_transport.py` (the formats, regions, `/ws2` end to end, touch, telemetry, display on/off; the
  client's `frames.py` loaded by path), `libs/discore/tests` (layout, hashes, targets). CI: `docker.yml`.
- Benchmark: `DI_CONFIG_PATH=.config-pcstate.json .venv/bin/python -m disinfo.bench --size 200x150 --size 800x480
  --size 1280x720 --at "2026-10-19 17:00" --label "..." 2>&1 >/dev/null` (report on stderr, `bench.jsonl`). Use
  `--at`: the screen's content changes through the day (evening frames are much lighter), and that moves both
  compose and transport. Home Assistant's data is still live. CHANGELOG's Performance table has each step.

### Gotchas

- `utils/hass.py` printed the HA token on connect (fixed). Still drop the app's stdout in logs; in zsh,
  `2>&1 >/dev/null | x` tees stdout into the pipe anyway (MULTIOS): use `bash -c`.
- `pkill -f <pattern>` matches the shell running it when the pattern is in its own command line: anchor it
  (`'^\.venv/bin/python -m ...'`).
- `draw_loop`'s painters are daemon threads again (`1a9759e` made them not: two Ctrl+C to stop).
- Scoped instances (scrollers, transitions) are told apart by their arguments: two unnamed equal ones share state.
  `uname()` names by call site (`sys._getframe`); in loops give names (`uname = lambda x: f'{x}_{id}'`).
- A frame's hash says what it shows: a frame redrawn every frame from the same inputs needs a derived hash, or the
  transitions around it restart every frame (tokens are only for one-off or cached frames).

### Left to do, as planned

- **2. I/O out of the render path.** `timer_app` scans Redis every frame, state managers read per frame; the
  70-90 ms worst frames at 720p are likely that. Background tasks keep state in memory, drawing only reads.
- **5. A declarative frame spec and a render step**, in `discore` core only (consumers won't tag). The hashes are
  meant for it. Known holes: transitions hash as themselves, not their progress (`Widget` relies on that: add a
  render key beside the identity hash); `composite_at`'s hash leaves out the destination (its behind + frost path
  caches a blur on it: stale if ever used, unused now).
- **6. Frost cached** by the spec hash of the layers under it (they move: news); never at a lower resolution.
- **Layers in `/ws2`**: the smooth background (solar) at the panel's own resolution, the pixel-art layer at 2x on
  top: sharper, and only the layer that changed is sent.
- **The device's own state to disinfo**: Wi-Fi (RSSI, IP: `sensor.guiton_dientry_ip_address` waits for it),
  uptime, brightness, over telemetry; and a way back (server -> device settings beyond `display`).
- Display side (esp-displays NOTES): internal RAM on the S3 boards is the thing to watch (LVGL now in PSRAM,
  `/api/status` `heap`/`heap_min`);  the UI's 30 ms gate (~33 fps) could go for region-only redraws; the Guition
  has one framebuffer (rows may tear); Wi-Fi OTA to the Guition timed out once (serial is sure).
