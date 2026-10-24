import time
import sys
import threading
import json

from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict, Counter, deque
from typing import Optional

import board

from adafruit_seesaw import digitalio, rotaryio, seesaw
from adafruit_apds9960.apds9960 import APDS9960
from adafruit_apds9960 import colorutility
from adafruit_mlx90640 import MLX90640, RefreshRate
from pydantic import BaseModel

from .modulino.buzzer import ModulinoBuzzer
from .modulino.rtttl import notes_to_rtttl, rtttl_to_notes
from .libs import sparkfun_da7280 as sf_haptic

_here = Path(__file__).parent / 'tof_bin'

sys.path.append(_here.as_posix())

from ._vl53lxcx import (
    DATA_DISTANCE_MM,
    DATA_TARGET_STATUS,
    RESOLUTION_8X8,
    STATUS_VALID,
    VL53L5CX,
)

class Config(BaseModel):
    buzzer_enable: bool = True
    buzzer_address: str = '0x1e'

    tof_enable: bool = True

    apds_enable: bool = True
    apds_color_enable: bool = True
    apds_gesture_enable: bool = False
    apds_proximity_enable: bool = False
    apds_proximity_params: list[int] = [20, 80, 1]

    seesaw_enable: bool = True
    seesaw_address: str = '0x49'

    node_name: str = 'discreen'


@dataclass
class APDSColor16:
    _sensor: APDS9960 = None
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
        if not self._sensor:
            return
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
    _sensor: APDS9960 = None
    proximity: int = 0
    updated_at: float = 0.0

    def update(self):
        if not self._sensor:
            return
        prox = self._sensor.proximity
        if prox != self.proximity:
            self.proximity = prox
            self.updated_at = time.monotonic()
    
    def __repr__(self):
        return f"Proximity(proximity={self.proximity})"

@dataclass
class APDSGesture:
    _sensor: APDS9960 = None
    value: int = 0
    detected_at: float = 0.0

    gesture_map = ['--', 'up', 'down', 'left', 'right']

    def update(self):
        if not self._sensor:
            return
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
    color: APDSColor16 = field(default_factory=APDSColor16)
    proximity: APDSProximitySensor = field(default_factory=APDSProximitySensor)
    gesture: APDSGesture = field(default_factory=APDSGesture)
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

    @classmethod
    def setup(cls, bus: board.I2C, conf: Config, **kwargs):
        if not conf.apds_enable:
            return cls(**kwargs)
        try:
            apds = APDS9960(bus)
            apds.enable_proximity = conf.apds_proximity_enable
            apds.enable_gesture = conf.apds_gesture_enable
            apds.enable_color = conf.apds_color_enable
            apds.proximity_interrupt_threshold = tuple(conf.apds_proximity_params)

            return cls(
                color=APDSColor16(apds),
                proximity=APDSProximitySensor(apds),
                gesture=APDSGesture(apds),
                **kwargs
            )
        except Exception as e:
            print('[APDS] Setup failed', str(e))
            return cls(**kwargs)


@dataclass
class IOButton:
    io_pin: digitalio.DigitalIO = None
    pressed: bool = False
    pressed_at: float = 0.0
    released_at: float = 0.0
    updated_at: float = 0.0

    def update(self):
        if not self.io_pin:
            return
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
    select: IOButton = field(default_factory=IOButton)
    up: IOButton = field(default_factory=IOButton)
    left: IOButton = field(default_factory=IOButton)
    down: IOButton = field(default_factory=IOButton)
    right: IOButton = field(default_factory=IOButton)

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
    encoder: rotaryio.IncrementalEncoder = None
    position: int = 0
    updated_at: float = 0.0
    last_values: list[int] = field(default_factory=lambda: deque(maxlen=5))

    def update(self):
        if not self.encoder:
            return
        current_position = self.encoder.position

        if abs(current_position - self.position) >= 1:
            self.position = current_position
            self.updated_at = time.monotonic()
    
    def __repr__(self):
        return f"RotaryEncoder(position={self.position})"

