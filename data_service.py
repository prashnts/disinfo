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
    'last_check': 'weather.last_check',
    'data': 'weather.forecast_data',
}

def get_weather():
    try:
        r = requests.get(forecast_url)
        data = r.json()
    except requests.exceptions.RequestException as e:
        print('error', e)

    # write out the forecast.
    db.set(keys['data'], json.dumps(data))
    db.set(keys['last_check'], str(int(time.time())))

# Every 15 minutes, fetch the weather.
min_delay = 15 * 60

while True:
    last_update = db.get(keys['last_check'])

    if not last_update:
        # first_run
        last_update = -min_delay
    else:
        last_update = int(last_update)

    if time.time() > last_update + min_delay:
        print('Fetching new weather data')
        get_weather()
        print(f'Sleeping for {min_delay=}s')
        time.sleep(min_delay)
    else:
        # sleep premptively
        print('No need to get weather right now, sleeping')
        time.sleep(time.time() + min_delay - last_update)
