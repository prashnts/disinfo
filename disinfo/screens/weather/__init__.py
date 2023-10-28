from ..drawer import draw_loop
from .app import composer
from .widgets import widgets

draw = draw_loop(composer, sleepms=100)
