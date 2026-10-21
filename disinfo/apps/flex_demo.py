'''Flex and grid demo: discore's layouts, live, in tabs. Toggled by show_flex_demo.

Each slide sits in a box whose width breathes, so the layout reflows on screen.
A tab (touched, or layout_demo_tab from the remote) picks flex or grid.
'''
import math

from PIL import Image, ImageDraw

from discore import ease
from discore.data_structures import FrameState
from discore.elements import Frame, Box
from discore.layers import div, DivStyle, rounded_rectangle
from discore.button import button, ButtonStyle
from discore.layouts import hstack, vstack, grid, composite_at, Spacer, Grow
from discore.progress import progress_bar, ProgressStyle
from discore.slides import Slides, SlidesStyle
from discore.text import text, TextStyle
from discore.widget import Widget
from disinfo import fonts
from disinfo.drat.app_states import RuntimeStateManager, TouchStateManager

title_style = TextStyle(font=fonts.bitocra7, color='#a6a6a6')
label_style = TextStyle(font=fonts.microfont_35_reg, color='#808080')
dim_style = TextStyle(font=fonts.microfont_35_reg, color='#5b5e64')
dark_style = TextStyle(font=fonts.microfont_35_reg, color='#000000')
body_style = TextStyle(font=fonts.microfont_35_reg, color='#a6a6a6', spacing=2)
palette = ['#42a459', '#2d83b4', '#b7925e', '#8a6cc8', '#c93f20']


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

def slide(title: str, w: int, body: Frame) -> Frame:
    head = hstack([text(title, title_style), Spacer(), text(f'w {w}', dim_style)], gap=4)
    return vstack([head, ruler(w), div(body, width=w, anchor='ml')], gap=3)


# Where Spacers put the blocks: the free space goes to them.
spacings = {
    'start': lambda a, b, c: [a, b, c],
    'end': lambda a, b, c: [Spacer(), a, b, c],
    'center': lambda a, b, c: [Spacer(), a, b, c, Spacer()],
    'between': lambda a, b, c: [a, Spacer(), b, Spacer(), c],
}

