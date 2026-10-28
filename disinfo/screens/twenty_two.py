import math
import random
import time
import numpy as np

from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import islice
from PIL import Image, ImageDraw, ImageOps, ImageColor

from disinfo import fonts
from discore.elements import Frame
from discore.layouts import place_at
from discore.layers import div
from discore.text import TextStyle, text
from discore.data_structures import FrameState
from ..drat import shown
from ..utils.drawer import draw_loop
from .aviator import sky


# The cat: pixel art facing right, cat_block px a pixel. Mine one day, nyan for now.
cat_path, cat_block, cat_step = 'assets/raster/nyan-cat2.gif', 8, 0.07

palettes = {
    'rainbow': ('#FF1A1A', '#FF9A00', '#FFF000', '#3CFF00', '#0AA5FF', '#7A3CFF'),
    'dawn': ('#FF7EB3', '#FF9E7A', '#FFD07A', '#FFF3B0'),
    'sunset': ('#7B2FBE', '#D9406B', '#FF7A3D', '#FFC53D'),
    'aurora': ('#1CE8A0', '#18B7C9', '#3D6BFF', '#9B4DFF'),
    'poptart': ('#FFCC99', '#FF99FF', '#FF3399'),
}
glitter = ['#4096D9', '#404BD9', '#AF4FD7', '#D9BC40', '#D96140', '#1CB751']
demos = [(22, 22), (14, 14), (12, 34), (13, 31), (11, 11), (19, 19)]    # pressed: each a while
demo_s = 12

rgb = lambda c: ImageColor.getrgb(c)[:3]
smooth = lambda u: (lambda u: u * u * (3 - 2 * u))(min(max(u, 0), 1))


