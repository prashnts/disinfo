import json
import time
from typing import Literal, TypeVar
from typing_extensions import Annotated
from pydantic import ValidationError, Field, model_validator, RootModel

from disinfo.data_structures import AppBaseModel, FrameState
from disinfo.drat.app_states import PubSubMessage, PubSubManager, PubSubStateManager
from disinfo.utils.color import AppColor
from disinfo.redis import publish
from disinfo.config import app_config


TriggerType = TypeVar('TriggerType')


class EdgeTriggerState(RootModel[TriggerType]):
    root: TriggerType

    def read(self, key: str) -> TriggerType:
        if not hasattr(self, '_read_for'):
            self._read_for = []
        if key in self._read_for:
            return None
        if self.root:
            self._read_for.append(key)
        return self.root

class DitButtonState(AppBaseModel):
    pressed: EdgeTriggerState[bool] = EdgeTriggerState[bool](False)
    pressed_at: float = 0.0
    released_at: float = 0.0
    updated_at: float = 0.0

    pressed_for: list[str] = Field(default_factory=list)


class DiRemoteButtons(AppBaseModel):
    select: DitButtonState = DitButtonState()
    up: DitButtonState = DitButtonState()
    left: DitButtonState = DitButtonState()
    down: DitButtonState = DitButtonState()
    right: DitButtonState = DitButtonState()

class DiEncoderState(AppBaseModel):
    position: int = 0
    updated_at: float = 0.0

class DiRemoteState(AppBaseModel):
    buttons: DiRemoteButtons = DiRemoteButtons()
    encoder: DiEncoderState = DiEncoderState()
    updated_at: float = 0.0



class DiLightSensorState(AppBaseModel):
    color_hex: str = '#000000FF'
    color_temp: float = 0.0
    lux: float = 0.0
    proximity: int = 0
    gesture: EdgeTriggerState[str] = EdgeTriggerState[str]('--')
    updated_at: float = 0.0

    @property
    def color(self) -> AppColor:
        return AppColor(self.color_hex)

class DiUserState(AppBaseModel):
    motion: bool = False
    updated_at: float = 0.0

class DiTofState(AppBaseModel):
    distance_mm: list[int] = []
    masked_distance_mm: list[int] = []
    render: list[list[int]] = []
    grid: int = 7
    updated_at: float = 0.0


class DiTelemetryState(AppBaseModel):
    remote: DiRemoteState = DiRemoteState()
    light_sensor: DiLightSensorState = DiLightSensorState()
    user: DiUserState = DiUserState()
    tof: DiTofState = DiTofState()
    _v: Literal['dit'] = 'dit'
    _readers: set = set()

class TelemetryStateManager(PubSubStateManager[DiTelemetryState]):
    model = DiTelemetryState
    channels = ('di.pubsub.telemetry',)

    def process_message(self, channel: str, data: PubSubMessage):
        try:
            data = json.loads(data.payload['data'])

            next_state = DiTelemetryState(**data)
            if next_state.light_sensor.updated_at > self.state.light_sensor.updated_at:
                self.state.light_sensor = next_state.light_sensor
            
            if next_state.remote.updated_at > self.state.remote.updated_at:
                print("Updating remote telemetry,", next_state.remote)
                self.state.remote = next_state.remote
            
            if next_state.remote.encoder.updated_at > self.state.remote.encoder.updated_at:
                self.state.remote.encoder = next_state.remote.encoder

            if next_state.user.updated_at > self.state.user.updated_at:
                self.state.user = next_state.user
            
            if next_state.tof.updated_at > self.state.tof.updated_at:
                self.state.tof = next_state.tof
        except (json.JSONDecodeError, ValidationError) as e:
            print(f'Error processing telemetry message: {e}')
            pass

    def remote_reader(self, ctx: str, fs: FrameState, exclusive: bool = False):
        self.state._readers.add((ctx, exclusive))
        def _read_btn(button: str) -> bool | int:
            remote_state = self.get_state(fs).remote
            if button == 'encoder':
                return remote_state.encoder.position
            button = getattr(remote_state.buttons, button)
            return button.pressed.read(ctx)
        return _read_btn

def act(res, command, hash_):
    publish('di.pubsub.acts',
        action='act',
        payload=dict(cmd=[res, command, hash_],
        dt=time.monotonic(),
        dest=app_config.name))