'''Layout utilities for arranging Frames and Images.

Some of the functions are inspired with CSS FlexBoxes. Namely the
horizontal and vertical alignments when differently sized elements
are in the same container.
'''
import math

from PIL import Image, ImageChops, ImageFilter
from typing import Literal, Optional, Type, Union, Sequence
from itertools import product
from functools import lru_cache

from .elements import Frame, Box, UNBOUNDED, measure, render, shifted

# *stretch: items get the row's height (column's width).
VerticalAlignment = Literal['center', 'top', 'bottom', 'vstretch']
HorizontalAlignment = Literal['center', 'left', 'right', 'hstretch']
ComposeAnchor = Literal['tl', 'tm', 'tr', 'ml', 'mm', 'mr', 'bl', 'bm', 'br']


def _share(total: int, weights: Sequence[float]) -> list[int]:
    '''total split by weights in whole pixels, leftovers to the largest remainders.'''
    exact = [total * w / sum(weights) for w in weights]
    parts = [int(x) for x in exact]
    for i in sorted(range(len(parts)), key=lambda i: parts[i] - exact[i])[:total - sum(parts)]:
        parts[i] += 1
    return parts


class Flex(Box):
    '''A row or column: growers take the free space, shrinkers give up the overflow.
    hstack and vstack make one with a size, a stretch, or Boxes.
    '''

    def __init__(self, elements, axis: str, gap: int, align: str, stretch: bool, size: Optional[int]):
        self.elements = [e for e in elements if e]
        self.axis, self.gap, self.align, self.stretch, self.size_ = axis, gap, align, stretch, size
        # Gap before each item. Spacers stretch theirs.
        self.gaps, seen = [], False
        for e in self.elements:
            spacer = isinstance(e, Spacer)
            self.gaps.append(gap if seen and not spacer else 0)
            seen = seen or not spacer
        boxes = [e for e in self.elements if isinstance(e, Box)]
        self.grow = max([e.grow_along(axis) for e in boxes] + [0]) if size is None else 0
        self.shrink = max([e.shrink_along(axis) for e in boxes] + [0]) if size is None else 0
        cross = 'y' if axis == 'x' else 'x'
        self.cross_shrink = max([e.shrink_along(cross) for e in boxes] + [0])
        self.hash = ('Flex', axis, gap, align, size, tuple(e.hash for e in self.elements))
        self._memo = {}

    # (main, cross) <-> (w, h)
    def _split(self, w, h):
        return (w, h) if self.axis == 'x' else (h, w)
    _join = _split

    def grow_along(self, axis: str) -> float:
        return self.grow if axis == self.axis else 0

    def shrink_along(self, axis: str) -> float:
        return self.shrink if axis == self.axis else self.cross_shrink

    def _measure(self, e, main, cross):
        key = (id(e), main, cross)
        if key not in self._memo:
            self._memo[key] = self._split(*measure(e, *self._join(main, cross)))
        return self._memo[key]

    def _resolve(self, main: int, cross: int):
        '''Main and cross size of each item within main.'''
        gaps = sum(self.gaps)
        base = [self._measure(e, UNBOUNDED, cross)[0] for e in self.elements]
        alloc = list(base)
        free = main - sum(base) - gaps
        grows = [e.grow_along(self.axis) if isinstance(e, Box) else 0 for e in self.elements]
        shrinks = [(e.shrink_along(self.axis) if isinstance(e, Box) else 0) * b for e, b in zip(self.elements, base)]
        if free > 0 and sum(grows):
            alloc = [b + g for b, g in zip(base, _share(free, grows))]
        elif free < 0 and sum(shrinks):
            # Down to min-content, then the others give more.
            lo = [self._measure(e, 0, cross)[0] if s else b for e, b, s in zip(self.elements, base, shrinks)]
            while (over := sum(alloc) + gaps - main) > 0:
                room = [s if a > l else 0 for s, a, l in zip(shrinks, alloc, lo)]
                if not sum(room):
                    break
                alloc = [max(a - c, l) for a, c, l in zip(alloc, _share(over, room), lo)]
        crosses = [self._measure(e, a, cross)[1] for e, a in zip(self.elements, alloc)]
        return alloc, crosses

    def measure(self, max_w: int, max_h: int) -> tuple[int, int]:
        if not self.elements:
            return 1, 1
        max_main, max_cross = self._split(max_w, max_h)
        gaps = sum(self.gaps)
        content = sum(self._measure(e, UNBOUNDED, max_cross)[0] for e in self.elements) + gaps
        if self.size_ is not None:
            main = self.size_
        elif max_main < UNBOUNDED and self.grow:
            main = max_main
        else:
            main = min(content, max_main) if self.shrink else content
        alloc, crosses = self._resolve(main, max_cross)
        if self.size_ is None:
            main = max(main, sum(alloc) + gaps)     # what can't shrink overflows
        return self._join(main, max(crosses))

    def render(self, w: int, h: int) -> Frame:
        main, cross = self._split(w, h)
        alloc, crosses = self._resolve(main, cross)
        img = Image.new('RGBA', (max(w, 1), max(h, 1)), (0, 0, 0, 0))
        pos, targets = 0, ()
        for e, a, c, g in zip(self.elements, alloc, crosses, self.gaps):
            pos += g
            f = render(e, *self._join(a, cross if self.stretch else min(c, cross)))
            fm, fc = self._split(*f.size)
            off = max({'center': (cross - fc) // 2, 'bottom': cross - fc, 'right': cross - fc}.get(self.align, 0), 0)
            # Cut to its slot.
            cut = self._join(min(fm, a), min(fc, cross - off))
            if pos < main and min(cut) > 0:
                img.alpha_composite(f.image.crop((0, 0) + cut), self._join(pos, off))
                targets += shifted(f.targets, *self._join(pos, off))
            pos += a
        return Frame(img, hash=('flex', (w, h), self.hash), targets=targets)


class Spacer(Box):
    '''Takes the free space of a row or column.'''

    def __init__(self, grow: float = 1, size: int = 0):
        self.grow = grow
        self.size_ = size
        self.hash = ('Spacer', grow, size)

    def measure(self, max_w: int, max_h: int) -> tuple[int, int]:
        return min(self.size_, max_w), min(self.size_, max_h)

    def render(self, w: int, h: int) -> Frame:
        return Frame.fallback(('Spacer', w, h), (max(w, 1), max(h, 1)))


class Grow(Box):
    '''Makes any frame take a share of the free space. A fixed frame is placed in it by `anchor`.'''

    def __init__(self, frame: Frame, grow: float = 1, anchor: ComposeAnchor = 'mm'):
        self.frame = frame
        self.grow = grow
        self.anchor = anchor
        self.hash = ('Grow', grow, anchor, frame.hash)

    def shrink_along(self, axis: str) -> float:
        return self.frame.shrink_along(axis) if isinstance(self.frame, Box) else 0

    def measure(self, max_w: int, max_h: int) -> tuple[int, int]:
        return measure(self.frame, max_w, max_h)

    def render(self, w: int, h: int) -> Frame:
        f = render(self.frame, w, h)
        if f.size == (w, h):
            return f
        return composite_at(f, Frame.fallback(size=(max(w, 1), max(h, 1))), self.anchor).tag(('Grow', (w, h), self.hash))


def _needs_flex(elements, size, stretch) -> bool:
    return size is not None or stretch or any(isinstance(e, Box) for e in elements)


def hstack(
    elements: Sequence[Optional[Frame]],
    gap: int = 0,
    align: VerticalAlignment = 'center',
    width: Optional[int] = None,
) -> Frame:
    '''Stacks the given elements horizontally with specified gap.

    With a `width`, align='vstretch' or Boxes it's a Flex row.

    Alignment is relative to the tallest element:

        T─┬──┬┬─┬┬─┬┬──┬─        ┌─┐   ┌──┐        ┌─┐
          │  ││ ││ ││  │     ┌──┐│ │┌─┐│* │        │ │   ┌──┐
          └──┘│ │└─┘│  │   C─┼──┼┼─┼┼─┼┼──┼─   ┌──┐│ │┌─┐│  │
              │ │   └──┘     └──┘│ │└─┘└──┘    │  ││ ││ ││  │
              └─┘                └─┘         B─┴──┴┴─┴┴─┴┴──┴─

    Returns a new frame.
    '''
    if _needs_flex(elements, width, align == 'vstretch'):
        return Flex(elements, 'x', gap, align, align == 'vstretch', width)
    if not any(elements):
        return Frame(Image.new('RGBA', (1, 1)), hash=('hstack', gap, align, None))

    _elems = [e for e in elements if e]

    gap_width = gap * (len(_elems) - 1)
    width = sum([e.width for e in _elems]) + gap_width
    height = max([e.height for e in _elems])
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))

    x, targets = 0, ()
    for e in _elems:
        if align == 'top':
            y = 0
        elif align == 'center':
            y = (height - e.height) // 2
        elif align == 'bottom':
            y = height - e.height
        img.alpha_composite(e.image, (x, y))
        targets += shifted(e.targets, x, y)
        x += e.width
        x += gap

    return Frame(img, hash=('hstack', gap, align, tuple(elements)), targets=targets)

