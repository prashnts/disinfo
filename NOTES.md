# Notes

Running notes: the state of things, findings, decisions. The hand-off on top is the current state.

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
