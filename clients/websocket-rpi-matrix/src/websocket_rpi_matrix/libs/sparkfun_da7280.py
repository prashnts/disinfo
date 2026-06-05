"""
CircuitPython driver for the SparkFun Qwiic Haptic Driver DA7280
Author: Converted from Arduino library by Elias Santistevan
Compatible with Raspberry Pi using Blinka bindings
Copied from https://github.com/almond-bot-research/sparkfun-da7280/blob/main/sparkfun_da7280.py, MIT
"""

from dataclasses import dataclass
import time

from busio import I2C

# I2C Constants
DEF_ADDR = 0x4A
CHIP_REV = 0xBA
ENABLE = 0x01
UNLOCKED = 0x01
DISABLE = 0x00
LOCKED = 0x00
LRA_TYPE = 0x00
ERM_TYPE = 0x01
RAMP = 0x01
STEP = 0x00

# Operation Modes
INACTIVE = 0x00
DRO_MODE = 0x01
PWM_MODE = 0x02
RTWM_MODE = 0x03
ETWM_MODE = 0x04

# Events
HAPTIC_SUCCESS = 0x00
E_SEQ_CONTINUE = 0x01
E_UVLO = 0x02
HAPTIC_HW_ERROR = 0x03
E_SEQ_DONE = 0x04
HAPTIC_INCORR_PARAM = 0x05
HAPTIC_UNKNOWN_ERROR = 0x06
E_OVERTEMP_CRIT = 0x08
E_SEQ_FAULT = 0x10
E_WARNING = 0x20
E_ACTUATOR_FAULT = 0x40
E_OC_FAULT = 0x80

# Diagnostic Status
NO_DIAG = 0x00
E_PWM_FAULT = 0x20
E_MEM_FAULT = 0x40
E_SEQ_ID_FAULT = 0x80

# Status
STATUS_NOM = 0x00
STA_SEQ_CONTINUE = 0x01
STA_UVLO_VBAT_OK = 0x02
STA_PAT_DONE = 0x04
STA_OVERTEMP_CRIT = 0x08
STA_PAT_FAULT = 0x10
STA_WARNING = 0x20
STA_ACTUATOR = 0x40
STA_OC = 0x80

# Memory Array Positions
BEGIN_SNP_MEM = 0x00
NUM_SNIPPETS = 0x00
NUM_SEQUENCES = 0x01
ENDPOINTERS = 0x02
SNP_ENDPOINTERS = 0x02
TOTAL_MEM_REGISTERS = 0x64

# Memory Registers
NUM_SNIPPETS_REG = 0x84
NUM_SEQUENCES_REG = 0x85
SNP_ENDPOINTERS_REGS = 0x88
END_OF_MEM = 0xE7

# Register Addresses
CHIP_REV_REG = 0x00
IRQ_EVENT1 = 0x03
IRQ_EVENT_WARN_DIAG = 0x04
IRQ_EVENT_SEQ_DIAG = 0x05
IRQ_STATUS1 = 0x06
IRQ_MASK1 = 0x07
CIF_I2C1 = 0x08
FRQ_LRA_PER_H = 0x0A
FRQ_LRA_PER_L = 0x0B
ACTUATOR1 = 0x0C
ACTUATOR2 = 0x0D
ACTUATOR3 = 0x0E
CALIB_V2I_H = 0x0F
CALIB_V2I_L = 0x10
CALIB_IMP_H = 0x11
CALIB_IMP_L = 0x12
TOP_CFG1 = 0x13
TOP_CFG2 = 0x14
TOP_CFG3 = 0x15
TOP_CFG4 = 0x16
TOP_INT_CFG1 = 0x17
TOP_INT_CFG6_H = 0x1C
TOP_INT_CFG6_L = 0x1D
TOP_INT_CFG7_H = 0x1E
TOP_INT_CFG7_L = 0x1F
TOP_INT_CFG8 = 0x20
TOP_CTL1 = 0x22
TOP_CTL2 = 0x23
SEQ_CTL1 = 0x24
SWG_C1 = 0x25
SWG_C2 = 0x26
SWG_C3 = 0x27
SEQ_CTL2 = 0x28
GPI_0_CTL = 0x29
GPI_1_CTL = 0x2A
GPI_2_CTL = 0x2B
MEM_CTL1 = 0x2C
MEM_CTL2 = 0x2D
ADC_DATA_H1 = 0x2E
ADC_DATA_L1 = 0x2F
POLARITY = 0x43
LRA_AVR_H = 0x44
LRA_AVR_L = 0x45
FRQ_LRA_PER_ACT_H = 0x46
FRQ_LRA_PER_ACT_L = 0x47
FRQ_PHASE_H = 0x48
FRQ_PHASE_L = 0x49
FRQ_CTL = 0x4C
TRIM3 = 0x5F
TRIM4 = 0x60
TRIM6 = 0x62
TOP_CFG5 = 0x6E
IRQ_EVENT_ACTUATOR_FAULT = 0x81
IRQ_STATUS2 = 0x82
IRQ_MASK2 = 0x83
SNP_MEM_X = 0x84


