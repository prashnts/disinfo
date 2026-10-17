import time

from PIL import Image

from discore.elements import Frame
from discore.data_structures import FrameState, scope
from discore.layers import div, DivStyle
from discore.stack import Stack, StackStyle
from discore.transitions import FadeIn
from discore.widget import Widget
from discore.spriteim import SpriteIcon


def solid(color, size=(4, 4)):
    return Frame(Image.new('RGBA', size, color))

def test_resize_returns_a_new_frame():
    red, green = solid((255, 0, 0, 255)), solid((0, 255, 0, 255))
    r = red.resize((8, 8))
    assert red.size == (4, 4) and r.size == (8, 8)
    assert r != green.resize((8, 8))

def test_div_keeps_background_frame():
    bg = solid((0, 0, 255, 255))
    div(solid((0, 0, 0, 0)), DivStyle(background_frame=bg, width=20, height=10))
    assert bg.size == (4, 4)

def test_instances_are_per_scope():
    with scope('a'):
        a = FadeIn('x')
    with scope('b'):
        b = FadeIn('x')
    with scope('a'):
        assert FadeIn('x') is a
    assert a is not b

def test_stack_survives_shrinking_list():
    fs = FrameState.create()
    w = lambda name: Widget(name, solid((255, 255, 255, 255), (10, 10)))
    stack = Stack('t', StackStyle(size=32)).mut([w('a'), w('b'), w('c')])
    stack.draw(fs)
    stack.pos = 2
    assert stack.mut([w('a')]).draw(fs)
    assert Stack('t.empty', StackStyle(size=32)).mut([]).draw(fs) is None

def test_animated_widget_keeps_animating(tmp_path):
    sprite = Image.new('RGBA', (4, 16))
    for i in range(4):
        sprite.paste((60 * i, 0, 0, 255), (0, 4 * i, 4, 4 * i + 4))
    sprite.save(tmp_path / 'sprite.png')
    icon = SpriteIcon(str(tmp_path / 'sprite.png'), step_time=0.01)
    seen = set()
    for _ in range(10):
        time.sleep(0.02)
        fs = FrameState.create()
        seen.add(Widget('anim', icon.draw(fs.tick)).draw(fs).image.tobytes())
    assert len(seen) > 1

def test_slides_follow_their_durations():
    from discore.slides import Slides, SlidesStyle
    drawn = []
    slide = lambda color, seconds: (lambda: drawn.append(color) or solid(color), seconds)
    s = Slides('t', SlidesStyle(width=10, height=6)).mut([slide((255, 0, 0, 255), 3), None, slide((0, 255, 0, 255), 1)])
    assert s.duration == 4
    assert [s.index(t) for t in (0, 2.9, 3, 3.9, 4)] == [0, 0, 1, 1, 0]
    f = s.draw(FrameState(tick=3.5, now=None))
    assert f.size == (10, 6) and drawn == [(0, 255, 0, 255)]   # only the slide on screen is drawn

def test_progress_bar_fills_whole_pixels():
    from discore.progress import progress_bar, ProgressStyle
    style = ProgressStyle(width=10, color='#ff0000', track='#00000000')
    bar = lambda v: progress_bar(v, style).image
    assert bar(0.42).size == (10, 2)
    assert [bar(0.42).getpixel((x, 0))[0] for x in (3, 4)] == [255, 0]
    assert bar(0.42) is bar(0.38) and bar(-1).getpixel((0, 0))[0] == 0 and bar(2).getpixel((9, 1))[0] == 255
    rounded = progress_bar(0.5, ProgressStyle(width=10, height=4, radius=2, color='#ff0000')).image
    assert rounded.size == (10, 4) and rounded.getpixel((5, 2))[0] == 255
