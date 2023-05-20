import math
import time
import random

from colour import Color
from PIL import Image, ImageDraw

from disp_info.components.elements import Frame
from disp_info.components.layouts import tile_copies

class GameOfLife:
    def __init__(self,
        w: int = 32,
        h: int = 32,
        speed: float = 0.1,
        scale: int = 1,
        idle_timeout: float = 10,
        reset_after: float = 30,
    ):
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
        self.color = Color(pick_for=self.last_changed)
        self.color.luminance = 0.15
        rint = lambda: int(random.random() > 0.75)
        return [[rint() for x in range(self.w)] for y in range(self.h)]

    def draw_board(self):
        s = self.scale
        img = Image.new('RGBA', (self.w * s, self.h * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        for x, row in enumerate(self.board):
            for y, cell in enumerate(row):
                if not cell:
                    continue
                color = self.color.hex
                rx, ry = y * s, x * s
                ex, ey = rx + (s - 1), ry + (s - 1)

                d.rectangle([(rx, ry), (ex, ey)], fill=color)

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
            changed = self.next_generation()
            if changed:
                self.last_changed = tick
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

gol = GameOfLife(speed=0.1, w=16, h=16, scale=1)


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
    return tile_copies(gol.draw(tick), nx=8, ny=4, seamless=True)