@dataclass
class AdafruitRemote:
    buttons: Buttons = field(default_factory=Buttons)
    encoder: RotaryEncoder = field(default_factory=RotaryEncoder)
    update_frequency: int = 1
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

    @classmethod
    def setup(cls, bus: board.I2C, conf: Config, **kwargs):
        if not conf.seesaw_enable:
            return cls(**kwargs)

        def _get_ssaw():
            try:
                ssaw = seesaw.Seesaw(bus, addr=int(conf.seesaw_address, base=16))

                seesaw_product = (ssaw.get_version() >> 16) & 0xFFFF
                print(f"Found product {seesaw_product}")
                if seesaw_product != 5740:
                    print("Wrong firmware loaded?  Expected 5740")

                ssaw.pin_mode(1, ssaw.INPUT_PULLUP)
                ssaw.pin_mode(2, ssaw.INPUT_PULLUP)
                ssaw.pin_mode(3, ssaw.INPUT_PULLUP)
                ssaw.pin_mode(4, ssaw.INPUT_PULLUP)
                ssaw.pin_mode(5, ssaw.INPUT_PULLUP)
                ssaw.pin_mode(6, ssaw.INPUT_PULLUP)
                ssaw.pin_mode(15, ssaw.INPUT_PULLUP)
                ssaw.pin_mode(16, ssaw.INPUT_PULLUP)

                return ssaw
            except Exception as e:
                print('[Seesaw] Initialization failed', str(e))
                return None

        try:
            for _ in range(5):
                ssaw = _get_ssaw()
                if ssaw:
                    break
                time.sleep(1)

            return cls(
                buttons=Buttons(*(IOButton(digitalio.DigitalIO(ssaw, i)) for i in range(1, 6))),
                encoder=RotaryEncoder(rotaryio.IncrementalEncoder(ssaw)),
                **kwargs,
            )
        except Exception as e:
            print('[Seesaw] Setup failed', str(e))
            return cls(**kwargs)
        
@dataclass
class ToFSensor:
    # Add: 0x29
    tof: VL53L5CX = None
    distance_mm: list[int] = None
    masked_distance_mm: list[int] = None
    grid: int = 7
    render: list[list[int]] = None
    updated_at: float = 0.0
    update_frequency: int = 10
    _n_update: int = 0

    def update(self):
        if self._n_update < self.update_frequency:
            self._n_update += 1
            return
        self._n_update = 0

        if not self.tof:
            return
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
        if not self.tof:
            return {}
        return {
            'distance_mm': self.distance_mm,
            'masked_distance_mm': self.masked_distance_mm,
            'updated_at': self.updated_at,
            'render': self.render,
            'grid': self.grid,
        }

    @classmethod
    def setup(cls, bus: board.I2C, conf: Config, **kwargs):
        if not conf.tof_enable:
            return cls(**kwargs)
        try:
            tof = VL53L5CX(bus)

            if not tof.is_alive():
                raise ValueError("VL53L8CX not detected")

            tof.init()
            tof.resolution = RESOLUTION_8X8
            tof.ranging_freq = 10
            tof.start_ranging({DATA_DISTANCE_MM, DATA_TARGET_STATUS})
            return cls(tof, **kwargs)
        except Exception as e:
            print(f"[VL53L5CX] not found: {e}")
            return cls(**kwargs)


@dataclass
class IRCamera:
    mlx: MLX90640 = None
    enabled: bool = False
    width: int = 32
    height: int = 24
    data: list[int] = field(default_factory=list)
    render: list[list[int]] = field(default_factory=lambda: [[0 for _ in range(24)] for _ in range(32)])
    updated_at: float = 0.0
    update_frequency: int = 30
    _n_update: int = 0

    def update(self):
        if self._n_update < self.update_frequency:
            self._n_update += 1
            return
        self._n_update = 0

        if not self.mlx or not self.enabled:
            return
        data = [0] * 768
        try:
            self.mlx.getFrame(data)
        except ValueError:
            return

        self.data = data
        for h in range(self.height):
            for w in range(self.width):
                self.render[w][h] = data[h * 32 + w]
        self.updated_at = time.time()

    def serialize(self) -> dict:
        if not self.mlx:
            return {}
        return {
            'active': bool(self.mlx),
            'updated_at': self.updated_at,
            'render': self.render,
            'enabled': self.enabled,
        }

    @classmethod
    def setup(cls, bus: board.I2C, conf: Config, **kwargs):
        try:
            mlx = MLX90640(bus)
            mlx.refresh_rate = RefreshRate.REFRESH_2_HZ
            return cls(mlx, **kwargs)
        except Exception as e:
            print(f"[MLX90640] not found: {e}")
            return cls(**kwargs)

    def act(self, params: str, hash_: str):
        if params == 'start':
            self.enabled = True
        elif params == 'stop':
            self.enabled = False

