import json
from typing import Literal
from pydantic import ValidationError, Field

from disinfo.data_structures import AppBaseModel
from disinfo.drat.app_states import PubSubMessage, PubSubManager, PubSubStateManager


# class Pop


class DitButtonState(AppBaseModel):
    pressed: bool = False
    pressed_at: float = 0.0
    released_at: float = 0.0
    updated_at: float = 0.0

    pressed_for: list[str] = Field(default_factory=list)

    def is_pressed(self, key: str) -> bool:
        if key in self.pressed_for:
            return False
        if self.pressed:
            self.pressed_for.append(key)
        return self.pressed


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
    color_hex: str = '#000000'
    color_temp: float = 0.0
    lux: float = 0.0
    proximity: int = 0
    gesture: str = '--'
    updated_at: float = 0.0

class DiUserState(AppBaseModel):
    motion: bool = False
    updated_at: float = 0.0

class DiTelemetryState(AppBaseModel):
    remote: DiRemoteState = DiRemoteState()
    light_sensor: DiLightSensorState = DiLightSensorState()
    user: DiUserState = DiUserState()
    _v: Literal['dit'] = 'dit'


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
        except (json.JSONDecodeError, ValidationError) as e:
            print(f'Error processing telemetry message: {e}')
            pass