'''What the screens share: the background, the cards in the side and bottom stacks.'''
from discore.data_structures import FrameState
from discore.elements import Frame
from discore.transitions import FadeIn

from . import aviator, debug_info, dishwasher, klipper, now_playing, solar, trash_pickup, washing_machine, weather
from .music.shazam import widgets as shazam_widgets
from .solar import AnalogClockStyle


def radar_wanted(fs: FrameState, on_top: list) -> bool:
    if aviator.app.quiet(fs):
        return False
    return aviator.app.view_mode(fs) == 'sky' or any(w and w.background == 'aviator' for w in on_top)

def background(fs: FrameState, style: AnalogClockStyle, clear: tuple, on_top: list) -> Frame:
    '''The background the widgets on top of the stacks bring (a plane's card: the radar), the solar clock otherwise.
    The sky view has the sun in it: it's the solar clock too, always there. Never the radar in the quiet hours.

    clear: the box the cards leave free, the radar keeps the plane of the card on top in it.
    '''
    if radar_wanted(fs, on_top):
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
