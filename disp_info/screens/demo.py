import math
import arrow

from functools import partial
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

L1 = lissajous(a=3, b=2, A=10, B=10, d=math.pi / 2)
L2 = lissajous(a=5, b=4, A=24, B=24, d=math.pi / 2)

def lissajous_ratio(*, A: float, B: float, d: float):
    # b is fixed to 1.
    b = 1
    def fn(r: float, t: float):
        a = r % 3
        x = A * math.sin((a * t) + d)
        y = B * math.sin(b * t)
        return (x, y)
    return fn

L3 = lissajous_ratio(A=10, B=10, d=math.pi / 2)

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

    xoffset = (w // 2)
    yoffset = (h // 2)

    def _pt(v):
        x, y = fn(v)
        # position the x and y values with center of the image.
        return (x + xoffset, y + yoffset)

    pts = [_pt(t + (i * step)) for i in range(tspan)]
    d.line(pts, fill=color, width=width, joint='curve')

    return Frame(img)



def draw_sin_wave(step, draw, yoffset, amp, divisor, color, width=1):
    AMP = amp
    OFFSET = 10
    DIVISOR = divisor # 1.5

    y_step = lambda x: round(math.sin(step + x / DIVISOR) * AMP + OFFSET)
    xys = [(x + 0, y_step(x) + yoffset) for x in range(128)]

    draw.line(xys, fill=color, width=width, joint='curve')



def draw(tick: float):
    image = Image.new('RGBA', (config.matrix_w, config.matrix_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)

    draw_sin_wave(step=(tick * 20), draw=d, yoffset=21, amp=4, divisor=2, color='#3A6D8C')

    # composite_at(plot_parametric(
    #     L1,
    #     tick,
    #     tspan=400,
    #     w=48,
    #     h=48,
    #     color='#052647aa',
    #     width=2,
    #     step=0.02,
    # ), image, 'mm')

    draw_sin_wave(step=(34 + (tick * 5)), draw=d, yoffset=20, amp=7, divisor=10, color='#282828')

    # composite_at(plot_parametric(
    #     L1,
    #     tick,
    #     tspan=60,
    #     w=48,
    #     h=38,
    #     color='#FF7E00',
    #     width=1,
    #     step=0.02,
    # ), image, 'mm')
    composite_at(plot_parametric(
        partial(L3, tick / 100),
        tick,
        tspan=360,
        w=48,
        h=38,
        color='#FF7E00',
        width=1,
        step=0.01,
    ), image, 'mm')

    return Frame(image)
