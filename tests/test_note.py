import json
import time

from disinfo.screens import note


def test_text_lines():
    assert note._lines('lean in|to the screen') == (('lean in', 'to the screen'), None)


def test_steps_in_turn():
    v, ttl = note.steps([[20, 'sit'], [15, 'lean|in']], start=10, title='ToF|starts in')
    assert ttl == 10 + 35 + 60
    n = json.loads(v)
    at = lambda s: note._lines(json.dumps({**n, 't0': time.time() - s}))
    assert at(-10) == (('ToF', 'starts in'), '10s')
    assert at(5)[0] == ('sit',)
    assert at(25) == (('lean', 'in'), '10s')
    assert at(40) == (('done, thanks!',), None)
