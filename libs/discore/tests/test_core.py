import time

import numpy as np

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

def test_attached_widgets_as_wide_under_it():
    fs = FrameState.create()
    small = Widget('att.small', solid((0, 0, 255, 255), (4, 4)))
    w = Widget('att', solid((255, 255, 255, 255), (20, 10)), attached=(small, Widget('att.none')))
    card = w.card(w.style)
    own = div(w.frame, w.style)
    assert card.width == own.width and card.height == own.height + 1 + div(small.frame, small.style).height
    assert Widget('att.alone', w.frame, attached=(Widget('att.none'),)).card(w.style).size == own.size

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

def test_ticker_rolls_up_by_the_old_line():
    # Slides with an edge: the new line pushes the old one out, whatever their heights.
    from discore.transitions import SlideIn
    line = lambda c, h: Frame(Image.new('RGBA', (4, h), c)).tag((c, h))
    with scope('test.ticker'):
        s = SlideIn('test.ticker', duration=1, edge='bottom')
        t = time.time()
        s.mut(line((255, 0, 0, 255), 6)); s.draw(FrameState(tick=t + 2, now=None))
        s.mut(line((0, 255, 0, 255), 3)); s.start_at = t + 2
        mid = s.draw(FrameState(tick=t + 2.5, now=None))
        assert mid.size == (4, 6) and mid.image.getpixel((0, 0))[0] == 255 and mid.image.getpixel((0, 3))[1] == 255
        end = s.draw(FrameState(tick=t + 3.1, now=None))
        assert end.size == (4, 3) and end.image.getpixel((0, 0))[1] == 255

def test_digits_come_in_from_the_way_the_value_went():
    from discore import ease
    from discore.transitions import Rank, SlideIn, text_slide_in
    with scope('test.rank'):
        r = Rank('r')
        assert [r.mut(v, 'top', 'bottom') for v in ('12:59', '13:00', '09:59', 'MON', '9.5', '-3')] == ['top', 'top', 'bottom', 'bottom', 'bottom', 'bottom']
        fs = lambda: FrameState(tick=time.time(), now=None)
        edge = lambda i: SlideIn(f'n.{i}', duration=0.25, easing=ease.linear.linear).edge
        text_slide_in(fs(), '19', name='n'); text_slide_in(fs(), '21', name='n')
        assert (edge(0), edge(1)) == ('top', 'top')
        text_slide_in(fs(), '20', name='n')
        assert (edge(0), edge(1)) == ('top', 'bottom')   # the 2 didn't change, it keeps its way


def test_placed_frames_differ_by_what_is_under_and_where():
    from discore.layouts import place_at, composite_at
    card, a, b = solid((255, 0, 0, 255)), solid((0, 0, 0, 255), (8, 8)), solid((0, 0, 255, 255), (8, 8))
    assert place_at(card, a, 4, 4) != place_at(card, b, 4, 4)
    assert place_at(card, a, 4, 4) != place_at(card, a, 5, 4)
    assert place_at(card, a, 4, 4) == place_at(card, a, 4, 4)
    assert composite_at(card, a, 'mm') != composite_at(card, b, 'mm') != composite_at(card, b, 'mm', frost=1)

def test_progress_bar_fills_whole_pixels():
    from discore.progress import progress_bar, ProgressStyle
    style = ProgressStyle(width=10, color='#ff0000', track='#00000000')
    bar = lambda v: progress_bar(v, style).image
    assert bar(0.42).size == (10, 2)
    assert [bar(0.42).getpixel((x, 0))[0] for x in (3, 4)] == [255, 0]
    assert bar(0.42) is bar(0.38) and bar(-1).getpixel((0, 0))[0] == 0 and bar(2).getpixel((9, 1))[0] == 255
    rounded = progress_bar(0.5, ProgressStyle(width=10, height=4, radius=2, color='#ff0000')).image
    assert rounded.size == (10, 4) and rounded.getpixel((5, 2))[0] == 255


from discore.elements import Box
from discore.layouts import hstack, vstack, composite_at, Spacer, Grow
from discore.layers import div
from discore.text import text, TextStyle
from discore import fonts
from pathlib import Path

fonts.default = fonts.TTFFont(Path(__file__).parents[3] / 'assets/fonts/bitocra7.bdf', 7)

opaque_at = lambda f, x, y: f.image.getpixel((x, y))[3] > 0
long_words = 'some long words that will not fit'

