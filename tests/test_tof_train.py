import os
os.environ.setdefault('DI_CONFIG_PATH', '.config.sample.json')
import json

from fastapi.testclient import TestClient

from disinfo.web import server
from disinfo.screens import note


class DB:
    def __init__(self):
        self.lists = {}

    def rpush(self, k, v):
        self.lists.setdefault(k, []).append(v)

    def lrange(self, k, a, b):
        return self.lists.get(k, [])[a:][: None if b == -1 else b + 1]


def test_train_session(monkeypatch):
    db, sent, notes = DB(), [], {}
    monkeypatch.setattr(server, 'db', db)
    monkeypatch.setattr(server, 'publish', lambda ch, action, payload: sent.append((ch, payload)))
    monkeypatch.setattr(note, 'put', lambda screen, value, ttl=0: notes.update({screen: (value, ttl)}))
    client = TestClient(server.app)
    s = client.post('/tof/train', json={'steps': [[20, 'sit'], [15, 'lean in']], 'start': 5}).json()
    assert s['screen'] == 'distudy' and s['steps'] == [[20, 'sit'], [15, 'lean in']]
    assert json.loads(notes['distudy'][0])['t0'] == s['t0']                 # the note's steps start when the session does
    (ch, p), = sent
    assert ch == 'di.pubsub.acts' and p['dest'] == 'distudy' and p['cmd'][:2] == ['tof', 'record:50']
    assert client.get('/tof/train').json() == [s]