def _frames(path: str, block: int) -> list[Image.Image]:
    frames = []
    with Image.open(path) as im:
        for i in range(getattr(im, 'n_frames', 1)):
            im.seek(i)
            f = im.convert('RGBA')
            frames.append(f.resize((f.width // block, f.height // block), Image.Resampling.NEAREST))
    return frames

cat_frames = _frames(cat_path, cat_block)

@lru_cache(maxsize=512)
def cat(i: int, k: int, flip: bool = False, tilt: int = 0) -> Frame:
    im = cat_frames[i % len(cat_frames)]
    im = im.resize((im.width * k, im.height * k), Image.Resampling.NEAREST)
    if flip:
        im = ImageOps.mirror(im)
    if tilt:
        im = im.rotate(tilt, Image.Resampling.NEAREST, expand=True)
    return Frame(im, hash=('cat', cat_path, i, k, flip, tilt))


@dataclass
class Moment:
    kind: str       # same 22:22, run 12:34, pair 14:14, mirror 13:31
    level: float    # 0..1, how big a show
    palette: str
    color: str

def by_hour(h: int) -> str:
    return 'aurora' if h < 6 or h >= 22 else 'dawn' if h < 11 else 'rainbow' if h < 17 else 'sunset'

def moment(t) -> Moment | None:
    hm, sec = t.strftime('%H%M'), t.second == t.minute
    if len(set(hm)) == 1:
        # 00:00, 11:11, 22:22: the largest the most.
        return Moment('same', min(1, 0.7 + 0.15 * int(hm[0]) + 0.1 * sec), 'rainbow', '#CF3F13' if sec else '#CF8C13')
    if hm in ('0123', '1234', '2345'):
        return Moment('run', 1 if t.strftime('%H%M%S') in ('012345', '123456') else 0.6, 'rainbow', '#13A7CF')
    if t.hour == t.minute:
        return Moment('pair', 0.25 + 0.2 * t.hour / 23 + 0.15 * sec, by_hour(t.hour), '#CF3F13' if sec else '#2FB21B')
    if hm == hm[::-1]:
        return Moment('mirror', 0.15, 'poptart', '#D94FB0')


@dataclass
class Flight:
    kind: str
    pos: np.ndarray
    at: float
    a: float = 0.0          # heading, y down
    dir: int = 1
    trail: deque = field(default_factory=lambda: deque(maxlen=900))
    sparks: list = field(default_factory=list)      # (x, y, born)
    rockets: list = field(default_factory=list)     # (x, from y, to y, born, colors, seed)
    phase: tuple = field(default_factory=lambda: tuple(random.uniform(0, 2 * math.pi) for _ in range(4)))

flights = {}    # per screen


def wander(f: Flight, now, dt, v, w, h, cw, ch, mo, roof):
    # A slow wobble of the heading, back to the middle near the edges; a loop now and then on the big ones.
    p = f.phase
    turn = 1.4 * (math.sin(now * 0.7 + p[0]) + 0.6 * math.sin(now * 1.9 + p[1]))
    mx, my, zone = cw / 2, ch / 2, min(w, h) / 4
    x, y = f.pos
    near = max(0, (mx + zone - x) / zone, (x - (w - mx - zone)) / zone, (my + zone - y) / zone, (y - (h - my - zone)) / zone)
    if near:
        to = math.atan2(h / 2 - y, w / 2 - x)
        turn += 4 * near * math.atan2(math.sin(to - f.a), math.cos(to - f.a))
    if mo.level >= 0.8 and (now + p[2]) % 7 < 1.3:
        turn = 2 * math.pi / 1.3
    f.a += turn * dt
    v *= 1 + 0.3 * math.sin(now * 0.5 + p[3])
    f.pos = np.clip(f.pos + v * dt * np.array([math.cos(f.a), math.sin(f.a)]), (mx, my), (w - mx, h - my))

def to_and_fro(f: Flight, v, dt, w, cw) -> float:
    lo, hi = cw / 2, w - cw / 2
    x = f.pos[0] + f.dir * v * dt
    if not lo <= x <= hi:
        f.dir *= -1
        x = min(max(x, lo), hi)
    return x

def stairs(f: Flight, now, dt, v, w, h, cw, ch, mo, roof):
    # 1, 2, 3, 4 up, then back down.
    x = to_and_fro(f, v, dt, w, cw)
    u = (x - cw / 2) / max(w - cw, 1) * 4
    n = min(int(u), 3)
    up = n + (smooth((u - n - 0.7) / 0.3) if n < 3 else 0)
    top, bottom = ch * 1.2, h - ch / 2 - 2
    f.pos = np.array([x, bottom - (bottom - top) * up / 3])

def wave(f: Flight, now, dt, v, w, h, cw, ch, mo, roof):
    x = to_and_fro(f, v, dt, w, cw)
    f.pos = np.array([x, h / 2 + (h / 2 - ch) * 0.6 * math.sin(2 * math.pi * x / (w / 1.5))])

def city(f: Flight, now, dt, v, w, h, cw, ch, mo, roof):
    # Over the roofs, the tallest ahead; diving behind them now and then.
    x = to_and_fro(f, v, dt, w, cw)
    a, b = int(max(x - cw * 0.8, 0)), int(min(x + cw * 0.8, w))
    to = np.percentile(roof[a:b], 25) - ch / 2 - 2 - 3 * math.sin(now * 2)
    if mo.level >= 0.4 and (now + f.phase[2] * 2) % 9 < 1.4:
        to += (ch + 6) * math.sin(math.pi * ((now + f.phase[2] * 2) % 9) / 1.4)
    y = f.pos[1] + (to - f.pos[1]) * min(1, dt * 4)
    f.pos = np.array([x, max(y, ch / 2)])

paths = {'wander': wander, 'stairs': stairs, 'wave': wave, 'city': city}


def ribbon(d: ImageDraw.ImageDraw, pts, length: float, band: int, colors: tuple, fade: float, now: float, k: int, mirror: int = 0):
    # The trail behind the cat along its way: a band of each colour across it, stepping like nyan's.
    step, samples, s = max(1, band // 3), [], 0.0
    for p0, p1 in zip(pts, islice(pts, 1, None)):
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        dist = math.hypot(dx, dy)
        if dist > 40:
            break
        if not dist:
            continue
        ux, uy = dx / dist, dy / dist
        nx, ny = (-uy, ux) if ux > 0 or (ux == 0 and uy < 0) else (uy, -ux)
        for j in np.arange(0, dist, step):
            samples.append((p0[0] + ux * j, p0[1] + uy * j, nx, ny, s + j))
        s += dist
        if s > length:
            break
    cols = [rgb(c) for c in colors]
    for x, y, nx, ny, s in reversed(samples):
        if s > length:
            continue
        a = 255 if s < fade * length else int(255 * (length - s) / (length * (1 - fade)))
        wob = k * ((int(s) // (6 * k) + int(now * 6)) % 2)
        for i, c in enumerate(cols):
            o = (i - (len(cols) - 1) / 2) * band + wob
            cx, cy = x + nx * o - band / 2, y + ny * o - band / 2
            cx = mirror - cx - band if mirror else cx
            d.rectangle((round(cx), round(cy), round(cx) + band - 1, round(cy) + band - 1), fill=(*c, a))

def star(d: ImageDraw.ImageDraw, x: int, y: int, r: int, k: int, color: tuple):
    # nyan's twinkle: a dot, a cross, its arms apart.
    if r == 0:
        d.rectangle((x, y, x + k - 1, y + k - 1), fill=color)
        return
    for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        for j in range(max(r - 1, 1) if r == 3 else 0, r + (r < 3)):
            ax, ay = x + sx * j * k, y + sy * j * k
            d.rectangle((ax, ay, ax + k - 1, ay + k - 1), fill=color)

def fireworks(d: ImageDraw.ImageDraw, f: Flight, now: float, w: int, h: int, k: int, mo: Moment, roof, dt: float):
    sp, rise, burst = min(w, h) * 0.4, 0.7, 1.4
    if random.random() < (mo.level - 0.3) * 1.5 * dt:
        x = random.uniform(w * 0.1, w * 0.9)
        y0 = float(roof[int(x)])
        cols = random.sample(palettes[mo.palette], 2)
        f.rockets.append((x, y0, random.uniform(h * 0.08, max(y0 - sp, h * 0.1)), now, cols, random.random()))
    f.rockets = [r for r in f.rockets if now - r[3] < rise + burst]
    for x, y0, y1, born, cols, seed in f.rockets:
        age = now - born
        if age < rise:
            y = y0 + (y1 - y0) * smooth(age / rise)
            d.rectangle((round(x), round(y), round(x) + k - 1, round(y) + 2 * k - 1), fill=(255, 230, 200, 220))
            continue
        tau = age - rise
        a = int(255 * (1 - tau / burst) ** 1.5)
        n = 18 + int(14 * mo.level)
        for i in range(n):
            ang = 2 * math.pi * (i + seed) / n
            r = sp * tau * (0.7 + 0.3 * ((i * 7919 * (seed + 1)) % 1))
            px, py = x + math.cos(ang) * r, y1 + math.sin(ang) * r + 0.5 * sp * tau * tau
            z = max(k - 1 + i % 2, 1)
            d.rectangle((round(px), round(py), round(px) + z - 1, round(py) + z - 1), fill=(*rgb(cols[i % 2]), a))

def roofline(fs: FrameState) -> np.ndarray | None:
    at, ys = sky.roofline.get(fs.config.name, (0, None))
    return ys if ys is not None and time.time() - at < 2 and len(ys) == fs.config.width else None


def composer(fs: FrameState):
    t = fs.now
    if shown.up(fs, 'twentytwo'):
        t = t.set(**dict(zip(('hour', 'minute'), demos[int(fs.tick // demo_s) % len(demos)])))
    if not (mo := moment(t)):
        return

    w, h, now = fs.config.width, fs.config.height, fs.tick
    roof = roofline(fs)
    kind = 'city' if roof is not None else {'same': 'wander', 'pair': 'wander', 'run': 'stairs', 'mirror': 'wave'}[mo.kind]
    k = 1 + min(w, h) // 160 + (mo.level >= 0.7) - (roof is not None and min(w, h) > 128)
    cw, ch = cat(0, k).width, cat(0, k).height

    f = flights.get(fs.config.name)
    if not f or f.kind != kind or now - f.at > 2:
        f = flights[fs.config.name] = Flight(kind, np.array([cw / 2 + 1, h / 2]), now)
    dt, f.at = min(now - f.at, 0.2), now
    paths[kind](f, now, dt, min(w, h) * (0.25 + 0.35 * mo.level), w, h, cw, ch, mo, roof)
    f.trail.appendleft(f.pos.copy())

    image = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    colors, band = palettes[mo.palette], max(1, round(k * (1.5 + mo.level)))
    length, fade = w * (0.3 + 1.5 * mo.level), 1 if mo.level >= 0.8 else 0.5
    twin = w if kind == 'wave' and mo.kind == 'mirror' else 0
    ribbon(d, f.trail, length, band, colors, fade, now, k)
    if twin:
        ribbon(d, f.trail, length, band, colors, fade, now, k, mirror=w)

    if roof is not None and mo.level >= 0.45:
        fireworks(d, f, now, w, h, k, mo, roof, dt)
    if mo.level >= 0.4 and random.random() < 6 * mo.level * dt:
        f.sparks.append((random.randrange(w), random.randrange(h), now))
    f.sparks = [s for s in f.sparks if now - s[2] < 0.8]
    for x, y, born in f.sparks:
        star(d, x, y, (0, 1, 2, 3, 2, 1)[int((now - born) / 0.8 * 6)], max(1, k - 1), (255, 255, 255, 230))
    if mo.level >= 0.7:
        # shimmering leds everywhere, it's the magic hour.
        for y, x in zip(*np.nonzero(np.random.random((h, w)) < 0.001 * mo.level)):
            z = random.choice((1, 1, 2))
            d.rectangle((x, y, x + z - 1, y + z - 1), fill=random.choice(glitter))

    back = f.trail[min(3, len(f.trail) - 1)]
    vx, vy = f.pos[0] - back[0], f.pos[1] - back[1]
    flip = vx < 0 if abs(vx) > 0.01 else f.dir < 0
    tilt = int(max(-45, min(45, round(math.degrees(math.atan2(-vy, abs(vx) + 1e-6)) / 15) * 15))) if kind != 'stairs' else 0
    i, spots = int(now / cat_step), []
    for mirror in ((False, True) if twin else (False,)):
        c = cat(i, k, flip != mirror, -tilt if flip != mirror else tilt)
        x = w - f.pos[0] if mirror else f.pos[0]
        x0 = min(max(round(x - c.width / 2), 0), w - c.width)
        y0 = min(max(round(f.pos[1] - c.height / 2), 0), h - c.height)
        image.alpha_composite(c.image, (x0, y0))
        spots.append((y0, y0 + c.height))

    if roof is not None:
        # behind the roofs, the cat and its trail.
        a = np.asarray(image).copy()
        a[np.arange(h)[:, None] > roof[None, :], 3] = 0
        image = Image.fromarray(a)

    label = text(t.strftime('%H:%M' if mo.level < 0.2 else '%H:%M:%S'), style=TextStyle(font=fonts.pix_tall, color=mo.color, outline=1))
    label = div(label, background='#5010A088', padding=2, radius=2)
    if (z := min(w, h) // 200):
        label = Frame(label.image.resize((label.width * (z + 1), label.height * (z + 1)), Image.Resampling.NEAREST), hash=('scaled', z, label))
    lx = min(max(round(f.pos[0] - label.width / 2), 0), w - label.width)
    top, bottom = spots[0]
    ly = top - label.height - 1 if top - label.height - 1 >= 0 else min(bottom + 1, h - label.height)
    place_at(label, image, lx, ly, 'tl')
    return Frame(image)


draw = draw_loop(composer, sleepms=50)
