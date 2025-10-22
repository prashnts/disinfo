import random

from PIL import Image

from .utils.weather_icons import render_icon, cursor
from .utils.func import throttle
from .components.layouts import hstack, vstack, composite_at
from .components.layers import div, DivStyle, rounded_rectangle
from .components.transitions import FadeIn
from .components.elements import Frame
from .components.stack import Stack
from .data_structures import FrameState
from .drat.app_states import CursorStateManager, PresenceSensorStateManager

from . import screens
from .screens.music.shazam import widgets as shazam_widgets
from .screens.music.shazam import indicators as shazam_indicators
from .config import app_config


config = {
    'width': 64,
    'height': 64,
    
}

def compose_small_frame(fs: FrameState):
    image = Image.new('RGBA', (app_config.width, app_config.height), (0, 0, 0, 255))
    if not should_turn_on_display(fs):
        # do not draw if nobody is there.
        return Frame(image).tag('not_present')

    # composite_at(screens.aviator.app.radar(fs), image, 'mm')
    composite_at(screens.solar.draw(fs), image, 'mm')
    stack = Stack('main_cards').mut([
        *screens.aviator.widgets.planes(fs),
        *shazam_widgets(fs),
        screens.weather.widgets.weather(fs),
        screens.dishwasher.widget(fs),
        screens.weather.widgets.moon_phase(fs),
        screens.now_playing.widget(fs),
        *screens.klipper.widget(fs),
        screens.trash_pickup.widget(fs),
        screens.date_time.calendar_widget(fs),
    ])
    composite_at(stack.draw(fs), image, 'ml', dx=p_stack_offset())
    composite_at(screens.date_time.sticky_widget(fs), image, 'tr', dy=p_time_offset())
    composite_at(screens.twenty_two.draw(fs), image, 'mm')
    composite_at(shazam_indicators(fs).draw(fs), image, 'br')

    return Frame(image).tag('present')