'''The planes as seen from home, out of the window.

The sky over the horizon, the elevation stretched near it (the approaches are a few degrees up), a drawn
Haussmann roofline with a few landmarks where they stand, the sun where it is. A quarter of the compass across,
turned towards the planes seen from the window. The view stays at home: it turns and zooms, never moves.
'''
import math
import time
import random
import numpy as np
import cairocffi as cairo

from functools import cache
from suncalc import get_position

from discore.cairo import to_pil
from discore.elements import Frame, Target
from discore.data_structures import FrameState
from discore.layouts import place_at
from discore.text import TextStyle, text
from disinfo import fonts
from disinfo.config import app_config
from disinfo.screens.solar.app import sky_color

from .state import ADSBxStateManager, OpenedStateManager, DEMO_S, SKY_HOLD
from .colors import marker_color
from .utils import airports, local_xy, bearing
from . import app, astro, skylook, skyline, weather


horizon = 0.6           # of the height, from the top
tilt = (0.45, 0.8)      # where the horizon may go: up to look down on the roofs, down to look up at a plane
tilt_sway, tilt_period = 0.06, 340      # the horizon drifts up and down that much while nothing's followed
elev_gamma = 0.5        # y ~ (elevation / top) ** gamma: the few degrees over the horizon get room
dip_max = 30            # degrees under the horizon at the bottom of the frame, the same stretch
earth_r = 6371
view_fov = 50           # degrees across, most of the time: the waypoints' piece of the skyline
fov_min = 20            # zoomed on a plane
wide_every, wide_for = 900, 45          # s: pulled back to the whole window that long, every so often
tour_dwell, tour_glide = 180, 90        # s: idle, on a sight (every other one the waypoints), then turning to the next
home_ground = 47        # m above the sea
compass = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
horizon_color = (1, 1, 1, 0.25)
sun_color = (1, 0.8, 0.4)
trail_alpha = 0.3       # the numbered planes' trails; the others are dots
dot_alpha = 0.45
sway = 4                # degrees
sway_period = 200       # s
lean_m = 2              # m the eye leans sideways with the sway: the near roofs slide over the far ones
# The roofs, far to near: dark greys, the far ones lighter; a faint rim on their tops.
far_color = (0.075, 0.08, 0.09)
near_color = (0.03, 0.032, 0.036)
hill_color = (0.11, 0.118, 0.13)        # the real roofline's farthest: the hills, hazy
# By day: Paris' limestone in the shade, hazier the farther (towards the horizon's colour): hills, then far to near.
stone_color = (0.27, 0.258, 0.24)
aerial = (0.5, 0.38, 0.26, 0.13, 0.03)          # as hazy as usual; the sky state's haze takes it up to:
aerial_max = 0.92
# The trees by the day of the year: bare (see-through), the new leaves, summer, autumn. (day, rgb, how dense)
leaves = ((0, (0.16, 0.15, 0.14), 0.5), (80, (0.16, 0.15, 0.14), 0.5), (125, (0.16, 0.22, 0.11), 0.95),
          (265, (0.13, 0.2, 0.11), 1), (300, (0.235, 0.2, 0.115), 0.9), (335, (0.22, 0.16, 0.1), 0.65),
          (350, (0.16, 0.15, 0.14), 0.5), (366, (0.16, 0.15, 0.14), 0.5))
leaf_light = (1, 0.85, 0.45)    # the crowns lighter, their leaves catching the light
tree_night = (0.02, 0.026, 0.021)
crown_m = 8             # a tree across: the bumps of the canopy
floor_m = 3             # the eye moved a floor at a time (the web page)
# By day, the facades: some white (Paris has a lot), some lighter stone, the rest as is; the nearer, the more it shows.
facade_white, facade_light = (0.6, 0.6, 0.58), (0.36, 0.35, 0.33)
facade_share = (0.35, 0.65)
tower_m = 70            # m tall and up: a little lighter, like the landmarks, standing out of the roofs
tower_light = (0.75, 0.76, 0.76)
crane_color, crane_streak, crane_night = (0.7, 0.16, 0.12), (0.86, 0.85, 0.82), (0.05, 0.05, 0.055)     # red, white bands
crane_band_m = 6        # a band of the mast or the jib: every third white
floor_dark = 0.35       # the frame darker to its bottom, the near roofs: depth
# The antennas, chimneys and pylons (skyline.py): steel, concrete; the tall ones banded red and white.
mast_color, chimney_color, pylon_color = (0.42, 0.43, 0.45), (0.6, 0.58, 0.55), (0.4, 0.42, 0.45)     # thin steel reads dark
mast_far = 7000, 60     # m away and up: only that tall (the far ones would be a picket fence on the horizon)
mast_banded_m = 100
tv_antenna_m = 2.5      # the TV antennas on the near roofs
crane_work = (210, 45, 35)      # s: a crane's round (turn, then the trolley, then the hook), turning, the trolley moving
tree_m, tree_trunk_m, tree_jitter_m = 13, 0.5, 4      # m: a tree tall, its trunk across, the crowns' heights apart
window_m = 1.5          # a window across, lit at night
window_shape = (1, 1.9, 3.2, 3)       # m: a window wide, tall, a bay, a floor; drawn so once a window is that many px:
window_px = 1.5
floors = 7
glint_rate = 0.03       # the windows sending back a low sun behind us, at most
beacon_color = (1, 0.2, 0.12)           # the lights on the tall ones' tops
beacon_gap = 6          # px between them
beacon_min_m = 80       # m tall and up: the ones lit (the skyline keeps them from 45 m)
band_m = (5000, 2000, 600, 150)         # m: how far the roofs of each band are, far to near (skyline.bands)
rim_color = (1, 1, 1, 0.15)
day_face = (1, 0.93, 0.8)       # the sun on the facades, by day
day_face_alpha, day_rim_alpha = 0.07, 0.3
label_style = TextStyle(font=fonts.microfont_35_reg, color='#8b8e94b0')

# Seen over the roofs, where they stand: (name, lat, lon, height m, ground m over the sea, width m, shape).
landmarks = [
    ('mercuriales', 48.8636, 2.4128, 122, 95, 30, 'twin'),
    ('vincennes', 48.8428, 2.4364, 52, 55, 30, 'keep'),
    ('sacre-coeur', 48.8867, 2.3431, 83, 130, 60, 'dome'),
    ('duo', 48.8273, 2.3779, 180, 40, 40, 'tower'),
    ('bnf', 48.8336, 2.3763, 79, 35, 120, 'twin'),
    ('montparnasse', 48.8421, 2.3220, 210, 60, 50, 'tower'),
    ('eiffel', 48.8584, 2.2945, 330, 35, 125, 'eiffel'),
]

# The demo (the web page's button): once around, slowly, through the skies one may see. Each scene: the sun (degrees
# up, its bearing), the day of the year, the clock; the cloud, the haze, the deck, the cirrus, the rain, its snow, the wind.
demo_scenes = (
    ('morning', (8, 100), 140, (8, 30), 0.1, 0.25, 0, 0.3, 0, 0, 2),
    ('noon', (58, 180), 180, (13, 0), 0.05, 0.15, 0, 0, 0, 0, 2),
    ('hazy autumn', (30, 200), 295, (14, 0), 0.25, 0.85, 0.1, 0.2, 0, 0, 1),
    ('overcast', (25, 210), 320, (15, 0), 0.9, 0.35, 0.9, 0, 0, 0, 4),
    ('rain', (20, 220), 320, (15, 30), 0.95, 0.5, 0.95, 0, 0.7, 0, 6),
    ('snow', (12, 200), 20, (14, 0), 0.9, 0.5, 0.9, 0, 0.6, 1, 3),
    ('fog', (6, 130), 330, (9, 0), 0.5, 1, 0.3, 0, 0, 0, 0),
    ('wind', (40, 200), 120, (13, 0), 0.4, 0.2, 0.45, 0.4, 0, 0, 11),
    ('sunset', (1, 250), 250, (19, 30), 0.15, 0.3, 0.1, 0.4, 0, 0, 2),
    ('dusk', (-5, 265), 250, (20, 15), 0.1, 0.25, 0.05, 0.2, 0, 0, 1),
    ('night', (-25, 330), 250, (22, 2), 0.05, 0.2, 0, 0, 0, 0, 1),
    ('cloudy night', (-30, 350), 340, (23, 0), 0.85, 0.3, 0.85, 0, 0, 0, 3),
)
demo_blend = 2          # s from one to the next
_demo = {}              # screen -> (the demo's start, the yaw it started at)

_cams = {}              # screen -> [yaw, fov, at]: eases towards the view
_roofs = {}             # screen -> (what they're drawn for, the layer, its rows)
_held = {}              # screen -> the yaw: turned only when what it looks at has moved away
_eye = {'m': home_ground + app_config.aviator_eye_m}


def wrap(a: float) -> float:
    return (a + 180) % 360 - 180

def sky_point(x: float, y: float, alt: float) -> tuple[float, float]:
    # Bearing and elevation, seen from the window, of a point km east, km north, m over the sea. The earth curves away.
    d = max(math.hypot(x, y), 0.01)
    return bearing(x, y), math.degrees(math.atan2(alt - _eye['m'], d * 1000)) - math.degrees(d / (2 * earth_r))

@cache
def city() -> tuple[list, list]:
    '''The roofline all around, in degrees: (far, near) blocks of (from, to, cornice, mansard's top, chimneys).

    Six floors and a mansard, the far ones about the horizon, the near ones under it (from the 11th floor one
    looks down on them). Drawn once, the same every time.
    '''
    rnd = random.Random(1853)       # Haussmann's year
    def row(widths, cornice, mansard, tall):
        blocks, b = [], 0.0
        while b < 360:
            w = rnd.uniform(*widths)
            c = cornice + rnd.uniform(-0.25, 0.25) + (tall if rnd.random() < 0.08 else 0)
            chimneys = [b + w * rnd.uniform(0.15, 0.85) for _ in range(rnd.randint(0, 3))]
            blocks.append((b, b + w, c, c + mansard * rnd.uniform(0.7, 1.2), chimneys))
            b += w
        return blocks
    return row((0.8, 2.2), -0.1, 0.25, 0.6), row((2.5, 5), -1.2, 0.5, 0.4)

def landmark_points(eye: float) -> list[tuple]:
    # (bearing, elevation of the top, angular width, shape) from the window.
    out = []
    for _, lat, lon, height, ground, width, shape in landmarks:
        x, y = local_xy(lat, lon)
        d = math.hypot(x, y) * 1000
        out.append((bearing(x, y), math.degrees(math.atan2(ground + height - eye, d)), math.degrees(width / d), shape))
    return out

def landmark_km() -> list[float]:
    return [math.hypot(*local_xy(lat, lon)) for _, lat, lon, *_ in landmarks]

