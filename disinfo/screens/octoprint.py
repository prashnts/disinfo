import arrow

from datetime import timedelta
from pydash import py_

from .drawer import draw_loop
from ..components.text import Text, TextStyle
from ..components.elements import StillImage
from ..components.layouts import vstack, hstack
from ..components.layers import div, DivStyle
from ..components.scroller import HScroller
from ..components.spriteim import SpriteIcon
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

tail_arrow_left         = Text(f'⤙', style=tail_arrow_style)
tail_arrow_right        = Text(f'⤚', style=tail_arrow_style)
text_time_left          = Text(style=muted_small_style)
text_completion_time    = Text(style=TextStyle(font=fonts.bitocra7, color='#e88a36'))
text_progress           = Text(style=TextStyle(font=fonts.cozette, color='#888888'))
text_percent_sign       = Text('%', style=TextStyle(font=fonts.tamzen__rs, color='#888888'))
text_file_name          = Text(style=muted_small_style)
text_toolt_current      = Text(style=muted_small_style)
text_bedt_current       = Text(style=muted_small_style)

hscroller_fname = HScroller(size=22, pause_at_loop=True)

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

    text_progress.update(value=f'{state["progress"]:0.1f}')
    text_toolt_current.update(value=f'{round(state["toolt_current"])}')
    text_bedt_current.update(value=f'{round(state["bedt_current"])}')

    fname_changed = text_file_name.update(value=state["file_name"])
    hscroller_fname.set_frame(text_file_name, fname_changed)

    completion_info = [
        tail_arrow_left,
        text_time_left,
        tail_arrow_right,
    ]

    if not state['is_done']:
        text_time_left.update(value=f'{state["time_left"]}')
        text_completion_time.update(value=f'{state["completion_time"]}')
        completion_info.append(text_completion_time)
    else:
        text_time_left.update(value='Done!')

    completion_text = hstack(completion_info, gap=2, align='center')

    info_elem = hstack([
        threed_icon.draw(fs.tick) if state['is_printing'] else done_icon,
        hstack([text_progress, text_percent_sign], gap=1, align='top'),
    ], gap=4)

    detail_elem = hstack([
        hstack([
            file_icon,
            hscroller_fname.draw(fs.tick),
        ], gap=1),
        hstack([
            hstack([toolt_icon, text_toolt_current], gap=1),
            hstack([bedt_icon, text_bedt_current], gap=1),
        ], gap=2),
    ], gap=2)

    elements = [
        info_elem,
        completion_text,
        detail_elem,
    ]

    return div(vstack(elements, gap=1, align='left'), style=DivStyle(background='#000000ac', radius=2, padding=1))


draw = draw_loop(composer, sleepms=10)
