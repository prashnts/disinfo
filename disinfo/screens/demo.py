import random

from statistics import mode
from itertools import cycle, product
from collections import defaultdict
from colour import Color
from PIL import Image, ImageDraw

from .drawer import draw_loop
from .. import config
from ..data_structures import FrameState
from ..components.elements import Frame
from ..components.layouts import mosaic
from ..utils.palettes import funkyfuture8, paper8, kirokazegb


class GameOfLife:
    '''A multi-color implementation of Conway's Game of Life.'''

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

    def _get_palette(self):
        palette = random.choice([funkyfuture8, paper8, kirokazegb])
        game_colors = []
        for c in palette:
            color = Color(c)
            color.luminance = 0.15
            color.saturation = 0.80
            game_colors.append(color)
        return game_colors

    def reinit_board(self):
        self.board = {coord: 0 for coord in product(range(self.w + 1), range(self.h + 1))}
        self.game_colors = self._get_palette()
        self.game_color_seq = cycle(self.game_colors)
        for _ in range(2):
            self.seed_cells()

    def neighbors(self, x: int, y: int):
        '''
        Iterates Moore neighbourhood around (x, y) with wrap around the edges.
        Yield alive cells.
        '''
        coords = [
            (    x, y - 1),
            (    x, y + 1),
            (x - 1,     y),
            (x - 1, y - 1),
            (x - 1, y + 1),
            (x + 1,     y),
            (x + 1, y - 1),
            (x + 1, y + 1),
        ]
        for dx, dy in coords:
            if cell := self.board[(dx % self.w, dy % self.h)]:
                yield cell

    def seed_cells(self):
        '''
        Seeds the board with new cells distributed randomly.
        - The cells are random points generated in a n x n region, n being a random
          number between [3, 6].
        - A random color is assigned to the cell.
        '''
        color = self.game_colors.index(next(self.game_color_seq))
        npts = random.randint(3, 6)
        seed_x = random.randint(0, self.w - npts - 1)
        seed_y = random.randint(0, self.h - npts - 1)
        x_coords = [seed_x + x for x in range(npts)]
        y_coords = [seed_y + y for y in range(npts)]
        for c in product(x_coords, y_coords):
            self.board[c] = color if random.random() > 0.6 else 0

    def next_generation(self):
        b = self.board.copy()
        changed = False

        for coord, cell in self.board.items():
            neighbors = list(self.neighbors(*coord))
            n_alive = len(neighbors)
            if cell:
                if n_alive not in [2, 3]:
                    b[coord] = 0
                    changed = True
            elif n_alive == 3:
                b[coord] = mode(neighbors)
                changed = True

        if changed:
            self.board = b
            self.frame = self.draw_board()
        return changed

    def draw_board(self):
        img = Image.new('RGBA', (self.w, self.h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # We collect the similarly colored cells together. This lets us draw
        # multiple points in a single draw call.
        pts = defaultdict(list)

        for coord, cell in self.board.items():
            pts[cell].append(coord[::-1])

        for cell, coords in pts.items():
            if not cell:
                continue
            d.point(coords, self.game_colors[cell - 1].hex)

        return Frame(img)

    def advance(self, tick: float):
        if tick - self.last_tick >= self.speed:
            self.next_generation()
            self.last_tick = tick
        if tick - self.last_seed >= self.seed_interval:
            self.seed_cells()
            self.last_seed = tick
        if tick - self.last_reset >= self.reset_after:
            self.reinit_board()
            self.last_reset = tick

    def draw(self, tick: float):
        self.advance(tick)
        return self.frame


gol = GameOfLife(w=28, h=22, speed=0.1)

def composer(fs: FrameState):
    return mosaic(
        gol.draw(fs.tick),
        nx=round(config.matrix_w / gol.w + 1),
        ny=round(config.matrix_h / gol.h + 1),
    )


draw = draw_loop(composer, sleepms=80, use_threads=True)
