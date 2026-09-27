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
