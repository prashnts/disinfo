import random

from PIL import Image

from discore import guard
from discore.color import Color, Palette, capped, resolve, using
from discore.elements import Ink
from discore.layers import div, shapes
from discore.layouts import hstack, place_at
from discore.scroller import HScroller
from discore.text import TextStyle, text
from disinfo import fonts


def test_color():
    c = Color('#a6a8ae')
    assert c == '#a6a8aeff' and round(c.L) == 69 and Color(c.rgba) == c
    assert abs(c.with_L(56).L - 56) < 1 and c.a(0.5).alpha == 128 / 255
    assert capped('#cbcdd9', 2).lum * 2 <= 0.51 and capped('#83868c', 1) == Color('#83868c')

def test_tokens():
    assert resolve('@fg') == Palette().fg and resolve('@ok/a3').rgba[3] == 0x50
    with using(Palette().of(fg='#ff0000')):
        t = text('x', TextStyle(color='@fg', font=fonts.bitocra7))
        assert t.style.color == '#ff0000ff'
    assert text('x', TextStyle(color='@fg', font=fonts.bitocra7)).style.color == Palette().fg
    assert div(text('x'), shapes.card).hash[1].background == Palette().card

def test_inks_travel():
    a, b = text('ab', fonts.roles.body), text('cd', fonts.roles.body)
    row = hstack([a, b], gap=3)
    assert [(i.x, i.w) for i in row.inks] == [(0, a.width), (a.width + 3, b.width)]
    assert not row.targets and all(isinstance(i, Ink) for i in row.marks)
    f = HScroller(size=8, name='t.inks').set_frame(row).draw(0)
    assert all(i.x + i.w <= 8 and i.mask.size == (i.w, i.h) for i in f.inks)

def test_fallback():
    assert [r for _, r in fonts.bitocra7.runs('10.8° ok')] == ['10.8', '°', ' ok']
    assert text('10.8°', fonts.roles.body).width > text('10.8', fonts.roles.body).width

def _over(ground: Image.Image, on: bool) -> Image.Image:
    guard.enabled = on
    im = ground.copy()
    place_at(text('Ligne 7', TextStyle(font=fonts.bitocra7, color='#a6a8ae')), im, 2, 2, 'tl')
    guard.enabled = True
    return im

def test_guard():
    black = Image.new('RGBA', (40, 12), (0, 0, 0, 255))
    assert _over(black, True).tobytes() == _over(black, False).tobytes()
    # A bright flat sky: the text goes dark.
    sky = Image.new('RGBA', (40, 12), (150, 200, 235, 255))
    lit = [p for p in _over(sky, True).get_flattened_data() if p != (150, 200, 235, 255)]
    assert lit and max(Color(p).L for p in lit) < 40
    # Busy: shadow-bold, dark px where there was no glyph.
    random.seed(1)
    noise = Image.new('RGBA', (40, 12))
    noise.putdata([(v, v, v, 255) for v in (random.randrange(60, 230) for _ in range(40 * 12))])
    on, off = _over(noise, True), _over(noise, False)
    dark = lambda im: sum(Color(p).L < 10 for p in im.get_flattened_data())
    assert dark(on) > dark(off)

def test_guard_follows_a_scroll():
    # A scroller keeps its hash while it moves: the guard mustn't hand back the last position.
    random.seed(2)
    noise = Image.new('RGBA', (30, 12))
    noise.putdata([(v, v, v, 255) for v in (random.randrange(60, 230) for _ in range(30 * 12))])
    s = HScroller(size=24, name='t.guard.scroll', speed=0.01, delta=1).set_frame(text('Ligne 7 trafic', fonts.roles.body))
    shots = []
    for t in (0, 1, 2):
        f = s.draw(t)
        im = noise.copy()
        place_at(f, im, 2, 2, 'tl')
        shots.append((f.hash, im.tobytes()))
    assert len({h for h, _ in shots}) == 1 and len({b for _, b in shots}) == 3