def test_plain_stacks_stay_frames():
    a, b = solid((255, 0, 0, 255), (4, 2)), solid((0, 255, 0, 255), (3, 5))
    row = hstack([a, None, b], gap=1)
    assert not isinstance(row, Box) and row.size == (8, 5)

def test_spacer_pushes_to_the_end():
    a, b = solid((255, 0, 0, 255), (4, 2)), solid((0, 255, 0, 255), (3, 2))
    row = hstack([a, Spacer(), b], width=20)
    f = row.render(*row.measure(100, 100))
    assert f.size == (20, 2) and opaque_at(f, 0, 0) and not opaque_at(f, 10, 0) and opaque_at(f, 19, 0)

def test_spacers_stretch_the_gap_not_add_one():
    a, b = solid((255, 0, 0, 255), (4, 2)), solid((0, 255, 0, 255), (4, 2))
    row = hstack([Spacer(), a, b, Spacer()], gap=2, width=20)
    f = row.render(20, 2)
    assert opaque_at(f, 5, 0) and not opaque_at(f, 4, 0) and opaque_at(f, 14, 0) and not opaque_at(f, 15, 0)   # 5 + 4 + 2 + 4 + 5
    tight = hstack([a, Spacer(), b], gap=3)
    assert tight.size == (11, 2)   # one gap, not two

def test_fit_text_shrinks_to_leave_room():
    icon = solid((255, 0, 0, 255), (6, 6))
    label = text(long_words, TextStyle(overflow='fit'))
    assert label.width > 40   # natural size where a Frame is expected
    row = hstack([label, icon], gap=2, width=40)
    f = row.render(*row.measure(100, 100))
    assert f.size[0] == 40 and opaque_at(f, 39, 3)   # the icon is whole, at the end

def test_wrap_in_a_div_width_and_through_a_div_without():
    style = TextStyle(overflow='wrap', max_lines=2)
    one_line = text('some', style).height
    boxed = div(text(long_words, style), width=30)
    assert boxed.width == 30 and boxed.height > one_line
    row = hstack([div(text(long_words, TextStyle(overflow='fit')), padding=1), solid((255, 0, 0, 255), (5, 5))], width=30)
    assert row.render(*row.measure(100, 100)).size[0] == 30

def test_box_works_as_a_frame():
    dest = solid((0, 0, 0, 0), (50, 20))
    f = composite_at(hstack([Spacer(size=3), solid((255, 0, 0, 255), (4, 4))]), dest, 'tl')
    assert f.size == (50, 20) and opaque_at(f, 3, 0) and not opaque_at(f, 1, 0)

def test_unbounded_stays_unbounded_through_padding():
    row = hstack([Spacer(), solid((255, 0, 0, 255), (4, 4)), Spacer()])
    assert div(row, padding=3).size == (10, 10)   # its content's size, not a fill of 'no limit'

def test_spaced_row_inside_a_row_takes_the_room_left():
    label, a, b = solid((0, 0, 255, 255), (5, 3)), solid((255, 0, 0, 255), (3, 3)), solid((0, 255, 0, 255), (3, 3))
    row = hstack([label, hstack([a, Spacer(), b])], gap=2, width=30)
    f = row.render(*row.measure(100, 100))
    assert f.size == (30, 3) and opaque_at(f, 7, 1) and not opaque_at(f, 15, 1) and opaque_at(f, 29, 1)

def test_rows_grow_along_themselves_only():
    head = hstack([solid((255, 0, 0, 255), (3, 3)), Spacer(), solid((0, 255, 0, 255), (3, 3))])
    col = vstack([head, solid((0, 0, 255, 255), (20, 4))], gap=1, height=30)
    f = col.render(*col.measure(20, 100))
    assert f.size == (20, 30) and opaque_at(f, 19, 1) and opaque_at(f, 0, 5)   # head spans the width, keeps its height

def test_column_of_text_shrinks_beside_a_fixed_item():
    col = vstack([text(long_words, TextStyle(overflow='fit')), text('short', TextStyle(overflow='fit'))])
    row = hstack([col, solid((255, 0, 0, 255), (6, 6))], gap=2, width=40, align='top')
    f = row.render(*row.measure(100, 100))
    assert f.size[0] == 40 and opaque_at(f, 39, 0)   # the column gave way, the fixed item is whole

