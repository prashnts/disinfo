import json
import time

from discore.data_structures import FrameState
from disinfo.data_structures import AppBaseModel
from disinfo.drat.app_states import PubSubStateManager, PubSubMessage
from disinfo.redis import db

from .tasks import TABLE_KEY, RADIUS_KEY, radius_km

VIEW_KEY = 'di.aviator.view'     # map, sky or solar on every screen, from the web page; their config's otherwise
VIEWS = ['map', 'sky', 'solar']


class AviatorState(AppBaseModel):
    now: float = 0
    planes: dict[str, dict] = {}
    focus: str | None = None
    watched: list[str] = []
    overhead: list[str] = []        # of the watched, the ones passing overhead: they get a card
    queues: dict[str, list[str]] = {}
    radius: float = radius_km

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
    map_up: dict[str, float] = {}       # screen -> the bearing up on its map, from the web page; until a restart

class OpenedStateManager(PubSubStateManager[OpenedState]):
    # Tapping a plane on the radar opens its card, tapping the card closes it. The web page sets the radius.
    model = OpenedState
    channels = ('di.pubsub.remote',)
    keep_open = 90

    def initial_state(self) -> OpenedState:
        return OpenedState(view=(db.get(VIEW_KEY) or b'').decode() or None)

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
            case 'aviator.map_up':
                self.state.map_up[data.payload['screen']] = float(data.payload['deg']) % 360
            case 'aviator.radius':
                # The poller reads it, every renderer gets it back with the table.
                db.set(RADIUS_KEY, float(data.payload['km']))

    def get_state(self, fs: FrameState | None = None) -> OpenedState:
        now = time.time()
        self.state.opened = {h: t for h, t in self.state.opened.items() if now - t < self.keep_open}
        return self.state
