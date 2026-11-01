import time
import uuid

import pytest

from disinfo import xbus
from disinfo.redis import db


def until(f, timeout: float = 2):
    t = time.monotonic()
    while not (v := f()) and time.monotonic() - t < timeout:
        time.sleep(0.02)
    return v

@pytest.fixture
def shared():
    # Owner and reader in one process: the bus delivers to itself too.
    name = f't{uuid.uuid4().hex[:8]}'
    data, calls = {'a.1': 'one', 'a.2': 'two', 'b.1': 'bee'}, []
    s = xbus.Shared(name, read=data.get, keys=lambda: list(data), on_call=calls.append)
    yield name, s, data, calls
    db.delete(f'x.{name}', f'x.{name}.wanted')

def test_a_key_comes_when_asked_and_follows(shared):
    name, s, data, _ = shared
    v = xbus.View(name, str.upper)
    assert v.get('a.1') is None                     # not wanted before: the owner sends it now
    assert until(lambda: v.get('a.1')) == 'ONE'
    data['a.1'] = 'uno'
    s.changed(['a.1', 'b.1'])
    assert until(lambda: v.get('a.1') == 'UNO')
    assert 'b.1' not in v.values                    # nobody asked for it: not mirrored
    assert not db.hexists(f'x.{name}', 'b.1')

def test_a_new_view_reads_the_hash(shared):
    name, s, _, _ = shared
    first = xbus.View(name, str)
    first.get('a.2')
    until(lambda: db.hexists(f'x.{name}', 'a.2'))
    assert xbus.View(name, str).get('a.2') == 'two'

def test_prefixes_and_gone(shared):
    name, s, data, _ = shared
    v = xbus.View(name, str)
    v.prefix('a.')
    assert until(lambda: v.prefix('a.')) and until(lambda: len(v.prefix('a.')) == 2)
    data['a.3'] = 'three'
    del data['a.1']
    s.changed(['a.1', 'a.3'])
    assert until(lambda: v.prefix('a.') == {'a.2': 'two', 'a.3': 'three'})

def test_wanted_kept_for_an_owner_starting_later(shared):
    name, _, data, _ = shared
    xbus.View(name, str).get('b.1')
    assert until(lambda: db.sismember(f'x.{name}.wanted', 'b.1'))
    assert xbus.Shared(name, read=data.get, keys=lambda: list(data)).wanted('b.1')

def test_calls_reach_the_owner(shared):
    name, _, _, calls = shared
    assert xbus.View(name, str).call(service='light.toggle', target={'entity_id': 'light.x'})
    assert until(lambda: calls) == [{'service': 'light.toggle', 'target': {'entity_id': 'light.x'}}]
    assert not xbus.View(f'{name}-nobody', str).call(x=1)