def spacer_slide(fs: FrameState, width: int) -> Frame:
    w = breathe(fs, width // 2, width)
    rows = [hstack([text(k, label_style), hstack(spaced(*[Swatch(c, 8, 6) for c in palette[:3]]), gap=2)], gap=4) for k, spaced in spacings.items()]
    return slide('spacer', w, vstack(rows, gap=3, align='hstretch'))

def grow_slide(fs: FrameState, width: int) -> Frame:
    w = breathe(fs, width // 2, width)
    return slide('grow', w, vstack([
        hstack([Swatch(palette[0], 6, 9, grow=1, label='1'), Swatch(palette[1], 6, 9, grow=2, label='2'), Swatch(palette[2], 6, 9, grow=1, label='1')], gap=2),
        hstack([Swatch(palette[3], 14, 9, label='fix'), Spacer(), Swatch(palette[4], 14, 9, label='fix')], gap=2),
        hstack([text('fit', label_style), text('this sentence gets cut to the room left', body_style, overflow='fit'), Swatch(palette[0], 9, 7)], gap=3),
    ], gap=4, align='hstretch'))

def text_slide(fs: FrameState, width: int) -> Frame:
    w = breathe(fs, width // 3, width)
    words = 'Constraints go down, sizes come up, and the text wraps into the room it is given.'
    return slide('wrap', w, vstack([
        div(text(words, body_style, overflow='wrap', max_lines=4), padding=2, radius=2, background='#ffffff10'),
        hstack([Swatch(palette[2], 7, 7), text('max_lines 1, then cut', body_style, overflow='wrap', max_lines=1)], gap=3),
    ], gap=4, align='hstretch'))

def shapes_slide(fs: FrameState, width: int) -> Frame:
    w = breathe(fs, width // 2, width)
    t = fs.tick
    values = [math.sin(t * 0.8 + i * 0.5) + 0.4 * math.sin(i * 1.7 + t * 2.1) for i in range(20)]
    value = 0.5 + 0.5 * math.sin(t * 0.6)
    return slide('shapes', w, vstack([
        # The column grows, its items stretch.
        hstack([Ring(value, palette[0]), Grow(vstack([
            Sparkline(values, palette[1]),
            hstack([Swatch(palette[3], 10, 7, label='pill'), Swatch(palette[2], 10, 7, label='box', grow=1)], gap=2),
        ], gap=3, align='hstretch'))], gap=4, align='center'),
        progress_bar(value, ProgressStyle(width=w, height=3, radius=1, color=palette[0])),
    ], gap=4, align='hstretch'))


# Grid: the same seven blocks, every few seconds another shape.
shapes = [dict(ncols=2), dict(ncols=3), dict(ncols=4), dict(nrows=2), dict()]

def grid_shape_slide(fs: FrameState, width: int) -> Frame:
    kw = shapes[int(fs.tick // 2.4) % len(shapes)]
    cells = [Swatch(palette[i % 5], 8 + 4 * (i % 3), 6, label=str(i + 1)) for i in range(7)]
    name = ' '.join(f'{k} {v}' for k, v in kw.items()) or 'square'
    return slide('grid', width, vstack([text(name, label_style), grid(cells, gap=2, anchor='ml', **kw)], gap=3))

def masonry_slide(fs: FrameState, width: int) -> Frame:
    # The same blocks: in rows, the tallest sets each row; masonry, under the shortest column.
    cells = [Swatch(palette[i % 5], 8, h) for i, h in enumerate([10, 4, 7, 4, 12, 6, 5, 8])]
    side = lambda name, masonry: vstack([text(name, label_style), grid(cells, ncols=3, gap=2, anchor='tm', masonry=masonry)], gap=3)
    return slide('masonry', width, hstack([side('rows', False), side('masonry', True)], gap=12, align='top'))

def share_slide(fs: FrameState, width: int) -> Frame:
    w = breathe(fs, width // 3, width)
    cells = [Swatch(palette[0], 6, 7, grow=1, label='grow'), Swatch(palette[1], 10, 7), Swatch(palette[2], 6, 7, grow=1),
             Swatch(palette[3], 10, 7), Swatch(palette[4], 46, 7, label='too wide, cut'), Swatch(palette[1], 6, 5)]
    return slide('width', w, vstack([
        text('cols share w', label_style),
        grid(cells, ncols=3, gap=2, width=w),
    ], gap=3))

anchors = ['tl', 'tm', 'tr', 'mr', 'br', 'bm', 'bl', 'ml', 'mm']

def anchor_slide(fs: FrameState, width: int) -> Frame:
    w = breathe(fs, width // 2, width)
    a = anchors[int(fs.tick // 1.2) % len(anchors)]
    cells = [Swatch(palette[i % 5], 6 + 2 * (i % 2), 4) for i in range(6)]
    # The cells: growers fill theirs.
    under = grid([Swatch('#ffffff14', 1, 1, grow=1)] * 6, ncols=3, gap=2, width=w, height=30)
    g = grid(cells, ncols=3, gap=2, width=w, height=30, anchor=a)
    return slide('anchor', w, vstack([text(f'anchor {a}', label_style), composite_at(g, under, 'tl')], gap=3))


tab_cell = dict(padding=(1, 4, 1, 4), radius=2, border=1)
tab_styles = {
    False: ButtonStyle(normal=DivStyle(background='#00000000', border_color='#ffffff20', **tab_cell),
                       pressed=DivStyle(background='#ffffff40', border_color='#ffffff90', **tab_cell)),
    True: ButtonStyle(normal=DivStyle(background='#ffffff20', border_color='#ffffff60', **tab_cell),
                      pressed=DivStyle(background='#ffffff40', border_color='#ffffff90', **tab_cell)),
}

def tabs(fs: FrameState, current: str) -> Frame:
    def tab(name):
        payload = {'tab': name}
        return button(text(name, title_style if name == current else dim_style), 'layout_demo_tab', payload,
                      pressed=TouchStateManager().is_pressed(fs, 'layout_demo_tab', payload), style=tab_styles[name == current])
    return hstack([tab('flex'), tab('grid')], gap=2)

def composer(fs: FrameState) -> Frame | None:
    state = RuntimeStateManager().get_state(fs)
    if not state.show_flex_demo:
        return None
    width = min(fs.config.width - 24, 160)
    style = SlidesStyle(width=width, height=min(fs.config.height - 42, 80))
    if state.layout_demo_tab == 'grid':
        slides = Slides('griddemo', style).mut([
            (lambda: grid_shape_slide(fs, width), 12),
            (lambda: masonry_slide(fs, width), 12),
            (lambda: share_slide(fs, width), 12),
            (lambda: anchor_slide(fs, width), 12),
        ])
    else:
        slides = Slides('flexdemo', style).mut([
            (lambda: spacer_slide(fs, width), 12),
            (lambda: grow_slide(fs, width), 12),
            (lambda: text_slide(fs, width), 12),
            (lambda: shapes_slide(fs, width), 12),
        ])
    return vstack([tabs(fs, state.layout_demo_tab), slides.draw(fs)], gap=4)

def flex_demo_app(fs: FrameState) -> Widget:
    return Widget(
        'di.flexdemo',
        composer(fs),
        ease_in=ease.cubic.cubic_in_out,
        style=DivStyle(padding=4, radius=3, background='#000000d8', border=1, border_color='#ffffff20'),
        transition_duration=.4,
    )
