import time
import sys
import threading
import json

from pathlib import Path
from dataclasses import dataclass

import board

from adafruit_seesaw import digitalio, rotaryio, seesaw
from adafruit_apds9960.apds9960 import APDS9960
from adafruit_apds9960 import colorutility

_here = Path(__file__).parent / 'tof_bin'

sys.path.append(_here.as_posix())

from _vl53lxcx import (
    DATA_DISTANCE_MM,
    DATA_TARGET_STATUS,
    RESOLUTION_8X8,
    STATUS_VALID,
    VL53L5CX,
)


@dataclass
class APDSColor16:
    _sensor: APDS9960
    red: int = 0
    green: int = 0
    blue: int = 0
    clear: int = 0
    updated_at: float = 0.0

    @property
    def as_8bit(self) -> tuple[int, int, int, int]:
        return (self.red // 256, self.green // 256, self.blue // 256, 255 - (self.clear // 256))
    
    @property
    def _is_zero(self):
        return self.red == 0 and self.green == 0 and self.blue == 0
    
    @property
    def temp(self):
        if self._is_zero:
            return 0
        return colorutility.calculate_color_temperature(self.red, self.green, self.blue)

    @property
    def lux(self):
        if self._is_zero:
            return 0
        return colorutility.calculate_lux(self.red, self.green, self.blue)

    @property
    def hex(self) -> str:
        r, g, b, a = self.as_8bit
        return f'#{r:02X}{g:02X}{b:02X}{a:02X}'

    def update(self):
        r, g, b, c = self._sensor.color_data
        if any([r != self.red, g != self.green, b != self.blue, c != self.clear]):
            self.red = r
            self.green = g
            self.blue = b
            self.clear = c
            self.updated_at = time.monotonic()
    
    def __repr__(self):
        return f"Color(hex={self.hex})"

@dataclass
class APDSProximitySensor:
    _sensor: APDS9960
    proximity: int = 0
    updated_at: float = 0.0

    def update(self):
        prox = self._sensor.proximity
        if prox != self.proximity:
            self.proximity = prox
            self.updated_at = time.monotonic()
    
    def __repr__(self):
        return f"Proximity(proximity={self.proximity})"

@dataclass
class APDSGesture:
    _sensor: APDS9960
    value: int = 0
    detected_at: float = 0.0

    gesture_map = ['--', 'up', 'down', 'left', 'right']

    def update(self):
        gesture = self._sensor.gesture()
        if gesture != self.value:
            self.value = gesture
            self.detected_at = time.monotonic()

    @property
    def gesture(self):
        return self.gesture_map[self.value]

    def __repr__(self):
        return f"Gesture(gesture={self.gesture})"


@dataclass
class LightSensor:
    color: APDSColor16
    proximity: APDSProximitySensor
    gesture: APDSGesture

    def update(self):
        self.color.update()
        self.proximity.update()
        self.gesture.update()

    def serialize(self) -> dict:
        return {
            'color_hex': self.color.hex,
            'color_temp': self.color.temp,
            'lux': self.color.lux,
            'proximity': self.proximity.proximity,
            'gesture': self.gesture.gesture,
            'updated_at': max(self.color.updated_at, self.proximity.updated_at, self.gesture.detected_at),
        }


@dataclass
class IOButton:
    io_pin: digitalio.DigitalIO
    pressed: bool = False
    pressed_at: float = 0.0
    released_at: float = 0.0
    updated_at: float = 0.0

    def update(self):
        current_value = self.io_pin.value
        if not current_value and not self.pressed:
            self.pressed = True
            self.updated_at = time.monotonic()
        elif current_value and self.pressed:
            self.pressed = False
            self.released_at = time.monotonic()
            self.updated_at = time.monotonic()
    
    def __repr__(self):
        return f"IOButton(pressed={self.pressed})"

    def serialize(self) -> dict:
        return {
            'pressed': self.pressed,
            'pressed_at': self.pressed_at,
            'released_at': self.released_at,
            'updated_at': self.updated_at,
        }

@dataclass
class Buttons:
    select: IOButton
    up: IOButton
    left: IOButton
    down: IOButton
    right: IOButton

    def iter(self):
        return [('select', self.select),
                ('up', self.up),
                ('left', self.left),
                ('down', self.down),
                ('right', self.right)]

    def update(self):
        for _, button in self.iter():
            button.update()

@dataclass
class RotaryEncoder:
    encoder: rotaryio.IncrementalEncoder
    position: int = 0
    updated_at: float = 0.0

    def update(self):
        current_position = self.encoder.position
        if current_position != self.position:
            self.position = current_position
            self.updated_at = time.monotonic()
    
    def __repr__(self):
        return f"RotaryEncoder(position={self.position})"

@dataclass
class AdafruitRemote:
    buttons: Buttons
    encoder: RotaryEncoder

    def update(self):
        self.buttons.update()
        self.encoder.update()
    
    def serialize(self) -> dict:
        return {
            'buttons': {name: button.serialize() for name, button in self.buttons.iter()},
            'encoder': {
                'position': self.encoder.position,
                'updated_at': self.encoder.updated_at,
            },
            'updated_at': max(button.updated_at for _, button in self.buttons.iter()),
        }

@dataclass
class ToFSensor:
    tof: VL53L5CX
    distance_mm: list[int] = None
    masked_distance_mm: list[int] = None
    grid: int = 7
    render: list[list[int]] = None
    updated_at: float = 0.0

    def update(self):
        if self.tof.check_data_ready():
            results = self.tof.get_ranging_data()
            distance_mm = results.distance_mm
            target_status = results.target_status
            grid = 7

            masked_distance_mm = [d if status == STATUS_VALID else 0 for d, status in zip(distance_mm, target_status)]

            self.distance_mm = distance_mm
            self.masked_distance_mm = masked_distance_mm
            self.updated_at = time.monotonic()
            if distance_mm != self.distance_mm:
                self.distance_mm = distance_mm
                self.masked_distance_mm = masked_distance_mm

            d_max = max(masked_distance_mm)
            render = []
            row = []
            for i, d in enumerate(masked_distance_mm):
                scaled = int((d / d_max) * 255) if d_max > 0 else 0
                row.append(scaled)
                if (i & grid) == grid:
                    render.append(row)
                    row = []
            self.render = render

    def serialize(self) -> dict:
        return {
            'distance_mm': self.distance_mm,
            'masked_distance_mm': self.masked_distance_mm,
            'updated_at': self.updated_at,
            'render': self.render,
            'grid': self.grid, 
        }


def setup():
    i2c = board.I2C()  # uses board.SCL and board.SDA
    print("i2c devices detected: ", [hex(x) for x in i2c.scan()])

    try:
        ssaw = seesaw.Seesaw(i2c, addr=0x49)

        seesaw_product = (ssaw.get_version() >> 16) & 0xFFFF
        print(f"Found product {seesaw_product}")
        if seesaw_product != 5740:
            print("Wrong firmware loaded?  Expected 5740")

        ssaw.pin_mode(1, ssaw.INPUT_PULLUP)
        ssaw.pin_mode(2, ssaw.INPUT_PULLUP)
        ssaw.pin_mode(3, ssaw.INPUT_PULLUP)
        ssaw.pin_mode(4, ssaw.INPUT_PULLUP)
        ssaw.pin_mode(5, ssaw.INPUT_PULLUP)
        remote = AdafruitRemote(
            buttons=Buttons(*(IOButton(digitalio.DigitalIO(ssaw, i)) for i in range(1, 6))),
            encoder=RotaryEncoder(rotaryio.IncrementalEncoder(ssaw)),
        )
    except Exception as e:
        print(f"Seesaw not found: {e}")
        remote = None

    try:
        apds = APDS9960(i2c)
        apds.enable_proximity = True
        apds.enable_gesture = True
        apds.enable_color = True

        light = LightSensor(
            color=APDSColor16(apds),
            proximity=APDSProximitySensor(apds),
            gesture=APDSGesture(apds),
        )
    except Exception as e:
        print(f"APDS9960 not found: {e}")
        light = None

    try:
        tof = VL53L5CX(i2c)
        # tof.reset()

        if not tof.is_alive():
            raise ValueError("VL53L8CX not detected")

        tof.init()

        tof.resolution = RESOLUTION_8X8
        grid = 7

        tof.ranging_freq = 2

        tof.start_ranging({DATA_DISTANCE_MM, DATA_TARGET_STATUS})
        tof = ToFSensor(tof)
    except Exception as e:
        print(f"VL53L5CX not found: {e}")
        tof = None

    return {
        'light_sensor': light,
        'remote': remote,
        'tof': tof,
    }

def sensor_loop(sensors: dict, callback=None):
    while True:
        payload = {
            "_v": "dit",
            "updated_at": time.monotonic(),
        }
        for name, sensor in sensors.items():
            if sensor:
                try:
                    sensor.update()
                    payload[name] = sensor.serialize()
                except Exception as e:
                    print(f"[DI Remote] Error updating sensor {name}: {e}")

        if callback:
            callback(payload)
        else:
            print(payload)
        time.sleep(0.01)

def sensor_thread(callback):
    threading.Thread(target=sensor_loop, args=(setup(), callback), daemon=True).start()
    print('[Gestures] Enabled')


if __name__ == "__main__":
    import redis
    db = redis.Redis(host='localhost', port=6379, db=0)
    def publish(channel: str, action: str, payload: dict = {}):
        db.publish(channel, json.dumps({'_action': action, **payload}))

    def callback(payload):
        publish('di.pubsub.telemetry', action='update', payload={'data': json.dumps(payload)})

    sensor_loop(setup(), callback)