def roofs(ctx: cairo.Context, in_view, to_px, h: int, sunlight: tuple[float, float] | None = None, rim: tuple = rim_color,
          daylit: tuple[float, float] | None = None):
    # Pixel-crisp: sharp on the LEDs, and nothing changes between frames when the view's still.
    ctx.set_antialias(cairo.ANTIALIAS_NONE)
    far, near = city()
    for blocks, color in ((far, far_color), (near, near_color)):
        rims, lit, faces = [], [], []
        for b0, b1, cornice, top, chimneys in blocks:
            if not (in_view(b0, 5) or in_view(b1, 5)):
                continue
            (x0, yc), (x1, _) = to_px(b0, cornice), to_px(b1, cornice)
            _, yt = to_px(0, top)
            inset = (x1 - x0) * 0.12
            outline = [(x0, yc), (x0 + inset, yt), (x1 - inset, yt), (x1, yc)]
            ctx.move_to(x0, h)
            for p in outline:
                ctx.line_to(*p)
            ctx.line_to(x1, h)
            ctx.close_path()
            for c in chimneys:
                cx, _ = to_px(c, top)
                ctx.rectangle(round(cx), round(yt) - 2, 1, 2)
            rims.append(outline)
            if sunlight and (k := max(0, 1 - abs(wrap((b0 + b1) / 2 - sunlight[0])) / 70) * sunlight[1]) > 0.03:
                lit.append((outline, k, x0, x1, yc, b0))
            # By day: the facades turned to the sun (it's behind us when they face us), as much as it's out.
            if daylit and (k := math.cos(math.radians(wrap((b0 + b1) / 2 + 180 - daylit[0]))) * daylit[1]) > 0.05:
                faces.append((outline, k, x0, x1, yc, b0))
        ctx.set_source_rgb(*color)
        ctx.fill()
        ctx.set_source_rgba(*rim)     # wet: shining with the rain's light
        for outline in rims:
            ctx.move_to(*outline[0])
            for p in outline[1:]:
                ctx.line_to(*p)
        ctx.stroke()
        for outline, k, x0, x1, yc, b0 in faces:
            ctx.move_to(x0, h)
            for p in outline:
                ctx.line_to(*p)
            ctx.line_to(x1, h)
            ctx.close_path()
            ctx.set_source_rgba(*day_face, day_face_alpha * k)
            ctx.fill()
            ctx.set_source_rgba(*day_face, day_rim_alpha * k)
            ctx.move_to(*outline[0])
            for p in outline[1:]:
                ctx.line_to(*p)
            ctx.stroke()
            # A window here and there sends the sun back: the same ones every frame.
            rnd = random.Random(round(b0 * 1000) + 7)
            for _ in range(max(1, round((x1 - x0) / 6))):
                if rnd.random() < 0.5:
                    ctx.set_source_rgba(1, 0.95, 0.8, min(0.8 * k, 0.8) * rnd.uniform(0.4, 1))
                    ctx.rectangle(round(rnd.uniform(x0 + 1, x1 - 1)), round(yc + rnd.uniform(2, 12)), 1, 1)
                    ctx.fill()
        # The sunset on the roofs facing it: a warm rim and a few windows catching it.
        for outline, k, x0, x1, yc, b0 in lit:
            ctx.set_source_rgba(*(c / 255 for c in skylook.glow_rgb), min(0.75 * k, 0.75))
            ctx.move_to(*outline[0])
            for p in outline[1:]:
                ctx.line_to(*p)
            ctx.stroke()
            rnd = random.Random(round(b0 * 1000))
            for _ in range(max(1, round((x1 - x0) / 3))):
                ctx.set_source_rgba(1, 0.75, 0.45, min(0.9 * k, 0.85) * rnd.uniform(0.5, 1))
                ctx.rectangle(round(rnd.uniform(x0, x1)), round(yc + rnd.uniform(2, 14)), 1, 1)
                ctx.fill()
    ctx.set_source_rgb(*far_color)
    shapes(ctx, landmark_points(_eye['m']), in_view, to_px)
    ctx.set_antialias(cairo.ANTIALIAS_DEFAULT)

