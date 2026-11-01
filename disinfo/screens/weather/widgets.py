from discore.data_structures import FrameState
from discore.widget import Widget
from discore.elements import Lazy
from .app import composer, astronomical_info, extended
from .graphs import shown as graphs_shown
from . import window

def weather(fs: FrameState) -> Widget:
    # Lazy: drawn when its stack shows it (Stack.draw), its size meanwhile from the last time.
    frame = Lazy(lambda: composer(fs), (fs.config.name, 'weather'))
    # Its graphs open under it (the metro's up): on top of its stack while they are.
    on, where = graphs_shown(fs)
    # Close the windows: attached under it while the wind blows in.
    attached = (Widget(name='weather.window', frame=Lazy(lambda: window.card(fs), (fs.config.name, 'weather.window')) if frame else None),)
    return Widget(name='weather.widget', frame=frame, priority=2, wait_time=10, share=3, focus=on and where == 'side', attached=attached)

def moon_phase(fs: FrameState) -> Widget:
    frame = Lazy(lambda: astronomical_info(fs), (fs.config.name, 'moon_phase'))
    return Widget(name='moon_phase.widget', frame=frame, priority=0.5)

def graphs(fs: FrameState) -> Widget:
    # Kept, empty while shut: it shrinks away (Resize), and grows back from nothing.
    frame = extended(fs)
    return Widget(name='weather.graphs', frame=frame, focus=frame is not None, priority=2, wait_time=14)
