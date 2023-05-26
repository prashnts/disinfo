import math
import random

from colour import Color
from PIL import Image, ImageDraw
from statistics import mode
from itertools import cycle

from .. import config
from ..components.elements import Frame
from ..components.layouts import tile_copies
from ..utilities.palettes import funkyfuture8, paper8, kirokazegb


class GameOfLife:
    def __init__(self,
        w: int = 32,
        h: int = 32,
        speed: float = 0.1,
        seed_interval: float = 2,
        reset_after: float = 180,
    ):
        self.w = w
        self.h = h
        self.seed_interval = seed_interval
        self.reset_after = reset_after
        self.last_tick = 0
        self.last_reset = 0
        self.last_seed = 0
        self.speed = speed
        self.reinit_board()
        self.frame = self.draw_board()

    def _get_palette(self, palette: list[str]):
        game_colors = []
        for c in palette:
            color = Color(c)
            color.luminance = 0.25
            game_colors.append(color)
        return game_colors

    def reinit_board(self):
        self.board = [[0 for x in range(self.w)] for y in range(self.h)]
        self.game_colors = self._get_palette(random.choice([funkyfuture8, paper8, kirokazegb]))
        self.game_color_cycler = cycle(self.game_colors)
        self.seed_cells()

    def draw_board(self):
        img = Image.new('RGBA', (self.w, self.h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        for x, row in enumerate(self.board):
            for y, cell in enumerate(row):
                if cell:
                    color = self.game_colors[cell - 1]
                    d.point((y, x), color.hex)

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
            self.next_generation()
            self.last_tick = tick
        if tick - self.last_seed >= self.seed_interval:
            self.seed_cells()
            self.last_seed = tick
        if tick - self.last_reset >= self.reset_after:
            self.reinit_board()
            self.last_reset = tick

    def seed_cells(self):
        # add n points within a region.
        # we generate a random point within the board
        # grab a n x n region
        # color = random.randint(0, len(self.game_colors))
        color = self.game_colors.index(next(self.game_color_cycler))
        npts = 4
        s_x = random.randint(0, self.h - npts - 1)
        s_y = random.randint(0, self.w - npts - 1)
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
