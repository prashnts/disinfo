import redis
import json


db = redis.Redis(host='localhost', port=6379, db=0)

def get_dict(key: str, default: dict = {}) -> dict:
    value = db.get(key)
    try:
        return json.loads(value)
    except TypeError:
        return default

def set_dict(key: str, payload: dict):
    data = json.dumps(payload)
    db.set(key, data)

def set_json(key: str, payload: dict):
    db.set(key, payload)

def publish(channel: str, action: str, payload: dict = {}):
    db.publish(channel, json.dumps({'_action': action, **payload}))