def test_stretch_on_plain_frames():
    a, b = solid((255, 0, 0, 255), (3, 2)), solid((0, 255, 0, 255), (5, 4))
    assert vstack([a, b], align='hstretch').size == (5, 6)
    f = hstack([a, b], align='vstretch')
    assert f.size == (8, 4) and opaque_at(f, 0, 0) and not opaque_at(f, 0, 3)   # a fixed frame sits at the top

def test_grow_gives_out_every_pixel():
    row = hstack([Grow(solid((255, 0, 0, 255), (1, 2)), anchor='tl') for _ in range(3)], width=10)
    alloc, _ = row._resolve(10, 2)
    assert sorted(alloc) == [3, 3, 4]

def test_shrink_stops_at_min_content_the_others_give_more():
    # inner's share of the overflow would cut into its fixed square: it stops short of it, the long text gives the rest.
    inner = hstack([solid((0, 0, 255, 255), (20, 3)), text('ab', TextStyle(overflow='fit'))], gap=1)
    row = hstack([inner, text(long_words, TextStyle(overflow='fit'))], gap=2, width=40, align='top')
    alloc, _ = row._resolve(40, 7)
    assert sum(alloc) + 2 == 40 and alloc[0] >= 21
    assert opaque_at(row.render(40, 7), 19, 0)   # the square is whole

def test_wrap_keeps_the_lines_that_fit_the_height():
    style = TextStyle(overflow='wrap')
    one_line = text('some', style).height
    assert text(long_words, style).measure(30, one_line + 3)[1] == one_line   # a second line doesn't fit
    assert text(long_words, style).measure(30, 100)[1] > one_line

def test_stretched_div_fills_its_slot():
    tall = solid((255, 0, 0, 255), (4, 10))
    row = hstack([div(text('ab', TextStyle(overflow='fit')), padding=1, background='#00ff00'), tall], align='vstretch')
    f = row.render(*row.measure(100, 100))
    assert f.size[1] == 10 and opaque_at(f, 0, 9)   # its background reaches the bottom

def test_frame_hash_is_never_from_pixels_unless_asked():
    img = Image.new('RGBA', (4, 4), (255, 0, 0, 255))
    a, b = Frame(img), Frame(img)
    assert a == a and a != b    # a token: equal only to itself
    assert Frame.of_pixels(img) == Frame.of_pixels(img.copy())
    assert Frame.fallback(size=(3, 2)) == Frame.fallback(size=(3, 2)) != Frame.fallback(size=(2, 3))

def test_scroller_keeps_its_hash_while_the_content_does():
    from discore.scroller import HScroller
    from discore.text import Text
    s = HScroller(size=10, name='test.scroller')
    words = lambda: Text('some long words', TextStyle())   # rebuilt every frame (not text()'s cache), same content
    assert words() is not words()
    first = s.set_frame(words()).draw(0.0)
    assert s.set_frame(words()).draw(0.1).hash == first.hash
    assert s.set_frame(text('other words', TextStyle())).draw(0.2).hash != first.hash


from discore.elements import Target
from discore.button import button, ButtonStyle
from discore.layouts import place_at

def boxes(f):
    return [(t.x, t.y, t.w, t.h, t.action) for t in f.targets]

def test_button_is_touchable_all_over():
    b = button(solid((255, 0, 0, 255), (10, 4)), 'go', {'n': 1})
    assert boxes(b) == [(0, 0, b.width, b.height, 'go')] and b.targets[0].payload == {'n': 1}

def test_targets_follow_the_layouts():
    b = button(solid((255, 0, 0, 255), (4, 4)), 'b')          # 14 x 12: padding 3/5, the border inside
    w, h = b.size
    a = solid((0, 255, 0, 255), (6, 6))
    assert boxes(hstack([a, b], gap=2, align='top')) == [(8, 0, w, h, 'b')]
    assert boxes(vstack([a, b], gap=1)) == [(0, 7, w, h, 'b')]
    assert boxes(hstack([a, Spacer(), b], width=40, align='top')) == [(40 - w, 0, w, h, 'b')]       # Flex
    assert boxes(div(b, padding=2)) == [(2, 2, w, h, 'b')]
    assert boxes(composite_at(b, solid((0, 0, 0, 255), (50, 50)), 'br')) == [(50 - w, 50 - h, w, h, 'b')]
    assert boxes(place_at(b, solid((0, 0, 0, 255), (50, 50)), 10, 20, 'tl')) == [(10, 20, w, h, 'b')]
    assert boxes(b.trim(left=1, upper=2)) == [(-1, -2, w, h, 'b')]
    assert boxes(b.rescale(2)) == [(0, 0, 2 * w, 2 * h, 'b')]

