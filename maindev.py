import os
import json
import uvicorn

from multiprocessing import Process

from disinfo.renderers.background import main as background_renderer
from disinfo.drat.app_states import PubSubManager, PubSubMessage
from disinfo.drat.data_service import main as data_service_main
from disinfo.drat.ha_service import main as ha_service_main
from disinfo.redis import publish

acts = []

def passthru_acts(channel_name, message: PubSubMessage):
    global acts
    acts.append(message.payload['cmd'])

PubSubManager().attach('maindev', ('di.pubsub.acts',), passthru_acts)

def run_sensors():
    os.environ['BLINKA_MCP2221'] = '1'
    from websocket_rpi_matrix.di_remote import setup as setup_sensors, sensor_loop, Config

    def callback(payload):
        global acts
        # print(f"[maindev] Sensor payload: {payload}")
        publish('di.pubsub.telemetry', action='update', payload={'data': json.dumps(payload)})
        if len(acts):
            local_acts = acts.copy()
            acts = []
            return local_acts

    print("[maindev] Setting up sensors")
    conf = Config(buzzer_address='0x3D', apds_proximity_enable=True)
    sensors = setup_sensors(conf)
    print("[maindev] Starting sensor thread")
    sensor_loop(sensors, callback)


def run_server():
    uvicorn.run("disinfo.web.server:app", host="0.0.0.0", port=4200)


if __name__ == "__main__":
    procs = {
        'webserver': run_server,
        'renderer': background_renderer,
        # 'data_loop': data_service_main,
        'ha_loop': ha_service_main, 
        'sensor_loop': run_sensors,
    }
    processes = []
    try:
        for name, proc in procs.items():
            p = Process(target=proc)
            p.start()
            processes.append(p)
            print(f"[maindev] Started process {name} with PID {p.pid}")
    finally:
        for p in processes:
            p.join()