from ..drawer import draw_loop
from .app import composer, persistent_view
from . import widgets

draw = draw_loop(composer, sleepms=100)