def test_nothing_to_touch_while_it_moves():
    from discore.transitions import FadeIn
    b = button(solid((255, 0, 0, 255), (4, 4)), 'b')
    fade = FadeIn('test.fade.targets', duration=10)
    assert fade.mut(b).draw(FrameState(tick=time.time(), now=None)).targets == ()
    fade.pos = 1
    assert boxes(fade.draw(FrameState(tick=time.time() + 20, now=None))) == boxes(b)

def test_targets_scroll_with_the_scroller():
    from discore.scroller import HScroller
    row = hstack([solid((0, 0, 0, 255), (30, 4)), button(solid((255, 0, 0, 255), (4, 4)), 'b')], align='top')
    s = HScroller(size=20, name='test.scroll.targets', static_if_small=False).set_frame(row)
    s.pos = 20 + 25                                    # the frame is padded by size: 25 px into the row
    t = s.draw(0.0).targets
    assert [(x.x, x.action) for x in t] == [(30 - 25, 'b')]
    s.pos = 20 + 0
    assert s.draw(0.0).targets == ()                   # out of view

def test_scroller_survives_shorter_content():
    # A plane leaves the tile: the line gets shorter than where it had scrolled to.
    from discore.scroller import HScroller
    s = HScroller(size=10, name='test.scroller.shrink', static_if_small=False)
    s.set_frame(Frame(Image.new('RGBA', (300, 9))))
    s.pos = 252
    f = s.set_frame(Frame(Image.new('RGBA', (233, 9)))).draw(0.0)   # no step: the tick doesn't move it
    assert f.width == 10

def test_fade_restarts_from_what_it_shows():
    # A new frame mid-fade starts its own fade, from the picture on the screen: no jump.
    solid = lambda v: Frame(Image.new('RGBA', (2, 2), (v, v, v, 255))).tag(v)
    with scope('test.fade'):
        f = FadeIn('test.fade', duration=1)
        t = time.time()
        f.mut(solid(0)); f.draw(FrameState(tick=t + 2, now=None, config=None))      # all in
        f.mut(solid(200)); f.start_at = t + 2
        half = f.draw(FrameState(tick=t + 2.5, now=None, config=None)).image.getpixel((0, 0))[0]
        f.mut(solid(100)); f.start_at = t + 2.5
        after = f.draw(FrameState(tick=t + 2.5, now=None, config=None)).image.getpixel((0, 0))[0]
        assert abs(after - half) <= 2, (half, after)
        assert f.draw(FrameState(tick=t + 3.6, now=None, config=None)).image.getpixel((0, 0))[0] == 100

def test_stack_gives_its_widgets_about_equal_time():
    # Waits of 2, 10 and 5 s, and a press now and then: over ten minutes each is on top about as long.
    card = lambda name, wait: Widget(name, Frame(Image.new('RGBA', (4, 4))), wait_time=wait)
    with scope('test.fair'):
        s = Stack('test.fair', StackStyle(size=32)).mut([card('a', 2), card('b', 10), card('c', 5)])
        s._prev_widgets = s._widgets
        s._frames = {w: w.frame for w in s._widgets}
        total = {}
        for k in range(6000):
            step = k * 0.1
            s.scroller.on_target = True
            s.tick(FrameState(tick=step, now=None, config=None))
            if k % 370 == 0:
                s.next_widget()
            total[s._widgets[s.pos].name] = total.get(s._widgets[s.pos].name, 0) + 0.1
        assert max(total.values()) / min(total.values()) < 1.35, total

def test_a_new_widget_gets_a_turn_not_the_stack():
    card = lambda name: Widget(name, Frame(Image.new('RGBA', (4, 4))), wait_time=2)
    with scope('test.newcomer'):
        s = Stack('test.newcomer', StackStyle(size=32)).mut([card('a'), card('b')])
        s._prev_widgets = s._widgets
        s._frames = {w: w.frame for w in s._widgets}
        for k in range(3000):
            s.scroller.on_target = True
            s.tick(FrameState(tick=k * 0.1, now=None, config=None))
        s.mut([card('a'), card('b'), card('c')])
        s._frames = {w: w.frame for w in s._widgets}
        on = {}
        for k in range(3000, 3600):
            s.scroller.on_target = True
            s.tick(FrameState(tick=k * 0.1, now=None, config=None))
            s._prev_widgets = s._widgets
            on[s._widgets[s.pos].name] = on.get(s._widgets[s.pos].name, 0) + 0.1
        assert on.get('c', 0) < 30, on

