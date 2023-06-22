import typer
import pendulum

from ..redis import set_dict
from .app_states import MetroInfoStateManager

app = typer.Typer()
trigger_app = typer.Typer()
#  = typer.Typer()
app.add_typer(trigger_app, name='trigger')

@trigger_app.command(name='metro')
def trigger_metro():
    mgr = MetroInfoStateManager()
    mgr.manual_trigger()

@trigger_app.command(name='twentytwo')
def trigger_twenty_two():
    ...

if __name__=='__main__':
    app()
