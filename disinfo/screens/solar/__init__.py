from ..drawer import draw_loop
from .app import composer

draw = draw_loop(composer, sleepms=100)
