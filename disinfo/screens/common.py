'''What the screens share: the background, the cards in the side and bottom stacks.'''
from discore.data_structures import FrameState
from discore.elements import Frame
from discore.transitions import FadeIn

from . import aviator, debug_info, dishwasher, klipper, now_playing, solar, trash_pickup, washing_machine, weather
from .music.shazam import widgets as shazam_widgets
from .solar import AnalogClockStyle


def background(fs: FrameState, style: AnalogClockStyle, clear: tuple) -> Frame:
    '''The radar when there's something to see from the window, the solar clock otherwise.

    clear: the box the cards leave free, the radar keeps the plane of the card on top in it.
    '''
    if aviator.app.active(fs):
        draw = aviator.sky.sky if aviator.app.view_mode(fs) == 'sky' else aviator.app.radar
        return FadeIn('aviator', duration=0.6).mut(aviator.app.throttled(fs, lambda: draw(fs, clear))).draw(fs)
    return FadeIn('solar', duration=0.3).mut(solar.draw(fs, style)).draw(fs)

def side_cards(fs: FrameState) -> list:
    return [
        weather.widgets.weather(fs),
        *shazam_widgets(fs),
        now_playing.slideshow_widget(fs),
        weather.widgets.moon_phase(fs),
        dishwasher.widget(fs),
        washing_machine.widget(fs),
        trash_pickup.widget(fs),
    ]

def bottom_cards(fs: FrameState) -> list:
    return [
        *aviator.widgets.planes(fs),
        now_playing.widget(fs),
        *klipper.widget(fs),
        *debug_info.widgets(fs),
    ]
