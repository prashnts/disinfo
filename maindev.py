import os
import json
import uvicorn

from multiprocessing import Process

from disinfo.renderers.background import main as background_renderer
from disinfo.drat.data_service import main as data_service_main
from disinfo.drat.ha_service import main as ha_service_main
from disinfo.redis import publish



def run_sensors():
    os.environ['BLINKA_MCP2221'] = '1'
    from websocket_rpi_matrix.di_remote import setup as setup_sensors, sensor_loop

    def callback(payload):
        # print(f"[maindev] Sensor payload: {payload}")
        publish('di.pubsub.telemetry', action='update', payload={'data': json.dumps(payload)})

    print("[maindev] Setting up sensors")
    sensors = setup_sensors()
    print("[maindev] Starting sensor thread")
    sensor_loop(sensors, callback)


def run_server():
    uvicorn.run("disinfo.web.server:app", host="0.0.0.0", port=4215)



if __name__ == "__main__":
    procs = [background_renderer, data_service_main, ha_service_main, run_server, run_sensors]
    processes = []
    try:
        for proc in procs:
            p = Process(target=proc)
            p.start()
            processes.append(p)
            print(f"[maindev] Started process {proc.__name__} with PID {p.pid}")
    finally:
        for p in processes:
            p.join()