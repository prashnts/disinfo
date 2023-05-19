import math
import time
import random

from functools import partial
from colour import Color
from PIL import Image, ImageDraw

from disp_info.components.elements import Frame
from disp_info.components.layouts import composite_at
from disp_info.components import fonts
from disp_info.components.layouts import stack_horizontal, stack_vertical
from disp_info.components.text import Text
from disp_info import config

colors_time = ['#1ba2ab', '#185e86']
color_date = '#6d7682'


class GameOfLife:
    color_map = {
        0: '#00000000',
        1: '#0d686e',
    }

    def __init__(self, w: int = 32, h: int = 32, speed: float = 0.1, scale: int = 1, idle_timeout: float = 3, reset_after: float = 30):
        self.w = w
        self.h = h
        self.scale = scale
        self.idle_timeout = idle_timeout
        self.reset_after = reset_after
        self.last_tick = 0
        self.last_changed = 0
        self.last_reset = time.time()
        self.speed = speed
        self.board = self._gen_board()
        self.frame = self.draw_board()

    def _gen_board(self):
        rint = lambda: int(random.random() > 0.8)
        return [[rint() for x in range(self.w)] for y in range(self.h)]

    def draw_board(self):
        s = self.scale
        img = Image.new('RGBA', (self.w * s, self.h * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        for x, row in enumerate(self.board):
            for y, cell in enumerate(row):
                color = self.color_map[cell]
                rx, ry = y * s, x * s
                ex, ey = rx + (s - 1), ry + (s - 1)

                d.rounded_rectangle([(rx, ry), (ex, ey)], fill=color, radius=2, outline='#00000000', width=1)

        return Frame(img)

    def neighbors(self, x: int, y: int):
        dirns = [
            (x - 1, y - 1),
            (x, y - 1),
            (x + 1, y - 1),
            (x - 1, y),
            (x + 1, y),
            (x - 1, y + 1),
            (x, y + 1),
            (x + 1, y + 1),
        ]
        for dx, dy in dirns:
            try:
                yield self.board[dx][dy]
            except IndexError:
                # todo: we'd like to wrap around.
                pass

    def _tick(self, tick: float):
        if tick - self.last_tick >= self.speed:
            changed = self.next_generation()
            if changed:
                self.last_changed = changed
            elif tick - self.last_changed >= self.idle_timeout:
                self.board = self._gen_board()
            self.last_tick = tick
        if tick - self.last_reset >= self.reset_after:
            self.board = self._gen_board()
            self.last_reset = tick


    def next_generation(self):
        # copy the board
        b = [row[:] for row in self.board]
        changed = False
        for x, row in enumerate(self.board):
            for y, cell in enumerate(row):
                neighbors = self.neighbors(x, y)
                n_alive = sum(neighbors)
                if cell and n_alive < 2:
                    b[x][y] = 0
                    changed = True
                elif cell and n_alive > 3:
                    b[x][y] = 0
                    changed = True
                if not cell and n_alive == 3:
                    b[x][y] = 1
                    changed = True
        if changed:
            self.board = b
            self.frame = self.draw_board()
        return changed

    def draw(self, tick: float):
        self._tick(tick)
        return self.frame


def cyclicvar(
    a: float,
    b: float,
    step: float = 0.1,
    reverse: bool = True,
    speed: float = 0.1,
):
    # todo: this looks like a class.
    var = a
    fwd = True
    last_tick = 0

    def _step():
        nonlocal var, fwd
        if fwd:
            var += step
        else:
            var -= step
        if var >= b:
            if reverse:
                fwd = False
                var = b
            else:
                var = a
        if var <= a:
            fwd = True
            var = a
        return var

    def _value(tick: float):
        nonlocal last_tick
        if tick - last_tick >= speed:
            _step()
            last_tick = tick
        return var

    return _value


def lissajous(*, a: float, b: float, A: float, B: float, d: float):
    # https://en.m.wikipedia.org/wiki/Lissajous_curve
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
        a = r
        x = A * math.sin((a * t) + d)
        y = B * math.sin(b * t)
        return (x, y)
    return fn

L3 = lissajous_ratio(A=10, B=10, d=math.pi / 2)
V1 = cyclicvar(1/2, 3/2, speed=5, step=0.2)

gol = GameOfLife(speed=0.5, w=16, h=8, scale=8)


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
    composite_at(gol.draw(tick), image, 'mm')

    # composite_at(plot_parametric(
    #     partial(L3, V1(tick)),
    #     tick,
    #     tspan=360,
    #     w=48,
    #     h=38,
    #     color='#FF7E00',
    #     width=1,
    #     step=.03,
    # ), image, 'mm')

    return Frame(image)
