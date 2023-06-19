import pendulum

from datetime import datetime
from pydantic import BaseModel
from typing import Optional

from . import idfm
from .data_service import get_metro_info
from .. import config
from ..redis import set_dict, get_dict, set_json, rkeys
from ..data_structures import FrameState
from ..utils.time import is_expired


class MetroAppState(BaseModel):
    show: bool = False
    visible: bool = False
    valid: bool = False
    toggled_at: Optional[datetime] = None
    data: Optional[idfm.MetroData] = None


class CursorState(BaseModel):
    x: int = 120
    y: int = 42


class MetroInfoStateManager:
    name = 'di.state.metroinfo'
    value: MetroAppState

    def refresh(self):
        self.value = MetroAppState(**get_dict(self.name))

    def process_mqtt_message(self, topic: str, msg: dict):
        # Executed in ha process!
        if topic in ['zigbee2mqtt/enki.rmt.0x03', 'zigbee2mqtt/ikea.rmt.0x01']:
            if msg['action'] in ['scene_2', 'toggle']:
                show = self.value.show
                if is_expired(self.value.toggled_at, seconds=25):
                    show = True
                else:
                    show = not show

                self.set_state(show=show, toggled_at=pendulum.now())
                if show:
                    # it was previously not visible, so we refresh.
                    get_metro_info(force=True)

    def set_state(self, **kwargs):
        self.value = MetroAppState(**{**self.value.dict(), **kwargs})
        set_json(self.name, self.value.json())

    def get_state(self, fs: FrameState, refresh: bool = True):
        if refresh:
            self.refresh()
        s = self.value
        s.data = idfm.MetroData(**get_dict(rkeys['metro_timing']))

        shown = s.show and not is_expired(s.toggled_at, seconds=25, now=fs.now)
        s.visible = idfm.is_active() or shown
        s.valid = not is_expired(s.data.timestamp, minutes=1, seconds=20, now=fs.now)

        return s

class CursorStateManager:
    name = 'di.state.cursor'
    value: CursorState

    def refresh(self):
        self.value = CursorState(**get_dict(self.name))

    def process_mqtt_message(self, topic: str, msg: dict):
        v = self.value
        if topic in ['zigbee2mqtt/enki.rmt.0x03', 'zigbee2mqtt/ikea.rmt.0x01']:
            if msg['action'] in ['color_saturation_step_up', 'brightness_up_click']:
                v.y -= 2
            if msg['action'] in ['color_saturation_step_down', 'brightness_down_click']:
                v.y += 2
            if msg['action'] in ['color_hue_step_up', 'arrow_right_click']:
                v.x += 2
            if msg['action'] in ['color_hue_step_down', 'arrow_left_click']:
                v.x -= 2
            v.x %= config.matrix_w
            v.y %= config.matrix_h
            set_json(self.name, v.json())

    def get_state(self, fs: FrameState, refresh: bool = True):
        if refresh:
            self.refresh()
        return self.value


state_vars = [MetroInfoStateManager(), CursorStateManager()]
