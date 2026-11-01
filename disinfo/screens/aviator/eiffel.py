'''The Eiffel tower: its outline from the real one's (the legs and their arch, the floors, the top, the antenna), at
any size, a coverage mask per pixel: crisp on the LEDs, never a triangle. Lit gold at night, sparkling the first
minutes of the hour, its lattice showing once it's big; the beacon on top turning its beams over the city.

Drawn as tall as the view puts it, as wide as its own proportions say (the view stretches the elevations).
'''
import math
import random
import numpy as np
import cairocffi as cairo


tall_m, wide_m = 330, 125
# (m up, half the width on a face, m): the legs' outside, the floors' levels, the top, the antenna
outline = ((0, 62.5), (20, 51), (40, 42), (57, 35.5), (80, 29), (116, 21), (150, 15.5), (190, 11), (230, 8), (276, 5.5),
           (290, 4.2), (296, 2.8), (300, 2.2), (312, 1.2), (316, 0.5), (330, 0.4))
floors = ((57, 4, 5), (116, 3, 3), (276, 2.5, 3))      # (m up, m out of the outline, m thick): the platforms
# The sky between the legs: (m up from, to, half-width m at the bottom, at the top, how round the arch's top)
gaps = ((0, 40, 37.5, 27, 2.2), (62, 112, 17, 9, 1.6))
lamp_m = 306            # the beacon
gold = (1, 0.64, 0.24)
gold_floor = (1, 0.8, 0.45)
sparkle = (1, 1, 0.95)
lattice_px = 90         # this tall and up: the lattice shows, see-through
beam_turn = 80          # s a turn of the beacon (four beams)
beam_km = 9             # how far a beam reaches, fading
beam_fade_km = 2.2
beam_up = 1.2           # degrees over the horizontal
beam_spread = 0.7       # degrees across
beam_alpha = 0.45
_cache = {}


def shape(z: np.ndarray, k: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    '''At heights z (m), k px a metre: the half-width (px) of the outline, of the sky between the legs, and the
    platforms (each a pixel and out of the outline at the least).'''
    zs, hs = np.array(outline).T
    o = np.interp(z, zs, hs) * k
    g = np.zeros_like(z)
    for z0, z1, h0, h1, arch in gaps:
        u = np.clip((z - z0) / (z1 - z0), 0, 1)
        inside = (z >= z0) & (z < z1)
        g = np.where(inside, (h0 + (h1 - h0) * u) * (1 - u ** (2 * arch)) ** (1 / arch) * k, g)
    plat = np.zeros(len(z), bool)
    m_px = (z[0] - z[1]) if len(z) > 1 else 1      # m a row
    for zf, out, thick in floors:
        on = np.abs(z - zf) <= max(thick / 2, m_px / 2)
        o = np.where(on, np.interp(zf, zs, hs) * k + max(out * k, 0.6), o)
        plat |= on
    return o, np.where(plat, 0, g), plat

def cover(a: np.ndarray, b: np.ndarray, xs: np.ndarray) -> np.ndarray:
    # How much of each pixel column (left edges xs) the spans [a, b] cover, by row.
    return np.clip(np.minimum(b[:, None], xs[None, :] + 1) - np.maximum(a[:, None], xs[None, :]), 0, 1)

def mask(tall: float, sub: float) -> tuple[np.ndarray, np.ndarray, int]:
    '''The tower tall px (its tip sub px under a row's top): the coverage by row and column, the platforms' rows and
    the column of its axis. Kept: the same size draws the same.'''
    key = round(tall, 1), round(sub, 1)
    if key in _cache:
        return _cache[key]
    k = tall / tall_m
    rows = math.ceil(tall + sub)
    z = (tall + sub - (np.arange(rows) + 0.5)) / k
    o, g, plat = shape(z, k)
    half = math.ceil(o.max()) + 1
    xs = np.arange(-half, half + 1) - 0.5           # the axis down the middle of a column: odd widths, crisp
    a = cover(-o, o, xs) - cover(-g, g, xs)
    a[z > 290, half] = np.maximum(a[z > 290, half], 0.85)    # the antenna and the top: never thinner than a pixel
    if tall >= lattice_px:
        # The lattice: the legs' crossing bars; the sky through the rest.
        p = max(tall / 45, 3)
        yy, xx = np.mgrid[0:rows, 0:len(xs)]
        d = xx - half
        bars = (np.abs(((yy + d) / p) % 1 - 0.5) > 0.36) | (np.abs(((yy - d) / p) % 1 - 0.5) > 0.36)
        edge = (a > 0) & ((np.roll(a, 1, 1) == 0) | (np.roll(a, -1, 1) == 0) | (np.roll(a, 1, 0) == 0) | (np.roll(a, -1, 0) == 0))
        a = np.where(bars | edge | plat[:, None], a, a * 0.6)
    if len(_cache) > 64:
        _cache.clear()
    _cache[key] = a.astype(np.float32), plat, half
    return _cache[key]

def surface(a: np.ndarray) -> cairo.ImageSurface:
    h, w = a.shape
    stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_A8, w)
    data = np.zeros((h, stride), np.uint8)
    data[:, :w] = np.round(np.clip(a, 0, 1) * 255)
    return cairo.ImageSurface.create_for_data(bytearray(data.tobytes()), cairo.FORMAT_A8, w, h, stride)

