'''What's in front of the ToF, from its 8x8 zones: done here, on the client; the server gets the result.

The grid is turned to the sensor's own view (as a camera: x to its right, y down) with `rotate` quarter turns. Each
zone has a background: the room's distance there. It follows a zone getting farther at once, and takes a nearer one
only after it has stayed still a long while (a chair moved, not a person). Zones nearer than their background, and
within `present_mm`, are the foreground; touching ones make blobs.

Out: `present` (someone there, with a hold-off), `target` (the biggest blob), `near` (a blob within `near_mm`: like a
button, pressed while it's there), `blobs`. The grid, the background and the foreground only while debug is asked for.
'''
import json
import time
from pathlib import Path
from dataclasses import dataclass, field

import numpy as np


@dataclass
class ToFParams:
    rotate: int = 0             # quarter turns (np.rot90) to the sensor's view
    margin_mm: int = 150        # nearer than the background by this: foreground
    present_mm: int = 1500      # and within this
    near_mm: int = 500          # a hand: within this,
    hand_gap_mm: int = 250      # and nearer than the body by this (leaning in, reaching across: not a hand)
    body_cells: int = 36        # a blob this big from body_cells_mm on is a body (a hand that near fills the view)
    body_cells_mm: int = 250
    min_cells: int = 3          # a body
    present_on_s: float = 0.5
    present_off_s: float = 5.0
    near_on_s: float = 0.3      # held this long to press (someone passing by is quicker)
    near_off_s: float = 0.25
    near_still_s: float = 20    # pressed and not moving this long: not a hand; ignored till it goes
    absorb_s: float = 600       # nearer and still (jitter under absorb_mm) this long: the background
    absorb_mm: float = 15
    save_s: float = 900         # the background to disk this often (it's kept across restarts)


