from .screen import composer_thread
from ..components.text import Text
from ..components.layouts import stack_vertical
from ..components.layers import add_background
from ..components import fonts
from ..utils.func import throttle
from ..data_structures import FrameState


text_brightness = Text(font=fonts.tamzen__rs, fill='#fff')
text_lux = Text(font=fonts.tamzen__rs, fill='#fff')
text_draw_time = Text(font=fonts.tamzen__rs, fill='#fff')
text_sys_temp = Text(font=fonts.tamzen__rs, fill='#fff')


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

    debuginfo = stack_vertical([text_brightness, text_lux, text_draw_time, text_sys_temp], gap=2)

    return add_background(debuginfo, fill='#044a18b6', padding=3, radius=2)


draw = composer_thread(composer, sleepms=100, use_threads=True)
