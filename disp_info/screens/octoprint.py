from disp_info.components.text import Text
from disp_info.components.elements import Frame
from disp_info.components.layouts import stack_vertical, stack_horizontal
from disp_info.components.layers import add_background
from disp_info.components.scroller import HScroller
from disp_info.sprite_icons import SpriteIcon, SpriteImage
from disp_info.components import fonts
from disp_info.redis import rkeys, get_dict

threed_icon = SpriteIcon('assets/raster/nozzle.png', step_time=0.1)
file_icon = SpriteImage('assets/raster/file-icon.png')[0]

text_time_left_icon = Text(f'⤙', font=fonts.scientifica__r, fill='#8c5b3e')
text_time_left = Text(font=fonts.bitocra, fill='#e88a36')
text_progress = Text(font=fonts.scientifica__b, fill='#888888')
text_percent_sign = Text('%', font=fonts.tamzen__rs, fill='#888')
text_file_name = Text(font=fonts.bitocra, fill='#8fd032')

hscroller_fname = HScroller(size=27)


def draw(tick: float) -> Frame:
    state = get_dict(rkeys['octoprint_printing'])

    if state['state']['text'] != 'Printing':
        return

    progress = state['progress']['completion']
    time_left = state['progress']['printTimeLeftFormatted']
    finish_at = state['progress']['printTimeFormatted']
    file_name = state['job']['file']['display']

    text_time_left.update(value=f'{time_left}')
    text_progress.update(value=f'{progress:0.1f}')

    fname_changed = text_file_name.update(value=file_name)
    hscroller_fname.set_frame(text_file_name, fname_changed)

    finish_text = stack_horizontal([
        text_time_left_icon,
        text_time_left,
    ], gap=2, align='center')

    info_text = stack_horizontal([
        text_progress,
        text_percent_sign,
    ], align='top')

    info_elem = stack_horizontal([
        threed_icon.draw(tick),
        info_text,
    ], gap=2, align='center')

    filename_elem = stack_horizontal([
        file_icon,
        hscroller_fname.draw(tick)
    ], gap=0, align='center')

    elements = [
        info_elem,
        finish_text,
        filename_elem,
    ]

    return add_background(stack_vertical(elements, gap=1, align='right'), fill='#0000008c')