@dataclass
class Buzzer:
    spk: ModulinoBuzzer = None
    enabled: bool = False

    active: bool = False
    duration: int = 125
    queue_max: int = 3      # distinct sounds waiting: more are dropped, they'd only stack up

    _buffer: list[tuple[str, tuple]] = field(default_factory=list)
    _wake: threading.Event = field(default_factory=threading.Event)


    # RTTTL = {
    #     'family_mart_1': 'melody:d=4,o=6,b=100:8p,8d5,32p,8d5,32p,16h5,32c#5,4d5,16p,16c#5,16c#5,16d5,32c#5,16g5,4f#5,16p,16d5,16d5,32c#5,8d5,32p,8d5,8c#5,16h5,4a4',
    #     'family_mart_1': 'melody:d=4,o=6,b=100:8p,8d5,32p,8d5,32p,16h5,32c#5,4d5,16p,16c#5,16c#5,16d5,32c#5,16g5,4f#5,16p,16d5,16d5,32c#5,8d5,32p,8d5,8c#5,16h5,4a4',
    #     'family_mart_2': 'm2:d=4,o=6,b=80:8p,32d4,16p,32f#5,16p,32a5,32p,32f4,16p,32a5,16p,32d5,32p,32e4,16p,32g#5,16p,32h5,32p,32c5,32p,32g#5,32p,32f4,32p,32c#4,32p,32d4,16p,32f#5,16p,32a5,32p,32e4,16p,32g#5,8p,32a4,16p,32a4,16p,32a4,32p',
    # }

    MELODIES = {
        "mario": (
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
        ),
        "nokia": (
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
        ),
        "family_mart": (
            ('REST', 400),
            ('D5',   400),
            ('REST', 50),
            ('D5',   400),
            ('REST', 50),
            ('B5',   200),
            ('CS5',  100),
            ('D5',   500),
            ('REST', 200),
            ('CS5',  200),
            ('CS5',  200),
            ('D5',   133),
            ('CS5',  66),
            ('G5',   133),
            ('FS5',  866),
            ('REST', 200),
            ('D5',   200),
            ('D5',   200),
            ('CS5',  100),
            ('D5',   300),
            ('REST', 100),
            ('D5',   300),
            ('CS5',  300),
            ('B5',   200),
            ('A4',   800),
        ),
        "family_mart_2": (
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
        ),
    }

    mario = 'smb:d=4,o=5,b=100:16e6,16e6,32p,8e6,16c6,8e6,8g6,8p,8g,8p,8c6,16p,8g,16p,8e,16p,8a,8b,16a#,8a,16g.,16e6,16g6,8a6,16f6,8g6,8e6,16c6,16d6,8b,16p,8c6,16p,8g,16p,8e,16p,8a,8b,16a#,8a,16g.,16e6,16g6,8a6,16f6,8g6,8e6,16c6,16d6,8b,8p,16g6,16f#6,16f6,16d#6,16p,16e6,16p,16g#,16a,16c6,16p,16a,16c6,16d6,8p,16g6,16f#6,16f6,16d#6,16p,16e6,16p,16c7,16p,16c7,16c7,p,16g6,16f#6,16f6,16d#6,16p,16e6,16p,16g#,16a,16c6,16p,16a,16c6,16d6,8p,16d#6,8p,16d6,8p,16c6'


    def update(self):
        pass    # plays in its own thread (_run): tones block, the sensors and acts don't wait for them

    def _run(self):
        # Each I2C write is one transfer to the kernel: sharing the bus with the sensor thread is fine.
        while True:
            self._wake.wait()
            self._wake.clear()
            while self._buffer:
                self.active = True
                for note, dur in self._buffer[0][1]:
                    if note == 'REST':
                        time.sleep(dur / 1000)
                    else:
                        self.spk.tone(note if isinstance(note, int) else ModulinoBuzzer.NOTES[note], dur - 5, blocking=True)
                self._buffer.pop(0)
            self.active = False

    def serialize(self) -> dict:
        return {
            'active': self.active,
            'duration': self.duration,
        }

    def act(self, params: str | list[str], hash_: str):
        '''params: a sound, or a list of them played as one (a melody, then a boop).'''
        if not self.enabled or not params:
            return
        notes = sum((self._sound(p) for p in ([params] if isinstance(params, str) else params)), [])
        sig = (hash_, tuple(notes))
        # The same sound again while it waits or plays: once is enough.
        if notes and sig not in self._buffer and len(self._buffer) < self.queue_max:
            self._buffer.append(sig)
            self._wake.set()

    def _sound(self, name: str) -> list[tuple[str | int, int]]:
        def scaled(notes, scale, rest=None):
            # rest: each rest that long whatever it says (ms). The family mart tunes had theirs as one sensor loop, ~60 ms.
            return [(n, rest if rest and n == 'REST' else int(d * scale)) for n, d in notes]
        if name == 'boop':
            return [('D5', 70), ('REST', 100)]
        elif name == 'rest_1s':
            return [('REST', 1000)]
        elif name == 'encoder':
            return [('A5', 10), ('REST', 10)]
        elif name == 'encoder-':
            return [('D5', 10), ('REST', 10)]
        elif name == 'ok':
            return [('E5', 125)]
        elif name == 'siren':
            return self.generate_siren(440, 880, 4000, 200, 2)
        elif name == 'nokia':
            return list(self.MELODIES['nokia'])
        elif name == 'fmart':
            return scaled(self.MELODIES['family_mart'], 1.25, rest=60)
        elif name == 'fmart.mid':
            return scaled(self.MELODIES['family_mart'], 1.35, rest=60)
        elif name == 'fmart.slow':
            return scaled(self.MELODIES['family_mart'], 2, rest=60)
        elif name == 'fmart2':
            return scaled(self.MELODIES['family_mart_2'], 1.2, rest=60)
        return []

    @classmethod
    def setup(cls, bus: board.I2C, conf: Config, **kwargs):
        if not conf.buzzer_enable:
            return cls(**kwargs)
        try:
            buzzer = ModulinoBuzzer(bus, address=int(conf.buzzer_address, base=16))
            buzz = cls(spk=buzzer, enabled=True, **kwargs)
            threading.Thread(target=buzz._run, daemon=True).start()
            # buzz.act('fmart.mid', '_init')
            # buzz.act('encoder', '_init')
            buzz.act('boop', '_init')
            # buzz.act('encoder', '_init')
            nrttl = notes_to_rtttl(cls.MELODIES['family_mart'], name="family_mart", default_duration=2**4, default_octave=4, bpm=160, _scale=1.35)
            # buzzer.play_rtttl(nrttl)
            # buzzer.play_rtttl(cls.mario)
            return buzz
        except Exception as e:
            print('[Buzzer] Setup failed', str(e))
            return cls(**kwargs)

    @staticmethod
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

