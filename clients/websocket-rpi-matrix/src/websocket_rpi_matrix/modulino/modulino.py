__version__ = '1.0.0'
__author__ = "Sebastian Romero"
__license__ = "MPL 2.0"

from board import I2C
from time import sleep
from micropython import const
import re
import os
from collections import namedtuple

I2CInterface = namedtuple('I2CInterface', ['type', 'bus_number', "scl", "sda"])

DEVICE_I2C_INTERFACES = {
  "Arduino Nano ESP32": I2CInterface("hw", 0, None, None),
  "Arduino Nano RP2040 Connect": I2CInterface("hw", 0, None, None),
  "Arduino Portenta H7": I2CInterface("hw", 3, None, None),
  "Arduino Portenta C33": I2CInterface("hw", 0, None, None),
  "Generic ESP32S3 module": I2CInterface("hw", 0, None, None),
}

PINSTRAP_ADDRESS_MAP = {
  0x3C: "Buzzer",
  0x7C: "Buttons",
  0x76: "Knob",
  0x74: "Knob",
  0x6C: "Pixels"
}

class _I2CHelper:
  """
  A helper class for interacting with I2C devices on supported boards.
  """
  i2c_bus: I2C = None
  frequency: int = const(100000)  # Modulinos operate at 100kHz

  @staticmethod
  def extract_i2c_info(i2c_bus: I2C) -> tuple[int, int, int]:
    bus_info = str(i2c_bus)
    # Use regex to find the values of the interface, scl, and sda
    interface_match = re.search(r'I2C\((\d+)', bus_info)
    scl_match = re.search(r'scl=(\d+)', bus_info)
    sda_match = re.search(r'sda=(\d+)', bus_info)

    # Extract the values if the matches are found
    interface = int(interface_match.group(1)) if interface_match else None
    scl = int(scl_match.group(1)) if scl_match else None
    sda = int(sda_match.group(1)) if sda_match else None

    return interface, scl, sda

  @staticmethod
  def get_interface() -> I2C:
    if _I2CHelper.i2c_bus is None:
      _I2CHelper.i2c_bus = _I2CHelper._find_interface()
      _I2CHelper.i2c_bus = _I2CHelper.reset_bus(_I2CHelper.i2c_bus)
    return _I2CHelper.i2c_bus

  @staticmethod
  def _find_interface() -> I2C:
    """
    Returns an instance of the I2C interface for the current board.

    Raises:
      RuntimeError: If the current board is not supported.

    Returns:
      I2C: An instance of the I2C interface.
    """
    board_name = os.uname().machine.split(' with ')[0]
    interface_info = DEVICE_I2C_INTERFACES.get(board_name, None)

    if interface_info is None:
      raise RuntimeError(f"I2C interface couldn't be determined automatically for '{board_name}'.")

    if interface_info.type == "hw":
      return I2C(interface_info.bus_number, freq=_I2CHelper.frequency)

    if interface_info.type == "sw":
      from board import SoftI2C, Pin
      return SoftI2C(scl=Pin(interface_info.scl), sda=Pin(interface_info.sda), freq=_I2CHelper.frequency)

