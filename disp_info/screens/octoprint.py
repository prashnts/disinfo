import arrow

from datetime import timedelta
from pydash import py_

from disp_info.components.text import Text
from disp_info.components.elements import Frame
from disp_info.components.layouts import stack_vertical, stack_horizontal
from disp_info.components.layers import add_background
from disp_info.components.scroller import HScroller
from disp_info.sprite_icons import SpriteIcon, SpriteImage
from disp_info.components import fonts
from disp_info.redis import rkeys, get_dict

threed_icon = SpriteIcon('assets/raster/nozzle.png', step_time=0.1)
file_icon = SpriteImage('assets/raster/fileicon-5x5.png')[0]
toolt_icon = SpriteImage('assets/raster/nozzle-5x5.png')[0]
bedt_icon = SpriteImage('assets/raster/printerbed-5x5.png')[0]

tail_arrow_left = Text(f'⤙', font=fonts.scientifica__r, fill='#8c5b3e')
tail_arrow_right = Text(f'⤚', font=fonts.scientifica__r, fill='#8c5b3e')
text_time_left = Text(font=fonts.bitocra, fill='#888888')
text_completion_time = Text(font=fonts.bitocra, fill='#e88a36')
text_progress = Text(font=fonts.scientifica__b, fill='#888888')
text_percent_sign = Text('%', font=fonts.tamzen__rs, fill='#888')
text_file_name = Text(font=fonts.bitocra, fill='#888888')
text_toolt_current = Text(font=fonts.bitocra, fill='#888888')
text_bedt_current = Text(font=fonts.bitocra, fill='#888888')

hscroller_fname = HScroller(size=22, pause_at_loop=True)

def _get_state():
    print_state = get_dict(rkeys['octoprint_printing'])
    tool_temp = get_dict(rkeys['octoprint_toolt'])
    bed_temp = get_dict(rkeys['octoprint_bedt'])
    filename = py_.human_case(
        print_state['job']['file']['display']
            .replace('.aw', '')
            .replace('.gcode', ''))
    time_left = print_state['progress']['printTimeLeft']

    now = arrow.now()
    completion_time = now.shift(seconds=time_left)
    completion_str = completion_time.strftime('%H:%M')
    # day_delta = completion_time.timetuple().tm_mday - now.timetuple().tm_mday
    # if day_delta:
        # completion_str = f'+{day_delta} {completion_str}'

    return dict(
        printing=print_state['state']['text'] == 'Printing',
        progress=print_state['progress']['completion'],
        time_left=print_state['progress']['printTimeLeftFormatted'],
        completion_time=completion_str,
        file_name=filename,
        toolt_current=tool_temp['actual'],
        toolt_target=tool_temp['target'],
        bedt_current=bed_temp['actual'],
        bedt_target=bed_temp['target'],
    )

get_state = py_.throttle(_get_state, 200)

def draw(tick: float) -> Frame:
    state = get_state()

    if not state['printing']:
        return

    text_time_left.update(value=f'{state["time_left"]}')
    text_progress.update(value=f'{state["progress"]:0.1f}')
    text_toolt_current.update(value=f'{round(state["toolt_current"])}')
    text_bedt_current.update(value=f'{round(state["bedt_current"])}')
    text_completion_time.update(value=f'{state["completion_time"]}')

    fname_changed = text_file_name.update(value=state["file_name"])
    hscroller_fname.set_frame(text_file_name, fname_changed)

    completion_text = stack_horizontal([
        tail_arrow_left,
        text_time_left,
        tail_arrow_right,
        text_completion_time,
    ], gap=2, align='center')

    info_text = stack_horizontal([
        text_progress,
        text_percent_sign,
    ], align='top')

    info_elem = stack_horizontal([
        threed_icon.draw(tick),
        info_text,
    ], gap=2)

    filename_elem = stack_horizontal([
        file_icon,
        hscroller_fname.draw(tick)
    ], gap=1)

    temp_elem = stack_horizontal([
        stack_horizontal([toolt_icon, text_toolt_current], gap=1),
        stack_horizontal([bedt_icon, text_bedt_current], gap=1),
    ], gap=2)

    detail_elem = stack_horizontal([
        filename_elem,
        temp_elem,
    ], gap=2)

    elements = [
        info_elem,
        completion_text,
        detail_elem,
    ]

    return add_background(stack_vertical(elements, gap=1, align='right'), fill='#000000ac')

