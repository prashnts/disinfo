import time
import threading

from ._apds9960 import APDS9960, DIRECTIONS


def setup():
    import smbus
    port = 1
    bus = smbus.SMBus(port)
    sensor = APDS9960(bus)

    sensor.setProximityIntLowThreshold(50)
    sensor.enableGestureSensor()
    sensor.enableLightSensor()
    sensor.enableProximitySensor()

    return sensor

def loop(sensor: APDS9960, callback):
    while True:
        time.sleep(0.03)
        values = {
            'prox': sensor.readProximity(),
        }
        if sensor.isLightAvailable():
            light_vals = {
                'v': sensor.readAmbientLight(),
                'r': sensor.readRedLight(),
                'g': sensor.readGreenLight(),
                'b': sensor.readBlueLight(),
            }
            values['als'] = light_vals
        if sensor.isGestureAvailable():
            gesture = sensor.readGesture()
            values['gx'] = DIRECTIONS[gesture]
        callback(values)


def gesture_detector(callback):
    try:
        sensor = setup()
        threading.Thread(target=loop, args=(sensor, callback), daemon=True).start()
        print('[Gestures] Enabled')
    except ImportError:
        print('[Gestures] Not enabled')