class Modulino:
  """
  Base class for all Modulino devices.
  """

  default_addresses: list[int] = []
  """
  A list of default addresses that the modulino can have.
  This list needs to be overridden derived classes.
  """

  convert_default_addresses: bool = True
  """
  Determines if the default addresses need to be converted from 8-bit to 7-bit.
  Addresses of modulinos without native I2C modules need to be converted.
  This class variable needs to be overridden in derived classes.
  """

  def __init__(self, i2c_bus: I2C = None, address: int = None, name: str = None):
    """
    Initializes the Modulino object with the given i2c bus and address.
    If the address is not provided, the device will try to auto discover it.
    If the address is provided, the device will check if it is connected to the bus.
    If the address is 8-bit, it will be converted to 7-bit.
    If no bus is provided, the default bus will be used if available.

    Parameters:
      i2c_bus (I2C): The I2C bus to use. If not provided, the default I2C bus will be used.
      address (int): The address of the device. If not provided, the device will try to auto discover it.
      name (str): The name of the device.
    """

    if i2c_bus is None:
      self.i2c_bus = _I2CHelper.get_interface()
    else:
      self.i2c_bus = i2c_bus

    self.name = name
    self.address = address

    if self.address is None:
      if len(self.default_addresses) == 0:
        raise RuntimeError(f"No default addresses defined for the {self.name} device.")

      if self.convert_default_addresses:
        # Need to convert the 8-bit address to 7-bit
        actual_addresses = list(map(lambda addr: addr >> 1, self.default_addresses))
        self.address = self.discover(actual_addresses)
      else:
        self.address = self.discover(self.default_addresses)

      if self.address is None:
        raise RuntimeError(f"Couldn't find the {self.name} device on the bus. Try resetting the board.")
    elif not self.connected:
      raise RuntimeError(f"Couldn't find a {self.name} device with address {hex(self.address)} on the bus. Try resetting the board.")

  def discover(self, default_addresses: list[int]) -> int | None:
    """
    Tries to find the given modulino device in the device chain
    based on the pre-defined default addresses. The first address found will be returned.
    If the address has been changed to a custom one it won't be found with this function.

    Returns:
      int | None: The address of the device if found, None otherwise.
    """
    if len(default_addresses) == 0:
      return None

    devices_on_bus = self.i2c_bus.scan()
    for addr in default_addresses:
      if addr in devices_on_bus:
        return addr

    return None

  def __bool__(self) -> bool:
    """
    Boolean cast operator to determine if the given i2c device has a correct address
    and if the bus is defined.
    In case of auto discovery this also means that the device was found on the bus
    because otherwise the address would be None.
    """
    # Check if a valid i2c address is set and bus is defined
    return self.i2c_bus is not None and self.address is not None and self.address <= 127 and self.address >= 0

  @property
  def connected(self) -> bool:
    """
    Determines if the given modulino is connected to the i2c bus.
    """
    if not bool(self):
      return False
    return self.address in self.i2c_bus.scan()

  @property
  def pin_strap_address(self) -> int | None:
    """
    Returns the pin strap i2c address of the modulino.
    This address is set via resistors on the modulino board.
    Since all modulinos generally use the same firmware, the pinstrap address
    is needed to determine the type of the modulino at boot time, so it know what to do.
    At boot it checks the internal flash in case its address has been overridden by the user
    which would take precedence.

    Returns:
      int | None: The pin strap address of the modulino.
    """
    if self.address is None:
      return None
    data = self.i2c_bus.readfrom(self.address, 1, True)
    # The first byte is always the pinstrap address
    return data[0]

  @property
  def device_type(self) -> str | None:
    """
    Returns the type of the modulino based on the pinstrap address as a string.
    """
    return PINSTRAP_ADDRESS_MAP.get(self.pin_strap_address, None)

  def change_address(self, new_address: int):
    """
    Sets the address of the i2c device to the given value.
    This is only supported on Modulinos that have a microcontroller.
    """
    # TODO: Check if device supports this feature by looking at the type

    data = bytearray(40)
    # Set the first two bytes to 'C' and 'F' followed by the new address
    data[0:2] = b'CF'
    data[2] = new_address * 2

    try:
      self.write(data)
    except OSError:
      pass  # Device resets immediately and causes ENODEV to be thrown which is expected

    self.address = new_address

  def enter_bootloader(self):
    """
    Enters the I2C bootloader of the device.
    This is only supported on Modulinos that have a microcontroller.

    Returns:
      bool: True if the device entered bootloader mode, False otherwise.
    """
    buffer = b'DIE'
    buffer += b'\x00' * (8 - len(buffer)) # Pad buffer to 8 bytes
    try:
        self.i2c_bus.writeto(self.address, buffer, True)
        sleep(0.25) # Wait for the device to reset
        return True
    except OSError as e:
      # ENODEV (e.errno == 19) can be thrown if either the device reset while writing out the buffer
      return False

  def read(self, amount_of_bytes: int) -> bytes | None:
    """
    Reads the given amount of bytes from the i2c device and returns the data.
    It skips the first byte which is the pinstrap address.

    Returns:
      bytes | None: The data read from the device.
    """

    if self.address is None:
      return None

    data = self.i2c_bus.readfrom(self.address, amount_of_bytes + 1, True)
    if len(data) < amount_of_bytes + 1:
      return None  # Something went wrong in the data transmission

    # data[0] is always the pinstrap address
    return data[1:]

  def write(self, data_buffer: bytearray) -> bool:
    """
    Writes the given buffer to the i2c device.

    Parameters:
      data_buffer (bytearray): The data to be written to the device.

    Returns:
      bool: True if the data was written successfully, False otherwise.
    """
    if self.address is None:
      return False
    self.i2c_bus.writeto(self.address, data_buffer)
    return True

  @property
  def has_default_address(self) -> bool:
    """
    Determines if the given modulino has a default address
    or if a custom one was set.
    """
    return self.address in self.default_addresses

  @staticmethod
  def available_devices(bus: I2C = None) -> list['Modulino']:
    """
    Finds all devices on the i2c bus and returns them as a list of Modulino objects.

    Parameters:
      bus (I2C): The I2C bus to use. If not provided, the default I2C bus will be used.

    Returns:
      list: A list of Modulino objects.
    """
    if bus is None:
      bus = _I2CHelper.get_interface()
    device_addresses = bus.scan()
    devices = []
    for address in device_addresses:
      device = Modulino(i2c_bus=bus, address=address)
      devices.append(device)
    return devices

  @staticmethod
  def reset_bus(i2c_bus: I2C) -> I2C:
    """
    Resets the i2c bus. This is useful when the bus is in an unknown state.
    The modulinos that are equipped with a micro controller use DMA operations.
    If the host board does a reset during such operation it can make the bus get stuck.

    Returns:
      I2C: A new i2c bus object after resetting the bus.
    """
    return _I2CHelper.reset_bus(i2c_bus)