@dataclass
class MotorParams:
    motor_type: int
    nom_volt: float
    abs_volt: float
    curr_max: float
    impedance: float
    lra_freq: float

    @staticmethod
    def default() -> "MotorParams":
        return MotorParams(
            motor_type=LRA_TYPE,
            nom_volt=2.106, 
            abs_volt=2.26, 
            curr_max=165.4, 
            impedance=13.8, 
            lra_freq=170
        )


class DA7280:
    """
    CircuitPython driver for DA7280 Haptic Motor Driver
    
    :param i2c: The I2C bus the DA7280 is connected to
    :param address: The I2C device address. Defaults to 0x4A
    """
    
    def __init__(self, i2c: I2C, address: int = DEF_ADDR, motor_params: MotorParams = MotorParams.default()):
        self._i2c = i2c
        self._address = address
        self.snp_mem_copy = [0] * 100
        self.last_pos_written = 0

        self.set_motor_params(motor_params)
        
    def begin(self) -> bool:
        """
        Initialize the DA7280 and verify chip revision
        
        :return: True if successful, False otherwise
        """
        time.sleep(0.002)  # 2ms delay
        
        chip_rev = self._read_register(CHIP_REV_REG)
        print(f'[DA7280] Chip revision: 0x{chip_rev:02X}')
        
        if chip_rev != CHIP_REV:
            return False
        return True
    
    def set_actuator_type(self, actuator: int) -> bool:
        """
        Set the actuator (motor) type: LRA_TYPE or ERM_TYPE
        
        :param actuator: Motor type (LRA_TYPE or ERM_TYPE)
        :return: True if successful, False otherwise
        """
        if actuator not in (LRA_TYPE, ERM_TYPE):
            return False
        
        return self._write_register(TOP_CFG1, 0xDF, actuator, 5)
    
    def set_operation_mode(self, mode: int = DRO_MODE) -> bool:
        """
        Set operation mode: PWM_MODE, DRO_MODE, RTWM_MODE, or ETWM_MODE
        
        :param mode: Operation mode (default: DRO_MODE for I2C control)
        :return: True if successful, False otherwise
        """
        if mode < 0 or mode > 3:
            return False
        
        result = self._write_register(TOP_CTL1, 0xF8, mode, 0)
        time.sleep(0.001)
        return result
    
    def get_operation_mode(self) -> int:
        """
        Get current operation mode
        
        :return: Current operation mode
        """
        mode = self._read_register(TOP_CTL1)
        return mode & 0x07
    
    def get_motor_params(self) -> MotorParams:
        """
        Get current motor settings
        
        :return: MotorParams object with current configuration
        """
        params = MotorParams()
        params.nom_volt = self._read_register(ACTUATOR1) * (23.4 * 10**-3)
        params.abs_volt = self._read_register(ACTUATOR2) * (23.4 * 10**-3)
        params.curr_max = (self._read_register(ACTUATOR3) * 7.2) + 28.6
        v2i_factor = (self._read_register(CALIB_V2I_H) << 8) | self._read_register(CALIB_V2I_L)
        params.impedance = (v2i_factor * 1.6104) / (self._read_register(ACTUATOR3) + 4)
        return params
    
    def set_motor_params(self, motor_params: MotorParams) -> bool:
        """
        Configure motor with custom settings
        
        :param motor_params: MotorParams object with desired configuration
        :return: True if successful, False otherwise
        """
        return (self.set_actuator_type(motor_params.motor_type) and
                self.set_actuator_abs_volt(motor_params.abs_volt) and
                self.set_actuator_nom_volt(motor_params.nom_volt) and
                self.set_actuator_imax(motor_params.curr_max) and
                self.set_actuator_impedance(motor_params.impedance) and
                self.set_actuator_lra_freq(motor_params.lra_freq))
    
    def set_actuator_abs_volt(self, abs_volt: float) -> bool:
        """
        Set absolute maximum voltage for the motor
        
        :param abs_volt: Voltage in volts (0 to 6.0)
        :return: True if successful, False otherwise
        """
        if abs_volt < 0 or abs_volt > 6.0:
            return False
        
        abs_volt = abs_volt / (23.4 * 10**-3)
        return self._write_register(ACTUATOR2, 0x00, int(abs_volt), 0)
    
    def get_actuator_abs_volt(self) -> float:
        """
        Get absolute maximum voltage setting
        
        :return: Voltage in volts
        """
        reg_val = self._read_register(ACTUATOR2)
        return reg_val * (23.4 * 10**-3)
    
    def set_actuator_nom_volt(self, rms_volt: float) -> bool:
        """
        Set nominal voltage for the motor
        
        :param rms_volt: Voltage in volts (0 to 3.3)
        :return: True if successful, False otherwise
        """
        if rms_volt < 0 or rms_volt > 3.3:
            return False
        
        rms_volt = rms_volt / (23.4 * 10**-3)
        return self._write_register(ACTUATOR1, 0x00, int(rms_volt), 0)
    
    def get_actuator_nom_volt(self) -> float:
        """
        Get nominal voltage setting
        
        :return: Voltage in volts
        """
        reg_val = self._read_register(ACTUATOR1)
        return reg_val * (23.4 * 10**-3)
    
    def set_actuator_imax(self, max_curr: float) -> bool:
        """
        Set maximum current for the motor
        
        :param max_curr: Current in milliamps (0 to 300)
        :return: True if successful, False otherwise
        """
        if max_curr < 0 or max_curr > 300.0:
            return False
        
        max_curr = (max_curr - 28.6) / 7.2
        return self._write_register(ACTUATOR3, 0xE0, int(max_curr), 0)
    
    def get_actuator_imax(self) -> int:
        """
        Get maximum current setting
        
        :return: Current in milliamps
        """
        reg_val = self._read_register(ACTUATOR3)
        reg_val &= 0x1F
        return int((reg_val * 7.2) + 28.6)
    
    def set_actuator_impedance(self, motor_impedance: float) -> bool:
        """
        Set motor impedance (must set IMAX first)
        
        :param motor_impedance: Impedance in ohms (0 to 50)
        :return: True if successful, False otherwise
        """
        if motor_impedance < 0 or motor_impedance > 50.0:
            return False
        
        max_curr = self._read_register(ACTUATOR3) & 0x1F
        v2i_factor = int((motor_impedance * (max_curr + 4)) / 1.6104)
        msb_impedance = (v2i_factor - (v2i_factor & 0x00FF)) // 256
        lsb_impedance = v2i_factor - (256 * (v2i_factor & 0x00FF))
        
        return (self._write_register(CALIB_V2I_L, 0x00, lsb_impedance, 0) and
                self._write_register(CALIB_V2I_H, 0x00, msb_impedance, 0))
    
    def get_actuator_impedance(self) -> int:
        """
        Get motor impedance setting
        
        :return: Impedance in ohms
        """
        reg_val_msb = self._read_register(CALIB_V2I_H)
        reg_val_lsb = self._read_register(CALIB_V2I_L)
        curr_val = self._read_register(ACTUATOR3) & 0x1F
        
        v2i_factor = (reg_val_msb << 8) | reg_val_lsb
        return int((v2i_factor * 1.6104) / (curr_val + 4))
    
    def set_actuator_lra_freq(self, frequency: float) -> bool:
        """
        Set LRA resonant frequency
        
        :param frequency: Frequency in Hz (0 to 500)
        :return: True if successful, False otherwise
        """
        if frequency < 0 or frequency > 500.0:
            return False
        
        lra_period = int(1 / (frequency * (1333.32 * 10**-9)))
        msb_frequency = (lra_period - (lra_period & 0x007F)) // 128
        lsb_frequency = lra_period - 128 * (lra_period & 0xFF00)
        
        return (self._write_register(FRQ_LRA_PER_H, 0x00, msb_frequency, 0) and
                self._write_register(FRQ_LRA_PER_L, 0x80, lsb_frequency, 0))
    
    def read_imp_adjust(self) -> int:
        """
        Read adjusted impedance calculated by the IC
        
        :return: Impedance in ohms
        """
        temp_msb = self._read_register(CALIB_IMP_H)
        temp_lsb = self._read_register(CALIB_IMP_L)
        
        total_imp = int((4 * 62.5 * 10**-3 * temp_msb) + (62.5 * 10**-3 * temp_lsb))
        return total_imp
    
    def enable_coin_erm(self) -> bool:
        """
        Configure settings for ERM (coin) vibration motor
        
        :return: True if successful, False otherwise
        """
        return (self.enable_acceleration(False) and
                self.enable_rapid_stop(False) and
                self.enable_amp_pid(False) and
                self.enable_v2i_factor_freeze(True) and
                self.calibrate_impedance_distance(True) and
                self.set_bemf_fault_limit(True))
    
    def enable_acceleration(self, enable: bool) -> bool:
        """
        Enable or disable active acceleration
        
        :param enable: True to enable, False to disable
        :return: True if successful, False otherwise
        """
        return self._write_register(TOP_CFG1, 0xFB, int(enable), 2)
    
    def enable_rapid_stop(self, enable: bool) -> bool:
        """
        Enable or disable rapid stop technology
        
        :param enable: True to enable, False to disable
        :return: True if successful, False otherwise
        """
        return self._write_register(TOP_CFG1, 0xFD, int(enable), 1)
    
    def enable_amp_pid(self, enable: bool) -> bool:
        """
        Enable or disable amplitude PID control
        
        :param enable: True to enable, False to disable
        :return: True if successful, False otherwise
        """
        return self._write_register(TOP_CFG1, 0xFE, int(enable), 0)
    
    def enable_freq_track(self, enable: bool) -> bool:
        """
        Enable or disable frequency tracking
        
        :param enable: True to enable, False to disable
        :return: True if successful, False otherwise
        """
        return self._write_register(TOP_CFG1, 0xF7, int(enable), 3)
    
    def set_bemf_fault_limit(self, enable: bool) -> bool:
        """
        Enable or disable BEMF fault limit
        
        :param enable: True to enable, False to disable
        :return: True if successful, False otherwise
        """
        return self._write_register(TOP_CFG1, 0xEF, int(enable), 4)
    
    def enable_v2i_factor_freeze(self, enable: bool) -> bool:
        """
        Enable or disable V2I factor freeze
        
        :param enable: True to enable, False to disable
        :return: True if successful, False otherwise
        """
        return self._write_register(TOP_CFG4, 0x7F, int(enable), 7)
    
    def calibrate_impedance_distance(self, enable: bool) -> bool:
        """
        Enable or disable automatic impedance updates
        
        :param enable: True to enable, False to disable
        :return: True if successful, False otherwise
        """
        return self._write_register(TOP_CFG4, 0xBF, int(enable), 6)
    
    def set_vibrate(self, val: int) -> bool:
        """
        Set vibration strength (127 max with acceleration on, 255 without)
        
        :param val: Vibration strength value
        :return: True if successful, False otherwise
        """
        if val < 0:
            return False
        
        accel_state = self._read_register(TOP_CFG1)
        accel_state &= 0x04
        accel_state = accel_state >> 2
        
        if accel_state == ENABLE:
            if val > 0x7F:
                val = 0x7F
        else:
            if val > 0xFF:
                val = 0xFF
        
        return self._write_register(TOP_CTL2, 0x00, val, 0)
    
    def get_vibrate(self) -> int:
        """
        Get current vibration strength setting
        
        :return: Vibration strength value
        """
        return self._read_register(TOP_CTL2)
    
    def get_full_brake(self) -> float:
        """
        Get full brake threshold
        
        :return: Brake threshold value
        """
        temp_thresh = self._read_register(TOP_CFG2)
        return (temp_thresh & 0x0F) * 6.66
    
    def set_full_brake(self, thresh: int) -> bool:
        """
        Set full brake threshold
        
        :param thresh: Threshold value (0 to 15)
        :return: True if successful, False otherwise
        """
        if thresh < 0 or thresh > 15:
            return False
        
        return self._write_register(TOP_CFG2, 0xF0, thresh, 0)
    
    def set_mask(self, mask: int) -> bool:
        """
        Set IRQ event mask
        
        :param mask: Mask value
        :return: True if successful, False otherwise
        """
        return self._write_register(IRQ_MASK1, 0x00, mask, 0)
    
    def get_mask(self) -> int:
        """
        Get IRQ event mask
        
        :return: Mask value
        """
        return self._read_register(IRQ_MASK1)
    
    def set_bemf(self, val: int) -> bool:
        """
        Set BEMF fault threshold
        
        :param val: Threshold value (0 to 3)
        :return: True if successful, False otherwise
        """
        if val < 0 or val > 3:
            return False
        
        return self._write_register(TOP_INT_CFG1, 0xFC, val, 0)
    
    def get_bemf(self) -> float:
        """
        Get BEMF fault threshold in millivolts
        
        :return: Threshold in mV
        """
        bemf = self._read_register(TOP_INT_CFG1)
        
        bemf_values = {
            0x00: 0.0,
            0x01: 4.9,
            0x02: 27.9,
            0x03: 49.9
        }
        return bemf_values.get(bemf, 4.9)
    
    def clear_irq(self, irq: int):
        """
        Clear IRQ event
        
        :param irq: IRQ event to clear
        """
        self._write_register(IRQ_EVENT1, ~irq & 0xFF, irq, 0)
    
    def get_irq_event(self) -> int:
        """
        Get IRQ event status
        
        :return: Event code
        """
        irq_event = self._read_register(IRQ_EVENT1)
        
        if not irq_event:
            return HAPTIC_SUCCESS
        
        return irq_event
    
    def get_event_diag(self) -> int:
        """
        Get diagnostic status for memory or PWM errors
        
        :return: Diagnostic status code
        """
        diag = self._read_register(IRQ_EVENT_SEQ_DIAG)
        
        if diag in (E_PWM_FAULT, E_MEM_FAULT, E_SEQ_ID_FAULT):
            return diag
        return NO_DIAG
    
    def get_irq_status(self) -> int:
        """
        Get IRQ status
        
        :return: Status code
        """
        status = self._read_register(IRQ_STATUS1)
        
        if status in (STA_SEQ_CONTINUE, STA_UVLO_VBAT_OK, STA_PAT_DONE,
                      STA_OVERTEMP_CRIT, STA_PAT_FAULT, STA_WARNING,
                      STA_ACTUATOR, STA_OC):
            return status
        return STATUS_NOM
    
    def add_snippet(self, ramp: int = RAMP, time_base: int = 2, 
                   amplitude: int = 2) -> bool:
        """
        Add a haptic snippet to waveform memory
        
        :param ramp: Ramp mode (RAMP or STEP)
        :param time_base: Time base value (0 to 7)
        :param amplitude: Amplitude value (0 to 15)
        :return: True if successful, False otherwise
        """
        if ramp < 0 or ramp > 1:
            return False
        
        if amplitude < 0 or amplitude > 15:
            return False
        
        if time_base < 0 or time_base > 7:
            return False
        
        self.set_operation_mode(INACTIVE)
        
        if (self._read_register(MEM_CTL2) >> 7) == LOCKED:
            self._write_register(MEM_CTL2, 0x7F, UNLOCKED, 7)
        
        pwl_val = (ramp << 7) | (time_base << 4) | (amplitude << 0)
        self._read_register(MEM_CTL1)
        
        self.snp_mem_copy[NUM_SNIPPETS] = self.snp_mem_copy[NUM_SNIPPETS] + 1
        self.snp_mem_copy[NUM_SEQUENCES] = self.snp_mem_copy[NUM_SEQUENCES] + 1
        
        frame_byte = self._add_frame(0, 3, 1)
        
        for i in range(self.snp_mem_copy[NUM_SNIPPETS]):
            self.snp_mem_copy[SNP_ENDPOINTERS + i] = SNP_ENDPOINTERS_REGS + i
            self.last_pos_written = SNP_ENDPOINTERS + i
        
        self.last_pos_written = self.last_pos_written + 1
        
        for i in range(self.snp_mem_copy[NUM_SEQUENCES]):
            self.snp_mem_copy[self.last_pos_written] = (SNP_ENDPOINTERS_REGS + 
                                                         self.snp_mem_copy[NUM_SNIPPETS] + i)
            self.last_pos_written = SNP_ENDPOINTERS + self.snp_mem_copy[NUM_SNIPPETS] + i
        
        self.last_pos_written = self.last_pos_written + 1
        self.snp_mem_copy[self.last_pos_written] = pwl_val
        self.last_pos_written = self.last_pos_written + 1
        self.snp_mem_copy[self.last_pos_written] = frame_byte
        
        self.set_seq_control(1, 0)
        
        return self._write_waveform_memory(self.snp_mem_copy)
    
    def _add_frame(self, gain: int, time_base: int, snip_id_low: int) -> int:
        """
        Create a frame command byte
        
        :param gain: Gain value
        :param time_base: Time base value
        :param snip_id_low: Snippet ID
        :return: Command byte
        """
        command_byte_zero = (gain << 5) | (time_base << 3) | (snip_id_low << 0)
        return command_byte_zero
    
    def play_from_memory(self, enable: bool = True) -> bool:
        """
        Play waveform from memory
        
        :param enable: True to play, False to stop
        :return: True if successful, False otherwise
        """
        return self._write_register(TOP_CTL1, 0xEF, int(enable), 4)
    
    def erase_waveform_memory(self):
        """
        Erase all waveform memory
        """
        for i in range(BEGIN_SNP_MEM, TOTAL_MEM_REGISTERS):
            self.snp_mem_copy[i] = 0
        self._write_waveform_memory(self.snp_mem_copy)
    
    def set_seq_control(self, repetitions: int, sequence_id: int) -> bool:
        """
        Set sequence control parameters
        
        :param repetitions: Number of repetitions (0 to 15)
        :param sequence_id: Sequence ID (0 to 15)
        :return: True if successful, False otherwise
        """
        if sequence_id < 0 or sequence_id > 15:
            return False
        
        if repetitions < 0 or repetitions > 15:
            return False
        
        return (self._write_register(SEQ_CTL2, 0xF0, sequence_id, 0) and
                self._write_register(SEQ_CTL2, 0x0F, repetitions, 4))
    
    # Private I2C helper methods
    
    def _write_register(self, reg: int, mask: int, bits: int, 
                       start_position: int) -> bool:
        """
        Write to a register with bit masking
        
        :param reg: Register address
        :param mask: Bit mask
        :param bits: Bits to write
        :param start_position: Starting bit position
        :return: True if successful, False otherwise
        """
        try:
            i2c_write = self._read_register(reg)
            i2c_write &= mask
            i2c_write |= (bits << start_position)
            
            buf = bytearray([reg, i2c_write])
            self._i2c.writeto(self._address, buf)
            return True
        except Exception:
            return False
    
    def _read_register(self, reg: int) -> int:
        """
        Read from a register
        
        :param reg: Register address
        :return: Register value
        """
        try:
            buf = bytearray([reg])
            self._i2c.writeto(self._address, buf)
            result = bytearray(1)
            self._i2c.readfrom_into(self._address, result)
            return result[0]
        except Exception as e:
            print(f'[DA7280] I2C read error: {e}')
            return 0
    
    def _write_waveform_memory(self, waveform_array: list[int]) -> bool:
        """
        Write waveform data to memory
        
        :param waveform_array: Array of waveform data
        :return: True if successful, False otherwise
        """
        try:
            buf = bytearray([NUM_SNIPPETS_REG])
            for i in range(BEGIN_SNP_MEM, TOTAL_MEM_REGISTERS):
                buf.append(waveform_array[i])
            
            self._i2c.writeto(self._address, buf)
            return True
        except Exception:
            return False