def vstack(
    elements: Sequence[Optional[Frame]],
    gap: int = 0,
    align: HorizontalAlignment = 'left',
    height: Optional[int] = None,
) -> Frame:
    '''Stacks the given elements vertically with specified gap.

    With a `height`, align='hstretch' or Boxes it's a Flex column.

    Alignment is relative to widest element:

        ├───┐        ┌─┼─┐        ┌───┤
        ├───┘        └─┼─┘        └───┤
        ├─────┐     ┌──┼──┐     ┌─────┤
        ├─────┘     └──┼──┘     └─────┤
        ├───┐        ┌─┼─┐        ┌───┤
        ├───┘        └─┼─┘        └───┤
        |left       cen|ter      right|

    Returns a new frame.
    '''
    if _needs_flex(elements, height, align == 'hstretch'):
        return Flex(elements, 'y', gap, align, align == 'hstretch', height)
    if not any(elements):
        return Frame(Image.new('RGBA', (1, 1)), hash=('vstack', gap, align, None))

    _elems = [e for e in elements if e]

    gap_width = gap * (len(_elems) - 1)
    width = max([e.width for e in _elems])
    height = sum([e.height for e in _elems]) + gap_width

    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))

    y, targets = 0, ()
    for e in _elems:
        if align == 'left':
            x = 0
        elif align == 'center':
            x = (width - e.width) // 2
        elif align == 'right':
            x = width - e.width
        img.alpha_composite(e.image, (x, y))
        targets += shifted(e.targets, x, y)
        y += e.height
        y += gap

    return Frame(img, hash=('vstack', gap, align, tuple(elements)), targets=targets)

