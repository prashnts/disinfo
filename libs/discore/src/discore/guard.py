'''Keeps text readable where it's placed: each Ink is recolored from what's under it.

Already far enough from it: left as is. Flat ground: vibrant, the glyph pixels lifted (or darkened, in the ground's
hue) to the floor. Grainy or mixed: shadow-bold, the glyph light and a dark copy 1 px down-right, where the frame
has nothing else. Frost panels get their dim solved instead (dimmed()).
'''
import numpy as np
from PIL import Image, ImageChops
from PIL.Image import ImagePointHandler

from .color import Color, palette, glare, lstar as lstar_of

enabled = True
# ΔL* a stroke needs from what's under it.
floor = {1: 45, 2: 35}
flat = 30           # p90 - p10 L* under the glyphs: flat below
grainy = 5          # mean |ground - its blur| L*, at the stroke's scale around the glyphs: grainy over
opaque = 0.9        # what's under it must be this opaque: on a transparent frame it isn't known yet
shadow = 0.85       # the shadow's alpha
dark = 25           # L* under it: a dark ink (text on a fill)

_W = np.array([0.2126, 0.7152, 0.0722])
_lut = np.array([c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in np.arange(256) / 255])
_lstar8 = [float(l) for l in np.where(_lut <= 0.008856, _lut * 903.3, 116 * np.cbrt(_lut) - 16)]     # of a grey 0-255


def lstar(lin: np.ndarray) -> np.ndarray:
    y = lin @ _W
    return np.where(y <= 0.008856, y * 903.3, 116 * np.cbrt(y) - 16)

def _y(l: np.ndarray) -> np.ndarray:
    l = np.clip(l, 0, 100)
    return np.where(l <= 8, l / 903.3, ((l + 16) / 116) ** 3)

def _srgb(lin: np.ndarray) -> np.ndarray:
    lin = np.clip(lin, 0, 1)
    return np.round(255 * np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055))

def toward(lin: np.ndarray, l: np.ndarray) -> np.ndarray:
    '''Linear colors (.., 3) at lightness l: scaled, then towards white where a channel is full.'''
    y, cur = _y(l)[..., None], (lin @ _W)[..., None]
    out = np.where(cur > 0, np.minimum(lin * y / np.maximum(cur, 1e-9), 1), y)
    got = (out @ _W)[..., None]
    t = np.where(got < y, (y - got) / np.maximum(1 - got, 1e-9), 0)
    return out + t * (1 - out)

def _box(a: np.ndarray, r: int) -> np.ndarray:
    '''Mean over the (2r + 1)² around each pixel, the edges repeated. Over the first two axes.'''
    k, pad = 2 * r + 1, ((r, r), (r, r)) + ((0, 0),) * (a.ndim - 2)
    c = np.pad(a, pad, mode='edge').cumsum(0)
    c = np.concatenate([np.zeros_like(c[:1]), c])
    c = (c[k:] - c[:-k]).cumsum(1)
    c = np.concatenate([np.zeros_like(c[:, :1]), c], 1)
    return (c[:, k:] - c[:, :-k]) / k ** 2

