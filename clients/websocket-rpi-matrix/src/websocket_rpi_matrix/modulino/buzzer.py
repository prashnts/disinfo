from time import sleep

from .modulino import Modulino
from .rtttl import rtttl_to_notes, NOTES

class ModulinoBuzzer(Modulino):
  """
  Class to play tones on the piezo element of the Modulino Buzzer.
  Predefined notes are available in the NOTES dictionary e.g. ModulinoBuzzer.NOTES["C4"]
  """
  NOTES = NOTES

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

  def tone(self, frequency: int, length_ms: int = 0xFFFF, blocking: bool = False) -> None:
    """
    Plays a tone with the given frequency and duration.
    If blocking is set to True, the function will wait until the tone is finished.

    Parameters:
        frequency: The frequency of the tone in Hz (freuqencies below 180 Hz are not supported)
        length_ms: The duration of the tone in milliseconds. If omitted, the tone will play indefinitely
        blocking: If set to True, the function will wait until the tone is finished
    """
    if frequency < 180 and frequency != 0:
      raise ValueError("Frequency must be greater than 180 Hz")
    
    self.data[0:4] = frequency.to_bytes(4, 'little')
    self.data[4:8] = length_ms.to_bytes(4, 'little')
    self.write(self.data)
    
    if blocking:
      # Subtract 5ms to avoid unwanted pauses between tones
      # Those pauses are caused by the time it takes to send the data to the buzzer
      sleep((length_ms - 5) / 1000)

  def no_tone(self) -> None:
    """
    Stops the current tone from playing.
    """
    self.data = bytearray(8)
    self.write(self.data)
  
  def play_rtttl(self, rtttl: str) -> None:
    notes = rtttl_to_notes(rtttl)
    for note, duration in notes:
      self.tone(NOTES[note], duration, blocking=True)
