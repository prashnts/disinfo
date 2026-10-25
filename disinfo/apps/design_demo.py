'''Design system demo: discore and disinfo's media, live, in tabs. Toggled by show_design_demo.

Full width, below the time. A tab and its pages are touch targets (or design_demo from the remote):
the pages cycle, a touched one stays until touched again. The layouts sit in a box whose width
breathes, so they reflow on screen.
'''
import math
from dataclasses import replace as dc_replace

from PIL import Image, ImageDraw

from discore import ease
from discore.cairo import load_svg
from discore.data_structures import FrameState
from discore.elements import Frame, Box, StillImage
from discore.layers import div, DivStyle, rounded_rectangle
from discore.button import button, ButtonStyle
from discore.layouts import hstack, vstack, grid, composite_at, place_at, Spacer, Grow
from discore.progress import progress_bar, ProgressStyle
from discore.scroller import HScroller, VScroller
from discore.stack import Stack, StackStyle
from discore.slides import Slides, SlidesStyle
from discore.spriteim import SpriteIcon
from discore.text import text, TextStyle
from discore.transitions import FadeIn, SlideIn, ScaleIn, Resize, NumberTransition, text_slide_in
from discore.widget import Widget
from disinfo import fonts
from disinfo.drat.app_states import RuntimeStateManager, TouchStateManager
from disinfo.utils import mdi
from disinfo.utils.mjpeg import MJPEGStream
from disinfo.utils.weather_icons import get_icon_for_condition

title_style = TextStyle(font=fonts.bitocra7, color='#a6a6a6')
label_style = TextStyle(font=fonts.microfont_35_reg, color='#808080')
dim_style = TextStyle(font=fonts.microfont_35_reg, color='#5b5e64')
dark_style = TextStyle(font=fonts.microfont_35_reg, color='#000000')
body_style = TextStyle(font=fonts.microfont_35_reg, color='#a6a6a6', spacing=2)
palette = ['#42a459', '#2d83b4', '#b7925e', '#8a6cc8', '#c93f20']
page_seconds = 10


class Swatch(Box):
    '''A rounded block, optionally labelled. Grows if asked to.'''

    def __init__(self, color: str, w: int = 8, h: int = 8, grow: float = 0, label: str = ''):
        self.color, self.w, self.h, self.grow, self.label = color, w, h, grow, label
        self.hash = ('Swatch', color, w, h, grow, label)

    def measure(self, max_w: int, max_h: int) -> tuple[int, int]:
        lw = text(self.label, dark_style).width + 4 if self.label else 0
        return min(max(self.w, lw), max_w), min(self.h, max_h)

    def render(self, w: int, h: int) -> Frame:
        img = rounded_rectangle(max(w, 2), max(h, 2), (2,) * 4, self.color, 0, '#00000000').copy()
        f = Frame(img, ('swatch', self.color, w, h))
        return composite_at(text(self.label, dark_style), f, 'mm') if self.label else f


