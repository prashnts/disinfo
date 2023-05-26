import math
import time
import random

from colour import Color
from PIL import Image, ImageDraw
from statistics import mode

from .. import config
from ..components.elements import Frame
from ..components.layouts import tile_copies

# cols = list(Color('#2d0982').range_to(Color('#722408'), steps=8))
cols = [
    Color('#a95a61'),
    Color('#cb8f68'),
    Color('#ddb483'),
    Color('#efd187'),
    Color('#ecda9d'),
    Color('#bcbc96'),
    Color('#879c8b'),
    Color('#5d8ea2'),
    Color('#57697c'),
    Color('#475264'),
    Color('#635362'),
    Color('#bb6650'),
]
# for color in cols:
#     color.luminance = 0.15

class GameOfLife:
    def __init__(self,
        w: int = 32,
        h: int = 32,
        speed: float = 0.1,
        idle_timeout: float = 5,
        reset_after: float = 180,
    ):
        self.w = w
        self.h = h
        self.idle_timeout = idle_timeout
        self.reset_after = reset_after
        self.last_tick = 0
        self.last_changed = 0
        self.last_reset = 0
        self.last_seed = 0
        self.speed = speed
        self.reinit_board()
        self.frame = self.draw_board()

    def _gen_board(self):
        self.color = Color(pick_for=self.last_changed)
        self.color.luminance = 0.15
        rint = lambda: 0 #int(random.random() > 0.65)
        return [[rint() for x in range(self.w)] for y in range(self.h)]

    def reinit_board(self):
        self.board = self._gen_board()
        self.drop_seed()

    def draw_board(self):
        img = Image.new('RGBA', (self.w, self.h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # pts = [
        #     (y, x)
        #     for x, row in enumerate(self.board)
        #     for y, cell in enumerate(row)
        #     if cell]

        # d.point(pts, self.color.hex)
        for x, row in enumerate(self.board):
            for y, cell in enumerate(row):
                if cell:
                    color = cols[cell - 1].hex

                    d.point((y, x), )

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
            # wraparound.
            if dx < 0:
                dx = self.h - 1
            elif dx > self.h - 1:
                dx = 0
            if dy < 0:
                dy = self.w - 1
            elif dy > self.w - 1:
                dy = 0
            yield self.board[dx][dy]

    def _tick(self, tick: float):
        if tick - self.last_tick >= self.speed:
            changed, any_alive = self.next_generation()
            if changed:
                self.last_changed = tick
            elif (tick - self.last_changed >= self.idle_timeout):
                self.reinit_board()
            if (tick - self.last_seed > 1):
                self.drop_seed()
                self.last_seed = tick
            self.last_tick = tick
        if tick - self.last_reset >= self.reset_after:
            self.reinit_board()
            self.last_reset = tick

    def drop_seed(self):
        # add n points within a region.
        # we generate a random point within the board
        # grab a n x n region
        color = random.randint(0, len(cols))
        npts = 4
        s_x = random.randint(0, self.h - npts - 1)
        s_y = random.randint(0, self.w - npts - 1)
        # print(s_x, s_y)
        for dx in range(npts):
            for dy in range(npts):
                self.board[s_x + dx][s_y + dy] = color if random.random() > 0.6 else 0


    def next_generation(self):
        # copy the board
        b = [row[:] for row in self.board]
        changed = False
        any_alive = False
        for x, row in enumerate(self.board):
            for y, cell in enumerate(row):
                neighbors = [n for n in self.neighbors(x, y) if n > 0]
                n_alive = len(neighbors)
                if cell and n_alive < 2:
                    b[x][y] = 0
                    changed = True
                elif cell and n_alive > 3:
                    b[x][y] = 0
                    changed = True
                if not cell and n_alive == 3:
                    b[x][y] = mode(neighbors)
                    changed = True
                if cell:
                    any_alive = True
        if changed:
            self.board = b
            self.frame = self.draw_board()
        return changed, any_alive

    def draw(self, tick: float):
        self._tick(tick)
        return self.frame


def lissajous(*, a: float, b: float, A: float, B: float, d: float):
    # https://en.m.wikipedia.org/wiki/Lissajous_curve
    def fn(t: float):
        x = A * math.sin((a * t) + d)
        y = B * math.sin(b * t)
        return (x, y)
    return fn

def lissajous_ratio(*, A: float, B: float, d: float):
    # b is fixed to 1.
    b = 1
    def fn(r: float, t: float):
        a = r
        x = A * math.sin((a * t) + d)
        y = B * math.sin(b * t)
        return (x, y)
    return fn

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

gol = GameOfLife(speed=0.1, w=18, h=12)

def draw(tick: float):
    return tile_copies(
        gol.draw(tick),
        nx=config.matrix_w // gol.w + 1,
        ny=config.matrix_h // gol.h + 1,
    )
