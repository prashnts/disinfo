from disp_info.components.text import Text
from disp_info.components.elements import Frame
from disp_info.components.layouts import stack_vertical, stack_horizontal
from disp_info.sprite_icons import SpriteImage
from disp_info.components import fonts
from disp_info.redis import rkeys, get_dict

threed_icon = SpriteImage('assets/3D.png')[0]


def draw() -> Frame:
    state = get_dict(rkeys['octoprint_printing'])

    if state['state']['text'] != 'Printing':
        return

    progress = state['progress']['completion']
    time_left = state['progress']['printTimeLeftFormatted']
    finish_at = state['progress']['printTimeFormatted']

    finish_text = stack_horizontal([
        Text(f'⤙', font=fonts.scientifica__r, fill='#096478'),
        Text(f'{time_left}', font=fonts.tamzen__rs, fill='#0d8c12'),
    ], gap=1, align='bottom')

    info_text = stack_horizontal([
        Text(f'{progress:0.1f}', font=fonts.scientifica__b, fill='#888888'),
        Text('%', font=fonts.tamzen__rs, fill='#888'),
    ], align='top')

    info_elem = stack_horizontal([
        threed_icon,
        info_text,
    ], gap=2, align='center')

    elements = [
        info_elem,
        finish_text,
    ]

    return stack_vertical(elements, gap=1, align='right')

