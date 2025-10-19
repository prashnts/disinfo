import time
import threading

from dataclasses import dataclass

import board

from adafruit_seesaw import digitalio, rotaryio, seesaw
from adafruit_apds9960.apds9960 import APDS9960
from adafruit_apds9960 import colorutility


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
        self.proximity = self._sensor.proximity
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
        self.value = gesture
        self.detected_at = time.monotonic()

    @property
    def gesture(self):
        return self.gesture_map[self.value]

    def __repr__(self):
        return f"Gesture(gesture={self.gesture})"

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
            'updated_at': time.monotonic(),
        }


def setup():
    i2c = board.I2C()  # uses board.SCL and board.SDA
    time.sleep(0.05)
    ssaw = seesaw.Seesaw(i2c, addr=0x49)
    time.sleep(0.05)

    seesaw_product = (ssaw.get_version() >> 16) & 0xFFFF
    print(f"Found product {seesaw_product}")
    if seesaw_product != 5740:
        print("Wrong firmware loaded?  Expected 5740")

    ssaw.pin_mode(1, ssaw.INPUT_PULLUP)
    ssaw.pin_mode(2, ssaw.INPUT_PULLUP)
    ssaw.pin_mode(3, ssaw.INPUT_PULLUP)
    ssaw.pin_mode(4, ssaw.INPUT_PULLUP)
    ssaw.pin_mode(5, ssaw.INPUT_PULLUP)

    time.sleep(0.05)

    apds = APDS9960(i2c)
    apds.enable_proximity = True
    # apds.enable_color = True
    apds.enable_gesture = True

    time.sleep(0.05)

    remote = AdafruitRemote(
        buttons=Buttons(*(IOButton(digitalio.DigitalIO(ssaw, i)) for i in range(1, 6))),
        encoder=RotaryEncoder(rotaryio.IncrementalEncoder(ssaw)),
    )
    light = LightSensor(
        color=APDSColor16(apds),
        proximity=APDSProximitySensor(apds),
        gesture=APDSGesture(apds),
    )

    return light, remote

def sensor_loop(apds, remote, callback=None):
    while True:
        apds.update()
        time.sleep(0.02)
        remote.update()
        try:
            payload = {"remote": remote.serialize(), "apds": apds.serialize(), "_v": "dit"}
            if callback:
                callback(payload)
            else:
                print(payload)
        except Exception as e:
            print(f'[DI Remote] Error in sensor loop: {e}')
        time.sleep(0.01)

def sensor_thread(callback):
    apds, remote = setup()
    try:
        threading.Thread(target=sensor_loop, args=(apds, remote, callback), daemon=True).start()
        print('[Gestures] Enabled')
    except ImportError:
        print('[Gestures] Not enabled')


if __name__ == "__main__":
    sensor_loop(*setup())
