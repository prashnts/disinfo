'''Screens: the items a composer lays out, the places they may go, and the choice among them.

A Screen names its items (the stacks, the time...) and the choices of where they go: in each choice an Option
puts some items on Spots. Every second each arrangement (an option per choice) is scored on a coarse grid:
what has to stay in sight (the focus) under the items, the items over each other or off the screen, how long
their spots have been lit (burn-in), and the options' penalties (the designated places have none). It changes
on relayout (someone came, or every_s) to the best, or anytime the current one gets much worse; the items slide.
'''
import math
import random
import time
from dataclasses import dataclass
from itertools import product
from typing import Callable, Optional

import numpy as np
from PIL import Image

from . import ease
from .elements import Frame
from .layouts import ComposeAnchor, place_at


@dataclass(frozen=True)
class Spot:
    anchor: ComposeAnchor
    dx: int = 0
    dy: int = 0
    jitter: tuple[int, int] = (0, 0)    # px, picked at each relayout: inwards from the edge it's on


@dataclass(frozen=True)
class Option:
    spots: dict                         # item -> Spot
    penalty: float = 0
    when: Optional[str] = None          # only while the composer says so (e.g. 'calm')


# The costs are about 0-1 each (the heat, per item), weighed.
focus_weight = 3
overlap_weight = 2
off_weight = 2
heat_weight = 1
switch_margin = 0.05    # on relayout: the best, if better by this
anytime_margin = 0.3    # in between: only if much better (a plane went under a card)
heat_half_life = 12 * 3600
heat_least = 3600
rescore_s = 1


class Focus:
    '''What has to stay in sight, on the screen's grid. Each disk weighs its weight in all.'''

    def __init__(self, size: tuple[int, int], cell: int = 4):
        self.cell = cell
        self.grid = np.zeros((math.ceil(size[1] / cell), math.ceil(size[0] / cell)), np.float32)

    def disk(self, cx: float, cy: float, r: float, weight: float = 1) -> 'Focus':
        ys, xs = np.mgrid[:self.grid.shape[0], :self.grid.shape[1]]
        c = self.cell
        inside = ((xs + 0.5) * c - cx) ** 2 + ((ys + 0.5) * c - cy) ** 2 <= max(r, c / 2) ** 2
        if inside.any():
            self.grid[inside] += weight / inside.sum()
        return self


@dataclass
class Layout:
    positions: dict             # item -> its top left, px
    clear: tuple                # the largest box the items leave free: x0, y0, x1, y1

    def place(self, item: str, frame: Optional[Frame], dest: Frame, frost: float = 0) -> Frame:
        if not frame or item not in self.positions:
            return dest
        return place_at(frame, dest, *self.positions[item], 'tl', frost=frost)


