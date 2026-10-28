import json
import time

from discore.data_structures import FrameState
from disinfo.data_structures import AppBaseModel
from disinfo.drat.app_states import PubSubStateManager, PubSubMessage
from disinfo.redis import db

from .tasks import TABLE_KEY, RADIUS_KEY, MAX_ALT_KEY, TRAIL_KEY, radius_km, trail_s

# The web page's settings, by screen ('*': all, a screen's own over it), JSON dicts:
VIEW_KEY = 'di.aviator.view'     # map, sky or solar pressed: [view, at], for VIEW_HOLD
VIEWS_OFF_KEY = 'di.aviator.views_off'  # the views unchecked: out of the turns
MAP_UP_KEY = 'di.aviator.map_up'  # the bearing up on its map
ZOOM_KEY = 'di.aviator.zoom'      # the same, the zoom
LIGHT_KEY = 'di.aviator.light'    # the radar in light mode
LAYERS_KEY = 'di.aviator.layers'  # the map's layers switched off
HORIZON_KEY = 'di.aviator.horizon'  # where the sky view's horizon rests, of the height from the top (None: its own)
EYE_KEY = 'di.aviator.eye'          # the sky view seen from floors under (or over) the window
LIVE_KEY = 'di.aviator.live'        # screen -> what its renderer shows now, for the web page: {view, yaw, fov, tilt, at}
VIEWS = ['map', 'sky', 'solar']
STORM = 'storm'                    # in views_off: no sky view brought by a storm
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
    # From the web page, by screen ('*': all): read with of(). Kept in redis but the demo and the sky held.
    view: dict[str, list] = {}          # [the view pressed, at]
    views_off: dict[str, list] = {}     # unchecked: out of the turns
    off: dict[str, list] = {}           # the map's layers switched off
    light: dict[str, bool] = {}         # the map's light mode
    map_up: dict[str, float] = {}       # the bearing up on its map
    zoom: dict[str, float] = {}         # its map's zoom
    demo: dict[str, list] = {}          # [when the sky view's demo started, the scene held (None: once around)]
    sky: dict[str, dict] = {}           # the sky view turned or zoomed: yaw, fov, at
    horizon: dict[str, float | None] = {}   # the sky view's horizon (None: its own)
    floors: dict[str, float] = {}       # the sky view from that many floors up (under 0: down) from the window

    def of(self, name: str, fs: FrameState | None):
        d = getattr(self, name)
        return d.get(fs and fs.config.name, d.get('*', unset[name]))

unset = {'view': [None, 0], 'views_off': [], 'off': [], 'light': False, 'demo': [None, None], 'sky': {}, 'horizon': None, 'floors': 0}

def read_dict(key: str) -> dict[str, float]:
    try:
        return {k: float(v) for k, v in json.loads(db.get(key) or '{}').items()}
    except (ValueError, AttributeError):
        return {}

def read_scoped(key: str) -> dict:
    # By screen; a value from before (one for all) is '*'.
    try:
        v = json.loads(db.get(key) or 'null')
    except ValueError:
        return {}
    if isinstance(v, dict) and 'at' in v:
        return {'*': [v.get('view'), v['at']]}
    return v if isinstance(v, dict) else {} if v is None else {'*': v}

