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

def test_date_in_the_time_row_only_when_covered():
    from types import SimpleNamespace
    from PIL import Image
    from discore.elements import Frame
    fs = SimpleNamespace(config=SimpleNamespace(width=128, height=128))
    box = lambda w, h: Frame(Image.new('RGBA', (w, h), (255, 255, 255, 255)))
    def items(card):
        return {'time': box(40, 30), 'date': box(40, 30), 'timedate': box(80, 30), 'side': card, 'bottom': None}
    free = compositor.big_screen('distudy', 'right')
    free.arrange(fs, items(box(50, 50)), relayout=True)
    assert 'date' in free.spots() and 'timedate' not in free.spots()
    # A card over where the date goes, below the time at the top corner: it moves into the time's row.
    covered = compositor.big_screen('distudy', 'right', time_side='left')
    covered.arrange(fs, items(box(128, 100)), relayout=True)
    layout = covered.arrange(fs, items(box(128, 100)), relayout=True)
    assert 'timedate' in covered.spots() and 'timedate' in layout.positions and 'date' not in layout.positions

def test_design_demo_pages_draw_in_their_room():
    import time
    import pendulum
    from discore.data_structures import FrameState
    from disinfo.config import app_config
    from disinfo.drat.app_states import RuntimeStateManager, PubSubMessage
    from disinfo.apps import design_demo as dd
    fs = FrameState(tick=time.time(), now=pendulum.now(), config=app_config)
    m = RuntimeStateManager()
    m.state.show_design_demo, m.state.stream_url = True, None
    m.state.design_demo = {}
    for tab, pages in dd.tabs.items():
        for i, (name, page) in enumerate(pages):
            if name == 'stream':
                continue        # starts a reader
            m.process_message('di.pubsub.remote', PubSubMessage(action='design_demo', payload={'tab': tab, 'page': i}))
            f = dd.composer(fs, 118, 94)
            assert f.size == (118, 94), (tab, name)
    m.process_message('di.pubsub.remote', PubSubMessage(action='design_demo', payload={'taps': 3}))
    assert m.state.design_demo['tab'] == 'touch' and m.state.design_demo['taps'] == 3     # merged
