import json
import time

from discore.data_structures import FrameState
from disinfo.data_structures import AppBaseModel
from disinfo.drat.app_states import PubSubStateManager, PubSubMessage
from disinfo.redis import db

from .tasks import TABLE_KEY, RADIUS_KEY, MAX_ALT_KEY, TRAIL_KEY, radius_km, trail_s

VIEW_KEY = 'di.aviator.view'     # map, sky or solar on every screen, from the web page; their config's otherwise
MAP_UP_KEY = 'di.aviator.map_up'  # screen -> bearing, a JSON dict
ZOOM_KEY = 'di.aviator.zoom'      # the same, the zoom
LIGHT_KEY = 'di.aviator.light'    # the radar in light mode on every screen, '1' or '0'
LAYERS_KEY = 'di.aviator.layers'  # the map's layers switched off: a JSON list
VIEWS = ['map', 'sky', 'solar']


class AviatorState(AppBaseModel):
    now: float = 0
    planes: dict[str, dict] = {}
    focus: str | None = None
    watched: list[str] = []
    overhead: list[str] = []        # of the watched, the ones passing overhead: they get a card
    queues: dict[str, list[str]] = {}
    radius: float = radius_km
    trail: float = trail_s          # s of trail the radar shows, the watched planes show all

def read_state() -> AviatorState:
    try:
        return AviatorState(**json.loads(db.get(TABLE_KEY) or '{}'))
    except ValueError:
        return AviatorState()

class ADSBxStateManager(PubSubStateManager[AviatorState]):
    # The poller (data service) keeps the table in redis and says when it changed.
    model = AviatorState
    channels = ('di.pubsub.aviator',)

    def initial_state(self) -> AviatorState:
        return read_state()

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'update':
            self.state = read_state()


class OpenedState(AppBaseModel):
    opened: dict[str, float] = {}       # hex -> when it was tapped
    view: str | None = None
    off: list[str] = []                 # the map's layers switched off, from the web page; kept in redis
    light: bool = False                 # the map's light mode, from the web page; kept in redis
    map_up: dict[str, float] = {}       # screen ('*': all) -> the bearing up on its map, from the web page; kept in redis
    zoom: dict[str, float] = {}         # screen ('*': all) -> its map's zoom, the same

def read_dict(key: str) -> dict[str, float]:
    try:
        return {k: float(v) for k, v in json.loads(db.get(key) or '{}').items()}
    except (ValueError, AttributeError):
        return {}

def read_list(key: str) -> list[str]:
    try:
        return [str(v) for v in json.loads(db.get(key) or '[]')]
    except (ValueError, TypeError):
        return []

class OpenedStateManager(PubSubStateManager[OpenedState]):
    # Tapping a plane on the radar opens its card, tapping the card closes it. The web page sets the radius.
    model = OpenedState
    channels = ('di.pubsub.remote',)
    keep_open = 90

    def initial_state(self) -> OpenedState:
        return OpenedState(view=(db.get(VIEW_KEY) or b'').decode() or None, map_up=read_dict(MAP_UP_KEY), zoom=read_dict(ZOOM_KEY), light=db.get(LIGHT_KEY) == b'1', off=read_list(LAYERS_KEY))

    def process_message(self, channel: str, data: PubSubMessage):
        match data.action:
            case 'aviator.open':
                self.state.opened = {data.payload['hex']: time.time()}
            case 'aviator.close':
                self.state.opened.pop(data.payload['hex'], None)
            case 'aviator.view':
                # The one asked for, or the next (the displays' button).
                current = self.state.view or 'map'
                self.state.view = (data.payload or {}).get('view') or VIEWS[(VIEWS.index(current) + 1) % len(VIEWS) if current in VIEWS else 0]
                db.set(VIEW_KEY, self.state.view)
            case 'aviator.light':
                # The one asked for, or the other.
                self.state.light = bool(data.payload['on']) if 'on' in (data.payload or {}) else not self.state.light
                db.set(LIGHT_KEY, '1' if self.state.light else '0')
            case 'aviator.layer':
                layer, on = data.payload['layer'], bool(data.payload['on'])
                self.state.off = [l for l in self.state.off if l != layer] + ([] if on else [layer])
                db.set(LAYERS_KEY, json.dumps(self.state.off))
            case 'aviator.map_up':
                self.set_all(self.state.map_up, MAP_UP_KEY, data.payload['screen'], float(data.payload['deg']) % 360)
            case 'aviator.zoom':
                self.set_all(self.state.zoom, ZOOM_KEY, data.payload['screen'], max(float(data.payload['zoom']), 0.05))
            case 'aviator.radius':
                # The poller reads it, every renderer gets it back with the table.
                db.set(RADIUS_KEY, float(data.payload['km']))
            case 'aviator.trail':
                db.set(TRAIL_KEY, float(data.payload['s']))
            case 'aviator.max_alt':
                db.set(MAX_ALT_KEY, float(data.payload['m']))

    @staticmethod
    def set_all(d: dict, key: str, screen: str, v: float):
        # 'all' is every screen, '*': the ones set after it keep their own.
        if screen == 'all':
            d.clear()
            screen = '*'
        d[screen] = v
        db.set(key, json.dumps(d))

    def get_state(self, fs: FrameState | None = None) -> OpenedState:
        now = time.time()
        self.state.opened = {h: t for h, t in self.state.opened.items() if now - t < self.keep_open}
        return self.state
