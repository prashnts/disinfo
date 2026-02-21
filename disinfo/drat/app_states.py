'''
State managers hold runtime-persistent states.

PubSubStateManager uses redis pubsub for inter-process communication.
'''
import json

from typing import Generic, TypeVar, Callable
from scipy.interpolate import interp1d

from disinfo.config import app_config
from disinfo.redis import db
from disinfo.data_structures import FrameState, AppBaseModel, UniqInstance

StateModel = TypeVar('StateModel')
class PubSubMessage(AppBaseModel):
    action: str
    payload: dict | None


class PubSubManager(metaclass=UniqInstance):
    def __init__(self):
        self.pubsub = db.pubsub()
        self.pubsub.psubscribe(**{'di.pubsub.*': self.handle_message})
        self.pubsub.run_in_thread(sleep_time=0.001, daemon=True)
        self.subscribers = {}

    def handle_message(self, message):
        if not message or message['type'] != 'pmessage':
            return

        channel_name = message['channel'].decode()
        try:
            data = json.loads(message['data'].decode())
            action = data['_action']
            del data['_action']
            payload = data
            msg = PubSubMessage(action=action, payload=payload)
        except KeyError:
            return

        for channels, callback in self.subscribers.values():
            if channel_name in channels:
                try:
                    callback(channel_name, msg)
                except Exception as e:
                    print(f'[PubSub] Error in callback: {e}')

    def attach(self, uid: str, channels: tuple[str], callback: Callable):
        if uid not in self.subscribers:
            self.subscribers[uid] = (channels, callback)
        return self

class StateManager(Generic[StateModel], metaclass=UniqInstance):
    model: StateModel

    def __init__(self):
        self.state = self.model()

    def get_state(self, fs: FrameState | None = None) -> StateModel:
        return self.state

class PubSubStateManager(Generic[StateModel], metaclass=UniqInstance):
    model: StateModel
    channels: tuple[str]

    def __init__(self):
        self.manager = PubSubManager().attach(self._uid(), self.channels, self.process_message)
        self.state = self.initial_state()

    def _uid(self) -> str:
        return self.__class__.__name__

    def initial_state(self) -> StateModel:
        return self.model()

    def process_message(self, channel: str, data: PubSubMessage):
        raise NotImplemented

    def get_state(self, fs: FrameState | None = None) -> StateModel:
        return self.state



class RuntimeState(AppBaseModel):
    x: int = 120
    y: int = 42

    # Simulate Motion
    motion_override: bool = app_config.devmode
    # Debug info
    show_debug: bool = False
    screen_capture: bool = False

    # Extras
    show_twentytwo: bool = False

class RuntimeStateManager(PubSubStateManager[RuntimeState]):
    model = RuntimeState
    channels = ('di.pubsub.remote',)

    def process_message(self, channel: str, data: PubSubMessage):
        match data.action:
            case 'up':
                self.state.y -= 1
            case 'down':
                self.state.y += 1
            case 'left':
                self.state.x -= 1
            case 'right':
                self.state.x += 1
            case 'motion_toggle':
                self.state.motion_override = not self.state.motion_override
            case 'show_debug':
                self.state.show_debug = not self.state.show_debug
            case 'screencap':
                self.state.screen_capture = not self.state.screen_capture
            case 'btn_twentytwo':
                self.state.show_twentytwo = not self.state.show_twentytwo

        self.state.x %= app_config.width
        self.state.y %= app_config.height


brightness_min: float = 10
brightness_max: float = 90
brightness_curve = [
    # LUX   BRIGHTNESS %
    [0,   10],
    [50,  10],
    [82,  40],
    [90,  50],
    [120, 75],
    [150, 80],
    [200, 90],
]
brightness_interpolator = interp1d(
    *zip(*brightness_curve),
    bounds_error=False,
    fill_value=(brightness_min, brightness_max),
)

class LightSensorState(AppBaseModel):
    lux: float = 100

    @property
    def brightness(self) -> int:
        return int(brightness_interpolator(self.lux))

class LightSensorStateManager(PubSubStateManager[LightSensorState]):
    model = LightSensorState
    channels = ('di.pubsub.lux',)

    def __init__(self, entity_id: str):
        self.entity_id = entity_id
        super().__init__()

    def _uid(self) -> str:
        return f'{self.__class__.__name__}.{self.entity_id}'

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action == 'update' and data.payload['entity_id'] == self.entity_id:
            self.state.lux = float(data.payload['new_state']['state'])
