import time
import sys
import threading
import json

from pathlib import Path
from dataclasses import dataclass, field

import board

from adafruit_seesaw import digitalio, rotaryio, seesaw
from adafruit_apds9960.apds9960 import APDS9960
from adafruit_apds9960 import colorutility

from .modulino.buzzer import ModulinoBuzzer

_here = Path(__file__).parent / 'tof_bin'

sys.path.append(_here.as_posix())

from ._vl53lxcx import (
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
    update_frequency: int = 10
    _n_update: int = 0

    def update(self):
        if self._n_update < self.update_frequency:
            self._n_update += 1
            return
        self._n_update = 0
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
    update_frequency: int = 4
    _n_update: int = 0

    def update(self):
        if self._n_update < self.update_frequency:
            self._n_update += 1
            return
        self._n_update = 0
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

def generate_siren(frequency_start, frequency_end, total_duration, steps, iterations):
    siren = []
    mid_point = steps // 2
    duration_rise = total_duration // 2
    duration_fall = total_duration // 2

    for _ in range(iterations):
        for i in range(steps):
            if i < mid_point:
                # Easing in rising part
                step_duration = duration_rise // mid_point + (duration_rise // mid_point * (mid_point - i) // mid_point)
                frequency = int(frequency_start + (frequency_end - frequency_start) * (i / mid_point))
            else:
                # Easing in falling part
                step_duration = duration_fall // mid_point + (duration_fall // mid_point * (i - mid_point) // mid_point)
                frequency = int(frequency_end - (frequency_end - frequency_start) * ((i - mid_point) / mid_point))

            siren.append((frequency, step_duration))

    return siren

mario = [
    ('E5', 125),
    ('REST', 25),
    ('E5', 125),
    ('REST', 125),
    ('E5', 125),
    ('REST', 125),
    ('C5', 125),
    ('E5', 125),
    ('REST', 125),
    ('G5', 125),
    ('REST', 375),
    ('G4', 250)
]
nokia = [
    ('E5', 150),
    ('D5', 150),
    ('FS4', 200),
    ('GS4', 200),
    ('REST', 25),
    ('CS5', 150),
    ('B4', 150),
    ('D4', 200),
    ('E4', 200),
    ('REST', 25),
    ('B4', 150),
    ('A4', 150),
    ('CS4', 200),
    ('E4', 200),
    ('REST', 10),
    ('A4', 400),
]
family_mart = [
    ('REST', 400),
    ('D6', 400),
    ('REST', 50),
    ('D6', 400),
    ('REST', 50),
    ('B5', 200),
    ('CS6', 100),
    ('D6', 500),
    ('REST', 100),
    ('CS5', 200),
    ('CS5', 200),
    ('D6', 133),
    ('CS6', 66),
    ('E6', 133),
    ('FS6', 866),
    ('REST', 100),
    ('D6', 200),
    ('D6', 200),
    ('CS6', 100),
    ('D6', 300),
    ('REST', 100),
    ('D6', 300),
    ('CS6', 300),
    ('B6', 200),
    ('A5', 800),
]
family_mart_2 = [
    
    
    ('REST',    400),
    ('D4',      100),
    ('REST',    200),
    ('FS5',     100),
    ('REST',    200),
    ('A5',      100),
    ('REST',    100),
    ('F4',      100),
    ('REST',    200),
    ('A5',      100),
    ('REST',    200),
    ('D5',      100),
    ('REST',    100), 
    ('E4',      100),
    ('REST',    200),
    ('GS5',     100),
    ('REST',    200),
    ('B5',      100),
    ('REST',    100),
    ('C5',      100),
    ('REST',    100), 
    ('GS5',     100),
    ('REST',    100),
    ('F4',      100),
    ('REST',    100),
    ('CS4',     100),
    ('REST',    100),
    ('D4',      100),
    ('REST',    200),
    ('FS5',     100),
    ('REST',    200),
    ('A5',      100),
    ('REST',    100),
    ('E4',      100),
    ('REST',    200),
    ('GS5',     100),
    ('REST',    400),
    ('A4',      100),
    ('REST',    200),
    ('A4',      100),
    ('REST',    200),
    ('A4',      100),
    ('REST',    100),
]

@dataclass
class Buzzer:
    spk: ModulinoBuzzer = None
    active: bool = False
    notes: tuple[tuple[str, int]] = field(default_factory=tuple)
    ix: int = 0
    duration: int = 125
    scale: float = 0.8

    async_rest: bool = False

    _is_resting: bool = False
    _resting_at: float = 0
    _rest_for: int = 0
    _buffer: list[tuple[list, int]] = field(default_factory=list)

    def update(self):
        if not self.active:
            if self._buffer:
                _, notes, scale = self._buffer.pop(0)
                self.active = True
                self.ix = 0
                self.notes = notes
                self.scale = scale
            return

        if self._is_resting and time.time() < (self._resting_at + (self._rest_for / 1000)):
            return

        remaining_notes = list(self.notes)[self.ix:]
        self._is_resting = False

        for i, (note, dur) in enumerate(remaining_notes):
            if self.async_rest and note == 'REST' and dur > 40:
                self.ix += (i + 1)
                self._rest_for = dur
                self._resting_at = time.time()
                self._is_resting = True
                return
            note1 = ModulinoBuzzer.NOTES[note]
            duration = int(dur * self.scale) - 5
            if self.spk:
                self.spk.tone(note1, duration, blocking=True)

        self.active = False
    
    def serialize(self) -> dict:
        return {
            'active': self.active,
            'duration': self.duration,
        }

    def act(self, params: str, hash_: str):
        if not params:
            return
        if params == 'boop':
            self._play(hash_, [('D5', 50)])
        elif params == 'ok':
            self._play(hash_, [('E5', 125)])
        elif params == 'siren':
            self._play(hash_, generate_siren(440, 880, 4000, 200, 2))
        elif params == 'nokia':
            self._play(hash_, nokia)
        elif params == 'fmart':
            self._play(hash_, family_mart, scale=1.2)
        elif params == 'fmart2':
            self._play(hash_, family_mart_2, scale=1.2)
    
    def _play(self, hash_, notes, block=True, scale=1):
        print(hash_, notes, scale, self._buffer)
        sig = (hash_, tuple(notes), scale)
        if sig not in self._buffer:
            self._buffer.append(sig)
        # if self.active:

        # else:
        #     self.active = True
        #     self.ix = 0
        #     self.notes = notes
        #     self.scale = scale
        #     self._buffer.append(sig)


def setup(with_tof=False):
    i2c = board.I2C()  # uses board.SCL and board.SDA
    bus_devs = i2c.scan()
    print("i2c devices detected: ", [hex(x) for x in bus_devs])

    try:
        buzzer2 = ModulinoBuzzer(i2c) if 0x39 in bus_devs else None
        # buzzer2 = ModulinoBuzzer(i2c, address=0x3d) if 0x3d in bus_devs else None
        # buzzer.change_address(0x3D)
        buzz1 = Buzzer(buzzer2)
        # buzz2 = Buzzer(buzzer2)
        buzz1.act('fmart', 'init')
        buzz1.act('fmart2', 'init')
        # buzz2.act('boop', 'init')
    except Exception as e:
        print(f"Buzzer not found: {e}")
        buzz1 = None
        buzz2 = None

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
        apds.enable_proximity = False
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
        if not with_tof:
            raise ValueError("Skipping ToF setup")

        tof = VL53L5CX(i2c)

        if not tof.is_alive():
            raise ValueError("VL53L8CX not detected")

        tof.init()
        tof.resolution = RESOLUTION_8X8
        tof.ranging_freq = 10
        tof.start_ranging({DATA_DISTANCE_MM, DATA_TARGET_STATUS})
        tof = ToFSensor(tof)
    except Exception as e:
        print(f"VL53L5CX not found: {e}")
        tof = None


    return {
        'light_sensor': light,
        'remote': remote,
        'tof': tof,
        'buzzer': buzz1,
        # 'buzzer2': buzz2,
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
            acts = callback(payload)
            if acts:
                for (actuator, cmd, hash_) in acts:
                    try:
                        sensors[actuator].act(cmd, hash_)
                    except:
                        print(f'Could not actuate {actuator=} for {cmd=}')
        else:
            print(payload)
        time.sleep(0.001)

def sensor_thread(callback):
    threading.Thread(target=sensor_loop, args=(setup(), callback), daemon=True).start()
    print('[Gestures] Enabled')

def main():
    import redis
    db = redis.Redis(host='localhost', port=6379, db=0)
    def publish(channel: str, action: str, payload: dict = {}):
        db.publish(channel, json.dumps({'_action': action, **payload}))

    def callback(payload):
        publish('di.pubsub.telemetry', action='update', payload={'data': json.dumps(payload)})

    sensor_loop(setup(), callback)


if __name__ == "__main__":
    main()