def top_left(spot: Spot, jitter: tuple[int, int], size: tuple[int, int], screen: tuple[int, int]) -> tuple[int, int]:
    (w, h), (W, H) = size, screen
    x = {'l': 0, 'm': (W - w) // 2, 'r': W - w}[spot.anchor[1]]
    y = {'t': 0, 'm': (H - h) // 2, 'b': H - h}[spot.anchor[0]]
    return x + spot.dx + jitter[0], y + spot.dy + jitter[1]

def rolled(spot: Spot) -> tuple[int, int]:
    def one(a, j, lo, hi):
        return 0 if not j else random.randint(0, j) if a == lo else -random.randint(0, j) if a == hi else random.randint(-j, j)
    return one(spot.anchor[1], spot.jitter[0], 'l', 'r'), one(spot.anchor[0], spot.jitter[1], 't', 'b')

def largest_free(free: np.ndarray) -> tuple[int, int, int, int]:
    '''The largest box of True cells: x0, y0, x1, y1 in cells.'''
    best, heights = (0, (0, 0, 0, 0)), np.zeros(free.shape[1], int)
    for y, row in enumerate(free):
        heights = np.where(row, heights + 1, 0)
        stack = []
        for x in range(len(heights) + 1):
            h = heights[x] if x < len(heights) else 0
            start = x
            while stack and stack[-1][1] >= h:
                start, sh = stack.pop()
                if sh * (x - start) > best[0]:
                    best = (sh * (x - start), (start, y - sh + 1, x, y + 1))
            stack.append((start, h))
    return best[1]


@dataclass
class Screen:
    '''A screen's layout, set up in code: its choices of where the items go. Kept per screen.'''
    name: str
    choices: list                       # [[Option, ...], ...]: an option of each
    compose: Optional[Callable] = None
    every_s: float = 900                # relayout at least this often: burn-in
    move_s: float = 0.8
    cell: int = 4
    load_heat: Optional[Callable[[], Optional[np.ndarray]]] = None
    save_heat: Optional[Callable[[np.ndarray], None]] = None
    save_every_s: float = 300
    covering: Optional[set] = None      # the items that count covering the focus, None: all
    stacked: set = frozenset()          # items that may go over each other (the stacks: one corner shared)

    def __post_init__(self):
        self.current = tuple(0 for _ in self.choices)
        self.jitter = {}                # item -> px, rolled at relayout
        self.moves = {}                 # item -> (dx, dy, since): sliding in from there
        self.heat = None                # the grid: seconds lit, fading by heat_half_life
        self.last = {}                  # item -> where it was drawn
        self.scored_at = self.saved_at = 0
        self.relaid_at = time.monotonic()
        self.costs = {}

    def spots(self, arrangement: Optional[tuple] = None) -> dict:
        arrangement = arrangement or self.current
        return {k: v for c, i in zip(self.choices, arrangement) for k, v in c[i].spots.items()}

    def spot(self, item: str) -> Optional[Spot]:
        return self.spots().get(item)

    def arrange(self, fs, items: dict, focus=None, when=(), relayout: bool = False) -> Layout:
        '''Where the items go now. focus: a Focus, or one for an arrangement's spots (what's to see moves with them);
        when: the conditions that hold; relayout: someone came, a good time to move.'''
        size, now = (fs.config.width, fs.config.height), time.monotonic()
        allowed = [[i for i, o in enumerate(c) if o.when is None or o.when in when] for c in self.choices]
        forced = any(i not in a for i, a in zip(self.current, allowed))
        relayout = relayout or forced or now - self.relaid_at > self.every_s
        if relayout or now - self.scored_at >= rescore_s:
            self._score(items, focus, size, allowed, relayout, forced, now)
        positions = {}
        for item, spot in self.spots().items():
            if f := items.get(item):
                x, y = top_left(spot, self.jitter.get(item, (0, 0)), f.size, size)
                if m := self.moves.get(item):
                    k = 1 - ease.cubic.cubic_in_out(min((now - m[2]) / self.move_s, 1))
                    x, y = round(x + m[0] * k), round(y + m[1] * k)
                positions[item] = (x, y)
        self.last = positions
        occ = self._occupancy({i: self._mask(f) for i, f in items.items() if f}, positions, size)
        x0, y0, x1, y1 = largest_free(occ < 0.2)
        c = self.cell
        return Layout(positions, (x0 * c, y0 * c, min(x1 * c, size[0]), min(y1 * c, size[1])))

    def _mask(self, f: Frame) -> np.ndarray:
        # Where it shows on the grid, 0-1: any alpha counts, a frosted card is there all the same.
        c = self.cell
        a = f.image.getchannel('A').point(lambda v: 255 if v > 8 else 0).resize((max(math.ceil(f.width / c), 1), max(math.ceil(f.height / c), 1)), Image.BOX)
        return np.asarray(a, np.float32) / 255

    def _placed(self, mask: np.ndarray, x: int, y: int, shape: tuple) -> np.ndarray:
        g = np.zeros(shape, np.float32)
        gx, gy = round(x / self.cell), round(y / self.cell)
        x0, y0 = max(gx, 0), max(gy, 0)
        x1, y1 = min(gx + mask.shape[1], shape[1]), min(gy + mask.shape[0], shape[0])
        if x1 > x0 and y1 > y0:
            g[y0:y1, x0:x1] = mask[y0 - gy:y1 - gy, x0 - gx:x1 - gx]
        return g

    def _shape(self, size):
        return math.ceil(size[1] / self.cell), math.ceil(size[0] / self.cell)

    def _occupancy(self, masks: dict, positions: dict, size) -> np.ndarray:
        shape = self._shape(size)
        return sum((self._placed(masks[i], *p, shape) for i, p in positions.items() if i in masks), np.zeros(shape, np.float32))

    def _cost(self, arrangement: tuple, masks: dict, sizes: dict, focus: Optional[Focus], size) -> float:
        shape, occs, off, covers = self._shape(size), {}, 0, []
        for item, spot in self.spots(arrangement).items():
            if item not in masks:
                continue
            o = occs[item] = self._placed(masks[item], *top_left(spot, (0, 0), sizes[item], size), shape)
            if self.covering is None or item in self.covering:
                covers.append(o)
            total = masks[item].sum()
            off += 1 - o.sum() / total if total else 0
        penalty = sum(c[i].penalty for c, i in zip(self.choices, arrangement))
        if not occs:
            return penalty
        # Each item's share under the others: a small one half covered counts, next to a large one.
        def under(item, o):
            others = [p for i, p in occs.items() if i != item and not (item in self.stacked and i in self.stacked)]
            return (o * np.clip(sum(others), 0, 1)).sum() / (o.sum() or 1) if others else 0
        overlap = sum(under(i, o) for i, o in occs.items())
        cost = penalty + off_weight * off / len(occs) + overlap_weight * overlap
        focus = focus(self.spots(arrangement)) if callable(focus) else focus
        if focus is not None and focus.grid.sum() and covers:
            cost += focus_weight * (focus.grid * np.clip(sum(covers), 0, 1)).sum() / focus.grid.sum()
        if self.heat is not None:
            # Per item: each one's own wear counts whole, however small it is. Against the most worn, an hour at least:
            # a screen just started doesn't run from its first minutes.
            heat = self.heat / max(self.heat.max(), heat_least)
            cost += heat_weight * sum((heat * o).sum() / (o.sum() or 1) for o in occs.values())
        return float(cost)

    def _score(self, items, focus, size, allowed, relayout, forced, now):
        masks = {i: self._mask(f) for i, f in items.items() if f}
        sizes = {i: f.size for i, f in items.items() if f}
        self._heat(masks, size, now)
        self.costs = {a: self._cost(a, masks, sizes, focus, size) for a in product(*allowed)}
        best = min(self.costs, key=self.costs.get)
        current = self.costs.get(self.current, math.inf)
        switch = forced or self.costs[best] < current - (switch_margin if relayout else anytime_margin)
        if switch or relayout:
            old = self.last
            if switch:
                self.current = best
            if relayout:
                self.relaid_at = now
                self.jitter = {i: rolled(s) for i, s in self.spots().items()}
            # Slide from where they were.
            for item, spot in self.spots().items():
                if item in old and item in sizes:
                    x, y = top_left(spot, self.jitter.get(item, (0, 0)), sizes[item], size)
                    if (x, y) != old[item]:
                        self.moves[item] = (old[item][0] - x, old[item][1] - y, now)
        self.scored_at = now

    def _heat(self, masks, size, now):
        # The lit spots, in seconds, fading out over hours.
        shape = self._shape(size)
        if self.heat is None or self.heat.shape != shape:
            loaded = self.load_heat() if self.load_heat else None
            self.heat = loaded if loaded is not None and loaded.shape == shape else np.zeros(shape, np.float32)
            self.saved_at = now
        dt = min(now - self.scored_at, 10) if self.scored_at else 0
        self.heat = self.heat * 0.5 ** (dt / heat_half_life) + np.clip(self._occupancy(masks, self.last, size), 0, 1) * dt
        if self.save_heat and now - self.saved_at > self.save_every_s:
            self.save_heat(self.heat)
            self.saved_at = now
