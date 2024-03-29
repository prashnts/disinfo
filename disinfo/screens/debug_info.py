from .drawer import draw_loop
from ..components.text import text
from ..components.layouts import vstack
from ..components.layers import div, DivStyle
from ..utils.func import throttle
from ..data_structures import FrameState
from ..drat.app_states import RemoteStateManager

@throttle(40)
def get_state(fs: FrameState):
    stateinfo = fs.rendererdata if fs.rendererdata else {
        'brightness': -1,
        'lux': -1,
        'draw_time': -1,
    }
    def _get_temp():
        # return a function to avoid unnecessary reads when hidden
        try:
            with open('/sys/class/thermal/thermal_zone0/temp') as fp:
                return int(fp.read()) / 1000
        except FileNotFoundError:
            return -1
    return {
        'is_visible': RemoteStateManager().get_state(fs).action == 'btn_debug',
        'sys_temp': _get_temp,
        **stateinfo,
    }


def composer(fs: FrameState):
    s = get_state(fs)
    if not s['is_visible']:
        return

    return div(
        vstack([
            text(f"Bri: {s['brightness']}%"),
            text(f"Lux: {s['lux']:0.1f}"),
            text(f"Tdr: {s['draw_time']:0.4f}"),
            text(f"t_s: {s['sys_temp']():0.1f}°"),
        ], gap=2),
        style=DivStyle(
            background='#032b0e',
            padding=3,
            margin=0,
            radius=(3, 5, 3, 0),
            border=1,
            border_color='#b196ce'
        ),
    )


draw = draw_loop(composer, sleepms=100, use_threads=True)
