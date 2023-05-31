import random
import time

from colour import Color
from PIL import Image, ImageDraw
from statistics import mode
from itertools import cycle

from .screen import composer_thread
from .. import config
from ..data_structures import FrameState
from ..components.elements import Frame
from ..components.layouts import tile_copies
from ..utils.palettes import funkyfuture8, paper8, kirokazegb


class GameOfLife:
    def __init__(self,
        w: int = 32,
        h: int = 32,
        speed: float = 0.05,
        seed_interval: float = 1,
        reset_after: float = 45,
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
            color.luminance = 0.15
            color.saturation = 0.80
            game_colors.append(color)
        return game_colors

    def reinit_board(self):
        self.board = [[0 for x in range(self.w)] for y in range(self.h)]
        self.game_colors = self._get_palette(random.choice([funkyfuture8, paper8, kirokazegb]))
        self.game_color_seq = cycle(self.game_colors)
        for _ in range(2):
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
        color = self.game_colors.index(next(self.game_color_seq))
        npts = random.randint(3, 6)
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


gol = GameOfLife(w=28, h=22, speed=0.1)

def composer(fs: FrameState):
    return tile_copies(
        gol.draw(fs.tick),
        nx=round(config.matrix_w / gol.w + 1),
        ny=round(config.matrix_h / gol.h),
    )


draw = composer_thread(composer, sleepms=100)