@dataclass
class Haptics:
    da7280: sf_haptic.DA7280 = None
    enabled: bool = False
    running: bool = False
    triggered_at: float = 0.0
    duration: float = 1.0
    update_frequency: int = 1
    _n_update: int = 0
    
    @classmethod
    def setup(cls, bus: board.I2C, conf: Config, **kwargs):
        driver = sf_haptic.DA7280(bus)
        if driver.begin():
            driver.set_operation_mode(sf_haptic.DRO_MODE)
            haptics = cls(da7280=driver, enabled=True, **kwargs)
            haptics.act('boop', '_init')
            return haptics
        return cls(**kwargs)
    
    def serialize(self) -> dict:
        return {
            'active': bool(self.da7280),
        }

    def act(self, params: str, hash_: str):
        if not self.da7280:
            return

        def _set_trigger(stength, duration):
            self.da7280.set_vibrate(stength)
            self.running = True
            self.triggered_at = time.monotonic()
            self.duration = duration

        if params == 'boop':
            _set_trigger(20, 2)
        elif params == 'stop':
            _set_trigger(0, 0)
        elif params == 'tap':
            _set_trigger(20, 0.05)

    def update(self):
        if not self.enabled:
            return
        if self._n_update < self.update_frequency:
            self._n_update += 1
            return
        self._n_update = 0
        if self.running and (self.triggered_at + self.duration) < time.monotonic():
            self.da7280.set_vibrate(0)
            self.running = False


def setup(conf: Config = None):
    if conf is None:
        conf = Config()     # use default conf
    i2c = board.I2C()  # uses board.SCL and board.SDA
    bus_devs = i2c.scan()
    print("[i2c devices detected] ", [hex(x) for x in bus_devs if x])

    return {
        'remote': AdafruitRemote.setup(i2c, conf),
        'buzzer': Buzzer.setup(i2c, conf),
        'tof': ToFSensor.setup(i2c, conf),
        'light_sensor': LightSensor.setup(i2c, conf),
        'haptics': Haptics.setup(i2c, conf),
        # 'ircam': IRCamera.setup(i2c, conf),
    }

def sensor_loop(sensors: dict, conf: Config, callback=None):
    while True:
        payload = {
            "_v": "dit",
            "_node": conf.node_name,
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
            acts = callback(payload) or []
            # print(acts)
            for (actuator, cmd, hash_) in acts:
                try:
                    sensors[actuator].act(cmd, hash_)
                except:
                    print(f'Could not actuate {actuator=} for {cmd=}')
        else:
            print(payload)
        time.sleep(0.001)

def sensor_thread(callback, conf: Config):
    threading.Thread(target=sensor_loop, args=(setup(conf), conf, callback), daemon=True).start()
    print('[Gestures] Enabled')

def main():
    import redis
    db = redis.Redis(host='localhost', port=6379, db=0)
    def publish(channel: str, action: str, payload: dict = {}):
        db.publish(channel, json.dumps({'_action': action, **payload}))

    def callback(payload):
        publish('di.pubsub.telemetry', action='update', payload={'data': json.dumps(payload)})

    sensor_loop(setup(Config()), Config(node_name='disalon'), callback)


if __name__ == "__main__":
    main()
