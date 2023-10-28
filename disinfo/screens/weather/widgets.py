from disinfo.data_structures import FrameState
from disinfo.components.widget import Widget
from .app import composer, astronomical_info

def weather(fs: FrameState) -> Widget:
    frame = composer(fs)
    return Widget('weather.widget', frame)

def moon_phase(fs: FrameState) -> Widget:
    frame = astronomical_info(fs)
    return Widget('moon_phase.widget', frame)

widgets = {
    'weather.widget': weather,
    'moon_phase.widget': moon_phase,
}
