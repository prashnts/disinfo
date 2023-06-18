from .screen import draw_loop
from ..components.text import Text, TextStyle
from ..components.layouts import vstack
from ..components.layers import div, DivStyle
from ..components import fonts
from ..utils.func import throttle
from ..data_structures import FrameState

debug_textstyle = TextStyle()

text_brightness = Text(style=debug_textstyle)
text_lux = Text(style=debug_textstyle)
text_draw_time = Text(style=debug_textstyle)
text_sys_temp = Text(style=debug_textstyle)


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
        'is_visible': fs.rmt0_action == 'scene_3',
        'sys_temp': _get_temp,
        **stateinfo,
    }


def composer(fs: FrameState):
    s = get_state(fs)
    if not s['is_visible']:
        return

    text_brightness.update(value=f"Bri: {s['brightness']}%")
    text_lux.update(value=f"Lux: {s['lux']:0.1f}")
    text_draw_time.update(value=f"Tdr: {s['draw_time']:0.4f}")
    text_sys_temp.update(value=f"t_s: {s['sys_temp']():0.1f}°")

    debuginfo = vstack([text_brightness, text_lux, text_draw_time, text_sys_temp], gap=2)

    return div(
        debuginfo,
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