def _clipped(targets: tuple, w: int, h: int) -> tuple:
    '''The targets cut to (0, 0, w, h); what's left outside goes.'''
    out = ()
    for t in targets:
        x0, y0, x1, y1 = max(t.x, 0), max(t.y, 0), min(t.x + t.w, w), min(t.y + t.h, h)
        if x1 > x0 and y1 > y0:
            out += (t._replace(x=x0, y=y0, w=x1 - x0, h=y1 - y0),)
    return out

def grid(
    elements: Sequence[Optional[Frame]],
    nrows: Optional[int] = None,
    ncols: Optional[int] = None,
    gap: int = 0,
    anchor: ComposeAnchor = 'mm',
    masonry: bool = False,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Frame:
    '''Places the elements in a grid of `nrows` and/or `ncols`.

    One given, the other follows from the count; both, and the overflow
    takes more rows; none, as square as it gets. An element sits in its
    cell by `anchor`; Boxes are measured in theirs, growers fill it.

    Row by row, each column is as wide as its widest element and each row
    as tall as its tallest. With `masonry` there are no rows: each element
    goes under the shortest column so far.

        ┌──┬────┬─┐          ┌──┬────┬─┐
        │▪▪│▪▪▪▪│▪│          │▪▪│▪▪▪▪│▪│
        ├──┼────┼─┤          │▪▪├────┤ │
        │▪ │ ▪▪ │ │          ├──┤ ▪▪ ├─┤
        │▪ │ ▪▪ │ │          │▪ │ ▪▪ │▪│
        └──┴────┴─┘          └──┴────┴─┘
          rows, 'mm'           masonry

    With a `width` the columns share it, with a `height` the rows do
    (masonry columns just stop there). What doesn't fit is clipped.

    Returns a new frame.
    '''
    _elems = [e for e in elements if e]
    hash_ = ('grid', nrows, ncols, gap, anchor, masonry, width, height, tuple(_elems))
    if not _elems:
        return Frame(Image.new('RGBA', (max(width or 1, 1), max(height or 1, 1))), hash=hash_)

    n = len(_elems)
    if ncols is None:
        ncols = math.ceil(n / nrows) if nrows else math.ceil(math.sqrt(n))
    ncols = max(min(ncols, n), 1)
    gaps_x = gap * (ncols - 1)
    shared = _share(max(width - gaps_x, 0), [1] * ncols) if width is not None else None

    # Cells: (element, x, y, w, h).
    cells = []
    if masonry:
        sizes = [measure(e, shared[0] if shared else UNBOUNDED, UNBOUNDED) for e in _elems]
        cols, tops = [[] for _ in range(ncols)], [0] * ncols
        for i, (_, h) in enumerate(sizes):
            c = tops.index(min(tops))
            cols[c].append((i, tops[c]))
            tops[c] += h + gap
        widths = shared or [max([sizes[i][0] for i, _ in col] + [0]) for col in cols]
        x = 0
        for col, w in zip(cols, widths):
            cells += [(_elems[i], x, y, w, sizes[i][1]) for i, y in col]
            x += w + gap
        full_h = max(tops) - gap
    else:
        rows = [list(range(i, min(i + ncols, n))) for i in range(0, n, ncols)]
        widths = shared or [max(measure(_elems[r[c]], UNBOUNDED, UNBOUNDED)[0] for r in rows if c < len(r)) for c in range(ncols)]
        heights = [max(measure(_elems[i], w, UNBOUNDED)[1] for i, w in zip(r, widths)) for r in rows]
        if height is not None:
            heights = _share(max(height - gap * (len(rows) - 1), 0), [1] * len(rows))
        y = 0
        for r, h in zip(rows, heights):
            x = 0
            for i, w in zip(r, widths):
                cells.append((_elems[i], x, y, w, h))
                x += w + gap
            y += h + gap
        full_h = y - gap

    W, H = width if width is not None else sum(widths) + gaps_x, height if height is not None else full_h
    img = Image.new('RGBA', (max(W, 1), max(H, 1)), (0, 0, 0, 0))
    targets = ()
    for e, x, y, w, h in cells:
        w, h = min(w, W - x), min(h, H - y)        # the canvas clips the cell
        if w <= 0 or h <= 0:
            continue
        mw, mh = measure(e, w, h)
        if isinstance(e, Box):      # growers fill their cell
            mw, mh = w if e.grow_along('x') else mw, h if e.grow_along('y') else mh
        f = render(e, mw, mh)
        dx = max({'l': 0, 'm': (w - f.width) // 2, 'r': w - f.width}[anchor[1]], 0)
        dy = max({'t': 0, 'm': (h - f.height) // 2, 'b': h - f.height}[anchor[0]], 0)
        # The cell clips the element.
        cw, ch = min(f.width, w - dx), min(f.height, h - dy)
        img.alpha_composite(f.image.crop((0, 0, cw, ch)), (x + dx, y + dy))
        targets += shifted(_clipped(f.targets, cw, ch), x + dx, y + dy)

    return Frame(img, hash=hash_, targets=targets)

def cut_alpha(left: Image.Image, right: Image.Image, threshold: int = 1, opaque: bool = False) -> Image.Image:
    '''Makes `left` transparent where `right` is (nearly) transparent, in place.
    Elsewhere left keeps its alpha, or becomes opaque.'''
    cut = right.getchannel('A').point([0] * (threshold + 1) + [255] * (255 - threshold))
    alpha = Image.new('L', left.size, 255) if opaque else left.getchannel('A')
    left.putalpha(ImageChops.multiply(alpha, cut))
    return left

def blur_region(img: Image.Image, box: tuple[int, int, int, int], radius: float) -> Image.Image:
    '''Same as img.filter(GaussianBlur(radius)).crop(box), but only blurs around the box.'''
    m = math.ceil(3 * radius) + 1
    pad = (max(box[0] - m, 0), max(box[1] - m, 0), min(box[2] + m, img.width), min(box[3] + m, img.height))
    blurred = img.crop(pad).filter(ImageFilter.GaussianBlur(radius))
    return blurred.crop((box[0] - pad[0], box[1] - pad[1], box[2] - pad[0], box[3] - pad[1]))

@lru_cache(maxsize=256)
def apply_blur(frame: Frame, radius: float) -> Frame:
    return Frame(frame.image.filter(ImageFilter.GaussianBlur(radius)), hash=('blur', radius, frame))


def composite_at(
    frame: Optional[Frame],
    dest: Union[Image.Image, Frame],
    anchor: ComposeAnchor = 'tl',
    dx: int = 0,
    dy: int = 0,
    frost: float = 0,
    behind: bool = False,
    vibrant: float = 0,
) -> Frame:
    '''Composes the `frame` so that it is at `anchor` corner of `dest`.

    Anchor positions with respect to `dest` are as follows:

        ┌──────────────────┐
        │tl      tm      tr│
        │                  │
        │ml      mm      mr│
        │                  │
        │bl      bm      br│
        └──────────────────┘

    It modifies the destination if it is an Image.
    Returns a Frame.
    '''
    if not frame:
        return dest

    targets = ()
    # What's under it, where and how: a frame moved, or over another picture, is another one. An image's pixels unknown: its size.
    under = dest.hash if isinstance(dest, Frame) else ('image', dest.size)
    key = ('composite_at', anchor, dx, dy, frost, behind, vibrant, frame, under)
    if isinstance(dest, Frame):
        targets = dest.targets
        dest = dest.image.copy()

    original = dest
    
    if behind:
        dest = Image.new('RGBA', dest.size, (0, 0, 0, 0))

    dw = dest.width
    dh = dest.height
    fw = frame.width
    fh = frame.height

    left = (dw - fw) // 2
    top = (dh - fh) // 2

    if anchor[0] == 't':
        top = 0
    elif anchor[0] == 'm':
        top = (dh - fh) // 2
    elif anchor[0] == 'b':
        top = dh - fh
    else:
        raise ValueError('Wrong value for anchor.')

    if anchor[1] == 'l':
        left = 0
    elif anchor[1] == 'm':
        left = (dw - fw) // 2
    elif anchor[1] == 'r':
        left = dw - fw
    else:
        raise ValueError('Wrong value for anchor.')

    blend = lambda left, right, threshold=1: cut_alpha(left, right, threshold, opaque=frost < 0)
    targets += shifted(frame.targets, left + dx, top + dy)

    if frost != 0:
        if behind:
            bg = apply_blur(composite_at(frame, dest.copy(), anchor, dx, dy), abs(frost)).image
            fg = composite_at(Frame(original), dest.copy()).image

            # if not vibrant:
            dest.alpha_composite(frame.opacity(1 if not vibrant else vibrant).image, (left + dx, top + dy))
            dest.alpha_composite(blend(bg, fg, 8), (0, 0))

            return Frame(composite_at(Frame(fg), dest, anchor).image, hash=key, targets=targets)
        
        region = blur_region(dest, (left + dx, top + dy, left + dx  + fw, top + dy + fh), abs(frost))
        dest.alpha_composite(blend(region, frame.image), (left + dx, top + dy))

    dest.alpha_composite(frame.image, (left + dx, top + dy))

    if behind:
        dest.alpha_composite(original, (0, 0))

    return Frame(dest, hash=key, targets=targets)

def mosaic(
    frame: Frame,
    nx: int = 2,
    ny: int = 2,
    seamless: bool = True,
) -> Frame:
    '''Tiles the frame in a grid.

    If `seamless` is enabled the frame is flipped in x and y axes to
    create a seamless tiling (illustrated below).

                    ┌───┬───┐         ┌───┬───┐
        ┌───┐       │ ◢ │ ◢ │         │ ◢ │ ◣ │
        │ ◢ │  ->   ├───┼───┤         ├───┼───┤
        └───┘       │ ◢ │ ◢ │         │ ◥ │ ◤ │
                    └───┴───┘         └───┴───┘

        Frame    Natural Tiling    Seamless Tiling


    Returns a new frame.
    '''
    w = frame.width * nx
    h = frame.height * ny
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))

    width_steps = [frame.width * i for i in range(nx)]
    height_steps = [frame.height * i for i in range(ny)]

    coords = product(width_steps, height_steps)

    if seamless:
        flip_x_states = [(i + 1) % 2 == 0 for i in range(nx)]
        flip_y_states = [(i + 1) % 2 == 0 for i in range(ny)]
        flip_states = product(flip_x_states, flip_y_states)
        i_lr = frame.image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        i_tb = frame.image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        i_tblr = i_tb.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

        for c, f in zip(coords, flip_states):
            if f[0] and f[1]:
                i = i_tblr
            elif f[0] and not f[1]:
                i = i_lr
            elif not f[0] and f[1]:
                i = i_tb
            else:
                i = frame.image
            img.alpha_composite(i, (c[0], c[1]))
    else:
        for cx, cy in coords:
            img.alpha_composite(frame.image, (cx, cy))

    return Frame(img, hash=('mosaic', nx, ny, seamless, frame))

def place_at(frame: Frame, dest: Union[Image.Image, Frame], x: int, y: int, anchor: ComposeAnchor='mm', frost: float = 0) -> Frame:
    '''Places the frame at the given coordinates.
    The anchor is relative to the frame and will be located at the given coordinates.

    Returns a new frame if dest is a Frame, else modifies the dest image.
    '''
    if not frame:
        return dest

    targets = ()
    under = dest.hash if isinstance(dest, Frame) else ('image', dest.size)
    if isinstance(dest, Frame):
        targets = dest.targets
        dest = dest.image.copy()

    fw = frame.width
    fh = frame.height

    # calculate the delta between the anchor and the top left corner of the frame.

    if anchor[0] == 't':
        dy = 0
    elif anchor[0] == 'm':
        dy = -fh // 2
    elif anchor[0] == 'b':
        dy = -fh
    else:
        raise ValueError('Wrong value for anchor.')

    if anchor[1] == 'l':
        dx = 0
    elif anchor[1] == 'm':
        dx = -fw // 2
    elif anchor[1] == 'r':
        dx = -fw
    else:
        raise ValueError('Wrong value for anchor.')

    if frost > 0:
        region = blur_region(dest, (x + dx, y + dy, x + dx + fw, y + dy + fh), frost)

        dest.alpha_composite(cut_alpha(region, frame.image, threshold=0), (x + dx, y + dy))

    dest.alpha_composite(frame.image, (x + dx, y + dy))
    return Frame(dest, hash=('place_at', anchor, x, y, frost, frame, under), targets=targets + shifted(frame.targets, x + dx, y + dy))

def tabular(table: list[list[Optional[Frame]]]):
    # convert a 2d list of frames into a tabular grid.
    # we need to find a way to put these irregular elements together.
    ...
