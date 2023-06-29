import typer
import pendulum

from ..redis import set_dict, db
# from .app_states import MetroInfoStateManager
from .data_service import get_weather, get_random_text, get_metro_info

app = typer.Typer()
trigger_app = typer.Typer()
sync_app = typer.Typer()
app.add_typer(trigger_app, name='trigger')
app.add_typer(sync_app, name='sync')


@trigger_app.command(name='metro')
def trigger_metro():
    # mgr = MetroInfoStateManager()
    # mgr.manual_trigger()
    get_metro_info(force=True)
    db.publish('di.pubsub.metro', 'toggle'.encode())

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


if __name__=='__main__':
    app()