def test_stack_moves_on_by_itself():
    # Nothing pressed: after its wait, the next card.
    card = lambda name: Widget(name, Frame(Image.new('RGBA', (4, 4))), wait_time=2)
    with scope('test.moves'):
        s = Stack('test.moves', StackStyle(size=32)).mut([card('a'), card('b'), card('c')])
        s._prev_widgets = s._widgets
        s._frames = {w: w.frame for w in s._widgets}
        seen = set()
        for k in range(200):
            s.scroller.on_target = True
            s.tick(FrameState(tick=k * 0.1, now=None, config=None))
            seen.add(s._widgets[s.pos].name)
        assert seen == {'a', 'b', 'c'}, seen


from discore.layouts import grid

red = lambda w, h: solid((255, 0, 0, 255), (w, h))

def test_grid_shape_from_rows_cols_both_or_none():
    cells = [red(4, 4)] * 5
    size = lambda **kw: grid(cells, gap=1, **kw).size
    assert size(ncols=2) == (9, 14)          # 3 rows
    assert size(nrows=2) == (14, 9)          # 3 columns
    assert size(nrows=1, ncols=2) == (9, 14) # the overflow takes rows
    assert size() == (14, 9)                 # as square as it gets
    assert size(ncols=9) == (24, 4)          # no empty columns
    assert grid([None, None]).size == (1, 1)

def test_grid_lines_up_columns_and_rows():
    f = grid([red(2, 2), red(6, 2), red(2, 5), red(2, 2)], ncols=2, anchor='tl')
    assert f.size == (8, 7)                  # widest per column, tallest per row
    assert opaque_at(f, 2, 0) and not opaque_at(f, 4, 2) and opaque_at(f, 2, 2)

def test_masonry_fills_the_shortest_column():
    f = grid([red(4, 10), red(4, 2), red(4, 2), red(4, 2)], ncols=2, gap=1, masonry=True, anchor='tl')
    assert f.size == (9, 10)                 # rows would take 10 + 1 + 2
    assert opaque_at(f, 5, 7) and not opaque_at(f, 5, 9)   # three under each other on the right

def test_grid_width_shares_and_clips_with_the_targets():
    b = button(red(20, 4), 'b')
    f = grid([b, b], ncols=2, gap=2, width=20, anchor='tl')
    assert f.width == 20 and boxes(f) == [(0, 0, 9, b.height, 'b'), (11, 0, 9, b.height, 'b')]
    assert grid([red(4, 4)] * 4, ncols=2, height=5).height == 5

def test_grid_renders_boxes_in_their_cells():
    f = grid([Grow(red(2, 2), anchor='tl'), red(10, 2)], ncols=1, anchor='tr')
    assert opaque_at(f, 0, 0) and not opaque_at(f, 9, 0)   # the Grow fills its cell, the frame in it at its anchor

def test_hold_button_fills_in_its_shape():
    style = ButtonStyle(fill='#00ff00ff')
    b = lambda p: button(red(20, 6), 'b', hold=5, progress=p, style=style)
    assert b(0).targets[0].hold == 5 and button(red(4, 4), 'b').targets[0].hold == 0
    half = b(0.5).image
    assert half.getpixel((3, 6)) != b(0).image.getpixel((3, 6))     # filled on the left
    assert half.getpixel((b(0).width - 4, 6)) == b(0).image.getpixel((b(0).width - 4, 6))   # not yet on the right
    assert half.getpixel((0, 0))[3] < 64 and half.getpixel((3, 6))[1] == 255   # the corner stays round, the fill shows


from types import SimpleNamespace
from discore import screen as scr
from discore.screen import Screen, Spot, Option, Focus

def sides(**kw):
    # A card on the left (designated) or the right, the time top right or, when calm, bottom right.
    return Screen('t', [
        [Option({'card': Spot('ml')}), Option({'card': Spot('mr')}, penalty=0.5)],
        [Option({'time': Spot('tr')}), Option({'time': Spot('br')}, penalty=0.3, when='calm')],
    ], **kw)

screen_fs = SimpleNamespace(config=SimpleNamespace(width=64, height=48))
card, clock = red(20, 30), red(16, 8)

def test_screen_keeps_the_designated_places():
    s = sides()
    l = s.arrange(screen_fs, {'card': card, 'time': clock})
    assert l.positions == {'card': (0, 9), 'time': (48, 0)}
    assert l.clear[0] >= 20 and l.clear[2] == 64     # the box right of the card

