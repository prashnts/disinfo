import typer
import pendulum

from ..redis import set_dict, db, publish
from .data_service import get_weather, get_random_text, get_metro_info
from disinfo.config import app_config

app = typer.Typer()
trigger_app = typer.Typer()
sync_app = typer.Typer()
app.add_typer(trigger_app, name='trigger')
app.add_typer(sync_app, name='sync')


@trigger_app.command(name='metro')
def trigger_metro():
    publish('di.pubsub.metro', action='toggle')

@trigger_app.command(name='twentytwo')
def trigger_twenty_two():
    ...

@sync_app.command(name='weather')
def sync_weather():
    get_weather()

@sync_app.command(name='numbers')
def sync_numbers():
    get_random_text()

@sync_app.command(name='metro')
def sync_metro():
    get_metro_info(force=True)


@trigger_app.command(name='motion')
def trigger_motion(state: str = 'off'):
    for entity in app_config.monitors.presence_sensors:
        payload = {
            'new_state': {
                'state': state,
            },
            '_timestamp': pendulum.now().isoformat(),
            'entity_id': entity,
        }
        publish('di.pubsub.presence', action='update', payload=payload)

@trigger_app.command(name='als')
def trigger_als(state: int = 100):
    for entity in app_config.monitors.ambient_light_sensors:
        payload = {
            'new_state': {
                'state': state,
            },
            '_timestamp': pendulum.now().isoformat(),
            'entity_id': entity,
        }
        publish('di.pubsub.lux', action='update', payload=payload)

if __name__=='__main__':
    app()