def _ground(under: np.ndarray, top: np.ndarray, glyphs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    '''Linear colors and alpha of top over under, the glyphs left out.'''
    ua, ta = under[..., 3:] / 255, top[..., 3:] / 255 * (1 - glyphs[..., None])
    a = ta + ua * (1 - ta)
    lin = (_lut[top[..., :3]] * ta + _lut[under[..., :3]] * ua * (1 - ta)) / np.maximum(a, 1e-9)
    return lin, a[..., 0]


def guarded(f, dest: Image.Image, x: int, y: int) -> Image.Image:
    '''The Frame f's image as it should go at (x, y) on dest (before it's there), its inks recolored. A copy, 1 px
    larger with a shadow, or its image when nothing changes.

    Cached on its pixels (not its hash: a scroller's or a transition's frame keeps it while it moves) and on the
    ground coarsely (under a card on an animated sky it changes every frame; only the frame's px are recolored).'''
    frame, inks = f.image, f.inks
    if not enabled or not inks or x < 0 or y < 0:      # off an edge: it's coming in, it moves
        return frame
    W, H = dest.size
    fw, fh = frame.size
    # The frame's box on dest, 1 px more for the shadows, 2 more for the context.
    x0, y0, x1, y1 = max(x - 2, 0), max(y - 2, 0), min(x + fw + 3, W), min(y + fh + 3, H)
    if x1 <= x0 or y1 <= y0:
        return frame
    # On nothing yet (a div's own image): a px under each ink tells.
    centers = [c for k in inks if 0 <= (c := (x + k.x + k.w // 2, y + k.y + k.h // 2))[0] < W and 0 <= c[1] < H]
    if dest.mode == 'RGBA' and all(dest.getpixel(c)[3] < 255 * opaque for c in centers):
        return frame
    crop = dest.crop((x0, y0, x1, y1))
    crop = crop if crop.mode == 'RGBA' else crop.convert('RGBA')
    if crop.getextrema()[3][1] < 255 * opaque:
        return frame
    # Most inks: on their own fill, or a floor over the brightest px under them.
    if not (inks := [k for k in inks if not _reads(k, frame, crop, x - x0, y - y0)]):
        return frame
    coarse = (crop.reduce(4) if min(crop.size) >= 4 else crop).tobytes().translate(_coarse)
    marks = tuple((k.x, k.y, k.w, k.h, k.color, k.stroke) for k in inks)
    key = (frame.size, frame.tobytes(), marks, x - x0, y - y0, crop.size, coarse, palette())
    if (done := _guarded.get(key)) is None:
        if len(_guarded) > 256:
            _guarded.clear()
        done = _guarded[key] = _guard(frame, inks, crop, x - x0, y - y0)
    return done

_guarded = {}
_inked = {}
_coarse = bytes(v >> 5 << 5 for v in range(256))     # 8 levels a channel


class _Lut(ImagePointHandler):
    # A LUT as it is: a list, PIL rounds entry by entry at every call.
    def __init__(self, lut: list[int]):
        self.lut = lut

    def point(self, im: Image.Image) -> Image.Image:
        return im._new(im.im.point(self.lut, None))

def need(k) -> float:
    '''The ΔL* an ink needs from its ground: the floor, or what a dim light ink (fg3) has on black.'''
    f, l = floor.get(k.stroke, floor[1]), Color(k.color).L
    return min(f, l) if l >= dark else f

def _reads(k, frame: Image.Image, crop: Image.Image, fx: int, fy: int) -> bool:
    # On its own fill (a pill), or light enough over the brightest px under it, through the frame's card.
    box = (k.x, k.y, k.x + k.w, k.y + k.h)
    card = frame.crop(box).getextrema()[3][0] / 255     # its least opaque px: the card's own alpha
    if card >= opaque:
        return True
    l = Color(k.color).L
    if l < dark:
        return False
    top = max(e[1] for e in crop.crop((fx + box[0], fy + box[1], fx + box[2], fy + box[3])).getextrema()[:3])
    return l - float(lstar(_lut[top] * (1 - card) * np.ones(3))) >= need(k)

def _guard(frame: Image.Image, inks: tuple, crop: Image.Image, fx: int, fy: int) -> Image.Image:
    # crop: dest under the frame and 2 px around, the frame at (fx, fy) in it. Each ink in its own box.
    solid = sum(crop.getchannel('A').histogram()[round(255 * opaque):]) if crop.mode == 'RGBA' else crop.width * crop.height
    if solid < crop.width * crop.height / 2:
        return frame
    # All the glyphs: shadows don't go over another ink's.
    glyphs = Image.new('L', crop.size)
    for k in inks:
        box = (fx + k.x, fy + k.y, fx + k.x + k.w, fy + k.y + k.h)
        glyphs.paste(ImageChops.lighter(glyphs.crop(box), k.mask), box[:2])
    fw, fh = frame.size
    arr = None      # the frame, 3 px of nothing around it, once an ink changes
    for k in inks:
        x0, y0 = max(fx + k.x - 2, 0), max(fy + k.y - 2, 0)
        x1, y1 = min(fx + k.x + k.w + 3, crop.width), min(fy + k.y + k.h + 3, crop.height)
        if x1 - x0 < 3 or y1 - y0 < 3:
            continue
        fbox = (x0 - fx, y0 - fy, x1 - fx, y1 - fy)
        top = np.asarray(frame.crop(fbox).convert('RGBA')).astype(np.float64) if arr is None else \
            arr[fbox[1] + 3:fbox[3] + 3, fbox[0] + 3:fbox[2] + 3]
        own = np.zeros((y1 - y0, x1 - x0))
        m = np.asarray(k.mask, dtype=np.float64) / 255
        oy, ox = fy + k.y - y0, fx + k.x - x0
        own[oy:oy + m.shape[0], ox:ox + m.shape[1]] = m[:y1 - y0 - oy, :x1 - x0 - ox]
        # Cached per ink: its own px exactly, the ground coarsely (it moves under a card on an animated sky).
        ground, gl = crop.crop((x0, y0, x1, y1)), glyphs.crop((x0, y0, x1, y1))
        coarse = ground.resize((max((x1 - x0) // 4, 1), max((y1 - y0) // 4, 1)), Image.BOX).tobytes().translate(_coarse)
        key = (k.mask.tobytes(), k.color, k.stroke, frame.crop(fbox).tobytes(), gl.tobytes(), coarse)
        if (done := _inked.get(key)) is None:
            if len(_inked) > 512:
                _inked.clear()
            under = np.asarray(ground).astype(np.int64)
            done = _inked[key] = _ink(k, under, top, own, np.asarray(gl, dtype=np.float64) / 255)
        if done is None:
            continue
        px, changed = done
        if arr is None:
            arr = np.zeros((fh + 6, fw + 6, 4))
            arr[3:fh + 3, 3:fw + 3] = np.asarray(frame.convert('RGBA'))
        region = arr[fbox[1] + 3:fbox[3] + 3, fbox[0] + 3:fbox[2] + 3]
        region[changed] = px[changed]
    # The frame's pixels, and the shadow's right and bottom px past them.
    return frame if arr is None else Image.fromarray(np.round(arr[3:fh + 4, 3:fw + 4]).astype(np.uint8), 'RGBA')

def _ink(k, under: np.ndarray, top: np.ndarray, own: np.ndarray, glyphs: np.ndarray) -> tuple | None:
    '''The frame's pixels in the ink's box, the ink recolored, and which changed; None when it reads as it is.'''
    g = own > 0
    if not g.any():
        return None
    lin, alpha = _ground(under, top.astype(np.int64), glyphs)
    if alpha[g].mean() < opaque:
        return None
    # What's under the glyphs: the ground around them, spread over them.
    gl, free = lstar(lin), (glyphs == 0).astype(np.float64)
    near = np.maximum(_box(free, 2), 1e-9)
    fill = np.where(free > 0, gl, _box(gl * free, 2) / near)
    c, f = Color(k.color), need(k)
    if np.percentile(np.abs(c.L - fill[g]), 10) >= f:
        return None
    lo, mid, hi = np.percentile(fill[g], (10, 50, 90))
    grain = np.abs(fill - _box(fill, k.stroke))[_box(g.astype(np.float64), 1) > 0].mean()
    base, px = _lut[np.array(c.rgb)], top.copy()
    if hi - lo < flat and grain < grainy:
        if mid <= 50:
            ink = toward(base, np.maximum(c.L, np.minimum(fill + f, 100)))
        else:
            # Dark, in the ground's own hue.
            ink = toward(_box(lin * free[..., None], 2) / near[..., None], np.maximum(fill - f, 0))
        px[..., :3] = np.where(g[..., None], _srgb(ink), px[..., :3])
        return px, (px != top).any(-1)
    # Light on the ground, no more glare than its stroke may add to it; a dark copy 1 px down-right.
    top_l = lstar_of(min(glare / k.stroke + float(_y(np.array(mid))), 1)) if palette().glare else 92
    px[..., :3] = np.where(g[..., None], _srgb(toward(base, np.array(max(c.L, min(mid + f, top_l, 92))))), px[..., :3])
    s = np.zeros_like(own)
    s[1:, 1:] = (own * top[..., 3] / 255)[:-1, :-1]
    s = shadow * s * (glyphs == 0)
    a = px[..., 3] / 255
    na = s + a * (1 - s)
    px[..., :3] *= (a * (1 - s) / np.maximum(na, 1e-9))[..., None]
    px[..., 3] = 255 * na
    return px, (px != top).any(-1)


def dimmed(region: Image.Image, frame: Image.Image, inks: tuple) -> Image.Image:
    '''The blurred ground of a frost panel, dimmed so its p90 sits a floor under the panel's light text.
    Only what the panel's own background doesn't already dim; between the palette's dim floor and cap.'''
    p = palette()
    light = [k for k in inks if Color(k.color).L > 50]
    if not enabled or not light or region.size != frame.size:
        return region
    target = min(Color(k.color).L - need(k) for k in light)
    # Blurred: a quarter of the px says as much.
    small = (lambda im: im.reduce(4)) if min(frame.size) >= 8 else (lambda im: im)
    under, top = small(region), small(frame)
    if _lstar8[max(e[1] for e in under.getextrema()[:3])] <= target:
        return region
    key = (under.tobytes(), top.tobytes(), under.size, target, p.dim)
    if (d := _dims.get(key)) is None:
        if len(_dims) > 64:
            _dims.clear()
        # In steps: a panel that dims a little differently every frame is redrawn and sent every frame.
        d = _dims[key] = round(_dim(under, top, target, p.dim) * 20) / 20
    if d <= 0:
        return region
    if (lut := _luts.get(d)) is None:
        lut = _luts[d] = _Lut(_srgb(_lut * (1 - d)).astype(int).tolist() * 3 + list(range(256)))
    return region.convert('RGBA').point(lut)

_dims, _luts = {}, {}

def _dim(region: Image.Image, frame: Image.Image, target: float, dim: tuple[float, float]) -> float:
    under = np.asarray(region.convert('RGBA')).astype(np.int64)
    top = np.asarray(frame.convert('RGBA')).astype(np.int64)
    panel = top[..., 3] > 0
    if not panel.any():
        return 0
    lin, _ = _ground(under, top, np.zeros(panel.shape))
    hi = np.percentile(lstar(lin)[panel], 90)
    lo, cap = dim
    return float(np.clip(1 - _y(np.array(target)) / max(float(_y(np.array(hi))), 1e-9), lo, cap)) if hi > target else lo
