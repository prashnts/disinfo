import json
import time

from discore.data_structures import FrameState
from disinfo.data_structures import AppBaseModel
from disinfo.drat.app_states import PubSubStateManager, PubSubMessage
from disinfo.redis import db

from .tasks import TABLE_KEY, RADIUS_KEY, MAX_ALT_KEY, TRAIL_KEY, radius_km, trail_s

VIEW_KEY = 'di.aviator.view'     # map, sky or solar pressed on the web page: {view, at}, for VIEW_HOLD
VIEWS_OFF_KEY = 'di.aviator.views_off'  # the views unchecked: out of the turns, a JSON list
MAP_UP_KEY = 'di.aviator.map_up'  # screen -> bearing, a JSON dict
ZOOM_KEY = 'di.aviator.zoom'      # the same, the zoom
LIGHT_KEY = 'di.aviator.light'    # the radar in light mode on every screen, '1' or '0'
LAYERS_KEY = 'di.aviator.layers'  # the map's layers switched off: a JSON list
HORIZON_KEY = 'di.aviator.horizon'  # where the sky view's horizon rests, of the height from the top
EYE_KEY = 'di.aviator.eye'          # the sky view seen from floors under (or over) the window
VIEWS = ['map', 'sky', 'solar']
DEMO_S = 132                       # s: the sky view's demo, once around
SKY_HOLD = 300                     # s the sky view stays where the web page turned it
VIEW_HOLD = 3600                   # s a view pressed stays, then the checked ones take turns again
VIEW_TURN = 1200                   # s each checked view has, in turn, over the day


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
    view: str | None = None             # pressed on the web page, at view_at; kept in redis
    view_at: float = 0
    views_off: list[str] = []           # unchecked: out of the turns; kept in redis
    off: list[str] = []                 # the map's layers switched off, from the web page; kept in redis
    light: bool = False                 # the map's light mode, from the web page; kept in redis
    map_up: dict[str, float] = {}       # screen ('*': all) -> the bearing up on its map, from the web page; kept in redis
    zoom: dict[str, float] = {}         # screen ('*': all) -> its map's zoom, the same
    demo: float | None = None           # when the sky view's demo started, from the web page
    sky: dict = {}                      # the sky view turned or zoomed from the web page: yaw, fov, at
    horizon: float | None = None        # the sky view's horizon from the web page (None: its own); kept in redis
    floors: float = 0                   # the sky view from that many floors up (under 0: down) from the window; the same

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
        try:
            pressed = json.loads(db.get(VIEW_KEY) or '{}')
        except ValueError:
            pressed = {}
        return OpenedState(view=pressed.get('view'), view_at=pressed.get('at', 0), views_off=read_list(VIEWS_OFF_KEY), map_up=read_dict(MAP_UP_KEY), zoom=read_dict(ZOOM_KEY), light=db.get(LIGHT_KEY) == b'1', off=read_list(LAYERS_KEY),
                           horizon=float(db.get(HORIZON_KEY) or 0) or None, floors=float(db.get(EYE_KEY) or 0))

    def process_message(self, channel: str, data: PubSubMessage):
        match data.action:
            case 'aviator.open':
                self.state.opened = {data.payload['hex']: time.time()}
            case 'aviator.close':
                self.state.opened.pop(data.payload['hex'], None)
            case 'aviator.view':
                # The one asked for (checked again), or the next (the displays' button), for VIEW_HOLD.
                current = self.state.view or 'map'
                self.pressed((data.payload or {}).get('view') or VIEWS[(VIEWS.index(current) + 1) % len(VIEWS) if current in VIEWS else 0])
            case 'aviator.views':
                # A checkbox: in the turns or out. Out, its press goes too.
                view, on = data.payload['view'], bool(data.payload['on'])
                self.state.views_off = [v for v in self.state.views_off if v != view] + ([] if on else [view])
                db.set(VIEWS_OFF_KEY, json.dumps(self.state.views_off))
                if not on and self.state.view == view:
                    self.pressed(None)
            case 'aviator.demo':
                # On the sky view (not kept), or off again.
                on = self.state.demo is None or time.time() - self.state.demo > DEMO_S
                self.state.demo = time.time() if on else None
                if on:
                    self.state.view, self.state.view_at = 'sky', time.time()
            case 'aviator.sky':
                # Turned or zoomed for a while (on the sky view, not kept), or back to its own.
                p = {k: float(v) for k, v in (data.payload or {}).items() if k in ('yaw', 'fov') and v is not None}
                self.state.sky = {**self.state.sky, **p, 'at': time.time()} if p else {}
                if p:
                    self.state.view, self.state.view_at = 'sky', time.time()
            case 'aviator.horizon':
                h = (data.payload or {}).get('h')
                self.state.horizon = min(max(float(h), 0.3), 0.85) if h is not None else None
                db.set(HORIZON_KEY, self.state.horizon or '')
            case 'aviator.eye':
                self.state.floors = min(max(float((data.payload or {}).get('floors') or 0), -12), 3)
                db.set(EYE_KEY, self.state.floors)
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

    def pressed(self, view: str | None):
        self.state.view, self.state.view_at = view, time.time()
        if view:
            self.state.views_off = [v for v in self.state.views_off if v != view]
            db.set(VIEWS_OFF_KEY, json.dumps(self.state.views_off))
        db.set(VIEW_KEY, json.dumps({'view': view, 'at': self.state.view_at}))

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
