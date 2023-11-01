from disinfo.data_structures import FrameState
from disinfo.components.widget import Widget
from .app import composer, astronomical_info

def weather(fs: FrameState) -> Widget:
    frame = composer(fs)
    return Widget(name='weather.widget', frame=frame)

def moon_phase(fs: FrameState) -> Widget:
    frame = astronomical_info(fs)
    return Widget(name='moon_phase.widget', frame=frame)
