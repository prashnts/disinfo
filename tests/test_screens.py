import os

os.environ.setdefault('DI_CONFIG_PATH', '.config.sample.json')

from disinfo import compositor


def test_the_designated_layout_comes_first():
    for name, side in [('disalon', 'l'), ('distudy', 'r'), ('di_pcstate', 'l')]:
        s = compositor.SCREENS[name]
        first = s.choices[0][0]
        assert first.penalty == 0 and first.spots['side'].anchor[1] == side and first.spots['time'].anchor == 't' + 'lr'['lr'.index(side) - 1]

def test_time_kept_on_a_side():
    s = compositor.big_screen('test.pinned', 'left', time_side='right')
    assert {o.spots['time'].anchor[1] for o in s.choices[0]} == {'r'}
    assert {o.spots['side'].anchor for o in s.choices[0]} == {'ml', 'mr'}      # the stack still moves
