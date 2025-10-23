from .modulino import Modulino
from time import sleep

class ModulinoBuzzer(Modulino):
  """
  Class to play tones on the piezo element of the Modulino Buzzer.
  Predefined notes are available in the NOTES dictionary e.g. ModulinoBuzzer.NOTES["C4"]
  """

  NOTES: dict[str, int] = {
    "FS3": 185,
    "G3": 196,
    "GS3": 208,
    "A3": 220,
    "AS3": 233,
    "B3": 247,
    "C4": 262,
    "CS4": 277,
    "D4": 294,
    "DS4": 311,
    "E4": 330,
    "F4": 349,
    "FS4": 370,
    "G4": 392,
    "GS4": 415,
    "A4": 440,
    "AS4": 466,
    "B4": 494,
    "C5": 523,
    "CS5": 554,
    "D5": 587,
    "DS5": 622,
    "E5": 659,
    "F5": 698,
    "FS5": 740,
    "G5": 784,
    "GS5": 831,
    "A5": 880,
    "AS5": 932,
    "B5": 988,
    "C6": 1047,
    "CS6": 1109,
    "D6": 1175,
    "DS6": 1245,
    "E6": 1319,
    "F6": 1397,
    "FS6": 1480,
    "G6": 1568,
    "GS6": 1661,
    "A6": 1760,
    "AS6": 1865,
    "B6": 1976,
    "C7": 2093,
    "CS7": 2217,
    "D7": 2349,
    "DS7": 2489,
    "E7": 2637,
    "F7": 2794,
    "FS7": 2960,
    "G7": 3136,
    "GS7": 3322,
    "A7": 3520,
    "AS7": 3729,
    "B7": 3951,
    "C8": 4186,
    "CS8": 4435,
    "D8": 4699,
    "DS8": 4978,
    "REST": 0
  }
  """
  Dictionary with the notes and their corresponding frequencies.
  The supported notes are defined as follows:
  - FS3, G3, GS3, A3, AS3, B3
  - C4, CS4, D4, DS4, E4, F4, FS4, G4, GS4, A4, AS4, B4
  - C5, CS5, D5, DS5, E5, F5, FS5, G5, GS5, A5, AS5, B5
  - C6, CS6, D6, DS6, E6, F6, FS6, G6, GS6, A6, AS6, B6
  - C7, CS7, D7, DS7, E7, F7, FS7, G7, GS7, A7, AS7, B7
  - C8, CS8, D8, DS8
  - REST (Silence)
  """

  default_addresses = [0x3C]

  def __init__(self, i2c_bus=None, address=None):
    """
    Initializes the Modulino Buzzer.

    Parameters:
        i2c_bus (I2C): The I2C bus to use. If not provided, the default I2C bus will be used.
        address (int): The I2C address of the module. If not provided, the default address will be used.
    """
    super().__init__(i2c_bus, address, "Buzzer")
    self.data = bytearray(8)
    self.no_tone()

  def tone(self, frequency: int, lenght_ms: int = 0xFFFF, blocking: bool = False) -> None:
    """
    Plays a tone with the given frequency and duration.
    If blocking is set to True, the function will wait until the tone is finished.

    Parameters:
        frequency: The frequency of the tone in Hz (freuqencies below 180 Hz are not supported)
        lenght_ms: The duration of the tone in milliseconds. If omitted, the tone will play indefinitely
        blocking: If set to True, the function will wait until the tone is finished
    """
    if frequency < 180 and frequency != 0:
      raise ValueError("Frequency must be greater than 180 Hz")
    
    self.data[0:4] = frequency.to_bytes(4, 'little')
    self.data[4:8] = lenght_ms.to_bytes(4, 'little')
    self.write(self.data)
    
    if blocking:
      # Subtract 5ms to avoid unwanted pauses between tones
      # Those pauses are caused by the time it takes to send the data to the buzzer
      sleep((lenght_ms - 5) / 1000)

  def no_tone(self) -> None:
    """
    Stops the current tone from playing.
    """
    self.data = bytearray(8)
    self.write(self.data)