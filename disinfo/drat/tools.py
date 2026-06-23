import typer

from ..redis import publish
from .data_service import get_metro_info

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

@sync_app.command(name='metro')
def sync_metro():
    get_metro_info(force=True)


@trigger_app.command(name='motion')
def trigger_motion(state: str = 'off'):
    publish('di.pubsub.remote', action='motion_toggle')


if __name__=='__main__':
    app()
