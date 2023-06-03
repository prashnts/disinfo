import pendulum

from dataclasses import dataclass
from typing import Optional, Union

from ..redis import set_dict, get_dict
from ..data_structures import FrameState
from .data_service import get_metro_info
from . import idfm


@dataclass
class MetroAppState:
    show: bool = False
    toggled_at: Optional[pendulum.DateTime] = None


def in_future(dt: Union[str, pendulum.DateTime, None], seconds: int = 0, minutes: int = 0):
    if not dt:
        return False

    if isinstance(dt, str):
        dt = pendulum.parse(dt)

    return dt.add(seconds=seconds, minutes=minutes) > pendulum.now()

class MetroInfoState:
    name = 'di.state.metroinfo'
    default_state = {'show': False, 'toggle_time': None}
    value: dict

    def refresh(self):
        self.value = get_dict(self.name, self.default_state)

    def process_mqtt_message(self, topic: str, msg: dict):
        if topic in ['zigbee2mqtt/enki.rmt.0x03', 'zigbee2mqtt/ikea.rmt.0x01']:
            if msg['action'] in ['scene_2', 'toggle']:
                visible = self.value['show']
                if in_future(self.value.get('toggle_time'), seconds=25):
                    visible = not visible
                else:
                    visible = True

                self.set_state(show=visible, toggle_time=pendulum.now().isoformat())
                if visible:
                    # it was previously not visible, so we refresh.
                    get_metro_info(force=True)

    def set_state(self, **kwargs):
        self.value = {**self.value, **kwargs}
        set_dict(self.name, self.value)

    def get_state(self, fs: FrameState, refresh: bool = True):
        if refresh:
            self.refresh()
        state = self.value

        shown = state['show'] and in_future(state.get('toggle_time'), seconds=25)
        state['visible'] = idfm.is_active() or shown

        return state


state_vars = [MetroInfoState()]