class Ring(Box):
    '''A gauge: as big as the space it gets, round.'''

    def __init__(self, value: float, color: str, size: int = 18):
        self.value, self.color, self.size_ = value, color, size
        self.hash = ('Ring', round(value, 2), color, size)

    def measure(self, max_w: int, max_h: int) -> tuple[int, int]:
        d = min(self.size_, max_w, max_h)
        return d, d

    def render(self, w: int, h: int) -> Frame:
        d, s = min(w, h), 4     # drawn 4x, scaled down: smooth edges
        img = Image.new('RGBA', (d * s, d * s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        box = (s, s, d * s - s, d * s - s)
        draw.arc(box, 0, 360, fill='#ffffff22', width=2 * s)
        draw.arc(box, -90, -90 + 360 * self.value, fill=self.color, width=2 * s)
        f = Frame(img.resize((d, d), Image.LANCZOS), ('ring', round(self.value, 2), d))
        return composite_at(text(f'{round(self.value * 100)}', label_style), f, 'mm')


class Sparkline(Box):
    '''A line through values, stretched to the width it gets.'''
    grow = 1

    def __init__(self, values: list[float], color: str, h: int = 12):
        self.values, self.color, self.h = values, color, h
        self.hash = ('Sparkline', tuple(round(v, 2) for v in values), color, h)

    def measure(self, max_w: int, max_h: int) -> tuple[int, int]:
        return min(16, max_w), min(self.h, max_h)

    def render(self, w: int, h: int) -> Frame:
        img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        lo, hi = min(self.values), max(self.values)
        pts = [(i * (w - 1) / (len(self.values) - 1), (h - 2) - (v - lo) / ((hi - lo) or 1) * (h - 3)) for i, v in enumerate(self.values)]
        ImageDraw.Draw(img).line(pts, fill=self.color, width=1)
        ImageDraw.Draw(img).point(pts[-1], fill='#ffffff')
        return Frame(img, ('sparkline', self.hash, w, h))


def breathe(fs: FrameState, lo: int, hi: int, period: float = 6) -> int:
    t = (fs.tick % period) / period
    return round(lo + (hi - lo) * ease.cubic.cubic_in_out(1 - abs(2 * t - 1)))

def ruler(w: int) -> Frame:
    # The breathing box's edges.
    img = Image.new('RGBA', (w, 3), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line([(0, 1), (w - 1, 1)], fill='#ffffff18')
    d.line([(0, 0), (0, 2)], fill='#ffffff60')
    d.line([(w - 1, 0), (w - 1, 2)], fill='#ffffff60')
    return Frame(img, ('ruler', w))

def breathing(w: int, body: Frame) -> Frame:
    return vstack([hstack([ruler(w - 18), text(f'w {w}', dim_style)], gap=2), div(body, width=w, anchor='ml')], gap=3)

def labelled(name: str, frame: Frame) -> Frame:
    return vstack([text(name, label_style), frame], gap=2)

def changing(fs: FrameState, every: float = 2, n: int = 10) -> int:
    return int(fs.tick // every) % n

def chip(v: int) -> Frame:
    # A value to move around: tagged by it, so transitions run when it changes.
    return div(text(str(v), dark_style), width=12, height=9, radius=2, background=palette[v % 5]).tag(('dd.chip', v))

photo = Frame(Image.open('assets/test.jpg').convert('RGBA'), 'assets/test.jpg')


# Flex: where Spacers put the blocks, the free space goes to them.
spacings = {
    'start': lambda a, b, c: [a, b, c],
    'end': lambda a, b, c: [Spacer(), a, b, c],
    'center': lambda a, b, c: [Spacer(), a, b, c, Spacer()],
    'between': lambda a, b, c: [a, Spacer(), b, Spacer(), c],
}

def spacer_page(fs: FrameState, width: int, h: int) -> Frame:
    w = breathe(fs, width // 2, width)
    rows = [hstack([text(k, label_style), hstack(spaced(*[Swatch(c, 8, 6) for c in palette[:3]]), gap=2)], gap=4) for k, spaced in spacings.items()]
    return breathing(w, vstack(rows, gap=3, align='hstretch'))

def grow_page(fs: FrameState, width: int, h: int) -> Frame:
    w = breathe(fs, width // 2, width)
    return breathing(w, vstack([
        hstack([Swatch(palette[0], 6, 9, grow=1, label='1'), Swatch(palette[1], 6, 9, grow=2, label='2'), Swatch(palette[2], 6, 9, grow=1, label='1')], gap=2),
        hstack([Swatch(palette[3], 14, 9, label='fix'), Spacer(), Swatch(palette[4], 14, 9, label='fix')], gap=2),
        hstack([text('fit', label_style), text('this sentence gets cut to the room left', body_style, overflow='fit'), Swatch(palette[0], 9, 7)], gap=3),
    ], gap=4, align='hstretch'))

def shapes_page(fs: FrameState, width: int, h: int) -> Frame:
    w = breathe(fs, width // 2, width)
    t = fs.tick
    values = [math.sin(t * 0.8 + i * 0.5) + 0.4 * math.sin(i * 1.7 + t * 2.1) for i in range(20)]
    value = 0.5 + 0.5 * math.sin(t * 0.6)
    return breathing(w, vstack([
        # The column grows, its items stretch.
        hstack([Ring(value, palette[0]), Grow(vstack([
            Sparkline(values, palette[1]),
            hstack([Swatch(palette[3], 10, 7, label='pill'), Swatch(palette[2], 10, 7, label='box', grow=1)], gap=2),
        ], gap=3, align='hstretch'))], gap=4, align='center'),
        progress_bar(value, ProgressStyle(width=w, height=3, radius=1, color=palette[0])),
    ], gap=4, align='hstretch'))


# Grid: the same seven blocks, every few seconds another shape.
shapes = [dict(ncols=2), dict(ncols=3), dict(ncols=4), dict(nrows=2), dict()]

def grid_shape_page(fs: FrameState, width: int, h: int) -> Frame:
    kw = shapes[int(fs.tick // 2.4) % len(shapes)]
    cells = [Swatch(palette[i % 5], 8 + 4 * (i % 3), 6, label=str(i + 1)) for i in range(7)]
    name = ' '.join(f'{k} {v}' for k, v in kw.items()) or 'square'
    return vstack([text(name, label_style), grid(cells, gap=2, anchor='ml', **kw)], gap=3)

def masonry_page(fs: FrameState, width: int, h: int) -> Frame:
    # The same blocks: in rows, the tallest sets each row; masonry, under the shortest column.
    cells = [Swatch(palette[i % 5], 8, h) for i, h in enumerate([10, 4, 7, 4, 12, 6, 5, 8])]
    side = lambda name, masonry: labelled(name, grid(cells, ncols=3, gap=2, anchor='tm', masonry=masonry))
    return hstack([side('rows', False), side('masonry', True)], gap=12, align='top')

def share_page(fs: FrameState, width: int, h: int) -> Frame:
    w = breathe(fs, width // 3, width)
    cells = [Swatch(palette[0], 6, 7, grow=1, label='grow'), Swatch(palette[1], 10, 7), Swatch(palette[2], 6, 7, grow=1),
             Swatch(palette[3], 10, 7), Swatch(palette[4], 46, 7, label='too wide, cut'), Swatch(palette[1], 6, 5)]
    return breathing(w, labelled('cols share w', grid(cells, ncols=3, gap=2, width=w)))

anchors = ['tl', 'tm', 'tr', 'mr', 'br', 'bm', 'bl', 'ml', 'mm']

def anchor_page(fs: FrameState, width: int, h: int) -> Frame:
    w = breathe(fs, width // 2, width)
    a = anchors[int(fs.tick // 1.2) % len(anchors)]
    cells = [Swatch(palette[i % 5], 6 + 2 * (i % 2), 4) for i in range(6)]
    # The cells: growers fill theirs.
    under = grid([Swatch('#ffffff14', 1, 1, grow=1)] * 6, ncols=3, gap=2, width=w, height=30)
    g = grid(cells, ncols=3, gap=2, width=w, height=30, anchor=a)
    return breathing(w, labelled(f'anchor {a}', composite_at(g, under, 'tl')))


# Type: fonts, sizes, weights, tones, outlines, overflow, digits that slide.
sample_fonts = [('bitocra7', fonts.bitocra7), ('microfont', fonts.microfont_35_reg), ('tamzen', fonts.tamzen__rs), ('spleen', fonts.spleen__s),
                ('scientifica', fonts.scientifica__r), ('cozette', fonts.cozette), ('px_op', fonts.px_op__r), ('galmuri9', fonts.galmuri9), ('px_op l', fonts.px_op__l)]

def fonts_page(fs: FrameState, w: int, h: int) -> Frame:
    rows = [hstack([text(name, dim_style), Spacer(), text('Aa 0123', TextStyle(font=font, color='#a6a6a6'))], gap=3) for name, font in sample_fonts]
    return div(vstack(rows, gap=2, align='hstretch'), width=w, anchor='tl')

sizes = [('5', fonts.microfont_35_reg), ('7', fonts.bitocra7), ('9', fonts.tamzen__rs), ('11', fonts.scientifica__r), ('13', fonts.cozette), ('16', fonts.px_op__l)]

def sizes_page(fs: FrameState, w: int, h: int) -> Frame:
    # The pixel fonts are drawn at their own size, one each.
    rows = [hstack([div(text(px, dim_style), width=10, anchor='ml'), text(fs.now.strftime('%H:%M'), TextStyle(font=font, color='#a6a6a6'))], gap=3) for px, font in sizes]
    return vstack(rows, gap=3)

weights = [
    ('scientifica', [('Regular', fonts.scientifica__r), ('Bold', fonts.scientifica__b), ('Italic', fonts.scientifica__i)]),
    ('px_op', [('Aa', fonts.px_op__l), ('Aa', fonts.px_op__lb)]),
    ('zx', [('Aa', fonts.zx_spectrum), ('Aa', fonts.zx_spectrum_b)]),
    ('mecha', [('Aa', fonts.mecha), ('Aa', fonts.mecha_bold), ('Aa', fonts.mecha_cond)]),
]

def weights_page(fs: FrameState, w: int, h: int) -> Frame:
    return vstack([labelled(name, hstack([text(s, TextStyle(font=f, color='#a6a6a6')) for s, f in faces], gap=5)) for name, faces in weights], gap=3)

# LEDs blow out light tones: the greys stop at #a6a6a6, colors are muted.
tones = [('dim', '#5b5e64'), ('muted', '#808080'), ('bright', '#a6a6a6'), ('white', '#ffffff'), ('warn', '#b7925e'), ('ok', '#42a459')]

def tones_page(fs: FrameState, w: int, h: int) -> Frame:
    rows = [hstack([Swatch(c, 5, 5), div(text(name, TextStyle(font=fonts.bitocra7, color=c)), width=34, anchor='ml'), text(c, dim_style)], gap=3) for name, c in tones]
    # Dark text on a color: unlit pixels read best.
    pills = hstack([div(text(s, dark_style), padding=(1, 2, 1, 2), radius=2, background=c) for s, c in [('done', palette[1]), ('ok', palette[0]), ('fail', palette[4])]], gap=2)
    return vstack([*rows, pills], gap=3)

def outline_page(fs: FrameState, w: int, h: int) -> Frame:
    # Over something busy. TTF only: the bitmap (.bdf) fonts can't be outlined.
    style = TextStyle(font=fonts.greybeard, color='#ffffff', outline_color='#000000')
    f = stripes(fs, w, 36)
    f = place_at(text('no outline', style), f, 4, 10, 'ml')
    f = place_at(text('outline 1', dc_replace(style, outline=1)), f, 4, 26, 'ml')
    return f


def wrap_page(fs: FrameState, width: int, h: int) -> Frame:
    w = breathe(fs, width // 3, width)
    words = 'Constraints go down, sizes come up, and the text wraps into the room it is given.'
    return breathing(w, vstack([
        div(text(words, body_style, overflow='wrap', max_lines=4), padding=2, radius=2, background='#ffffff10'),
        hstack([Swatch(palette[2], 7, 7), text('max_lines 1, then cut', body_style, overflow='wrap', max_lines=1)], gap=3),
        # multiline: its own wrap, at a fixed width.
        text('multiline, at width 60 whatever the room', body_style, multiline=True, width=60),
    ], gap=4, align='hstretch'))

def digits_page(fs: FrameState, w: int, h: int) -> Frame:
    big = TextStyle(font=fonts.cozette, color='#a6a6a6')
    n = f'{int(fs.tick * 2) % 1000:03}'
    # Up from the top, down from the bottom: a value that wanders.
    wander = f'{round(50 + 40 * math.sin(int(fs.tick) / 3))}'
    return grid([
        labelled('per digit', text_slide_in(fs, fs.now.strftime('%H:%M:%S'), big, name='dd.clock')),
        labelled('up, down', text_slide_in(fs, wander, big, name='dd.wander')),
        labelled('from the top', text_slide_in(fs, n, big, edge='top', name='dd.count')),
        labelled('together', text_slide_in(fs, n, big, together=True, name='dd.together')),
    ], ncols=2, gap=4)


# Boxes: div, frost, images behind, bars.
def div_page(fs: FrameState, w: int, h: int) -> Frame:
    box = lambda name, **kw: div(text(name, label_style), **kw)
    return grid([
        box('padding', padding=3, background='#ffffff14'),
        box('radius', padding=3, radius=3, background='#ffffff14'),
        box('border', padding=3, border=1, border_color=palette[1]),
        box('both', padding=3, radius=3, border=1, border_color=palette[0], background='#42a45930'),
        box('margin', padding=2, margin=2, radius=2, background='#ffffff14'),
        box('w 40 tl', width=40, height=14, anchor='tl', background='#ffffff14'),
    ], ncols=2, gap=3, anchor='tl')

def stripes(fs: FrameState, w: int, h: int) -> Frame:
    # Moves, so the frost shows.
    off = int(fs.tick * 8) % 12
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, x in enumerate(range(-h - 12 + off, w, 6)):
        d.line([(x, h), (x + h, 0)], fill=palette[i % 5], width=2)
    return Frame(img, ('dd.stripes', w, h, off))

def panned(fs: FrameState, w: int, h: int) -> Frame:
    # The photo's header pins, sliding by: something sharp to blur.
    img = photo.resize((w * 2, w * 2), ratio_fn=max).image
    off, top = int(fs.tick * 6) % (img.width - w), int(img.height * 0.3) - h // 2
    return Frame(img.crop((off, top, off + w, top + h)), ('dd.panned', w, h, off))

def frost_page(fs: FrameState, w: int, h: int) -> Frame:
    # place_at (and composite_at) frost: blurs what's under the frame first.
    h = min(h, 44)
    cw = (w - 8) // 3
    card = lambda s: div(text(s, title_style), width=cw, height=h - 8, radius=3, background='#00000030')
    f = panned(fs, w, h)
    for i, frost in enumerate([0, 1.5, 3]):
        f = place_at(card(f'{frost:g}'), f, 2 + i * (cw + 2), 4, 'tl', frost=frost)
    return labelled('frost 0, 1.5, 3', f)

def image_page(fs: FrameState, w: int, h: int) -> Frame:
    # An image behind: a div's background_frame, filled. The text on a scrim.
    h = min(h, 48)
    scrim = div(hstack([text('miniPiTFT', title_style), Spacer(), text('240x135', label_style)]), padding=(1, 2, 1, 2), background='#000000a0', width=w - 4)
    return div(scrim, width=w, height=h, radius=3, anchor='bl', background_frame=photo)

def bars_page(fs: FrameState, w: int, h: int) -> Frame:
    v = 0.5 + 0.5 * math.sin(fs.tick * 0.7)
    styles = [ProgressStyle(width=w, height=2), ProgressStyle(width=w, height=4, radius=2, color=palette[1]), ProgressStyle(width=w, height=6, radius=1, color=palette[2], track='#ffffff10')]
    return vstack([
        *[progress_bar(v, s) for s in styles],
        hstack([Ring(v, palette[0]), Ring(1 - v, palette[3]), Ring(0.42, palette[4], 14)], gap=4),
    ], gap=4)


# Motion: transitions run when the value (its hash) changes.
def transitions_page(fs: FrameState, w: int, h: int) -> Frame:
    v = chip(changing(fs))
    return grid([
        labelled('fade', FadeIn('dd.fade', 0.5).mut(v).draw(fs)),
        labelled('slide up', SlideIn('dd.up', 0.4, ease.cubic.cubic_out, edge='bottom').mut(v).draw(fs)),
        labelled('slide left', SlideIn('dd.left', 0.4, ease.cubic.cubic_out, edge='right').mut(v).draw(fs)),
        labelled('scale', ScaleIn('dd.scale', 0.4).mut(v).draw(fs)),
        labelled('resize', Resize('dd.resize', 0.5, ease.cubic.cubic_in_out).mut(Swatch(palette[changing(fs, 2, 3)], 8 + 10 * changing(fs, 2, 3), 7).natural).draw(fs)),
    ], ncols=3, gap=4, anchor='tl')

ticker_lines = [('L88/212', '23:30'), ('Bracket left +2', ''), ('PLA Basic Red', '41.5g')]

def ticker_page(fs: FrameState, w: int, h: int) -> Frame:
    # Slides with an edge and no height: each line rolls up, the scrim stays.
    line = lambda a, b: div(hstack([text(a, title_style), Spacer(), text(b, label_style)], gap=3), width=w - 4)
    rolled = Slides('dd.ticker', SlidesStyle(width=w - 4, edge='bottom')).mut([(lambda a=a, b=b: line(a, b), 2) for a, b in ticker_lines]).draw(fs)
    return div(div(rolled, padding=(1, 2, 1, 2), background='#000000a0'), width=w, height=min(h, 48), radius=3, anchor='bl', background_frame=photo)

def number_page(fs: FrameState, w: int, h: int) -> Frame:
    # A number eased to its new value: what draws it is plain.
    target = [0.2, 0.9, 0.5, 0.7][changing(fs, 3, 4)]
    v = NumberTransition('dd.number', 1.2, ease.cubic.cubic_in_out, initial=0).mut(target).value(fs)
    return vstack([
        hstack([Ring(v, palette[1], 22), text(f'{v:.2f}', TextStyle(font=fonts.cozette, color='#a6a6a6'))], gap=6, align='center'),
        progress_bar(v, ProgressStyle(width=w, height=4, radius=2, color=palette[1])),
    ], gap=4)


# Scroll: what doesn't fit moves through a window. speed: seconds per step, delta: px per step.
long = 'A line longer than the box scrolls by, pauses at the start, and goes again.'
items = ['Weather', 'Trash', 'Printer', 'Metro', 'Calendar', 'Planes', 'Dishwasher', 'Music', 'News']

def lines(n: int = len(items)) -> list[Frame]:
    return [hstack([Swatch(palette[i % 5], 4, 4), text(name, title_style)], gap=3) for i, name in enumerate(items[:n])]

def marquee_page(fs: FrameState, w: int, h: int) -> Frame:
    return vstack([
        labelled('pause at the start', HScroller(size=w, name='dd.marquee', speed=0.02, pause_at_loop=True).set_frame(text(long, title_style)).draw(fs.tick)),
        labelled('slower, bar', HScroller(size=w, name='dd.slow', speed=0.06, scrollbar=True).set_frame(text(long, label_style)).draw(fs.tick)),
        labelled('fits: still', HScroller(size=w, name='dd.still').set_frame(text('short', title_style)).draw(fs.tick)),
    ], gap=4)

def pauses_page(fs: FrameState, w: int, h: int) -> Frame:
    # Stops at each line: pauses are the px it stops at, in the content.
    rows = lines()
    ys = [sum(r.height + 3 for r in rows[:i]) for i in range(len(rows))]
    v = VScroller(size=rows[0].height, name='dd.pauses', pause_duration=1.2).set_frame(vstack(rows, gap=3), pauses=ys, pause_offset=0).draw(fs.tick)
    return labelled('a line at a time', div(v, padding=2, radius=2, background='#ffffff10'))

def vertical_page(fs: FrameState, w: int, h: int) -> Frame:
    v = VScroller(size=min(h, 50) - 7, name='dd.vertical', speed=0.05, scrollbar=True).set_frame(div(vstack(lines(), gap=3), width=w - 4, anchor='tl')).draw(fs.tick)
    return labelled('vertical, bar', v)

def target_page(fs: FrameState, w: int, h: int) -> Frame:
    # Scrolls to a position and stays: what the card stacks do.
    rows = lines()
    i = changing(fs, 2, len(rows))
    to = sum(r.height + 3 for r in rows[:i])
    v = VScroller(size=24, name='dd.target', speed=0.01).set_frame(vstack(rows, gap=3)).set_target(to + 24).draw(fs.tick)
    return labelled(f'target: {items[i]}', div(v, padding=2, radius=2, background='#ffffff10'))


# Stack: cards (Widgets) in a scroller that goes to the one on top. Each waits its wait_time, then the next.
def card(name: str, body: Frame, focus: bool = False) -> Widget:
    return Widget(name, body, focus=focus, wait_time=2)

def cards(fs: FrameState, prefix: str, focus: str | None = None) -> list[Widget]:
    big = TextStyle(font=fonts.cozette, color='#a6a6a6')
    return [card(f'{prefix}.{name}', body, name == focus) for name, body in [
        ('weather', hstack([Frame(get_icon_for_condition('rain', 1), ('dd.weather', 'rain')), text('11.2', big)], gap=3, align='center')),
        ('printer', vstack([hstack([sprites[0].draw(fs.tick), text('63%', big)], gap=3, align='center'), progress_bar(0.63, ProgressStyle(width=40))], gap=2)),
        ('trash', hstack(pngs[:2], gap=2)),
        ('note', div(text('cards come and go', body_style, overflow='wrap', max_lines=2), width=40, anchor='tl')),
    ]]

def column_page(fs: FrameState, w: int, h: int) -> Frame:
    return Stack('dd.column', StackStyle(size=min(h, 56))).mut(cards(fs, 'dd.column')).draw(fs)

def row_page(fs: FrameState, w: int, h: int) -> Frame:
    return Stack('dd.row', StackStyle(size=w, horizontal=True, offset_top=0)).mut(cards(fs, 'dd.row')).draw(fs)

def focus_page(fs: FrameState, w: int, h: int) -> Frame:
    # A card with focus stays on top: a print starting, a plane overhead.
    focused = RuntimeStateManager().get_state(fs).design_demo.get('focus')
    names = ['weather', 'printer', 'trash', 'note']
    buttons = vstack([toggle(fs, text(n, title_style if n == focused else dim_style), {'focus': None if n == focused else n}, on=n == focused) for n in names], gap=2)
    stack = Stack('dd.focus', StackStyle(size=min(h, 56))).mut(cards(fs, 'dd.focus', focused)).draw(fs)
    return hstack([buttons, stack], gap=6, align='top')


# Media: icons, sprites, images, streams.
pngs = [StillImage(f'assets/raster/{f}') for f in ('trash-bin-green-10x14.png', 'trash-bin-yellow-10x14.png', 'plant-9x9.png', 'nozzle-9x9-done.png', 'sunset-7x9.png')]
sprites = [SpriteIcon('assets/raster/nozzle-alt-9x9.png', step_time=0.1), SpriteIcon('assets/unicorn-weather-icons/cloudy.png', step_time=0.05), SpriteIcon('assets/sunset-arrow.png', step_time=0.2)]
svgs = [load_svg('assets/airliner.svg'), load_svg('assets/helicopter.svg')]
nyan = SpriteIcon('assets/raster/nyan-cat2.gif', step_time=0.07)

def icon_row(name: str, frames: list[Frame]) -> Frame:
    return hstack([div(text(name, dim_style), width=24, anchor='ml'), *frames], gap=3, align='center')

def raster_page(fs: FrameState, w: int, h: int) -> Frame:
    weather = [Frame(get_icon_for_condition(c, 1), ('dd.weather', c)) for c in ('clear-day', 'partly-cloudy-day', 'rain', 'snow')]
    return vstack([
        icon_row('png', pngs),
        icon_row('sprite', [s.draw(fs.tick) for s in sprites]),
        icon_row('pixel', weather),
        icon_row('gif', [nyan.draw(fs.tick).resize((20, 20), ratio_fn=min)]),
    ], gap=3)

def vector_page(fs: FrameState, w: int, h: int) -> Frame:
    # Drawn at the size asked: svg files, Material Design Icons by name (downloaded once, kept in assets/mdi).
    return vstack([
        icon_row('svg', [f.resize((14, 14), ratio_fn=min) for f in svgs]),
        icon_row('mdi', [mdi.icon(n, 12, c) for n, c in [('lightbulb', palette[2]), ('weather-night', palette[1]), ('robot-vacuum', '#a6a6a6')]]),
        icon_row('mdi 20', [mdi.icon('weather-sunset', 20, palette[2])]),
    ], gap=3)

def ops_page(fs: FrameState, w: int, h: int) -> Frame:
    # Frame ops: each a new frame, hashed by the op.
    size = min((w - 6) // 3, (h - 17) // 2)
    thumb = photo.resize((size, size), ratio_fn=min)
    return grid([labelled(name, f) for name, f in [
        ('as is', thumb), ('opacity', thumb.opacity(0.4)), ('bright', thumb.brightness(0.5)),
        ('color', thumb.color_(0)), ('contrast', thumb.contrast(2)), ('rotate', thumb.rotate(changing(fs, 0.1, 36) * 10)),
    ]], ncols=3, gap=3, anchor='tl')

def stream_page(fs: FrameState, w: int, h: int) -> Frame:
    # Latest frame of an MJPEG stream, decoded at the size asked. None while it connects.
    url = RuntimeStateManager().get_state(fs).stream_url or next(iter(fs.config.printer_streams.values()), None)
    if not url:
        return text('no stream: set stream_url', label_style)
    view = MJPEGStream(url).read(w, h - 9)
    return labelled(url.split('//')[-1][:40], view or text('connecting', dim_style))


# Touch: buttons are targets; the server finds the one touched and sends its action.
def toggle(fs: FrameState, label: Frame, payload: dict, on: bool = False, hold: float = 0) -> Frame:
    touch = TouchStateManager()
    return button(label, 'design_demo', payload, pressed=touch.is_pressed(fs, 'design_demo', payload), style=tab_styles[on],
                  hold=hold, progress=hold and touch.held_for(fs, 'design_demo', payload) / hold)

def buttons_page(fs: FrameState, w: int, h: int) -> Frame:
    s = RuntimeStateManager().get_state(fs).design_demo
    taps, lamp = s.get('taps', 0), s.get('lamp', False)
    bulb = mdi.icon('lightbulb' if lamp else 'lightbulb-outline', 9, palette[2] if lamp else '#808080')
    return vstack([
        labelled('tap', toggle(fs, text(f'tapped {taps}', title_style), {'taps': taps + 1})),
        labelled('toggle', toggle(fs, hstack([bulb, text('lamp', title_style)], gap=2, align='center'), {'lamp': not lamp}, on=lamp)),
    ], gap=4)

def hold_page(fs: FrameState, w: int, h: int) -> Frame:
    held = RuntimeStateManager().get_state(fs).design_demo.get('held', False)
    return vstack([
        labelled('hold 1.5 s', toggle(fs, text('armed' if held else 'hold to arm', title_style), {'held': not held}, on=held, hold=1.5)),
        text('fills while held, acts once full', dim_style),
    ], gap=4)

def scrolled_page(fs: FrameState, w: int, h: int) -> Frame:
    # Targets move with what they're in: here, a scroller.
    picked = RuntimeStateManager().get_state(fs).design_demo.get('picked')
    row = hstack([toggle(fs, text(c, title_style), {'picked': c}, on=c == picked) for c in 'abcdefghijkl'], gap=2)
    return vstack([
        labelled('in a scroller', HScroller(size=w, name='dd.targets', speed=0.04, pause_at_loop=True).set_frame(row).draw(fs.tick)),
        text(f'picked {picked}' if picked else 'pick one', label_style),
    ], gap=4)


tabs = {
    'flex': [('spacer', spacer_page), ('grow', grow_page), ('shapes', shapes_page)],
    'grid': [('grid', grid_shape_page), ('masonry', masonry_page), ('width', share_page), ('anchor', anchor_page)],
    'stack': [('column', column_page), ('row', row_page), ('focus', focus_page)],
    'type': [('fonts', fonts_page), ('sizes', sizes_page), ('weights', weights_page), ('tones', tones_page), ('outline', outline_page), ('wrap', wrap_page)],
    'box': [('div', div_page), ('frost', frost_page), ('image', image_page), ('bars', bars_page)],
    'motion': [('transitions', transitions_page), ('digits', digits_page), ('ticker', ticker_page), ('number', number_page)],
    'scroll': [('marquee', marquee_page), ('pauses', pauses_page), ('vertical', vertical_page), ('target', target_page)],
    'media': [('icons', raster_page), ('vector', vector_page), ('ops', ops_page), ('stream', stream_page)],
    'touch': [('buttons', buttons_page), ('hold', hold_page), ('scrolled', scrolled_page)],
}

tab_cell = dict(padding=(1, 3, 1, 3), radius=2, border=1)
tab_styles = {
    False: ButtonStyle(normal=DivStyle(background='#00000000', border_color='#ffffff20', **tab_cell),
                       pressed=DivStyle(background='#ffffff40', border_color='#ffffff90', **tab_cell)),
    True: ButtonStyle(normal=DivStyle(background='#ffffff20', border_color='#ffffff60', **tab_cell),
                      pressed=DivStyle(background='#ffffff40', border_color='#ffffff90', **tab_cell)),
}

def tab_row(fs: FrameState, current: str, w: int) -> Frame:
    buttons = [toggle(fs, text(name, title_style if name == current else dim_style), {'tab': name, 'page': None}, on=name == current) for name in tabs]
    # One row if it fits, else as few rows as fit, as even as they go.
    for n in range(len(buttons), 1, -1):
        if grid(buttons, ncols=n, gap=2).width <= w:
            break
    rows = math.ceil(len(buttons) / n)
    return grid(buttons, ncols=math.ceil(len(buttons) / rows), gap=2, anchor='ml')

def page_row(fs: FrameState, name: str, shown: list[int], pinned: int | None, n: int) -> Frame:
    # The first page's name, the page numbers to touch: pins one, again unpins.
    dot = lambda i: toggle(fs, text(str(i + 1), title_style if i in shown else dim_style), {'page': None if i == pinned else i}, on=i == pinned)
    return hstack([text(name, title_style), Spacer(), *[dot(i) for i in range(n)]], gap=2, align='center')

def packed(fs: FrameState, pages: list, first: int, w: int, h: int) -> tuple[list[int], Frame]:
    # The page, and the next ones while they fit: the room below isn't left empty.
    shown, frames, room = [], [], h
    for k in range(len(pages)):
        i = (first + k) % len(pages)
        name, page = pages[i]
        f = div(page(fs, w, room), width=w, anchor='tl')
        if k:
            f = vstack([hstack([text(name, title_style), Swatch('#ffffff14', 4, 1, grow=1)], gap=3, align='center'), f], gap=3)
            f = div(f, width=w, anchor='tl')
        if k and f.height > room:
            break
        shown.append(i)
        frames.append(f)
        room -= f.height + 8
        if room < 12:
            break
    return shown, vstack(frames, gap=8)

def composer(fs: FrameState, w: int, h: int) -> Frame | None:
    state = RuntimeStateManager().get_state(fs)
    if not state.show_design_demo:
        return None
    s = state.design_demo
    tab = s.get('tab') if s.get('tab') in tabs else 'flex'
    pages, pinned = tabs[tab], s.get('page')
    pinned = pinned if pinned is not None and pinned < len(pages) else None
    head = tab_row(fs, tab, w)
    first = pinned if pinned is not None else int(fs.tick // page_seconds) % len(pages)
    row = lambda shown: div(page_row(fs, pages[first][0], shown, pinned, len(pages)), width=w)
    ph = h - head.height - row([first]).height - 8
    shown, body = packed(fs, pages, first, w, ph)
    row = row(shown)
    # A slides of one: it fades in when the pages change.
    body = Slides(f'dd.{tab}.{first}', SlidesStyle(width=w, height=ph)).mut([(lambda: body, page_seconds)]).draw(fs)
    return div(vstack([head, row, body], gap=4), width=w, height=h, anchor='tl').tag(('design_demo', w, h))

def design_demo_app(fs: FrameState, size: tuple[int, int]) -> Widget:
    # size: the room it gets, the box's padding and border are within.
    return Widget(
        'di.designdemo',
        composer(fs, size[0] - 10, size[1] - 10),
        ease_in=ease.cubic.cubic_in_out,
        style=DivStyle(padding=4, radius=3, background='#000000e0', border=1, border_color='#ffffff20'),
        transition_duration=.4,
    )
