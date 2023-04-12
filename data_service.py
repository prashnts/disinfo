import os
import requests
import redis
import time
import json

latitude = 48.842
longitude = 2.391

pw_api_key = os.environ.get('PIRATE_WEATHER_TOKEN')
pw_unit = 'ca'  # SI units with kmph for wind.


if not pw_api_key:
    print('WARNING: No API Key for Pirate Weather')

forecast_url = f'https://api.pirateweather.net/forecast/{pw_api_key}/{latitude},{longitude}?units={pw_unit}'


db = redis.Redis(host='localhost', port=6379, db=0)

keys = {
    'weather_last_check': 'weather.last_check',
    'weather_data': 'weather.forecast_data',
    'random_msg_last_check': 'misc.random_msg.last_check',
    'random_msg': 'misc.random_msg',
}


def get_weather():
    # Every 15 minutes, fetch the weather.
    min_delay = 15 * 60

    last_update = db.get(keys['weather_last_check'])
    if not last_update:
        # first_run
        last_update = -min_delay
    else:
        last_update = int(last_update)

    if time.time() < (last_update + min_delay):
        print('No need to fetch weather')

    try:
        r = requests.get(forecast_url)
        data = r.json()
        # write out the forecast.
        db.set(keys['weather_data'], json.dumps(data))
        db.set(keys['weather_last_check'], str(int(time.time())))
    except requests.exceptions.RequestException as e:
        print('error', e)

def get_random_text():
    min_delay = 2 * 60
    last_update = db.get(keys['random_msg_last_check'])
    if not last_update:
        # first_run
        last_update = -min_delay
    else:
        last_update = int(last_update)

    if time.time() < (last_update + min_delay):
        print('not fetching random text')
        return
    try:
        r = requests.get('http://numbersapi.com/random/year')
        data = r.text
        db.set(keys['random_msg'], data)
        db.set(keys['random_msg_last_check'], str(int(time.time())))
    except requests.exceptions.RequestException as e:
        print('error', e)


while True:
    get_weather()
    get_random_text()
    time.sleep(0.1)