def shapes(ctx: cairo.Context, points: list, in_view, to_px):
    # The landmarks drawn, filled in the colour set.
    for b, e, width, shape in points:
        if not in_view(b, 5):
            continue
        x, y = to_px(b, e)
        _, base = to_px(b, -1)
        wpx = max(1, round(to_px(b + width / 2, 0)[0] - to_px(b - width / 2, 0)[0]))
        x, y, base = round(x), round(y), round(base)
        match shape:
            case 'twin':
                ctx.rectangle(x - wpx, y, max(1, wpx * 2 // 3), base - y)
                ctx.rectangle(x + wpx // 3, y, max(1, wpx * 2 // 3), base - y)
            case 'keep':
                ctx.rectangle(x - wpx // 2, y, wpx, base - y)
                ctx.rectangle(x - wpx // 2 - 1, y - 1, 1, 1)
                ctx.rectangle(x + wpx // 2, y - 1, 1, 1)
            case 'dome':
                ctx.rectangle(x - wpx // 2, y + 2, wpx, base - y - 2)
                ctx.arc(x, y + 2, max(wpx / 3, 1), math.pi, 0)
            case 'eiffel':
                ctx.move_to(x - wpx / 2, base)
                ctx.line_to(x, y)
                ctx.line_to(x + wpx / 2, base)
            case _:
                ctx.rectangle(x - wpx // 2, y, wpx, base - y)
        ctx.fill()

def runs(v: np.ndarray) -> list[tuple[int, int, int]]:
    # (from, to, value) of the stretches where v stays the same.
    cut = [0, *(np.flatnonzero(np.diff(v)) + 1), len(v)]
    return [(a, b, int(v[a])) for a, b in zip(cut, cut[1:])]

def season(doy: int) -> tuple[tuple, float]:
    # The trees' colour and how dense they are, that day of the year.
    days = [d for d, _, _ in leaves]
    return tuple(float(np.interp(doy, days, [c[i] for _, c, _ in leaves])) for i in range(3)), float(np.interp(doy, days, [k for *_, k in leaves]))

def mix(a: tuple, b: tuple, k: float) -> tuple:
    return tuple(x + (y - x) * k for x, y in zip(a, b))

def real_roofs(ctx: cairo.Context, sk: skyline.Skyline, yaw: float, fov: float, w: int, h: int, to_y,
               sunlight: tuple[float, float] | None = None, rim: tuple = rim_color, daylit: tuple[float, float] | None = None,
               night: float = 0, day: float = 0, haze: tuple = hill_color, lean: float = 0, hazy: float = 0.2,
               today: tuple | None = None, dz: float = 0, now: float | None = None) -> np.ndarray:
    '''The roofline from the window (skyline.py), a pixel's column at a time: the hills, then the roofs far to near,
    each band's trees in front of its roofs. Paris' stone by day, hazier the farther; the eye leaned lean m to the
    right, the nearer slide the more. Lit the same as the drawn one: the sun on the facades, the sunset on the tops
    facing it, a window sending back a low sun behind us. At night the windows light up here and there, each in its
    place, on and off over the evening: window-shaped once they're big enough. dz m: the eye moved up (down under 0),
    each band as much higher as it's near (the same occlusion); the landmarks and the cranes stand out a little.
    The rows drawn, for the beacons over them.'''
    ctx.set_antialias(cairo.ANTIALIAS_NONE)
    step, nb = fov / w, len(band_m)
    eye_m, sk = sk.eye[2], sk.lifted(dz)
    # By band, the hills (they don't move) to the near: what its columns show.
    shifts = [0] + [math.degrees(lean / d) for d in band_m]
    bss = [yaw - fov / 2 + (np.arange(w) + 0.5) * step + s for s in shifts]
    rows = np.stack([sk.columns(yaw - fov / 2 + s, step, w, sk.p[nb - n:nb - n + 1])[0] for n, s in enumerate(shifts)])
    woods = [sk.columns(yaw - fov / 2 + s, step, w, sk.t[nb - n:nb - n + 1])[0] if sk.t is not None and n else None
             for n, s in enumerate(shifts)]
    # How far the trees are, to stand them on the ground (an older skyline: their band's).
    wood_m = [sk.columns(yaw - fov / 2 + s, step, w, sk.td[nb - n:nb - n + 1])[0] if sk.td is not None and n else
              np.full(w, band_m[n - 1], np.float32) if n else None for n, s in enumerate(shifts)]
    if sk.pd is None:
        # An older skyline, without how far its roofs are: each band as far as it's said to be.
        for n, d in enumerate((15000, *band_m)):
            lift = math.degrees(math.atan(-dz / d))
            rows[n] = np.where(rows[n] > -90, rows[n] + lift, -90)
            if woods[n] is not None:
                woods[n] = np.where(woods[n] > -90, woods[n] + lift, -90)
    rows[0] = np.maximum(rows[0], 0)       # the land reaches the horizon: none of the sky under it (down the valley)
    # What stands out, by band: the landmarks in reach and the towers, (bearing, degrees up, degrees wide, m tall);
    # the cranes, (x, y m from the eye, mast, jib, m away).
    ex, ey = (v * 1000 for v in local_xy(*sk.eye[:2]))
    eye = eye_m + dz
    marks = [(b, e, wd, lm[3], km * 1000) for (b, e, wd, _), lm, km in zip(landmark_points(eye), landmarks, landmark_km()) if km < skyline.reach_km]
    marks += [(b, e + math.degrees(math.atan(-dz / d)), math.degrees(35 / d), tall, d) for b, e, d, tall in sk.beacons if tall >= tower_m]
    standing = [[] for _ in rows]
    for m in marks:
        standing[nb - int(np.searchsorted(skyline.bands, m[4]))].append(m)
    crane_at, mast_at = [[] for _ in rows], [[] for _ in rows]
    for x, y, top, tall, kind in sk.masts:
        d = math.hypot(x, y)
        if abs(wrap(math.degrees(math.atan2(x, y)) - yaw)) < fov / 2 + 2 and (d < mast_far[0] or tall >= mast_far[1]):
            mast_at[nb - int(np.searchsorted(skyline.bands, d))].append((x, y, top, tall, kind, d))
    for lat, lon, mast, jib in app_config.screen_data.aviator.cranes:
        x, y = (v * 1000 - o for v, o in zip(local_xy(lat, lon), (ex, ey)))
        crane_at[nb - int(np.searchsorted(skyline.bands, math.hypot(x, y)))].append((x, y, mast, jib, math.hypot(x, y)))
    t = time.localtime()
    today = today or (t.tm_yday, t.tm_hour, t.tm_min)
    leaf, dense = season(today[0])
    # The haze between: the sky state's (the visibility, the fog), the farther the more.
    aer = [min(a * (0.7 + 1.5 * hazy), aerial_max) for a in aerial]
    sb = sunlight[0] if sunlight else daylit[0] if daylit else 0
    now = time.time() if now is None else now
    for n, row in enumerate(rows):
        k = n / (len(rows) - 1)
        bs = bss[n]
        ys = np.minimum(np.round(to_y(row)), h).astype(int)
        top = runs(ys)
        ctx.move_to(0, h)
        for a, b, y in top:
            ctx.line_to(a, y)
            ctx.line_to(b, y)
        ctx.line_to(w, h)
        ctx.close_path()
        far = mix(stone_color, (0.55 * c for c in haze), aer[n])
        ctx.set_source_rgb(*mix(mix(hill_color, near_color, k), far, day))
        ctx.fill()
        if n == 0:
            # The landmarks out of the buildings' reach (the Eiffel tower) over the hills, in the far roofs' colour.
            ctx.set_source_rgb(*mix(mix(hill_color, near_color, 0.25), mix(stone_color, (0.55 * c for c in haze), aer[1]), day))
            to_x = lambda b: w / 2 + wrap(b - yaw) / fov * w
            far_ones = [p for p, d in zip(landmark_points(eye), landmark_km()) if d > skyline.reach_km]
            to_px = lambda b, e: (to_x(b), float(to_y(np.array([e]))[0]))
            ctx.set_source_rgb(*mix(mix(hill_color, near_color, 0.25), mix(mix(stone_color, (0.42, 0.37, 0.31), 0.4), (0.55 * c for c in haze), aer[1]), day))
            shapes(ctx, far_ones, lambda b, m=0: abs(wrap(b - yaw)) < fov / 2 + m, to_px)
            eiffel(ctx, [p for p in far_ones if p[3] == 'eiffel'], yaw, fov, to_px, night, now, today[1:])
            continue
        # The windows by bearing, a fifth of a degree each: they stay where they are when the view turns.
        cell = np.floor(bs * 5)
        r = (np.sin(cell * 12.9898) * 43758.5453) % 1
        off = lambda b: np.abs((b + 180) % 360 - 180)
        glow = np.clip(1 - off(bs - sunlight[0]) / 70, 0, None) * sunlight[1] if sunlight else np.zeros(w)
        face = np.cos(np.radians(bs + 180 - daylit[0])) * daylit[1] if daylit else np.zeros(w)
        on = ys < h
        px_m = w / math.radians(fov) / band_m[n - 1]
        if day > 0.05:
            # The facades' tones, each building its own (by its roof's height: the same as the view turns), the nearer
            # the more; the landmarks and the towers a little lighter, their own tops' rim too.
            # Only the facades wide enough to tell (the far bands' are a pixel each: stripes).
            show = day * (1 - aer[n]) * (0.35 + 0.65 * k)
            spans = [(a, b, y, (math.sin(round(float(row[a]) * 20) * 12.9898) * 43758.5453) % 1) for a, b, y in top if y < h and b - a >= 4]
            for lo, hi, c in ((0, facade_share[0], facade_white), (facade_share[0], facade_share[1], facade_light)):
                for a, b, y, tone in spans:
                    if lo <= tone < hi:
                        ctx.rectangle(a, y, b - a, h - y)
                ctx.set_source_rgba(*mix(c, (0.55 * c_ for c_ in haze), aer[n]), 0.45 * show)
                ctx.fill()
            for b, e, wd, tall, d in standing[n]:
                xc, half = w / 2 + wrap(b - shifts[n] - yaw) / step, max(wd / 2 / step, 1)
                xs = np.arange(max(int(xc - half), 0), min(int(xc + half) + 1, w))
                xs = xs[on[xs] & (row[xs] >= e - 0.6)] if len(xs) else xs
                for x in xs:
                    ctx.rectangle(int(x), int(ys[x]), 1, max(round(tall * w / math.radians(fov) / d), 1))
                ctx.set_source_rgba(*tower_light, (0.1 + 0.12 * k) * day)
                ctx.fill()
                for x in xs:
                    ctx.rectangle(int(x), int(ys[x]), 1, 1)
                ctx.set_source_rgba(*tower_light, 0.35 * day)
                ctx.fill()
        # By day: the facades turned to the sun (it's behind us when they face us), as much as it's out.
        for level in range(1, 5):
            sel = on & (np.ceil(face * 4) == level) & (face > 0.05)
            if sel.any():
                for a, b, v in runs(np.where(sel, ys + 1, 0)):
                    if v:
                        ctx.rectangle(a, v - 1, b - a, h)
                ctx.set_source_rgba(*day_face, day_face_alpha * level / 4)
                ctx.fill()
        for a, b, y in top:
            if y < h:
                ctx.rectangle(a, y, b - a, 1)
        ctx.set_source_rgba(*rim)     # wet: shining with the rain's light
        ctx.fill()
        # The sunset on the tops facing it.
        for level in range(1, 5):
            sel = on & (np.ceil(glow * 4) == level) & (glow > 0.03)
            if sel.any():
                for x in np.flatnonzero(sel):
                    ctx.rectangle(int(x), int(ys[x]), 1, 1)
                ctx.set_source_rgba(*(c / 255 for c in skylook.glow_rgb), 0.75 * level / 4)
                ctx.fill()
        # A low sun behind us: a few of the windows facing it send it back. At night, the lit ones: the nearer, the
        # more of them and the deeper down the facade; a few have the TV's blue. Dimmer the farther; a soft halo once
        # a window is a pixel or more.
        catch = np.clip(np.cos(np.radians(bs + 180 - sb)), 0, None) * (sunlight[1] if sunlight else 0)
        px = window_m * px_m
        alpha = 0.1 + 0.2 * min(px / 2, 1)
        if px >= window_px:
            panes(ctx, bs, ys, on, px_m, n, now, catch, night, alpha, h)
        else:
            lit = on & (r < glint_rate * catch)
            for x in np.flatnonzero(lit):
                ctx.rectangle(int(x), int(ys[x] + 2 + (r[x] * 97 % 1) * 8), 1, 1)
            ctx.set_source_rgba(1, 0.85, 0.6, 0.7)
            ctx.fill()
            if night > 0.05:
                q = (np.sin(cell * 78.233 + n * 31.7 + np.floor(now / 600 + r * 7)) * 43758.5453) % 1
                on_ = on & (q < night * 0.09 * (0.4 + k))
                size = min(max(round(px), 1), 3)
                for cool in (False, True):
                    spots = [(int(x), int(ys[x] + 2 + (q[x] * 37 % 1) * (4 + 24 * k))) for x in np.flatnonzero(on_ & ((q * 113 % 1 < 0.15) == cool))]
                    color = (0.65, 0.75, 1) if cool else (1, 0.78, 0.45)
                    for grow, a in ((1, alpha * 0.35), (0, alpha)) if px >= 0.9 else ((0, alpha),):
                        for x, y in spots:
                            ctx.rectangle(x - grow, y - grow, size + 2 * grow, size + 2 * grow)
                        ctx.set_source_rgba(*color, a)
                        ctx.fill()
        if woods[n] is not None and (woods[n] > -90).any():
            trees(ctx, woods[n], wood_m[n], bs, step, band_m[n - 1], px_m, to_y, h,
                  mix(mix(tree_night, near_color, 0.6 * (1 - k)), mix(leaf, (0.55 * c for c in haze), aer[n]), day), dense, day,
                  mix(mix(hill_color, near_color, k), far, day))
        if mast_at[n]:
            masts(ctx, mast_at[n], eye, yaw - shifts[n], fov, w, to_y, ys, aer[n], haze, day, night)
        if n >= nb - 1 and px_m * tv_antenna_m >= 2:
            # The TV antennas on the near roofs: one or two on some, each in its place on its roof.
            dark = mix(mix(mix(hill_color, near_color, k), far, day), (0, 0, 0), 0.35)
            hgt, arm = max(round(tv_antenna_m * px_m), 2), max(round(1.2 * px_m), 2)
            for a, b, y, tone in ((a, b, y, (math.sin(round(float(row[a]) * 20) * 78.233) * 43758.5453) % 1) for a, b, y in top if y < h and b - a >= 8):
                for j in range(int(tone * 3) if tone > 0.35 else 0):
                    ax = a + int((b - a) * ((tone * (7 + 5 * j)) % 0.8 + 0.1))
                    ctx.rectangle(ax, y - hgt, 1, hgt)
                    ctx.rectangle(ax - arm // 2, y - hgt, arm, 1)
                    ctx.rectangle(ax - arm // 3, y - hgt + max(hgt // 3, 1), max(arm * 2 // 3, 1), 1)
            ctx.set_source_rgb(*dark)
            ctx.fill()
        if crane_at[n]:
            cranes(ctx, crane_at[n], eye, yaw - shifts[n], fov, w, to_y,
                   *(mix(crane_night, mix(c, (0.55 * c_ for c_ in haze), aer[n]), day) for c in (crane_color, crane_streak)), night, now)
    ctx.set_antialias(cairo.ANTIALIAS_DEFAULT)
    return rows

def masts(ctx: cairo.Context, items: list, eye: float, yaw: float, fov: float, w: int, to_y, roof: np.ndarray,
          aer: float, haze: tuple, day: float, night: float):
    '''The antennas (a thin lattice, its arms), the chimneys (tapering), the pylons (a lattice tapering to its arms):
    (x, y m from the eye, top m over the sea, m tall, kind, m away). From over the roofs in front of them (roof: the
    band's, px); the tall ones banded red and white, a red light on their tops at night.'''
    deg = w / fov
    for x, y, top, tall, kind, d in items:
        cx = w / 2 + wrap(math.degrees(math.atan2(x, y)) - yaw) * deg
        if not 0 <= cx < w:
            continue
        px = w / math.radians(fov) / d
        ty = float(to_y(np.array([math.degrees(math.atan2(top - eye, d))]))[0])
        by = min(float(to_y(np.array([math.degrees(math.atan2(top - tall - eye, d))]))[0]), float(roof[int(cx)]))
        if by - ty < 1:
            continue
        base = {'antenna': mast_color, 'chimney': chimney_color, 'pylon': pylon_color}[kind]
        c = mix(mix(near_color, (0.6 * v for v in haze), 0.5 * aer), mix(base, (0.55 * v for v in haze), 0.6 * aer), day)
        red, white = (mix(mix(near_color, (0.6 * v for v in haze), 0.5 * aer), mix(v, (0.55 * q for q in haze), aer), day)
                      for v in (crane_color, crane_streak))
        frac = lambda m: ty + (by - ty) * min(m / max(tall, 1), 1)     # m down from the top, px
        half = lambda m: max(m * px / 2, 0.5)
        ctx.set_source_rgb(*c)
        if kind == 'chimney':
            top_w, base_w = half(6), half(9)
            ctx.move_to(cx - top_w, ty)
            ctx.line_to(cx + top_w, ty)
            ctx.line_to(cx + base_w, by)
            ctx.line_to(cx - base_w, by)
            ctx.close_path()
            ctx.fill()
            if tall >= mast_banded_m:
                for j, cc in enumerate((red, white, red)):
                    ctx.rectangle(round(cx - top_w), round(frac(j * 6)), max(round(2 * top_w), 1), max(round(frac(6) - ty), 1))
                    ctx.set_source_rgb(*cc)
                    ctx.fill()
        elif kind == 'pylon':
            # Tapering from 10 m at its foot to 2 m under its arms; the arms 14 and 10 m across, near the top.
            w0, w1 = half(10), half(2)
            yb = frac(tall)
            ctx.move_to(round(cx - w0) + 0.5, round(yb))
            ctx.line_to(round(cx - w1) + 0.5, round(ty))
            ctx.line_to(round(cx + w1) + 0.5, round(ty))
            ctx.line_to(round(cx + w0) + 0.5, round(yb))
            if w0 >= 2:
                for j in range(6):
                    y0, y1 = frac(tall * (1 - j / 6)), frac(tall * (1 - (j + 1) / 6))
                    k0, k1 = w0 + (w1 - w0) * j / 6, w0 + (w1 - w0) * (j + 1) / 6
                    ctx.move_to(round(cx - k0) + 0.5, round(y0))
                    ctx.line_to(round(cx + k1) + 0.5, round(y1))
            for m, arm in ((0.12 * tall, 7), (0.28 * tall, 5)):
                ctx.move_to(round(cx - half(2 * arm)) + 0.5, round(frac(m)) + 0.5)
                ctx.line_to(round(cx + half(2 * arm)) + 0.5, round(frac(m)) + 0.5)
            ctx.set_line_width(1)
            ctx.stroke()
        else:
            # The antenna: 2 m of lattice (a line once it's that thin), a few arms near its top.
            hw = half(2)
            ctx.rectangle(round(cx - hw), round(ty), max(round(2 * hw), 1), max(round(by - ty), 1))
            ctx.fill()
            for m in (0.06, 0.14):
                ctx.rectangle(round(cx - half(5)), round(frac(m * tall)), max(round(2 * half(5)), 1), 1)
            ctx.fill()
            if tall >= mast_banded_m:
                band = max((by - ty) / 7, 1)
                for j in range(0, 7, 2):
                    ctx.rectangle(round(cx - hw), round(ty + j * band), max(round(2 * hw), 1), max(round(band), 1))
                ctx.set_source_rgb(*red)
                ctx.fill()
        if night > 0.05 and tall >= 45:
            for ly in ((ty, (ty + by) / 2) if tall >= mast_banded_m else (ty,)):
                ctx.set_source_rgba(*beacon_color, 0.85 * night)
                ctx.rectangle(round(cx), round(ly), 1, 1)
                ctx.fill()

def cranes(ctx: cairo.Context, items: list, eye: float, yaw: float, fov: float, w: int, to_y, color: tuple,
           streak: tuple, night: float, now: float):
    '''Tower cranes, (x, y m from the eye, mast, jib m, m away): a lattice mast and jib once they're wide enough, the
    counter-jib and its weight, the ties from the top, the trolley and its hook; each jib turning slowly its own way.
    At night dark, a red light on the top and the jib's end.'''
    def to(x, y, z):
        d = max(math.hypot(x, y), 1)
        return w / 2 + wrap(math.degrees(math.atan2(x, y)) - yaw) / fov * w, float(to_y(np.array([math.degrees(math.atan2(z - eye, d))]))[0])
    def line(*ps):
        ctx.move_to(round(ps[0][0]) + 0.5, round(ps[0][1]) + 0.5)
        for p in ps[1:]:
            ctx.line_to(round(p[0]) + 0.5, round(p[1]) + 0.5)
    for x, y, mast, jib, d in items:
        bx, by = to(x, y, home_ground)
        if not -jib / d * w / math.radians(fov) < bx < w * (1 + jib / d / math.radians(fov)):
            continue
        # At work, each its own round: turning to its next heading (mostly side on from here, the jib's length shows),
        # then the trolley going out or in, then the hook down and up again; eased, slow.
        phase = (x * 0.37 + y * 0.61) % 1
        period, turn, roll = crane_work
        k, into = divmod(now / period + phase, 1)
        into *= period
        pick = lambda j, s: (math.sin(j * s + phase * 91) * 43758.5453) % 1
        ease = lambda v: (v := min(max(v, 0), 1)) * v * (3 - 2 * v)
        side = math.degrees(math.atan2(x, y)) + 90
        a0, a1 = side + 100 * (pick(k - 1, 12.9898) - 0.5), side + 100 * (pick(k, 12.9898) - 0.5)
        heading = math.radians(a0 + wrap(a1 - a0) * ease(into / turn))
        s0, s1 = 0.3 + 0.6 * pick(k - 1, 39.346), 0.3 + 0.6 * pick(k, 39.346)
        trolley = jib * (s0 + (s1 - s0) * ease((into - turn) / roll))
        dip = math.sin(math.pi * ease((into - turn - roll) / (period - turn - roll - 20)))
        ux, uy = math.sin(heading), math.cos(heading)
        top, head = home_ground + mast, home_ground + mast + 0.14 * jib
        px = w / math.radians(fov) / d
        tx, ty = to(x, y, top)
        # Its head linear from the mast's top: the view's easing near the horizon would stretch a few m into many px.
        def at(s, z):
            px_, py_ = x + ux * s, y + uy * s
            dp = max(math.hypot(px_, py_), 1)
            return (to(px_, py_, top)[0], ty - ((z - eye) / dp - (top - eye) / d) * w / math.radians(fov))
        half = max(px, 0.5)         # the mast 2 m across
        ctx.set_source_rgb(*color)
        if 2 * half >= 2:
            # The lattice: its two sides, the bracing zigzag every 2 m.
            line((tx - half, ty), (bx - half, by))
            line((tx + half, ty), (bx + half, by))
            k = max(int(mast / 2), 1) if 2 * half >= 4 else 0
            for j in range(k):
                y0, y1 = ty + (by - ty) * j / k, ty + (by - ty) * (j + 1) / k
                line((tx - half if j % 2 else tx + half, y0), (tx + half if j % 2 else tx - half, y1))
        else:
            line((tx, ty), (bx, by))
        hx, hy = at(0, head)
        line((tx - half, ty), (hx, hy), (tx + half, ty))
        # The jib: two chords, braced when they're apart; the counter-jib behind, its weight.
        tip, tip_up = at(jib, top), at(jib, top + 1.6)
        line((tx, ty), tip)
        if abs(tip_up[1] - tip[1]) + abs(at(0, top + 1.6)[1] - ty) >= 4:
            line(at(0, top + 1.6), tip_up)
            k = max(int(jib / 3), 1)
            for j in range(k):
                line(at(jib * j / k, top + (1.6 if j % 2 else 0)), at(jib * (j + 1) / k, top + (0 if j % 2 else 1.6)))
        back = at(-0.3 * jib, top)
        line((tx, ty), back)
        line(at(0.6 * jib, top + 1.6), (hx, hy), back)
        ctx.stroke()
        # The white bands: every third along the mast and the jib.
        k = max(int(mast / crane_band_m), 1)
        for j in range(1, k, 3):
            y0, y1 = ty + (by - ty) * j / k, ty + (by - ty) * (j + 1) / k
            ctx.rectangle(round(tx - half), round(y0), max(round(2 * half), 1) + 1, max(round(y1 - y0), 1))
        ctx.set_source_rgb(*streak)
        ctx.fill()
        k = max(int(jib / crane_band_m), 1)
        for j in range(1, k, 3):
            line(at(jib * j / k, top), at(jib * (j + 1) / k, top))
            line(at(jib * j / k, top + 1.6), at(jib * (j + 1) / k, top + 1.6))
        ctx.stroke()
        ctx.set_source_rgb(*color)
        cw = [at(-0.3 * jib, top), at(-0.22 * jib, top), at(-0.22 * jib, top - 3), at(-0.3 * jib, top - 3)]
        ctx.move_to(*cw[0])
        for p in cw[1:]:
            ctx.line_to(*p)
        ctx.close_path()
        ctx.fill()
        # The trolley going in and out, its hook up and down.
        s = trolley
        drop = mast * (0.08 + 0.35 * dip)
        (ax, ay), (cx, cy) = at(s, top), at(s, top - drop)
        line((ax, ay), (ax, cy))
        ctx.set_source_rgba(*color, 0.55)
        ctx.stroke()
        ctx.set_source_rgb(*color)
        ctx.rectangle(round(ax) - (1 if px > 1 else 0), round(cy), 2 if px > 1 else 1, 2 if px > 1 else 1)
        ctx.fill()
        if night > 0.05:
            for lx, ly in ((hx, hy), tip):
                g = cairo.RadialGradient(round(lx) + 0.5, ly, 0, round(lx) + 0.5, ly, 3)
                g.add_color_stop_rgba(0, *beacon_color, 0.45 * night)
                g.add_color_stop_rgba(1, *beacon_color, 0)
                ctx.set_source(g)
                ctx.arc(round(lx) + 0.5, ly, 3, 0, 2 * math.pi)
                ctx.fill()
                ctx.set_source_rgba(*beacon_color, 0.9 * night)
                ctx.rectangle(round(lx), round(ly), 1, 1)
                ctx.fill()
            ctx.set_source_rgb(*color)

def trees(ctx: cairo.Context, top: np.ndarray, far: np.ndarray, bs: np.ndarray, step: float, d: float, px_m: float, to_y,
          h: int, color: tuple, dense: float, day: float, base: tuple = near_color):
    '''A band's trees, d m away: crowns every few m in two rows, the back one between the front one's, each its own
    size, height and a lobe, darker under; on trunks once they're a pixel. The band's facades show under and between
    them. By day each crown its shade, the near ones' leaves catching the light here and there, the tops in it.
    Where the wood's end is under a crown's middle it's left out. Placed by bearing: they stay as the view turns.
    Each stands on the ground, far m away: as tall as the view makes a tree there (the crown its upper part, a trunk
    under it, a shadow at its foot), like the buildings around it.'''
    w = len(bs)
    def oval(x, y, rx, ry, a0=0, a1=2 * math.pi):
        ctx.new_sub_path()
        ctx.save()
        ctx.translate(x, y)
        ctx.scale(rx, ry)
        ctx.arc(0, 0, 1, a0, a1)
        ctx.restore()
    dense = 1 if dense > 0.8 else dense     # in leaf: solid; bare, the facades through the branches
    cw = math.degrees(crown_m / d)
    r_px = 0.5 * crown_m / d / math.radians(step)
    fine = r_px >= 3        # crowns a few px across: the back row, the shades, round; under that a canopy's enough
    for back, off in ((True, 0.5), (False, 0)) if fine else ((False, 0),):
        i = np.arange(math.floor(bs[0] / cw + off) - 1, math.ceil(bs[-1] / cw + off) + 2)
        x = ((i + 0.5 - off) * cw - bs[0]) / step + 0.5
        xm = np.round(x).astype(int)
        ok = (xm >= 0) & (xm < w)
        i, x, xm = i[ok], x[ok], xm[ok]
        ok = top[xm] > -90
        i, x, xm = i[ok], x[ok], xm[ok]
        if not len(i):
            continue
        r1, r2, r3, r4 = ((np.sin(i * s + off * 17) * 43758.5453) % 1 for s in (12.9898, 39.346, 78.233, 93.989))
        r = r_px * ((0.8 + 0.25 * r1) if back else (0.85 + 0.2 * r1))
        # Its top, its crown's bottom and its foot, through the view's own easing.
        dm = np.maximum(far[xm], 5)
        crest = top[xm] + np.degrees((r2 - 0.5) * tree_jitter_m / dm)
        below = lambda m: np.degrees(np.arctan(np.tan(np.radians(crest)) - m / dm))
        ty, foot = to_y(crest), to_y(below(tree_m))
        ry = np.clip((to_y(below(0.65 * tree_m)) - ty) / 2, 0.7 * r, 2.2 * r)
        cy = ty + ry + (0.25 * ry if back else 0)
        c = mix(color, (0, 0, 0), 0.12) if back else color
        if not back and fine:
            # The trunks, under the crowns' middles, down to the ground.
            for xx, yy, ff in zip(x, cy, foot):
                ctx.rectangle(int(xx), int(yy), max(round(tree_trunk_m * px_m), 1), max(int(ff - yy), 0))
            ctx.set_source_rgba(*mix(color, (0, 0, 0), 0.45), dense)
            ctx.fill()
            # The ground they stand on: the undergrowth, the lawn, fading into what's behind.
        if not back:
            # The ground they stand on: the undergrowth, the lawn, fading into what's behind (in steps: a fill each).
            # The ground they stand on, down to the frame's bottom (the farther facades are hidden there): the street
            # and the low roofs, in the facades' tone a little darker; the undergrowth, the lawn, at their feet.
            for xx, ff, rr in zip(x, foot, r):
                ctx.rectangle(int(xx - 1.1 * rr), int(ff), max(int(2.2 * rr) + 1, 1), max(h - int(ff), 0))
            ctx.set_source_rgb(*mix(base, (0, 0, 0), 0.12))
            ctx.fill()
            for xx, ff, rr in zip(x, foot, r):
                ctx.rectangle(int(xx - 1.1 * rr), int(ff) - 1, max(int(2.2 * rr) + 1, 1), max(int(0.5 * rr), 2))
            ctx.set_source_rgba(*mix(mix(color, base, 0.4), (0, 0, 0), 0.25), dense)
            ctx.fill()
        kinds = ((r4 < 0.3, mix(c, leaf_light, 0.1 * day)), (r4 > 0.75, mix(c, (0, 0, 0), 0.15)),
                 ((r4 >= 0.3) & (r4 <= 0.75), c)) if fine else ((r4 >= 0, c),)
        for sel, cc in kinds:
            for xx, yy, rr, vv, lo in zip(x[sel], cy[sel], r[sel], ry[sel], r3[sel]):
                if not fine:
                    # A few px: a blob's enough (a cross of two: its corners off).
                    x0, y0, cw_, ch_ = round(xx - rr), round(yy - vv), max(round(2 * rr), 1), max(round(2 * vv), 1)
                    ctx.rectangle(x0, y0 + 1, cw_, max(ch_ - 2, 1))
                    ctx.rectangle(x0 + 1, y0, max(cw_ - 2, 1), ch_)
                    continue
                oval(xx, yy, max(rr, 0.6), max(vv, 0.6))
                if fine:
                    # A lobe, up on one side: not quite round.
                    oval(xx + (lo - 0.5) * rr, yy - 0.4 * vv, 0.65 * rr, 0.65 * vv)
            ctx.set_source_rgba(*cc, dense)
            ctx.fill()
        if not fine:
            continue
        # Under, in their own shade.
        for xx, yy, rr, vv in zip(x, cy, r, ry):
            oval(xx, yy, rr, vv, 0.12 * math.pi, 0.88 * math.pi)
            ctx.close_path()
        ctx.set_source_rgba(0, 0, 0, 0.18 * dense)
        ctx.fill()
        if day < 0.1 or back:
            continue
        if crown_m * px_m >= 4:
            for k, (xx, yy, rr) in enumerate(zip(x, cy, r)):
                rnd = random.Random(int(i[k]))
                vv = ry[k]
                for _ in range(min(int(0.12 * rr * vv), 40)):
                    a, q = rnd.uniform(0, 2 * math.pi), rnd.random() ** 0.5 * 0.85
                    if math.sin(a) < 0.3:
                        ctx.rectangle(int(xx + q * rr * math.cos(a)), int(yy + q * vv * math.sin(a)), 1, 1)
            ctx.set_source_rgba(*mix(color, leaf_light, 0.35), 0.6 * dense * day)
            ctx.fill()
        for xx, yy, rr, vv in zip(x, cy, r, ry):
            oval(xx, yy, rr - 0.5, vv - 0.5, 1.15 * math.pi, 1.85 * math.pi)
        ctx.set_line_width(1)
        ctx.set_source_rgba(*mix(color, leaf_light, 0.3), 0.7 * dense * day)
        ctx.stroke()

def eiffel(ctx: cairo.Context, points: list, yaw: float, fov: float, to_px, night: float, now: float, clock: tuple):
    # Lit gold from dusk to 23:45, sparkling the first five minutes of each hour. clock: (hour, minute)
    if night < 0.05 or clock >= (23, 45) or 3 < clock[0] < 12:
        return
    for b, e, width, _ in points:
        if abs(wrap(b - yaw)) > fov / 2 + 5:
            continue
        (x, y), (_, base) = to_px(b, e), to_px(b, -1)
        wpx = max(1, to_px(b + width / 2, 0)[0] - to_px(b - width / 2, 0)[0])
        ctx.move_to(x - wpx / 2, base)
        ctx.line_to(x, y)
        ctx.line_to(x + wpx / 2, base)
        ctx.set_source_rgba(1, 0.72, 0.35, 0.35 * night)
        ctx.fill()
        if clock[1] < 5:
            rnd = random.Random(int(now * 4))
            for _ in range(max(3, round(wpx * 2))):
                v = rnd.random()
                ctx.rectangle(round(x + (rnd.random() - 0.5) * wpx * v), round(y + (base - y) * v), 1, 1)
            ctx.set_source_rgba(1, 1, 0.95, 0.9 * night)
            ctx.fill()

def panes(ctx: cairo.Context, bs: np.ndarray, ys: np.ndarray, on: np.ndarray, px_m: float, n: int, now: float,
          catch: np.ndarray, night: float, alpha: float, h: int):
    # The near windows as windows: a bay every few m along the band, a floor every 3 m down from its roofs.
    ww, wh, bay, story = window_shape
    w, step = len(bs), bs[1] - bs[0]
    bay_px = bay * px_m
    j0 = math.floor(bs[0] / step / bay_px) - 1
    js = np.arange(j0, j0 + math.ceil(w / bay_px) + 3)
    xs = np.round(js * bay_px - bs[0] / step + (bay_px - ww * px_m) / 2).astype(int)
    pw, ph = max(round(ww * px_m), 1), max(round(wh * px_m), 2)
    out = (xs >= 0) & (xs + pw <= w)
    js, xs = js[out], xs[out]
    if not len(xs):
        return
    # On one facade: each column under it covered, its roof the lowest of them.
    span = np.stack([ys[np.clip(xs + d, 0, w - 1)] for d in range(pw)])
    ok = on[xs] & on[np.minimum(xs + pw - 1, w - 1)] & (span.max(0) - span.min(0) <= max(story * px_m, 2))
    js, xs, roof = js[ok], xs[ok], span.max(0)[ok]
    fl = np.arange(floors)
    y = roof[:, None] + np.round((fl[None, :] + 0.5) * story * px_m).astype(int)
    r = (np.sin(js * 12.9898 + n * 31.7) * 43758.5453) % 1
    q = (np.sin(js[:, None] * 78.233 + fl[None, :] * 39.425 + n * 31.7 + np.floor(now / 600 + r[:, None] * 7)) * 43758.5453) % 1
    seen = y < h
    xi = np.clip(xs, 0, w - 1)
    groups = [((1, 0.85, 0.6), 0.6, seen & (q < glint_rate * catch[xi][:, None]))]
    if night > 0.05:
        lit = seen & (q < night * 0.09 * (0.4 + n / len(band_m)))
        cool = (q * 113 % 1) < 0.15
        groups += [((1, 0.78, 0.45), alpha, lit & ~cool), ((0.65, 0.75, 1), alpha, lit & cool)]
    for color, a, sel in groups:
        idx = np.argwhere(sel)
        if not len(idx):
            continue
        for grow, k in ((1, 0.3), (0, 1)):
            for i, f in idx:
                ctx.rectangle(int(xs[i]) - grow, int(y[i, f]) - grow, pw + 2 * grow, ph + 2 * grow)
            ctx.set_source_rgba(*color, a * k)
            ctx.fill()

def beacons(ctx: cairo.Context, sk: skyline.Skyline, yaw: float, fov: float, w: int, to_y, rows: np.ndarray, night: float,
            lean: float = 0, dz: float = 0):
    # The red lights on the tall ones' tops, each pulsing slowly at its own pace; hidden by nearer roofs. Bigger and
    # brighter the nearer: a glow around a bright pixel.
    # The highest first, a few pixels apart: on a small screen only the tallest of a cluster.
    now, taken = time.time(), []
    for b, e, d, tall in sorted(sk.beacons, key=lambda s: -s[1]):
        e += math.degrees(math.atan(-dz / d))
        x = w / 2 + wrap(b - math.degrees(lean / d) - yaw) / fov * w
        if tall < beacon_min_m or not 0 <= x < w or any(abs(x - t) < beacon_gap for t in taken):
            continue
        nearer = rows[len(rows) - 1 - np.searchsorted(skyline.bands, d) + 1:, int(x)]
        if len(nearer) and nearer.max() > e:
            continue
        taken.append(x)
        y = float(to_y(np.array([e]))[0])
        k = min((600 / d) ** 0.5, 1.5)
        pulse = 0.55 + 0.45 * math.sin(2 * math.pi * (now / (2 + b % 1.5) + b))
        a = night * pulse * (0.35 + 0.4 * min(k, 1))
        r = 1.5 + 2.5 * k
        g = cairo.RadialGradient(int(x) + 0.5, y, 0, int(x) + 0.5, y, r)
        g.add_color_stop_rgba(0, *beacon_color, a * 0.6)
        g.add_color_stop_rgba(1, *beacon_color, 0)
        ctx.set_source(g)
        ctx.arc(int(x) + 0.5, y, r, 0, 2 * math.pi)
        ctx.fill()
        ctx.set_source_rgba(*beacon_color, min(a * 1.6, 1))
        ctx.rectangle(int(x), int(y), 1, 1)
        ctx.fill()

def camera(fs: FrameState, target: tuple[float, float, float]) -> tuple[float, float, float]:
    now = time.monotonic()
    c = _cams.setdefault(fs.config.name, [*target, now])
    k = 1 - math.exp(-(now - c[3]) / 0.8)
    c[:] = c[0] + wrap(target[0] - c[0]) * k, c[1] + (target[1] - c[1]) * k, c[2] + (target[2] - c[2]) * k, now
    app._moving[fs.config.name] = abs(wrap(target[0] - c[0])) > 0.3 or abs(target[1] - c[1]) > 0.3 or abs(target[2] - c[2]) > 0.004
    if not app._moving[fs.config.name]:
        c[:3] = target
    return c[0], c[1], c[2]

def top_of(fov: float) -> float:
    # Degrees over the horizon at the top of the frame: zoomed in, the few over the roofs get the room.
    return min(90, max(fov * 1.2, 30))

def dip_of(fov: float) -> float:
    return dip_max * min(max(fov, fov_min) / 90, 1)

def tilt_to(e: float, fov: float) -> float:
    # The horizon where a plane e degrees up sits a third down the frame.
    s = (min(max(e, 0), 90) / top_of(fov)) ** elev_gamma
    return min(max(0.33 / max(1 - s, 0.01), tilt[0]), tilt[1])

def mean_bearing(bs: list[float]) -> float:
    return math.degrees(math.atan2(sum(math.sin(math.radians(b)) for b in bs), sum(math.cos(math.radians(b)) for b in bs)))

_stops = {}             # the tour's stops, kept once picked

def sights(st, sun: tuple, moon: tuple) -> list:
    '''The bearings worth a look all around, None where there's nothing now: the landmarks, the low sun, the moon
    low enough, where most planes are.'''
    bs = [p['bearing'] for p in st.planes.values() if 'bearing' in p]
    return [*(bearing(*local_xy(lat, lon)) for _, lat, lon, *_ in landmarks), sun[0] if -4 < sun[1] < 12 else None,
            moon[0] if 0 < moon[1] < 25 else None, int(np.bincount(np.array(bs, int) % 360 // 30).argmax()) * 30 + 15 if len(bs) >= 3 else None]

def tour(home: float, sights: list, t: float) -> float:
    # Every other stop the waypoints, the others a sight; turning slowly between them, the shorter way.
    def stop(k):
        if k not in _stops:
            pick = sights[int(abs(math.sin(k * 12.9898)) * 43758.5453) % len(sights)] if sights and k % 2 else None
            _stops[k] = home if pick is None else pick
            for o in [o for o in _stops if o < k - 2]:
                del _stops[o]
        return _stops[k]
    k, into = divmod(int(t), tour_dwell + tour_glide)
    a, b = stop(k - 1), stop(k)
    s = min(into / tour_glide, 1)
    return (a + wrap(b - a) * s * s * (3 - 2 * s)) % 360

def aim(st, fov: float, around: list = ()) -> tuple[float, float]:
    '''(yaw, fov): towards the planes seen from the window, wide enough for them all; without any, on the waypoints
    (the landmarks seen from here), turning now and then to the sights around, or pulled back to the whole window.'''
    start, end = app_config.aviator_window
    span = (end - start) % 360 or 360
    seen = [st.planes[h]['bearing'] for h in st.watched if h in st.planes]
    marks = [bearing(*local_xy(*p)) for p in app_config.screen_data.aviator.landmarks]
    if seen:
        yaw = mean_bearing(seen)
        fov = min(max(fov, 2 * max(abs(wrap(b - yaw)) for b in seen) + 15), span)
    elif time.time() % wide_every < wide_for:
        yaw, fov = start + span / 2, span
    else:
        yaw = tour(mean_bearing(marks) if marks else start + span / 2, list(around), time.time())
    return yaw, fov

def look(fs: FrameState, st, clear: tuple, w: int) -> tuple[float, float, float]:
    # Held still while what it looks at stays in view: zoomed on the plane of a card the first time it's on top,
    # then turned only when the followed plane leaves the clear box, or the planes seen move a quarter view away.
    # The horizon goes down to look up at the followed plane; otherwise it drifts, now the roofs, now the sky.
    fov = view_fov
    yaw = _held.get(fs.config.name)
    followed = app.following(fs)
    middle = (clear[0] + clear[2]) / 2 - w / 2
    if followed:
        p = st.planes[followed]
        b, e = sky_point(*app.position(p, time.time()), p['alt'])
        swept_hex, swept_at = app._swept.get(fs.config.name, (None, 0))
        if swept_hex == followed and time.monotonic() - swept_at < app.sweep:
            zoom = max(fov_min, fov / app.sweep_zoom)
            return b - middle / w * zoom, zoom, tilt_to(e, zoom)
        px = w / 2 + wrap(b - (yaw if yaw is not None else b)) / fov * w
        if yaw is None or not clear[0] + 6 <= px <= clear[2] - 6:
            yaw = b - middle / w * fov
        _held[fs.config.name] = yaw
        return yaw, fov, tilt_to(e, fov)
    sun = get_position(fs.now.in_tz('UTC'), fs.config.longitude, fs.config.latitude)
    sun = (math.degrees(sun['azimuth']) + 180) % 360, math.degrees(sun['altitude'])
    target, fov = aim(st, fov, sights(st, sun, astro.moon_at(time.time(), fs.config.latitude, fs.config.longitude)[:2]))
    # Idle it follows the tour; on planes, it turns only when they're a quarter view away.
    if yaw is None or abs(wrap(target - yaw)) > fov / 4 or not any(h in st.planes for h in st.watched):
        yaw = target
    _held[fs.config.name] = yaw
    # Slow motion while nothing's followed: the heading sways a few degrees, over a few minutes.
    t = time.time()
    rest = OpenedStateManager().get_state(fs).horizon or horizon
    return yaw + sway * math.sin(2 * math.pi * t / sway_period), fov, rest + tilt_sway * math.sin(2 * math.pi * t / tilt_period)

def demo_at(t: float) -> tuple:
    '''The demo t s in: (sun (bearing, degrees up), the sky state as seen, (day of the year, hour, minute)), each
    scene blending into the next.'''
    each = DEMO_S / len(demo_scenes)
    i, into = divmod(t, each)
    a, b = demo_scenes[int(i) % len(demo_scenes)], demo_scenes[(int(i) + 1) % len(demo_scenes)]
    k = min(max((into - each + demo_blend) / demo_blend, 0), 1)
    k = k * k * (3 - 2 * k)
    (ae, ab), (be, bb) = a[1], b[1]
    cloud, haze, deck, high, wet, snow, wind = (x + (y - x) * k for x, y in zip(a[4:], b[4:]))
    se = ae + (be - ae) * k
    seen = skylook.Seen((cloud, haze, 0.6 * cloud * deck), deck, high, (1 - cloud) if se > 0 else None, 0.5 * cloud * deck,
                        0.6 if wind > 8 else 0.2, None, wet, snow, None, wind, wind * 1.5, 250)
    return ((ab + wrap(bb - ab) * k) % 360, se), seen, (b if k > 0.5 else a)[2], *(b if k > 0.5 else a)[3]

def shade(hex: str, k: float) -> tuple[float, float, float]:
    return tuple(min(int(hex[i:i + 2], 16) / 255 * k, 1) for i in (1, 3, 5))

cloud_alpha = 0.55      # 0.8 in a downpour
cloud_weights = (0.4, 0.3, 0.2, 0.1)       # the nearer, the more it counts
rain_color = (0.68, 0.76, 0.9)
rain_weights = (1, 0.8, 0.6, 0.45, 0.3)
cloud_base_km = 4       # the rain hangs from here: higher in the view the nearer it is
col_step = 2            # px between the columns of a band
# The drops at home, far then near: (per px of the view, length px, px/s falling, alpha).
drop_layers = ((1 / 380, 3, 55, 0.22), (1 / 1100, 6, 120, 0.42))
puff_alpha = 0.7
puff_base_km = 1.5      # the cumulus' base
puff_km = 1.6           # a cloud across
# Far to near: (km away, the satellite's bin). The three nearest are over home, in the nearest bin.
puff_layers = ((100, 3), (60, 2), (30, 1), (10, 0), (6, 0), (3.5, 0), (2, 0))
snow_color = (0.93, 0.95, 1.0)
# The flakes, the same: (per px of the view, size px, px/s falling, alpha).
flake_layers = ((1 / 260, 1, 9, 0.35), (1 / 700, 2, 18, 0.6))
# The wind at home: streaks over the roofs going with it, some curling on the way.
curl_ms = 3             # from this wind on
curl_life = 5           # s a streak lives
curl_trail = 16         # points along its tail, a 40th of its life apart
curl_r = 1 / 150        # of the width, the loop's radius (more in the gusts)

def clouds(ctx: cairo.Context, yaw: float, fov: float, w: int, hz: int, h: int, color: tuple, floor: float = 0, alpha: float = cloud_alpha):
    # A band of cloud over the horizon, as high as the cover is thick in each direction, going to nothing upwards.
    # floor: the cover all around when it rains at home. Returns the cover (0..1) by bearing, for what it hides.
    prof = weather.sky_profile('clouds')
    if not prof and not floor:
        return lambda b: 0.0
    xs = np.arange(0, w + col_step, col_step)
    weights = np.array(cloud_weights, np.float32)
    cover_at = lambda bs: np.maximum(np.clip((weather.along(prof[0], bs) * weights).sum(axis=1) * 2.5, 0, 1) if prof else np.zeros(len(bs)), floor)
    top = hz - hz * 0.95 * cover_at(yaw + (xs - w / 2) / w * fov) ** 0.8
    if top.min() < hz - 1:
        g = cairo.LinearGradient(0, top.min(), 0, hz)
        g.add_color_stop_rgba(0, *color, 0)
        g.add_color_stop_rgba(1, *color, alpha)
        ctx.set_source(g)
        ctx.move_to(0, hz)
        for x, y in zip(xs, top):
            ctx.line_to(float(x), float(y))
        ctx.line_to(w, hz)
        ctx.close_path()
        ctx.fill()
    return lambda b: float(cover_at(np.array([b]))[0])

def puffs(ctx: cairo.Context, yaw: float, fov: float, w: int, to_px, color: tuple, floor: float = 0, alpha: float = puff_alpha):
    # The clouds themselves where the satellite sees them, a puff a cloud wide as often as the cover is thick: the far
    # ones low and small, the ones over home high up and big. Each has its place by bearing, the same every frame.
    prof = weather.sky_profile('clouds')
    if not prof and not floor:
        return
    for d, k in puff_layers:
        size = math.degrees(puff_km / d)
        step = size * 0.8
        i0 = math.floor((yaw - fov / 2 - size) / step)
        bs = np.arange(i0, i0 + math.ceil((fov + 2 * size) / step) + 1) * step
        cover = np.maximum(np.clip(weather.along(prof[0], bs)[:, k] * 3, 0, 1) if prof else np.zeros(len(bs)), floor)
        e = math.degrees(math.atan2(puff_base_km, d))
        near = min(size / 20, 1)
        a = alpha * (1 - 0.4 * near)    # the near ones thin: one sees through their edges
        for i, b, c in zip(range(i0, i0 + len(bs)), bs, cover):
            r = (math.sin(i * 12.9898 + d * 78.233) * 43758.5453) % 1
            if r >= c:
                continue
            j = (r * 7.31) % 1
            x, y = to_px(b + (j - 0.5) * step * 0.6, e * (0.85 + 0.3 * j))
            rx = max(size / fov * w * (0.45 + 0.4 * j) * (1 - 0.4 * near), 0.6)
            ry = max(rx * (0.3 + 0.35 * near), 0.6)
            puff(ctx, x, y, rx, ry, color, a * (0.6 + 0.4 * c), r)

def lobes(rx: float, r: float) -> list[tuple[float, float, float]]:
    '''A cumulus' heaps (x, y, radius in units of rx and ry), r its own number: a row along the base, then smaller
    tiers piled up the middle, the more the bigger it shows (a few pixels: one row of three).'''
    out = []
    tiers = 1 if rx < 8 else 2 if rx < 30 else 3
    for tier in range(tiers):
        n = int(min(max(rx / 6, 3), 8)) - 2 * tier
        width = 0.95 * (1 - 0.3 * tier)
        for k in range(max(n, 1)):
            t = 0.5 if n <= 1 else k / (n - 1)
            j = (r * (31.7 + 17.3 * k + 7.1 * tier)) % 1
            hump = math.sin(math.pi * t)
            out.append((-width + 2 * width * t + (j - 0.5) * 0.2, 0.25 - 0.55 * tier - 0.3 * hump * (tier + 1) / tiers - 0.15 * j,
                        (0.3 + 0.25 * hump + 0.12 * j) * (1 - 0.15 * tier)))
    return out

def puff(ctx: cairo.Context, x: float, y: float, rx: float, ry: float, color: tuple, a: float, r: float):
    # Lit on top, grey under, a flat base; a big one gets a lit rim on its heaps.
    heaps = lobes(rx, r)
    g = cairo.LinearGradient(0, y - ry * 1.4, 0, y + ry * 0.45)
    g.add_color_stop_rgba(0, *(min(v * 1.15, 1) for v in color), a)
    g.add_color_stop_rgba(1, *(v * 0.75 for v in color), a)
    ctx.save()
    ctx.rectangle(x - rx * 2, y - ry * 3, rx * 4, ry * 3.45)        # the base, flat
    ctx.clip()
    ctx.set_source(g)
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(rx, ry)
    for hx, hy, hr in heaps:
        ctx.new_sub_path()
        ctx.arc(hx, hy, hr, 0, 2 * math.pi)
    ctx.restore()
    ctx.fill()
    if rx > 12:
        ctx.set_source_rgba(*(min(v * 1.25, 1) for v in color), a * 0.35)
        ctx.save()
        ctx.translate(x, y)
        ctx.scale(rx, ry)
        for hx, hy, hr in heaps:
            ctx.new_sub_path()
            ctx.arc(hx - 0.1 * hr, hy - 0.15 * hr, hr * 0.7, 0, 2 * math.pi)
        ctx.restore()
        ctx.fill()
    ctx.restore()

cirrus_alpha = 0.35
# The streaks: (per degree of the view, elevation range, length in degrees).
cirrus_density, cirrus_elev, cirrus_len = 0.12, (20, 60), (5, 14)

def cirrus(ctx: cairo.Context, yaw: float, fov: float, w: int, to_px, color: tuple, lk, k: float):
    # High cloud (the model's, the light can't tell it): thin streaks high up, each where it is by bearing. They keep
    # the sunset's colour after it's gone from the low ones.
    c = tuple(v * (1 - lk.glow) + g / 255 * lk.glow for v, g in zip(color, skylook.glow_rgb))
    ctx.set_line_width(1)
    step = 1 / cirrus_density
    for i in range(math.floor((yaw - fov / 2 - cirrus_len[1]) / step), math.ceil((yaw + fov / 2) / step) + 1):
        r = (math.sin(i * 91.345 + 3.1) * 43758.5453) % 1
        if r >= k:
            continue
        j = (r * 13.17) % 1
        b, e = i * step, cirrus_elev[0] + (cirrus_elev[1] - cirrus_elev[0]) * j
        length = cirrus_len[0] + (cirrus_len[1] - cirrus_len[0]) * ((r * 7.7) % 1)
        (x0, y0), (x1, y1) = to_px(b, e), to_px(b + length, e - 2 * (j - 0.5))
        g = cairo.LinearGradient(x0, y0, x1, y1)
        g.add_color_stop_rgba(0, *c, 0)
        g.add_color_stop_rgba(0.4, *c, cirrus_alpha * (0.5 + 0.5 * k))
        g.add_color_stop_rgba(1, *c, 0)
        ctx.set_source(g)
        ctx.move_to(x0, y0)
        ctx.line_to(x1, y1)
        ctx.stroke()

contrail_alpha = 0.5
contrail_life = (25, 600)       # s a trail stays: in dry air, in air saturated over ice

def contrails(ctx: cairo.Context, planes, now: float, in_view, to_px, color: tuple, trails: tuple):
    # Behind the planes flying where it's cold enough (skystate.py: the planes' own temperatures, else the model's):
    # short in dry air, long and spreading when the air is saturated over ice, drifting with the wind up there.
    form, persist, u, v = trails
    life = contrail_life[0] + (contrail_life[1] - contrail_life[0]) * persist
    for p in planes:
        if p['ground'] or p['alt'] < form:
            continue
        pts = [(t, *local_xy(la, lo), alt or p['alt']) for t, la, lo, alt in p['trail'] if now - t < life]
        pts.append((now, *app.position(p, now), p['alt']))
        prev = None
        for t, x, y, alt in pts:
            age = now - t
            b, e = sky_point(x + u * age / 1000, y + v * age / 1000, alt)
            if prev and in_view(b) and in_view(prev[0]):
                k = 1 - age / life
                ctx.set_line_width(1 + 2 * persist * (1 - k))
                ctx.set_source_rgba(*color, contrail_alpha * k * (1 - 0.5 * persist * (1 - k)))
                ctx.move_to(*to_px(*prev))
                ctx.line_to(*to_px(b, e))
                ctx.stroke()
            prev = b, e
    ctx.set_line_width(1)

def fall_tint(lk, color: tuple, k: float = 0.6) -> tuple:
    # Rain and snow are lit by what's around: at night the streetlights.
    k *= lk.city
    return tuple(c * (1 - k) + v / 255 * k for c, v in zip(color, skylook.city_rgb))

def rain(ctx: cairo.Context, yaw: float, fov: float, w: int, hz: int, to_px, tint: tuple):
    # Curtains of rain hanging in the directions it rains in, nearer ones higher and stronger.
    if not (prof := weather.sky_profile('rain')):
        return
    values = prof[0]
    xs = np.arange(0, w, col_step)
    along = weather.along(values, yaw + (xs - w / 2) / w * fov) * np.array(rain_weights, np.float32)
    best = along.argmax(axis=1)
    power = along.max(axis=1)
    ctx.set_line_width(1)
    for i, (x, k) in enumerate(zip(xs, best)):
        if power[i] < 0.05:
            continue
        _, top = to_px(0, math.degrees(math.atan2(cloud_base_km, weather.rain_bins[k])))
        # Streaky: each column its own strength.
        streak = 0.5 + 0.5 * ((x * 37 + k * 11) % 7) / 6
        ctx.set_source_rgba(*tint, min(power[i] * 1.4, 0.6) * streak)
        ctx.move_to(float(x) + 0.5, top)
        ctx.line_to(float(x) + 0.5, hz)
        ctx.stroke()

def drops(ctx: cairo.Context, w: int, h: int, now: float, wet: float, slant: float, tint: tuple, share: float = 1):
    # The rain at home, across the whole view: the near drops longer, brighter and faster. They fall along the wind.
    for depth, (per_px, length, speed, alpha) in enumerate(drop_layers):
        ctx.set_source_rgba(*tint, alpha * (0.5 + 0.5 * wet))
        for i in range(int(w * h * per_px * (0.3 + wet) * share)):
            y = ((i * 0.7548776662 + depth * 0.37) % 1 * h + now * speed) % (h + length) - length
            x = ((i * 0.6180339887 + depth * 0.5) % 1 * (w + 40) - 20 + slant * y) % (w + 40) - 20
            ctx.move_to(x, y)
            ctx.line_to(x + slant * length, y + length)
        ctx.stroke()

def flakes(ctx: cairo.Context, w: int, h: int, now: float, wet: float, slant: float, tint: tuple, share: float = 1):
    # The snow at home: slow, the near flakes bigger, each its own speed and sway, blown further than the rain.
    ctx.set_antialias(cairo.ANTIALIAS_NONE)
    for depth, (per_px, size, speed, alpha) in enumerate(flake_layers):
        ctx.set_source_rgba(*tint, alpha * (0.5 + 0.5 * wet))
        for i in range(int(w * h * per_px * (0.3 + wet) * share)):
            v = speed * (0.7 + 0.6 * ((i * 0.381966) % 1))
            y = ((i * 0.7548776662 + depth * 0.37) % 1 * h + now * v) % (h + size) - size
            x = ((i * 0.6180339887 + depth * 0.5) % 1 * (w + 40) - 20 + 2 * slant * y + 1.5 * math.sin(now * 1.2 + i)) % (w + 40) - 20
            ctx.rectangle(round(x), round(y), size, size)
        ctx.fill()
    ctx.set_antialias(cairo.ANTIALIAS_DEFAULT)

def curls(ctx: cairo.Context, w: int, top: float, hz: int, now: float, yaw: float, wind: float, gust: float, dir: float, color: tuple):
    # Each streak is born at its own place and time, drifts across with the wind (its part across the view), every
    # other one loops once half way: a trochoid. Fading in and out, the tail fainter.
    r = math.radians(yaw)
    e, n = -wind * math.sin(math.radians(dir)), -wind * math.cos(math.radians(dir))   # where it blows to
    across = e * math.cos(r) - n * math.sin(r)
    side = 1 if across >= 0 else -1
    run = (abs(across) + 1) * w * 0.03                      # px over its life; a wind at us still stirs
    loop = max(curl_r * w, 3) * min(gust / max(wind, 1), 2)
    alpha = min(0.3 + 0.04 * wind, 0.65)
    color = tuple(min(c * 1.6 + 0.15, 1) for c in color)     # a little brighter than the clouds behind
    count = round(min(wind * 1.5, 18) * max(w / 400, 0.4))
    frac = lambda x: x % 1
    def at(i: int, born: int, u: float) -> tuple[float, float]:
        x0, y0 = frac(i * 0.6180339887 + born * 0.381966) * w, top + frac(i * 0.7548776662 + born * 0.2763932) * (hz - top - 6)
        th = 2 * math.pi * min(max((u - 0.35) / 0.3, 0), 1) if i % 2 else 0
        return (x0 + side * (run * u + loop * math.sin(th)),
                y0 - loop * (1 - math.cos(th)) + 1.5 * math.sin(2 * math.pi * (u * 1.5 + i * 0.3)))
    for i in range(count):
        life = now / curl_life + frac(i * 0.414213)
        born, u = int(life), life % 1
        points = [at(i, born, max(u - k * 0.025, 0)) for k in range(curl_trail)]
        for k, (a, b) in enumerate(zip(points, points[1:])):
            ctx.set_source_rgba(*color, alpha * math.sin(math.pi * u) * (1 - k / curl_trail) ** 0.5)
            ctx.move_to(*a)
            ctx.line_to(*b)
            ctx.stroke()

def drop_slant(yaw: float) -> float:
    # The wind at home across the view (right is yaw + 90), in px sideways per px falling.
    doc = weather.wind_doc()
    if not doc or not (wv := weather.wind_at(doc, 0, 0)):
        return -0.25
    u, v = wv
    r = math.radians(yaw)
    return float(np.clip((u * math.cos(r) - v * math.sin(r)) / 8, -0.8, 0.8))

def sky(fs: FrameState, clear: tuple | None = None) -> Frame:
    st = ADSBxStateManager().get_state(fs)
    opened = OpenedStateManager().get_state(fs).opened
    w, h = fs.config.width, fs.config.height
    now = time.time()
    followed = app.following(fs)
    sk = skyline.get(now)
    dz = OpenedStateManager().get_state(fs).floors * floor_m
    _eye['m'] = (sk.eye[2] if sk else home_ground + fs.config.aviator_eye_m) + dz
    opened_ = OpenedStateManager().get_state(fs)
    started, held = opened_.demo, opened_.sky
    demo = started is not None and now - started < DEMO_S
    if demo:
        # Once around from where it was, slowly; the scene's sky instead of the one outside.
        if _demo.get(fs.config.name, (None,))[0] != started:
            _demo[fs.config.name] = started, _cams.get(fs.config.name, [90])[0]
        (dsb, dse), dseen, *today = demo_at(now - started)
        view = (_demo[fs.config.name][1] + 360 * (now - started) / DEMO_S) % 360, view_fov, opened_.horizon or horizon
    else:
        view = look(fs, st, clear or (0, 0, w, h), w)
        if held and now - held['at'] < SKY_HOLD:
            # Where the web page turned it, a while.
            view = held.get('yaw', view[0]), held.get('fov', view[1]), view[2]
    yaw, fov, tl = camera(fs, view)
    # Whole pixels: between them the frame stays the same (the roofs from the cache, nothing new to send).
    yaw = round(yaw / (fov / w)) * fov / w
    hz = round(h * tl)
    top, dip = top_of(fov), dip_of(fov)
    in_view = lambda b, margin=10: abs(wrap(b - yaw)) < fov / 2 + margin
    to_x = lambda b: w / 2 + wrap(b - yaw) / fov * w
    to_px = lambda b, e: (to_x(b), hz - hz * (min(e, 90) / top) ** elev_gamma if e >= 0 else hz + (h - hz) * (min(-e, dip) / dip) ** elev_gamma)
    to_y = lambda e: np.where(e >= 0, hz - hz * (np.minimum(np.abs(e), 90) / top) ** elev_gamma, hz + (h - hz) * (np.minimum(np.abs(e), dip) / dip) ** elev_gamma)

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    ctx.set_line_width(1)
    labels, taken = [], []

    # The sky: the sun's height, the weather state and the room's light (skylook.py).
    sun = get_position(fs.now.in_tz('UTC'), fs.config.longitude, fs.config.latitude)
    sb, se = (dsb, dse) if demo else ((math.degrees(sun['azimuth']) + 180) % 360, math.degrees(sun['altitude']))
    off = OpenedStateManager().get_state(fs).off
    # The sky state: every source over home together (skystate.py, the same for all screens).
    seen = dseen if demo else skylook.seen(fs)
    wet, snow = seen.wet, seen.snow
    lk = skylook.look(se, seen.cond, skylook.light_gain(fs), None, seen.warmth)
    skylook.paint(ctx, lk, w, hz, h, to_x(sb) if in_view(sb, 30) else None)
    ctx.set_source_rgba(*horizon_color)
    ctx.move_to(0, hz)
    ctx.line_to(w, hz)
    ctx.stroke()

    info, show_planes = 'info' not in off, 'planes' not in off
    tint, snow_tint = fall_tint(lk, rain_color), fall_tint(lk, snow_color, 0.5)
    if 'clouds' not in off or wet:
        cc = skylook.cloud_color(lk, wet * (1 - 0.7 * snow))
        if seen.high > 0.05:
            cirrus(ctx, yaw, fov, w, to_px, cc, lk, seen.high)
        # The low and mid cloud all around: the satellite (infrared) misses the low, warm ones.
        # A deck when it's steady, puffs when the sun goes in and out.
        deck, broken = seen.deck, 0.3 if seen.broken is None else seen.broken
        cloud_dim = clouds(ctx, yaw, fov, w, hz, h, cc, max(min(wet * 1.4, 0.8), 0.6 * deck * (1 - 0.5 * broken)), cloud_alpha + 0.25 * wet)
        puffs(ctx, yaw, fov, w, to_px, cc, max(min(wet * 1.4, 0.8), deck * (0.2 + 0.5 * broken)))
    else:
        cloud_dim = lambda b: 0.0

    # The sun where it is, its glow over the horizon a little after it's set.
    if se > -6 and in_view(sb, 20):
        sx, sy = to_px(sb, se)
        glow = cairo.RadialGradient(sx, sy, 0, sx, sy, 16)
        dim = 1 - 0.8 * cloud_dim(sb)       # a cloud band in front of it, or the sky state says it's in
        if seen.sun is not None:
            dim = min(dim, (0.15 + 0.85 * seen.sun) * (1 - 0.9 * seen.dark))
        glow.add_color_stop_rgba(0, *sun_color, (0.35 if se > 0 else 0.2) * dim)
        glow.add_color_stop_rgba(1, *sun_color, 0)
        ctx.set_source(glow)
        ctx.paint()
        if se > 0:
            ctx.set_source_rgba(*sun_color, dim)
            ctx.arc(sx, sy, 2.5, 0, 2 * math.pi)
            ctx.fill()

    # Stars once the sun is well down (dimmed by the cloud), the moon where it is, fainter in daylight.
    clear_sky = (1 - 0.9 * lk.cloud) * max(1 - 2 * wet, 0)
    astro.draw_stars(ctx, now, fs.config.latitude, fs.config.longitude, to_px, in_view, min(max((-se - 3) / 12, 0), 1) * clear_sky)
    mb, me, phase = astro.moon_at(now, fs.config.latitude, fs.config.longitude)
    if me > -1 and in_view(mb, 10):
        mx, my = to_px(mb, max(me, 0))
        astro.draw_moon(ctx, mx, my, 3, phase, (1 - 0.65 * min(max(se / 10, 0), 1)) * (1 - 0.8 * cloud_dim(mb)) * (1 - 0.5 * lk.cloud) * max(1 - 2 * wet, 0))

    if 'rain' not in off:
        rain(ctx, yaw, fov, w, hz, to_px, tint)

    if show_planes and seen.trails and 'clouds' not in off:
        contrails(ctx, st.planes.values(), now, in_view, to_px, skylook.cloud_color(lk), seen.trails)

    targets, lit = [], []
    for hex, p in sorted(st.planes.items() if show_planes else (), key=lambda i: (i[0] == followed, i[0] in st.watched)):
        color = marker_color(p['alt']).rgb
        x, y = app.position(p, now)
        b, e = sky_point(x, y, p['alt'])
        if not in_view(b):
            continue
        px, py = to_px(b, e)
        targets.append(Target(round(px) - 6, round(py) - 6, 13, 13, 'aviator.open', {'hex': hex}))
        if not (hex in st.watched or hex in opened):
            # The others: a dot.
            ctx.set_source_rgba(*color, dot_alpha)
            ctx.rectangle(round(px), round(py), 1, 1)
            ctx.fill()
            continue
        stepped = now // app.fade_step * app.fade_step
        points = [(t, sky_point(*local_xy(la, lo), alt or 0)) for t, la, lo, alt in p['trail'] if stepped - t < app.watched_fade]
        for (_, (b0, e0)), (t1, (b1, e1)) in zip(points, points[1:]):
            if in_view(b0) and in_view(b1):
                ctx.set_source_rgba(*color, trail_alpha * (1 - max(stepped - t1, 0) / app.watched_fade))
                ctx.move_to(*to_px(b0, e0))
                ctx.line_to(*to_px(b1, e1))
                ctx.stroke()
        ctx.set_dash([1, 2])
        ctx.set_source_rgba(*color, 0.4)
        ctx.move_to(px, py)
        for k in range(1, 7):
            ax, ay = app.position(p, now, app.ahead * k / 6)
            ctx.line_to(*to_px(*sky_point(ax, ay, p['alt'] + p['vr'] * app.ahead * k / 6 / 60)))
        ctx.stroke()
        ctx.set_dash([])
        # Pointing where it goes on the screen, bigger when near.
        nx, ny = to_px(*sky_point(*app.position(p, now, 20), p['alt'] + p['vr'] / 3))
        heading = math.degrees(math.atan2(nx - px, py - ny)) if (nx, ny) != (px, py) else 90
        size = min(max(1.5 + 6 / max(p['slant'], 1) ** 0.7, 1.8), 4)
        ctx.set_source_rgb(*color)
        app.chevron(ctx, px, py, heading, size * 1.3)
        ctx.fill()
        if hex == followed:
            lit.append((px, py))
        if info and (n := app.number(st, hex)):
            labels.append((app.pill(n, marker_color(p['alt']).hex), round(px) + 5, round(py) - 10))

    # The roofs over all that: a low plane goes behind them. Its number and the ring stay on top.
    # Wet roofs shine with the rain's light, snowy ones are white along their tops.
    rim = (*snow_tint, 0.3 + 0.3 * wet) if snow >= 0.5 else (*tint, rim_color[3] + 0.2 * wet)
    # The sun on the facades: the light says how much it's out, else the cloud does.
    sun_out = (seen.sun if seen.sun is not None else 1 - lk.cloud) * float(np.clip(se / 8, 0, 1)) * (1 - wet)
    lights = (sb, lk.glow) if lk.glow > 0.03 else None, rim if wet > 0.05 else rim_color, (sb, sun_out) if sun_out > 0.05 else None
    if sk:
        night = min(max((-se - 2) / 8, 0), 1)
        # The eye's lean a pixel at a time (the nearest band's), the light and the hour rounded: the same roofs are
        # drawn once, then painted from the cache; a crane or the Eiffel tower sparkling in view, more often.
        q = band_m[-1] * math.radians(fov / w)
        lean = round(lean_m * math.sin(2 * math.pi * now / sway_period) / q) * q
        r2 = lambda v: tuple(round(x, 2) for x in v) if isinstance(v, tuple) else v
        lit_q = [None if v is None else r2(v) if i == 1 else (round(v[0]), round(v[1], 2)) for i, v in enumerate(lights)]
        t = time.localtime(now)
        clock = tuple(today) if demo else (t.tm_yday, t.tm_hour, t.tm_min)
        moving = any(abs(wrap(bearing(*local_xy(la, lo)) - yaw)) < fov / 2 + 10 for la, lo, *_ in app_config.screen_data.aviator.cranes)
        tick = 0.25 if night > 0.05 and clock[2] < 5 else 1 if moving else 60
        args = (yaw, fov, w, h, to_y, *lit_q, round(night, 2), round(float(np.clip((se + 3) / 10, 0, 1)) * (1 - 0.3 * lk.cloud), 2),
                r2(lk.horizon), lean, round(lk.haze, 2), clock, dz, now // tick * tick)
        key = (id(sk), hz, top, dip, *args[:4], *args[5:])
        if (hit := _roofs.get(fs.config.name)) is None or hit[0] != key:
            layer = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            hit = _roofs[fs.config.name] = key, layer, real_roofs(cairo.Context(layer), sk, *args)
        ctx.set_source_surface(hit[1])
        ctx.paint()
        if night > 0.05:
            beacons(ctx, sk.lifted(dz), yaw, fov, w, to_y, hit[2], night, lean, dz)
    else:
        roofs(ctx, in_view, to_px, h, *lights)
    # Darker to the bottom: the near roofs under, the far ones over them.
    g = cairo.LinearGradient(0, hz, 0, h)
    g.add_color_stop_rgba(0, 0, 0, 0, 0)
    g.add_color_stop_rgba(1, 0, 0, 0, floor_dark)
    ctx.set_source(g)
    ctx.rectangle(0, hz, w, h - hz)
    ctx.fill()
    # The wind over the roofs, then the rain or snow at home in front of all that, at a few frames a second.
    windy = 'wind' not in off and (seen.wind or 0) >= curl_ms and seen.wind_dir is not None
    if windy:
        curls(ctx, w, hz * 0.3, hz, now, yaw, seen.wind, seen.gust or seen.wind, seen.wind_dir, skylook.cloud_color(lk))
    app._raining[fs.config.name] = wet > 0.05 or windy
    if wet > 0.05:
        slant = drop_slant(yaw)
        drops(ctx, w, h, now, wet, slant, tint, 1 - snow)
        flakes(ctx, w, h, now, wet, slant, snow_tint, snow)
    for px, py in (lit if info else ()):
        ctx.set_source_rgba(1, 1, 1, 0.85)
        ctx.arc(px, py, 6.5, 0, 2 * math.pi)
        ctx.stroke()
    for i, name in enumerate(compass if info else ()):
        if in_view(i * 45, 0):
            if at := app.label_at(t := text(name, label_style), round(to_x(i * 45)), hz + 4, taken):
                labels.append((t, *at))
    for a in (airports if info else ()):
        ab = bearing(a.x, a.y)
        if in_view(ab, 0) and (at := app.label_at(t := text(a.code, label_style), round(to_x(ab)), hz + 4, taken)):
            labels.append((t, *at))

    img = to_pil(surface)
    for label, x, y in labels:
        place_at(label, img, x, y, 'tl')
    return Frame(img, targets=tuple(targets)).tag(('aviator.sky', fs.config.name))