def blobs(fg: np.ndarray, grid: np.ndarray) -> list[dict]:
    '''Touching foreground zones (4-neighbours): nearest (2nd nearest from 3 zones up), mean, centroid, zones.'''
    seen = np.zeros_like(fg)
    out = []
    for y0, x0 in zip(*np.nonzero(fg)):
        if seen[y0, x0]:
            continue
        stack, cells = [(y0, x0)], []
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop()
            cells.append((y, x))
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < fg.shape[0] and 0 <= nx < fg.shape[1] and fg[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        ys, xs = np.array(cells).T
        mm = np.sort(grid[ys, xs])
        out.append({'mm': int(mm[1] if len(mm) >= 3 else mm[0]), 'mean': int(mm.mean()),
                    'x': round(float(xs.mean()), 2), 'y': round(float(ys.mean()), 2), 'cells': len(cells)})
    return sorted(out, key=lambda b: -b['cells'])


@dataclass
class ToFTracker:
    params: ToFParams = field(default_factory=ToFParams)
    path: Path | None = None    # the background, kept

    bg: np.ndarray | None = None
    grid: np.ndarray | None = None
    fg: np.ndarray | None = None
    found: list = field(default_factory=list)
    updated_at: float = 0.0
    hz: float = 0.0

    present: dict = field(default_factory=lambda: {'on': False, 'since': 0.0, 'updated_at': 0.0})
    near: dict = field(default_factory=lambda: {'pressed': False, 'pressed_at': 0.0, 'released_at': 0.0,
                                                'updated_at': 0.0, 'mm': 0, 'x': 0.0, 'y': 0.0})
    target: dict = field(default_factory=dict)

    _nearer_since: np.ndarray | None = None
    _still: np.ndarray | None = None
    _last: np.ndarray | None = None
    _seen_at: float = 0.0       # someone there last (present's hold-off)
    _first_at: float = 0.0      # someone there since (present's hold-on)
    _near_from: float = 0.0     # a hand since (0: none)
    _near_gone: float = 0.0     # none since
    _near_veto: bool = False
    _near_still: tuple = (0.0, 0.0, 0.0)     # (since, x, y) it last moved
    _body_mm: float = 0.0       # the body's distance, slow, while no hand
    _saved_at: float = 0.0

    def __post_init__(self):
        if self.path and self.path.exists():
            try:
                self.bg = np.array(json.loads(self.path.read_text())['bg'], dtype=float).reshape(8, 8)
                self.bg[self.bg <= 0] = np.nan
            except Exception as e:
                print(f'[ToF] background not read: {e}')
        self._saved_at = time.monotonic()

    def update(self, distance_mm: list[int], now: float | None = None):
        '''One frame: distances by zone, 0 where there's no reading.'''
        now = time.monotonic() if now is None else now
        p = self.params
        g = np.rot90(np.array(distance_mm, dtype=float).reshape(8, 8), p.rotate)
        valid = g > 0
        g[~valid] = np.nan

        if self.bg is None:
            self.bg = np.full((8, 8), np.nan)
            self._nearer_since = np.full((8, 8), np.nan)
        if self._nearer_since is None:
            self._nearer_since = np.full((8, 8), np.nan)
        if self._still is None:
            self._still, self._last = np.zeros((8, 8)), g.copy()

        bg = self.bg
        fresh = valid & np.isnan(bg)
        bg[fresh] = g[fresh]
        farther = valid & (g > bg + 30)
        bg[farther] += 0.2 * (g[farther] - bg[farther])

        jitter = np.where(valid & ~np.isnan(self._last), np.abs(g - self._last), 0)
        self._still = 0.98 * self._still + 0.02 * jitter
        self._last = np.where(valid, g, self._last)

        known = ~np.isnan(bg)
        fg = valid & (g < p.present_mm) & (~known | (g < bg - p.margin_mm))
        since = self._nearer_since
        since[~fg] = np.nan
        since[fg & np.isnan(since)] = now
        absorb = fg & (now - since > p.absorb_s) & (self._still < p.absorb_mm)
        bg[absorb] = g[absorb]
        since[absorb] = np.nan

        found = blobs(fg, g)
        if self.updated_at:
            self.hz = 0.9 * self.hz + 0.1 / max(now - self.updated_at, 1e-3)
        self.grid, self.fg, self.found, self.updated_at = g, fg, found, now

        body = [b for b in found if b['cells'] >= p.min_cells]
        if body:
            self._first_at = self._first_at or now
            self._seen_at = now
        else:
            self._first_at = 0.0
        on = self.present['on']
        if not on and body and now - self._first_at >= p.present_on_s:
            self.present.update(on=True, since=now, updated_at=now)
        elif on and now - self._seen_at > p.present_off_s:
            self.present.update(on=False, since=now, updated_at=now)

        if body:
            b, t = body[0], self.target
            k = 0.3 if t else 1.0
            self.target = {'mm': int(t.get('mm', b['mm']) + k * (b['mm'] - t.get('mm', b['mm']))),
                           'x': round(t.get('x', b['x']) + k * (b['x'] - t.get('x', b['x'])), 2),
                           'y': round(t.get('y', b['y']) + k * (b['y'] - t.get('y', b['y'])), 2),
                           'cells': b['cells']}
        elif not self.present['on']:
            self.target = {}

        n = self.near
        if body and not n['pressed'] and body[0]['mm'] >= p.near_mm:
            k = 0.02 if self._body_mm else 1.0
            self._body_mm += k * (body[0]['mm'] - self._body_mm)
        hand = min((b for b in found if self.is_hand(b)), key=lambda b: b['mm'], default=None)
        if hand:
            self._near_from = self._near_from or now
            self._near_gone = 0.0
            n.update(mm=hand['mm'], x=hand['x'], y=hand['y'])
            since, sx, sy = self._near_still
            if abs(hand['x'] - sx) > 0.5 or abs(hand['y'] - sy) > 0.5:
                self._near_still = (now, hand['x'], hand['y'])
        else:
            self._near_from = 0.0
            self._near_gone = self._near_gone or now
            if now - self._near_gone >= p.near_off_s:
                self._near_veto = False
        if not n['pressed'] and hand and not self._near_veto and now - self._near_from >= p.near_on_s:
            n.update(pressed=True, pressed_at=now, updated_at=now)
            self._near_still = (now, hand['x'], hand['y'])
        elif n['pressed'] and (not hand and now - self._near_gone >= p.near_off_s or hand and now - self._near_still[0] > p.near_still_s):
            if hand:
                self._near_veto = True
            n.update(pressed=False, released_at=now, updated_at=now)

        if self.path and now - self._saved_at > p.save_s:
            self.save()

    def is_hand(self, b: dict) -> bool:
        p = self.params
        if b['mm'] >= p.near_mm or b['cells'] < 2:
            return False
        if b['cells'] >= p.body_cells and b['mm'] >= p.body_cells_mm:
            return False
        return not self._body_mm or b['mm'] < self._body_mm - p.hand_gap_mm

    def reset(self):
        '''The background again from the next frames (the sensor moved: the room must be empty).'''
        self.bg = self._nearer_since = self._still = None
        self._saved_at = 0.0        # saved on the next frame

    def save(self):
        self._saved_at = time.monotonic()
        try:
            self.path.write_text(json.dumps({'bg': np.nan_to_num(self.bg, nan=0).astype(int).ravel().tolist(),
                                             'rotate': self.params.rotate, 'at': time.time()}))
        except Exception as e:
            print(f'[ToF] background not saved: {e}', flush=True)

    def serialize(self, debug: bool = False) -> dict:
        out = {'updated_at': self.updated_at, 'hz': round(self.hz, 1), 'present': dict(self.present),
               'near': dict(self.near), 'target': dict(self.target),
               'blobs': [[b['mm'], b['x'], b['y'], b['cells']] for b in self.found[:4]]}
        if debug and self.grid is not None:
            out['debug'] = {'grid': np.nan_to_num(self.grid, nan=0).astype(int).ravel().tolist(),
                            'bg': np.nan_to_num(self.bg, nan=0).astype(int).ravel().tolist(),
                            'fg': self.fg.astype(int).ravel().tolist()}
        return out


@dataclass
class ToFRate:
    '''The ranging frequency from the light: in continuous mode a frame integrates for its whole period, so slower
    sees farther in daylight (sweep 2026-10-29, the sun on the window: valid zones 15 Hz 4.9 %, 10 Hz 6.9 %, 5 Hz
    11.6 %). The ambient is the sensor's own, the median zone, kcps/spad (night ~1, that sun ~150). A hand that near
    is seen at any rate: full speed while it's pressed.'''
    steps: tuple = ((0, 15), (20, 10), (60, 5))     # (from this ambient, Hz)
    down: float = 0.7           # back a step below its ambient times this
    smooth_s: float = 5
    hz: int = 15
    ambient: float = 0.0
    _at: float = 0.0

    def update(self, ambient: float, pressed: bool, now: float | None = None) -> int:
        '''The frequency to range at, with the frame's median ambient.'''
        now = time.monotonic() if now is None else now
        k = min(1.0, (now - self._at) / self.smooth_s) if self._at else 1.0
        self.ambient += k * (ambient - self.ambient)
        self._at = now
        i = max(j for j, (a, _) in enumerate(self.steps) if self.ambient >= a)
        cur = next((j for j, (_, hz) in enumerate(self.steps) if hz == self.hz), 0)
        if i < cur and self.ambient >= self.steps[cur][0] * self.down:
            i = cur
        self.hz = self.steps[0][1] if pressed else self.steps[i][1]
        return self.hz


@dataclass
class ToFRecorder:
    '''Raw frames for training (the statuses too: the mask can be redone) with what the tracker made of them, a
    compressed file a minute in `path` (a RAM disk), till `until` (epoch) or `max_mb` there.'''
    path: Path
    until: float
    max_mb: float = 1200
    every_s: float = 60
    _rows: list = field(default_factory=list)
    _since: float = 0.0
    _full: bool = False

    def on(self) -> bool:
        return not self._full and time.time() < self.until

    def add(self, distance_mm, status, targets, tracker: 'ToFTracker', ambient: float = 0.0, hz: int = 0):
        if not self.on():
            return
        now = time.time()
        t, n = tracker.target, tracker.near
        self._rows.append((now, distance_mm, status, targets, tracker.present['on'], n['pressed'],
                           t.get('mm', 0), t.get('x', -1), t.get('y', -1), tracker._body_mm, ambient, hz))
        self._since = self._since or now
        if now - self._since >= self.every_s:
            self.flush()

    def flush(self):
        rows, self._rows, self._since = self._rows, [], 0.0
        if not rows:
            return
        try:
            self.path.mkdir(parents=True, exist_ok=True)
            if sum(f.stat().st_size for f in self.path.glob('*.npz')) > self.max_mb * 1e6:
                self._full = True
                print('[ToF] recording: full')
                return
            c = list(zip(*rows))
            np.savez_compressed(self.path / time.strftime('tof-%Y%m%d-%H%M%S.npz', time.localtime(rows[0][0])),
                                t=np.array(c[0]), d=np.array(c[1], np.int16), s=np.array(c[2], np.uint8),
                                n=np.array(c[3], np.uint8), present=np.array(c[4], bool), near=np.array(c[5], bool),
                                target=np.array(c[6:9], np.float32).T, body=np.array(c[9], np.float32),
                                amb=np.array(c[10], np.float32), hz=np.array(c[11], np.uint8))
        except Exception as e:
            print(f'[ToF] recording: {e}')