def at(x: float, top: float, base: float) -> tuple[np.ndarray, np.ndarray, int, int, int]:
    # The mask for the tower from its tip (top) to its foot (base), x its axis: (coverage, platforms, left, top row).
    tall = max(base - top, 3)
    a, plat, half = mask(tall, top - math.floor(top))
    return a, plat, half, math.floor(x) - half, math.floor(top)

def draw(ctx: cairo.Context, x: float, top: float, base: float, color: tuple):
    a, _, _, x0, y0 = at(x, top, base)
    s = surface(a)
    ctx.set_source_rgb(*color)
    ctx.mask_surface(s, x0, y0)

def lights(ctx: cairo.Context, x: float, top: float, base: float, night: float, haze: float = 0.3):
    '''Lit at night: gold all over, the platforms the brightest, a glow around it in the haze.'''
    a, plat, half, x0, y0 = at(x, top, base)
    s = surface(a)
    if (glow := (0.08 + 0.12 * haze) * night) > 0.02:
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ctx.set_source_rgba(*gold, glow)
            ctx.mask_surface(s, x0 + dx, y0 + dy)
    ctx.set_source_rgba(*gold, 0.8 * night)
    ctx.mask_surface(s, x0, y0)
    if plat.any():
        ctx.set_source_rgba(*gold_floor, 0.7 * night)
        ctx.mask_surface(surface(a * plat[:, None]), x0, y0)

def sparkles(ctx: cairo.Context, x: float, top: float, base: float, night: float, now: float, front: np.ndarray):
    '''Sparkling: white lights all over it, new ones a few times a second; none where what's in front (its top y by
    column) hides it.'''
    a, _, _, x0, y0 = at(x, top, base)
    rnd = random.Random(int(now * 4))
    r, c = np.nonzero(a > 0.45)
    big = base - top >= lattice_px
    i = np.array(rnd.sample(range(len(r)), min(len(r), max(3, round(len(r) * (0.04 if big else 0.12))))), int)
    xs, ys = x0 + c[i], y0 + r[i]
    seen = (xs >= 0) & (xs < len(front))
    seen[seen] &= ys[seen] < front[xs[seen]]
    for grow, alpha in ((1, 0.3), (0, 0.95)) if big else ((0, 0.95),):
        for u, v in zip(xs[seen], ys[seen]):
            ctx.rectangle(int(u) - grow, int(v) - grow, 1 + 2 * grow, 1 + 2 * grow)
        ctx.set_source_rgba(*sparkle, alpha * night)
        ctx.fill()

def lamp(top: float, base: float) -> float:
    # The beacon's y, on the tower from its tip to its foot.
    return top + (base - top) * (1 - lamp_m / tall_m)

def beams(ctx: cairo.Context, x: float, y: float, z: float, now: float, point, to_px, px_rad: float, strength: float,
          w: int):
    '''The beacon's four beams, x, y km from the eye, z m over the sea: each a cone a little up from the horizontal,
    projected from the eye (sideways, a long sweep over the city; at us, a short one and the lamp flaring), fading
    the farther. point(x, y, alt) -> (bearing, elevation) from the eye; px_rad: the view's px a radian, w its width.'''
    d = math.hypot(x, y)
    if strength < 0.01 or d < 0.05:
        return
    ctx.save()
    ctx.set_antialias(cairo.ANTIALIAS_DEFAULT)
    ss = np.r_[0, np.geomspace(0.01, beam_km, 30)]
    up, spread = math.radians(beam_up), math.radians(beam_spread) / 2
    flare = 0
    for j in range(4):
        phi = math.radians(360 * now / beam_turn + 90 * j)
        ux, uy = math.sin(phi) * math.cos(up), math.cos(phi) * math.cos(up)
        flare = max(flare, -(ux * x + uy * y) / d)
        pts = []
        for s in ss:
            px, py = x + ux * s, y + uy * s
            r = math.hypot(px, py)
            if r < 0.3 * d:
                break
            u, v = to_px(*point(px, py, z + s * 1000 * math.sin(up)))
            pts.append((u, v, max(spread * s / r * px_rad, 0.6), strength * beam_alpha * math.exp(-s / beam_fade_km)))
        for (u0, v0, w0, a0), (u1, v1, w1, a1) in zip(pts, pts[1:]):
            n = math.hypot(u1 - u0, v1 - v0)
            if n < 0.01:
                continue
            nx, ny = -(v1 - v0) / n, (u1 - u0) / n
            ctx.move_to(u0 + nx * w0, v0 + ny * w0)
            ctx.line_to(u1 + nx * w1, v1 + ny * w1)
            ctx.line_to(u1 - nx * w1, v1 - ny * w1)
            ctx.line_to(u0 - nx * w0, v0 - ny * w0)
            ctx.close_path()
            ctx.set_source_rgba(1, 0.93, 0.78, min(a0, 0.6) / max(min(w0, 6), 1))
            ctx.fill()
    # The lamp: a point, flaring as a beam comes round at us.
    u, v = to_px(*point(x, y, z))
    f, r = max(flare, 0) ** 40, min(w / 400, 1)
    g = cairo.RadialGradient(u, v, 0, u, v, (2 + 7 * f) * r)
    g.add_color_stop_rgba(0, 1, 0.97, 0.88, min(0.5 + 0.5 * f, 1) * min(strength * 2, 1))
    g.add_color_stop_rgba(1, 1, 0.9, 0.7, 0)
    ctx.set_source(g)
    ctx.arc(u, v, (2 + 7 * f) * r, 0, 2 * math.pi)
    ctx.fill()
    ctx.restore()
