import arrow

from datetime import timedelta
from pydash import py_

from .drawer import draw_loop
from ..components.text import Text, TextStyle, text
from ..components.elements import StillImage
from ..components.layouts import vstack, hstack
from ..components.layers import div, DivStyle
from ..components.scroller import HScroller
from ..components.spriteim import SpriteIcon
from ..components.widget import Widget
from ..components.transitions import text_slide_in
from ..components import fonts
from ..redis import rkeys, get_dict
from ..utils.func import throttle
from ..data_structures import FrameState

threed_icon = SpriteIcon('assets/raster/nozzle-alt-9x9.png', step_time=0.1)
done_icon = StillImage('assets/raster/nozzle-9x9-done.png')
file_icon = StillImage('assets/raster/fileicon-5x5.png')
toolt_icon = StillImage('assets/raster/nozzle-5x5.png')
bedt_icon = StillImage('assets/raster/printerbed-5x5.png')

tail_arrow_style = TextStyle(font=fonts.scientifica__r, color='#8c5b3e')
muted_small_style = TextStyle(font=fonts.bitocra7, color='#888888')

tail_arrow_left         = text(f'⤙', style=tail_arrow_style)
tail_arrow_right        = text(f'⤚', style=tail_arrow_style)
text_percent_sign       = Text('%', style=TextStyle(font=fonts.tamzen__rs, color='#888888'))

hscroller_fname = HScroller(size=33, pause_at_loop=True)

@throttle(1061)
def get_state(fs: FrameState):
    print_state = get_dict(rkeys['octoprint_printing'])
    tool_temp = get_dict(rkeys['octoprint_toolt'])
    bed_temp = get_dict(rkeys['octoprint_bedt'])

    time_left = print_state['progress']['printTimeLeft']
    progress = print_state['progress']['completion'] or -1
    flags = print_state['state']['flags']
    last_update = arrow.get(print_state['_timestamp'], tzinfo='local')

    is_printing = flags['printing']
    is_on = flags['operational'] or is_printing
    is_done = is_on and progress == 100

    now = arrow.now()

    is_visible = (is_on or is_done) and (last_update + timedelta(minutes=45)) > now

    completion_time = now.shift(seconds=time_left).strftime('%H:%M') if time_left else 'Idle'

    try:
        filename = print_state['job']['file']['display'] or ''
    except (KeyError, TypeError):
        filename = 'No file selected'

    filename = py_.human_case(filename.replace('.aw', '').replace('.gcode', ''))

    # day_delta = completion_time.timetuple().tm_mday - now.timetuple().tm_mday
    # if day_delta:
        # completion_str = f'+{day_delta} {completion_str}'

    time_left = print_state['progress']['printTimeLeftFormatted'] or '--:--'

    return dict(
        is_on=is_on,
        is_visible=is_visible,
        is_done=is_done,
        is_printing=is_printing,
        progress=progress,
        time_left=time_left,
        completion_time=completion_time,
        file_name=filename,
        toolt_current=tool_temp['actual'],
        toolt_target=tool_temp['target'],
        bedt_current=bed_temp['actual'],
        bedt_target=bed_temp['target'],
    )

def composer(fs: FrameState):
    state = get_state(fs)

    if not state['is_visible']:
        return

    completion_time = None

    if not state['is_done']:
        completion_time = text_slide_in(fs, 'op.eta', f'{state["completion_time"]}', style=TextStyle(font=fonts.bitocra7, color='#888888'))
        time_left = text_slide_in(fs, 'op.time_left', f'{state["time_left"]}', muted_small_style)
    else:
        time_left = text('Done!', style=muted_small_style)


    completion_text = hstack([tail_arrow_right, time_left], gap=2, align='center')
    completion_eta = hstack([tail_arrow_left, completion_time], gap=2, align='center') if completion_time else None

    info_elem = hstack([
        threed_icon.draw(fs.tick) if state['is_printing'] else done_icon,
        hstack([
            text_slide_in(fs, 'op.progress', f'{state["progress"]:0.1f}', TextStyle(font=fonts.cozette, color='#888888')),
            text_percent_sign,
        ], gap=1, align='top'),
    ], gap=4)

    file_detail = hstack([
        file_icon,
        hscroller_fname.set_frame(text(state["file_name"], muted_small_style)).draw(fs.tick),
    ], gap=2)

    temp_detail = hstack([
        hstack([toolt_icon, text_slide_in(fs, 'op.toolt', f'{round(state["toolt_current"])}', muted_small_style)], gap=2),
        hstack([bedt_icon, text_slide_in(fs, 'op.bedt', f'{round(state["bedt_current"])}', muted_small_style)], gap=2),
    ], gap=4)

    elements = [
        info_elem,
        completion_text,
        completion_eta,
        file_detail,
        temp_detail,
    ]

    return div(vstack(elements, gap=1, align='left'), style=DivStyle(padding=1))

def widget(fs: FrameState):
    frame = composer(fs)
    return Widget('octoprint', frame=frame, priority=15 if frame else 0, wait_time=20 if frame else 0)


draw = draw_loop(composer, sleepms=10)
