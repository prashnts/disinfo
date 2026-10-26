from discore.data_structures import FrameState
from discore.widget import Widget
from .app import composer, astronomical_info, extended
from .graphs import shown as graphs_shown
from . import window

def weather(fs: FrameState) -> Widget:
    frame = composer(fs)
    # Its graphs open under it (the metro's up): on top of its stack while they are.
    on, where = graphs_shown(fs)
    # Close the windows: attached under it while the wind blows in.
    attached = (Widget(name='weather.window', frame=window.card(fs) if frame else None),)
    return Widget(name='weather.widget', frame=frame, priority=2, wait_time=10, share=3, focus=on and where == 'side', attached=attached)

def moon_phase(fs: FrameState) -> Widget:
    frame = astronomical_info(fs)
    return Widget(name='moon_phase.widget', frame=frame, priority=0.5)

def graphs(fs: FrameState) -> Widget:
    # Kept, empty while shut: it shrinks away (Resize), and grows back from nothing.
    frame = extended(fs)
    return Widget(name='weather.graphs', frame=frame, focus=frame is not None, priority=2, wait_time=14)