def test_screen_moves_off_the_focus_and_slides():
    s = sides()
    s.arrange(screen_fs, {'card': card, 'time': clock})
    under_card = Focus((64, 48)).disk(8, 24, 6)
    l = s.arrange(screen_fs, {'card': card, 'time': clock}, under_card, relayout=True)
    assert s.spot('card').anchor == 'mr' and l.positions['card'][0] < 44     # on its way right
    s.moves = {}
    assert s.arrange(screen_fs, {'card': card, 'time': clock}, under_card).positions['card'] == (44, 9)

def test_screen_fades_far_moves():
    s = sides(fading={'card'})
    s.arrange(screen_fs, {'card': card, 'time': clock})
    l = s.arrange(screen_fs, {'card': card, 'time': clock}, Focus((64, 48)).disk(8, 24, 6), relayout=True)
    assert l.positions['card'] == (44, 9) and l.fades['card'] == ((0, 9), 0)     # there already, fading from the left

def test_screen_options_only_when():
    s = sides()
    s.current = (0, 1)          # the time was down while calm
    s.arrange(screen_fs, {'card': card, 'time': clock}, Focus((64, 48)).disk(56, 4, 4))
    assert s.spot('time').anchor == 'tr'     # not calm: forced back up, focus or not
    s.arrange(screen_fs, {'card': card, 'time': clock}, Focus((64, 48)).disk(56, 4, 4), when={'calm'}, relayout=True)
    assert s.spot('time').anchor == 'br'

def test_screen_burn_in_takes_turns():
    s = sides()
    s.arrange(screen_fs, {'card': card, 'time': clock})
    s.heat[:, :5] = 20 * 3600   # the designated side lit for long
    s.arrange(screen_fs, {'card': card, 'time': clock}, relayout=True)
    assert s.spot('card').anchor == 'mr'

def test_screen_heat_is_kept():
    saved = []
    s = sides(load_heat=lambda: np.full((12, 16), 7, np.float32), save_heat=saved.append, save_every_s=0)
    s.arrange(screen_fs, {'card': card, 'time': clock})
    s.scored_at -= 2
    s.arrange(screen_fs, {'card': card, 'time': clock}, relayout=True)
    assert s.heat[0, 0] > 6.9 and saved     # loaded, fading a little

def test_screen_counts_only_the_covering_items():
    s = sides(covering={'card'})
    under_time = Focus((64, 48)).disk(56, 4, 4)
    s.arrange(screen_fs, {'card': card, 'time': clock}, under_time, when={'calm'}, relayout=True)
    assert s.spot('time').anchor == 'tr'     # the time over it is fine

def test_screen_sees_frosted_items_overlap():
    faint = lambda w, h: solid((0, 0, 0, 90), (w, h))
    s = Screen('t', [[Option({'a': Spot('tl')})], [Option({'b': Spot('tl')}), Option({'b': Spot('tr')}, penalty=0.3)]])
    s.arrange(screen_fs, {'a': faint(20, 20), 'b': faint(20, 20)}, relayout=True)
    assert s.spot('b').anchor == 'tr'

def test_screen_waits_before_moving_in_between(monkeypatch):
    now = [time.monotonic()]
    monkeypatch.setattr(scr.time, 'monotonic', lambda: now[0])
    s, under_card = sides(), Focus((64, 48)).disk(8, 24, 6)
    for _ in range(scr.anytime_s):
        s.arrange(screen_fs, {'card': card, 'time': clock}, under_card)
        now[0] += 1
    assert s.spot('card').anchor == 'ml'     # a card passing by
    s.arrange(screen_fs, {'card': card, 'time': clock}, under_card)
    assert s.spot('card').anchor == 'mr'     # it stays

def test_screen_following_focus_only_on_relayout(monkeypatch):
    now = [time.monotonic()]
    monkeypatch.setattr(scr.time, 'monotonic', lambda: now[0])
    s, radar = sides(), Focus((64, 48), follows=True).disk(8, 24, 6)
    for _ in range(scr.anytime_s + 5):
        s.arrange(screen_fs, {'card': card, 'time': clock}, radar)
        now[0] += 1
    assert s.spot('card').anchor == 'ml'     # drawn for this arrangement: says nothing of the others
    s.arrange(screen_fs, {'card': card, 'time': clock}, radar, relayout=True)
    assert s.spot('card').anchor == 'mr'
