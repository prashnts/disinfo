import redis
import json

from redis_om import get_redis_connection

from .config import app_config


db = redis.Redis(host=app_config.redis_host, port=6379, db=0)
# redis_om models want decoded responses.
om_db = get_redis_connection(host=app_config.redis_host, port=6379)

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
