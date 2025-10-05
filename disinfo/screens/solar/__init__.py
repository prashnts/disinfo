from ..drawer import draw_loop
from .app import composer, AnalogClockStyle

draw = draw_loop(composer, sleepms=100)
