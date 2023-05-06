from disp_info.components.text import Text
from disp_info.components.elements import Frame
from disp_info.components.layouts import stack_vertical, stack_horizontal
from disp_info.sprite_icons import SpriteIcon
from disp_info.components import fonts
from disp_info.redis import rkeys, get_dict

threed_icon = SpriteIcon('assets/raster/nozzle.png', step_time=0.1)

text_time_left_icon = Text(f'⤙', font=fonts.scientifica__r, fill='#8c5b3e')
text_time_left = Text(font=fonts.tamzen__rs, fill='#d6a851')
text_progress = Text(font=fonts.scientifica__b, fill='#888888')
text_percent_sign = Text('%', font=fonts.tamzen__rs, fill='#888')


def draw(tick: float) -> Frame:
    state = get_dict(rkeys['octoprint_printing'])

    if state['state']['text'] != 'Printing':
        return

    progress = state['progress']['completion']
    time_left = state['progress']['printTimeLeftFormatted']
    finish_at = state['progress']['printTimeFormatted']

    text_time_left.update(value=f'{time_left}')
    text_progress.update(value=f'{progress:0.1f}')

    finish_text = stack_horizontal([
        text_time_left_icon,
        text_time_left,
    ], gap=1, align='bottom')

    info_text = stack_horizontal([
        text_progress,
        text_percent_sign,
    ], align='top')

    info_elem = stack_horizontal([
        threed_icon.draw(tick),
        info_text,
    ], gap=2, align='center')

    elements = [
        info_elem,
        finish_text,
    ]

    return stack_vertical(elements, gap=1, align='right')