class OpenedStateManager(PubSubStateManager[OpenedState]):
    # Tapping a plane on the radar opens its card, tapping the card closes it. The web page's settings, by screen:
    # payload's screen, 'all' (or none) for every one (their own go).
    model = OpenedState
    channels = ('di.pubsub.remote',)
    keep_open = 90
    kept = {'view': VIEW_KEY, 'views_off': VIEWS_OFF_KEY, 'map_up': MAP_UP_KEY, 'zoom': ZOOM_KEY, 'light': LIGHT_KEY,
            'off': LAYERS_KEY, 'horizon': HORIZON_KEY, 'floors': EYE_KEY}

    def initial_state(self) -> OpenedState:
        return OpenedState(**{k: read_scoped(key) for k, key in self.kept.items()})

    def process_message(self, channel: str, data: PubSubMessage):
        p, now = data.payload or {}, time.time()
        screen = p.get('screen') or 'all'
        mine = lambda name: self.mine(name, screen)
        match data.action:
            case 'aviator.open':
                self.state.opened = {p['hex']: now}
            case 'aviator.close':
                self.state.opened.pop(p['hex'], None)
            case 'aviator.view':
                # The one asked for (checked again), or the next (the displays' button), for VIEW_HOLD.
                current = mine('view')[0] or 'map'
                self.pressed(screen, p.get('view') or VIEWS[(VIEWS.index(current) + 1) % len(VIEWS) if current in VIEWS else 0])
            case 'aviator.views':
                # A checkbox: in the turns or out. Out, its press goes too.
                view, on = p['view'], bool(p['on'])
                self.put('views_off', screen, [v for v in mine('views_off') if v != view] + ([] if on else [view]))
                if not on and mine('view')[0] == view:
                    self.pressed(screen, None)
            case 'aviator.demo':
                # On the sky view (not kept), once around or a scene held SKY_HOLD; or off again.
                scene = p.get('scene')
                started, was = mine('demo')
                on = scene != was or started is None or now - started > (SKY_HOLD if was else DEMO_S)
                self.put('demo', screen, [now, scene] if on else [None, None])
                if on:
                    self.put('view', screen, ['sky', now])
            case 'aviator.sky':
                # Turned or zoomed for a while (on the sky view, not kept), or back to its own.
                turned = {k: float(v) for k, v in p.items() if k in ('yaw', 'fov') and v is not None}
                held = mine('sky') if now - mine('sky').get('at', 0) < SKY_HOLD else {}
                self.put('sky', screen, {**held, **turned, 'at': now} if turned else {})
                if turned:
                    self.put('view', screen, ['sky', now])
            case 'aviator.horizon':
                h = p.get('h')
                self.put('horizon', screen, min(max(float(h), 0.3), 0.85) if h is not None else None)
            case 'aviator.eye':
                self.put('floors', screen, min(max(float(p.get('floors') or 0), -12), 3))
            case 'aviator.light':
                # The one asked for, or the other.
                self.put('light', screen, bool(p['on']) if 'on' in p else not mine('light'))
            case 'aviator.layer':
                layer, on = p['layer'], bool(p['on'])
                self.put('off', screen, [l for l in mine('off') if l != layer] + ([] if on else [layer]))
            case 'aviator.map_up':
                self.put('map_up', screen, float(p['deg']) % 360)
            case 'aviator.zoom':
                self.put('zoom', screen, max(float(p['zoom']), 0.05))
            case 'aviator.radius':
                # The poller reads it, every renderer gets it back with the table.
                db.set(RADIUS_KEY, float(p['km']))
            case 'aviator.trail':
                db.set(TRAIL_KEY, float(p['s']))
            case 'aviator.max_alt':
                db.set(MAX_ALT_KEY, float(p['m']))

    def pressed(self, screen: str, view: str | None):
        self.put('view', screen, [view, time.time()])
        if view:
            self.put('views_off', screen, [v for v in self.mine('views_off', screen) if v != view])

    def mine(self, name: str, screen: str):
        d = getattr(self.state, name)
        return d.get(screen, d.get('*', unset[name]))

    def put(self, name: str, screen: str, v):
        self.set_all(getattr(self.state, name), self.kept.get(name), screen, v)

    @staticmethod
    def set_all(d: dict, key: str | None, screen: str, v):
        # 'all' is every screen, '*': the ones set after it keep their own.
        if screen == 'all':
            d.clear()
            screen = '*'
        d[screen] = v
        if key:
            db.set(key, json.dumps(d))

    def get_state(self, fs: FrameState | None = None) -> OpenedState:
        now = time.time()
        self.state.opened = {h: t for h, t in self.state.opened.items() if now - t < self.keep_open}
        return self.state


live_every = 1          # s between two notes of what a screen shows
_live = {}              # screen -> (when noted, what)

def live(fs: FrameState, **kw):
    # What the screen shows now (its view, where the sky looks): the web page reads it back.
    at, was = _live.get(fs.config.name, (0, {}))
    shows = {**was, **kw}
    if time.time() - at > live_every:
        db.hset(LIVE_KEY, fs.config.name, json.dumps({**shows, 'at': round(time.time(), 1)}))
        at = time.time()
    _live[fs.config.name] = at, shows
