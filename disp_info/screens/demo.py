import math
import arrow

from PIL import Image, ImageDraw

from disp_info.components.elements import Frame
from disp_info.components.layouts import composite_at
from disp_info.components import fonts
from disp_info.components.layouts import stack_horizontal, stack_vertical
from disp_info.components.text import Text
from disp_info import config

colors_time = ['#1ba2ab', '#185e86']
color_date = '#6d7682'


def lissajous(*, a: float, b: float, A: float, B: float, d: float):
    def fn(t: float):
        x = A * math.sin((a * t) + d)
        y = B * math.sin(b * t)
        return (x, y)
    return fn

L1 = lissajous(a=3, b=2, A=16, B=16, d=math.pi / 2)
L2 = lissajous(a=5, b=4, A=24, B=24, d=math.pi / 2)


def plot_parametric(
    fn,
    t: float,
    *,
    tspan: int = 20,
    w: int = 32,
    h: int = 32,
    step: float = 0.2,
    color: str = '#1ba2ab',
    width: int = 1) -> Frame:
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    xoffset = (w // 2) - 1
    yoffset = (h // 2) - 1

    def _pt(v):
        x, y = fn(v)
        # position the x and y values with center of the image.
        return (x + xoffset, y + yoffset)

    pts = [_pt(t + (i * step)) for i in range(tspan)]
    d.line(pts, fill=color, width=width, joint='curve')

    return Frame(img)


def draw(tick: float):
    image = Image.new('RGBA', (config.matrix_w, config.matrix_h), (0, 0, 0, 0))
    composite_at(plot_parametric(
        L1,
        tick,
        tspan=100,
        w=48,
        h=48,
        color='#0f793d',
        width=1,
        step=0.05,
    ), image, 'mm')
    return Frame(image)