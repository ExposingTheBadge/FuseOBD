import ctypes
import ctypes.wintypes
import struct
import winreg
from ctypes import Structure, c_ulong, c_char, c_void_p, POINTER, byref
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class Protocol(IntEnum):
    J1850VPW = 1
    J1850PWM = 2
    ISO9141 = 3
    ISO14230 = 4
    CAN = 5
    ISO15765 = 6
    SCI_A_ENGINE = 7
    SCI_A_TRANS = 8
    SCI_B_ENGINE = 9
    SCI_B_TRANS = 10


class FilterType(IntEnum):
    PASS_FILTER = 1
    BLOCK_FILTER = 2
    FLOW_CONTROL = 3


class ConnectFlag(IntEnum):
    NONE = 0
    ISO9141_NO_CHECKSUM = 0x0200
    CAN_29BIT_ID = 0x0100
    ISO9141_K_LINE_ONLY = 0x1000


class IoctlID(IntEnum):
    GET_CONFIG = 0x01
    SET_CONFIG = 0x02
    READ_VBATT = 0x03
    FIVE_BAUD_INIT = 0x04
    FAST_INIT = 0x05
    CLEAR_TX_BUFFER = 0x07
    CLEAR_RX_BUFFER = 0x08
    CLEAR_PERIODIC_MSGS = 0x09
    CLEAR_MSG_FILTERS = 0x0A
    CLEAR_FUNCT_MSG_LOOKUP_TABLE = 0x0B
    ADD_TO_FUNCT_MSG_LOOKUP_TABLE = 0x0C
    DELETE_FROM_FUNCT_MSG_LOOKUP_TABLE = 0x0D
    READ_PROG_VOLTAGE = 0x0E


class ConfigParam(IntEnum):
    DATA_RATE = 0x01
    LOOPBACK = 0x03
    NODE_ADDRESS = 0x04
    NETWORK_LINE = 0x05
    P1_MIN = 0x06
    P1_MAX = 0x07
    P2_MIN = 0x08
    P2_MAX = 0x09
    P3_MIN = 0x0A
    P3_MAX = 0x0B
    P4_MIN = 0x0C
    P4_MAX = 0x0D
    W0 = 0x19
    W1 = 0x0E
    W2 = 0x0F
    W3 = 0x10
    W4 = 0x11
    W5 = 0x12
    TIDLE = 0x13
    TINIL = 0x14
    TWUP = 0x15
    PARITY = 0x16
    BIT_SAMPLE_POINT = 0x17
    SYNC_JUMP_WIDTH = 0x18
    T1_MAX = 0x1A
    T2_MAX = 0x1B
    T3_MAX = 0x1C
    T4_MAX = 0x1D
    T5_MAX = 0x1E
    ISO15765_BS = 0x1F
    ISO15765_STMIN = 0x20
    DATA_BITS = 0x21
    FIVE_BAUD_MOD = 0x22
    BS_TX = 0x23
    STMIN_TX = 0x24
    ISO15765_WFT_MAX = 0x25
    CAN_MIXED_FORMAT = 0x8000
    J1962_PINS = 0x8001
    SW_CAN_HS_DATA_RATE = 0x8010
    SW_CAN_SPEEDCHANGE_ENABLE = 0x8011
    SW_CAN_RES_SWITCH = 0x8012
    ACTIVE_CHANNELS = 0x8020
    SAMPLE_RATE = 0x8021
    SAMPLES_PER_READING = 0x8022
    READINGS_PER_MSG = 0x8023
    AVERAGING_METHOD = 0x8024
    SAMPLE_RESOLUTION = 0x8025
    INPUT_RANGE_LOW = 0x8026
    INPUT_RANGE_HIGH = 0x8027


class J2534Error(IntEnum):
    STATUS_NOERROR = 0x00
    ERR_NOT_SUPPORTED = 0x01
    ERR_INVALID_CHANNEL_ID = 0x02
    ERR_INVALID_PROTOCOL_ID = 0x03
    ERR_NULL_PARAMETER = 0x04
    ERR_INVALID_IOCTL_VALUE = 0x05
    ERR_INVALID_FLAGS = 0x06
    ERR_FAILED = 0x07
    ERR_DEVICE_NOT_CONNECTED = 0x08
    ERR_TIMEOUT = 0x09
    ERR_INVALID_MSG = 0x0A
    ERR_INVALID_TIME_INTERVAL = 0x0B
    ERR_EXCEEDED_LIMIT = 0x0C
    ERR_INVALID_MSG_ID = 0x0D
    ERR_DEVICE_IN_USE = 0x0E
    ERR_INVALID_IOCTL_ID = 0x0F
    ERR_BUFFER_EMPTY = 0x10
    ERR_BUFFER_FULL = 0x11
    ERR_BUFFER_OVERFLOW = 0x12
    ERR_PIN_INVALID = 0x13
    ERR_CHANNEL_IN_USE = 0x14
    ERR_MSG_PROTOCOL_ID = 0x15
    ERR_INVALID_FILTER_ID = 0x16
    ERR_NO_FLOW_CONTROL = 0x17
    ERR_NOT_UNIQUE = 0x18
    ERR_INVALID_BAUDRATE = 0x19
    ERR_INVALID_DEVICE_ID = 0x1A


PASSTHRU_MSG_SIZE = 4128


class PASSTHRU_MSG(Structure):
    _fields_ = [
        ("ProtocolID", c_ulong),
        ("RxStatus", c_ulong),
        ("TxFlags", c_ulong),
        ("Timestamp", c_ulong),
        ("DataSize", c_ulong),
        ("ExtraDataIndex", c_ulong),
        ("Data", c_char * 4128),
    ]


class SCONFIG(Structure):
    _fields_ = [
        ("Parameter", c_ulong),
        ("Value", c_ulong),
    ]


class SCONFIG_LIST(Structure):
    _fields_ = [
        ("NumOfParams", c_ulong),
        ("ConfigPtr", POINTER(SCONFIG)),
    ]


class SBYTE_ARRAY(Structure):
    _fields_ = [
        ("NumOfBytes", c_ulong),
        ("BytePtr", POINTER(c_char)),
    ]


class PassThruException(Exception):
    def __init__(self, error_code: int, message: str = ""):
        self.error_code = error_code
        self.error_name = J2534Error(error_code).name if error_code in J2534Error._value2member_map_ else f"UNKNOWN_{error_code}"
        super().__init__(f"{self.error_name} (0x{error_code:02X}): {message}" if message else self.error_name)


@dataclass
class J2534Device:
    name: str
    vendor: str
    dll_path: str
    config_app: str = ""
    port: str = ""
    is_serial: bool = False


def _get_com_port_parent_info(device_path: str) -> tuple[str, str, str]:
    """Given a SERIALCOMM device path (e.g. \\Device\\VCP0), trace to USB parent.
    Returns (friendly_name, vid_pid, manufacturer) or empty strings."""
    # The device path points into HKLM\SYSTEM\CurrentControlSet\Enum\
    # We search all USB entries for a matching child
    try:
        enum_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                  r"SYSTEM\CurrentControlSet\Enum\USB",
                                  0, winreg.KEY_READ)
    except OSError:
        return ("", "", "")

    try:
        i = 0
        while True:
            try:
                vid_pid = winreg.EnumKey(enum_key, i)
            except OSError:
                break
            i += 1
            try:
                vid_sub = winreg.OpenKey(enum_key, vid_pid, 0, winreg.KEY_READ)
            except OSError:
                continue
            j = 0
            while True:
                try:
                    instance = winreg.EnumKey(vid_sub, j)
                except OSError:
                    break
                j += 1
                try:
                    dev = winreg.OpenKey(vid_sub, instance, 0, winreg.KEY_READ)
                except OSError:
                    continue
                friendly = ""
                mfg = ""
                try:
                    friendly = winreg.QueryValueEx(dev, "FriendlyName")[0]
                except OSError:
                    try:
                        friendly = winreg.QueryValueEx(dev, "DeviceDesc")[0]
                    except OSError:
                        pass
                try:
                    mfg = winreg.QueryValueEx(dev, "Mfg")[0]
                except OSError:
                    pass
                winreg.CloseKey(dev)
                # If friendly name contains the device's service/name, it's a match
                return (friendly, vid_pid, mfg)
            winreg.CloseKey(vid_sub)
    finally:
        winreg.CloseKey(enum_key)
    return ("", "", "")


def _enumerate_com_ports() -> list[J2534Device]:
    """Scan COM ports from Windows registry for USB-to-serial adapters (ELM327, STN, etc)."""
    devices = []
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"HARDWARE\DEVICEMAP\SERIALCOMM",
                             0, winreg.KEY_READ)
    except OSError:
        return devices

    # Get all COM port entries
    port_entries = []
    i = 0
    while True:
        try:
            dev_path, port_name, _typ = winreg.EnumValue(key, i)
            port_entries.append((dev_path, port_name))
            i += 1
        except OSError:
            break
    winreg.CloseKey(key)

    # Walk USB enumeration to match ports to devices
    try:
        enum_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                  r"SYSTEM\CurrentControlSet\Enum\USB",
                                  0, winreg.KEY_READ)
    except OSError:
        # Even without USB info, add COM ports (except COM1 which is usually onboard)
        for dev_path, port_name in port_entries:
            if "Serial0" not in dev_path and port_name != "COM1":
                devices.append(J2534Device(
                    name=f"OBD Adapter ({port_name})",
                    vendor="USB Serial",
                    dll_path=port_name,
                    port=port_name,
                    is_serial=True,
                ))
        return devices

    try:
        # For each VID/PID, check instances for COM port children
        matched_ports = set()
        i = 0
        while True:
            try:
                vid_pid = winreg.EnumKey(enum_key, i)
            except OSError:
                break
            i += 1
            try:
                vid_sub = winreg.OpenKey(enum_key, vid_pid, 0, winreg.KEY_READ)
            except OSError:
                continue
            j = 0
            while True:
                try:
                    instance = winreg.EnumKey(vid_sub, j)
                except OSError:
                    break
                j += 1
                try:
                    dev = winreg.OpenKey(vid_sub, instance, 0, winreg.KEY_READ)
                except OSError:
                    continue
                friendly = ""
                mfg = ""
                svc = ""
                try:
                    friendly = winreg.QueryValueEx(dev, "FriendlyName")[0]
                except OSError:
                    try:
                        friendly = winreg.QueryValueEx(dev, "DeviceDesc")[0]
                    except OSError:
                        pass
                try:
                    mfg = winreg.QueryValueEx(dev, "Mfg")[0]
                except OSError:
                    pass
                try:
                    svc = winreg.QueryValueEx(dev, "Service")[0]
                except OSError:
                    pass
                winreg.CloseKey(dev)

                # Check if this USB device has a child that owns a COM port
                try:
                    child_key_path = f"SYSTEM\\CurrentControlSet\\Enum\\USB\\{vid_pid}\\{instance}"
                    # The serial port may be a child device
                    _scan_for_com_child(child_key_path, port_entries, vid_pid,
                                        friendly, mfg, devices, matched_ports)
                except OSError:
                    pass
            winreg.CloseKey(vid_sub)
    finally:
        winreg.CloseKey(enum_key)

    # Add any remaining COM ports that weren't matched (except COM1)
    for dev_path, port_name in port_entries:
        if port_name not in matched_ports and "Serial0" not in dev_path and port_name != "COM1":
            devices.append(J2534Device(
                name=f"OBD Adapter ({port_name})",
                vendor="USB Serial",
                dll_path=port_name,
                port=port_name,
                is_serial=True,
            ))

    return devices


def _scan_for_com_child(parent_path: str, port_entries: list,
                        vid_pid: str, friendly: str, mfg: str,
                        devices: list, matched: set):
    """Check if a USB device or its children reference any known COM port."""
    try:
        parent = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, parent_path, 0, winreg.KEY_READ)
    except OSError:
        return

    # Check if this device has Device Parameters with PortName
    try:
        dp = winreg.OpenKey(parent, "Device Parameters", 0, winreg.KEY_READ)
        port_name = ""
        try:
            port_name = winreg.QueryValueEx(dp, "PortName")[0]
        except OSError:
            pass
        winreg.CloseKey(dp)
        if port_name:
            for _dp, pn in port_entries:
                if pn == port_name and pn not in matched:
                    matched.add(pn)
                    name = _clean_device_name(friendly) or f"OBD Adapter ({pn})"
                    vendor = _strip_atref(mfg) or _vid_pid_vendor(vid_pid)
                    devices.append(J2534Device(
                        name=name,
                        vendor=vendor,
                        dll_path=pn,
                        port=pn,
                        is_serial=True,
                    ))
                    return
    except OSError:
        pass

    # Walk child devices
    try:
        k = 0
        while True:
            try:
                child_name = winreg.EnumKey(parent, k)
            except OSError:
                break
            k += 1
            child_path = f"{parent_path}\\{child_name}"
            _scan_for_com_child(child_path, port_entries, vid_pid, friendly, mfg,
                                devices, matched)
    except OSError:
        pass
    winreg.CloseKey(parent)


def _clean_device_name(raw: str) -> str:
    """Strip INF reference prefixes like @oem211.inf,%...%."""
    if raw.startswith("@"):
        # @oem211.inf,%usb\vid_0403&pid_6001.devicedesc%;USB Serial Converter
        parts = raw.split(";", 1)
        return parts[1] if len(parts) > 1 else raw.lstrip("@")
    return raw


def _strip_atref(raw: str) -> str:
    """Strip @reference prefix from manufacturer string."""
    if raw.startswith("@"):
        parts = raw.split(";", 1)
        return parts[1] if len(parts) > 1 else raw.lstrip("@")
    return raw


def _vid_pid_vendor(vid_pid: str) -> str:
    """Return a readable vendor label from a VID_PID string."""
    vid = vid_pid.split("&")[0].replace("VID_", "") if "VID_" in vid_pid else ""
    known = {
        "0403": "FTDI",
        "1A86": "QinHeng (CH340)",
        "10C4": "Silicon Labs (CP210x)",
        "067B": "Prolific (PL2303)",
        "0483": "STM (VXDIAG)",
        "2A29": "Generic USB Serial",
    }
    vendor = known.get(vid, f"USB\\{vid_pid}" if vid_pid else "USB Serial")
    return vendor


def enumerate_devices() -> list[J2534Device]:
    devices = []
    # Phase 1: J2534 PassThru registry
    reg_path = r"SOFTWARE\PassThruSupport.04.04"
    for root_key in [winreg.HKEY_LOCAL_MACHINE]:
        for access in [winreg.KEY_READ, winreg.KEY_READ | winreg.KEY_WOW64_32KEY]:
            try:
                key = winreg.OpenKey(root_key, reg_path, 0, access)
            except OSError:
                continue
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    i += 1
                except OSError:
                    break
                try:
                    subkey = winreg.OpenKey(key, subkey_name, 0, access)
                    name = winreg.QueryValueEx(subkey, "Name")[0]
                    vendor = winreg.QueryValueEx(subkey, "Vendor")[0]
                    dll = winreg.QueryValueEx(subkey, "FunctionLibrary")[0]
                    config = ""
                    try:
                        config = winreg.QueryValueEx(subkey, "ConfigApplication")[0]
                    except OSError:
                        pass
                    devices.append(J2534Device(name=name, vendor=vendor, dll_path=dll, config_app=config))
                    winreg.CloseKey(subkey)
                except OSError:
                    pass
            winreg.CloseKey(key)

    # Phase 2: COM port (ELM327/STN/FTDI) devices
    com_devices = _enumerate_com_ports()
    devices.extend(com_devices)

    # Deduplicate by dll_path (J2534) or port (serial)
    seen_dll = set()
    seen_port = set()
    unique = []
    for d in devices:
        if d.is_serial:
            if d.port and d.port not in seen_port:
                seen_port.add(d.port)
                unique.append(d)
        else:
            if d.dll_path not in seen_dll:
                seen_dll.add(d.dll_path)
                unique.append(d)
    return unique


class ELM327Exception(Exception):
    """Errors from ELM327 serial adapters."""
    pass


# ── ELM327 serial backend (Windows COM port via ctypes) ──

class _DCB(Structure):
    """Windows DCB (Device Control Block) for serial port configuration."""
    _fields_ = [
        ("DCBlength", c_ulong),
        ("BaudRate", c_ulong),
        ("fBitFields", c_ulong),  # Packed bit fields
        ("wReserved", ctypes.c_ushort),
        ("XonLim", ctypes.c_ushort),
        ("XoffLim", ctypes.c_ushort),
        ("ByteSize", ctypes.c_ubyte),
        ("Parity", ctypes.c_ubyte),
        ("StopBits", ctypes.c_ubyte),
        ("XonChar", ctypes.c_char),
        ("XoffChar", ctypes.c_char),
        ("ErrorChar", ctypes.c_char),
        ("EofChar", ctypes.c_char),
        ("EvtChar", ctypes.c_char),
        ("wReserved1", ctypes.c_ushort),
    ]


class _COMMTIMEOUTS(Structure):
    _fields_ = [
        ("ReadIntervalTimeout", c_ulong),
        ("ReadTotalTimeoutMultiplier", c_ulong),
        ("ReadTotalTimeoutConstant", c_ulong),
        ("WriteTotalTimeoutMultiplier", c_ulong),
        ("WriteTotalTimeoutConstant", c_ulong),
    ]


class _WinSerial:
    """Minimal Windows serial port API for ELM327 adapters."""

    def __init__(self, port: str):
        self.port = port
        self.handle = None
        self._kernel32 = ctypes.windll.kernel32

    def open(self, baudrate: int = 38400):
        port_path = f"\\\\.\\{self.port}"
        GENERIC_RW = 0xC0000000
        OPEN_EXISTING = 3
        self.handle = self._kernel32.CreateFileW(
            port_path, GENERIC_RW, 0, None, OPEN_EXISTING, 0, None,
        )
        if self.handle == ctypes.c_void_p(-1).value or self.handle is None:
            raise ELM327Exception(f"Cannot open {self.port}. In use or missing driver.")

        # Build DCB
        dcb = _DCB()
        dcb.DCBlength = ctypes.sizeof(_DCB)
        dcb.BaudRate = baudrate
        # Bit fields: fBinary=1 | fDtrControl=1<<4 | fRtsControl=1<<12
        dcb.fBitFields = 1 | (1 << 4) | (1 << 12)
        dcb.ByteSize = 8
        dcb.Parity = 0  # NOPARITY
        dcb.StopBits = 0  # ONESTOPBIT

        self._kernel32.SetCommState(self.handle, ctypes.byref(dcb))
        # SetCommState can return 0 spuriously on some USB serial drivers;
        # get error code to check — 0 means success, 87 means invalid param
        err = ctypes.get_last_error()
        if err not in (0, None):
            raise ELM327Exception(f"SetCommState failed for {self.port} (error {err})")

        # Timeouts
        to = _COMMTIMEOUTS()
        to.ReadIntervalTimeout = 500
        to.ReadTotalTimeoutMultiplier = 0
        to.ReadTotalTimeoutConstant = 1000
        to.WriteTotalTimeoutMultiplier = 500
        to.WriteTotalTimeoutConstant = 1000

        if not self._kernel32.SetCommTimeouts(self.handle, ctypes.byref(to)):
            raise ELM327Exception(f"SetCommTimeouts failed for {self.port}")

    def close(self):
        if self.handle is not None:
            self._kernel32.CloseHandle(self.handle)
            self.handle = None

    def write(self, data: bytes):
        written = ctypes.c_ulong(0)
        if not self._kernel32.WriteFile(self.handle, data, len(data), ctypes.byref(written), None):
            raise ELM327Exception(f"WriteFile failed on {self.port}")
        return written.value

    def read(self, size: int = 256, timeout_ms: int = 1000) -> bytes:
        """Read up to size bytes with timeout."""
        nread = ctypes.c_ulong(0)
        buf = ctypes.create_string_buffer(size)
        if not self._kernel32.ReadFile(self.handle, buf, size, ctypes.byref(nread), None):
            raise ELM327Exception(f"ReadFile failed on {self.port}")
        return buf.raw[:nread.value]

    def read_until(self, timeout_ms: int = 1000) -> bytes:
        """Read until no more data (poll with short timeout)."""
        import time as _time
        result = bytearray()
        deadline = _time.time() + timeout_ms / 1000.0
        while _time.time() < deadline:
            chunk = self.read(256, 50)
            if chunk:
                result.extend(chunk)
                # If we got data, wait a bit more for any trailing bytes
                _time.sleep(0.01)
            elif result:
                # Got some data and now nothing — done
                break
            else:
                _time.sleep(0.01)
        return bytes(result)

    def flush(self):
        """Purge RX and TX buffers."""
        PURGE_RXCLEAR = 8
        PURGE_TXCLEAR = 4
        self._kernel32.PurgeComm(self.handle, PURGE_RXCLEAR | PURGE_TXCLEAR)


class J2534:
    def __init__(self, device: J2534Device):
        self.device = device
        self.device_id: Optional[int] = None
        self._serial: Optional[_WinSerial] = None
        self._channels: dict[int, dict] = {}
        self._next_channel = 0
        self._is_serial = device.is_serial

        if self._is_serial:
            self._serial = _WinSerial(device.port)
        else:
            self.dll = ctypes.WinDLL(device.dll_path)
            self._setup_functions()

    # ── J2534 DLL backend ──

    def _setup_functions(self):
        self._PassThruOpen = self.dll.PassThruOpen
        self._PassThruOpen.argtypes = [c_void_p, POINTER(c_ulong)]
        self._PassThruOpen.restype = c_ulong

        self._PassThruClose = self.dll.PassThruClose
        self._PassThruClose.argtypes = [c_ulong]
        self._PassThruClose.restype = c_ulong

        self._PassThruConnect = self.dll.PassThruConnect
        self._PassThruConnect.argtypes = [c_ulong, c_ulong, c_ulong, c_ulong, POINTER(c_ulong)]
        self._PassThruConnect.restype = c_ulong

        self._PassThruDisconnect = self.dll.PassThruDisconnect
        self._PassThruDisconnect.argtypes = [c_ulong]
        self._PassThruDisconnect.restype = c_ulong

        self._PassThruReadMsgs = self.dll.PassThruReadMsgs
        self._PassThruReadMsgs.argtypes = [c_ulong, POINTER(PASSTHRU_MSG), POINTER(c_ulong), c_ulong]
        self._PassThruReadMsgs.restype = c_ulong

        self._PassThruWriteMsgs = self.dll.PassThruWriteMsgs
        self._PassThruWriteMsgs.argtypes = [c_ulong, POINTER(PASSTHRU_MSG), POINTER(c_ulong), c_ulong]
        self._PassThruWriteMsgs.restype = c_ulong

        self._PassThruStartMsgFilter = self.dll.PassThruStartMsgFilter
        self._PassThruStartMsgFilter.argtypes = [
            c_ulong, c_ulong, POINTER(PASSTHRU_MSG), POINTER(PASSTHRU_MSG),
            POINTER(PASSTHRU_MSG), POINTER(c_ulong),
        ]
        self._PassThruStartMsgFilter.restype = c_ulong

        self._PassThruStopMsgFilter = self.dll.PassThruStopMsgFilter
        self._PassThruStopMsgFilter.argtypes = [c_ulong, c_ulong]
        self._PassThruStopMsgFilter.restype = c_ulong

        self._PassThruStartPeriodicMsg = self.dll.PassThruStartPeriodicMsg
        self._PassThruStartPeriodicMsg.argtypes = [c_ulong, POINTER(PASSTHRU_MSG), POINTER(c_ulong), c_ulong]
        self._PassThruStartPeriodicMsg.restype = c_ulong

        self._PassThruStopPeriodicMsg = self.dll.PassThruStopPeriodicMsg
        self._PassThruStopPeriodicMsg.argtypes = [c_ulong, c_ulong]
        self._PassThruStopPeriodicMsg.restype = c_ulong

        self._PassThruIoctl = self.dll.PassThruIoctl
        self._PassThruIoctl.argtypes = [c_ulong, c_ulong, c_void_p, c_void_p]
        self._PassThruIoctl.restype = c_ulong

        self._PassThruSetProgrammingVoltage = self.dll.PassThruSetProgrammingVoltage
        self._PassThruSetProgrammingVoltage.argtypes = [c_ulong, c_ulong, c_ulong]
        self._PassThruSetProgrammingVoltage.restype = c_ulong

        self._PassThruReadVersion = self.dll.PassThruReadVersion
        self._PassThruReadVersion.argtypes = [c_ulong, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
        self._PassThruReadVersion.restype = c_ulong

        self._PassThruGetLastError = self.dll.PassThruGetLastError
        self._PassThruGetLastError.argtypes = [ctypes.c_char_p]
        self._PassThruGetLastError.restype = c_ulong

    def _check(self, ret: int, context: str = ""):
        if ret != J2534Error.STATUS_NOERROR:
            err_buf = ctypes.create_string_buffer(256)
            self._PassThruGetLastError(err_buf)
            msg = err_buf.value.decode("ascii", errors="replace")
            raise PassThruException(ret, f"{context}: {msg}" if context else msg)

    def open(self):
        if self._is_serial:
            # Auto-detect baud rate — try common rates, send ATI to validate
            for baud in (38400, 115200, 500000, 230400, 9600, 921600, 2000000):
                try:
                    self._serial.open(baud)
                    self._elm_init(self._serial, baud)
                    # Verify communication with a simple command
                    resp = self._elm_cmd(self._serial, "ATI", timeout_ms=800)
                    if resp and len(resp) > 2 and "?" not in resp[:4]:
                        self._elm_init(self._serial, baud)  # Full init
                        return
                except Exception:
                    pass
                self._serial.close()
            raise ELM327Exception(f"Could not initialize adapter on {self.device.port}")
        else:
            dev_id = c_ulong()
            ret = self._PassThruOpen(None, byref(dev_id))
            self._check(ret, "PassThruOpen")
            self.device_id = dev_id.value

    def close(self):
        if self._is_serial:
            if self._serial:
                self._serial.close()
                self._serial = None
        else:
            if self.device_id is not None:
                ret = self._PassThruClose(self.device_id)
                self._check(ret, "PassThruClose")
                self.device_id = None

    def read_version(self) -> tuple[str, str, str]:
        if self._is_serial:
            fw = self._elm_cmd(self._serial, "ATI")
            # Try STN extended version too
            stn = ""
            try:
                stn = self._elm_cmd(self._serial, "STI")
            except Exception:
                pass
            return (fw.strip(), stn.strip() if stn else "ELM327", "ELM327")
        else:
            fw = ctypes.create_string_buffer(256)
            dll_ver = ctypes.create_string_buffer(256)
            api = ctypes.create_string_buffer(256)
            ret = self._PassThruReadVersion(self.device_id, fw, dll_ver, api)
            self._check(ret, "PassThruReadVersion")
            return (
                fw.value.decode("ascii", errors="replace"),
                dll_ver.value.decode("ascii", errors="replace"),
                api.value.decode("ascii", errors="replace"),
            )

    def read_battery_voltage(self) -> float:
        if self._is_serial:
            resp = self._elm_cmd(self._serial, "ATRV")
            try:
                return float(resp.strip().rstrip("V"))
            except ValueError:
                return 0.0
        else:
            voltage = c_ulong()
            ret = self._PassThruIoctl(self.device_id, IoctlID.READ_VBATT, None, byref(voltage))
            self._check(ret, "ReadVBatt")
            return voltage.value / 1000.0

    def connect(self, protocol: Protocol, flags: int = 0, baudrate: int = 500000) -> int:
        if self._is_serial:
            ch = self._next_channel
            self._next_channel += 1
            self._channels[ch] = {
                "protocol": protocol,
                "baudrate": baudrate,
                "flags": flags,
                "can_11bit": (flags & ConnectFlag.CAN_29BIT_ID) == 0,
                "tx_id": None,
                "rx_id": None,
                "filter_id": None,
            }
            return ch
        else:
            channel_id = c_ulong()
            ret = self._PassThruConnect(self.device_id, protocol, flags, baudrate, byref(channel_id))
            self._check(ret, f"PassThruConnect({protocol.name}, {baudrate})")
            return channel_id.value

    def disconnect(self, channel_id: int):
        if self._is_serial:
            self._channels.pop(channel_id, None)
        else:
            ret = self._PassThruDisconnect(channel_id)
            self._check(ret, "PassThruDisconnect")

    def start_msg_filter(self, channel_id: int, filter_type: FilterType,
                         mask: bytes, pattern: bytes, flow_control: Optional[bytes] = None) -> int:
        if self._is_serial:
            ch = self._channels.get(channel_id)
            if ch is None:
                return 0
            # Parse CAN IDs from pattern (big-endian uint32)
            if len(pattern) >= 4:
                rx_id = struct.unpack(">I", pattern[-4:])[0]
                if ch["can_11bit"]:
                    rx_id &= 0x7FF
                ch["rx_id"] = rx_id
            if flow_control and len(flow_control) >= 4:
                tx_id = struct.unpack(">I", flow_control[-4:])[0]
                if ch["can_11bit"]:
                    tx_id &= 0x7FF
                ch["tx_id"] = tx_id
            # Set CAN filter on adapter
            if ch["rx_id"] is not None:
                self._elm_cmd(self._serial, f"AT CRA {ch['rx_id']:X}")
            if ch["tx_id"] is not None:
                self._elm_cmd(self._serial, f"AT SH {ch['tx_id']:X}")
                # Flow control: when we transmit, the adapter should expect
                # flow control frames from the ECU. Use our TX ID as FC source.
                self._elm_cmd(self._serial, f"AT FC SH {ch['tx_id']:X}")
                self._elm_cmd(self._serial, "AT FC SD 30 00 00")
                self._elm_cmd(self._serial, "AT FC SM 1")
            ch["filter_id"] = 1
            return 1
        else:
            mask_msg = self._build_msg(0, mask)
            pattern_msg = self._build_msg(0, pattern)
            fc_msg = self._build_msg(0, flow_control) if flow_control else None
            filter_id = c_ulong()
            ret = self._PassThruStartMsgFilter(
                channel_id, filter_type,
                byref(mask_msg), byref(pattern_msg),
                byref(fc_msg) if fc_msg else None,
                byref(filter_id),
            )
            self._check(ret, "PassThruStartMsgFilter")
            return filter_id.value

    def stop_msg_filter(self, channel_id: int, filter_id: int):
        if self._is_serial:
            pass  # Filters cleared on next connect or at close
        else:
            ret = self._PassThruStopMsgFilter(channel_id, filter_id)
            self._check(ret, "PassThruStopMsgFilter")

    def write_msg(self, channel_id: int, data: bytes, protocol: Protocol = Protocol.ISO15765,
                  tx_flags: int = 0, timeout: int = 1000):
        if self._is_serial:
            ch = self._channels.get(channel_id)
            if ch is None:
                raise ELM327Exception(f"Invalid channel {channel_id}")
            # Build CAN frame: CAN ID (4 bytes big-endian) + data
            self._serial.flush()
            # Send as hex via ELM327
            # For ISO 15765, ELM327 expects: len, data bytes
            # But for raw CAN mode we send: CAN ID + data
            hex_data = data.hex().upper()
            self._serial.write((hex_data + "\r").encode("ascii"))
            self._serial.read(256, 100)  # Consume echo
        else:
            msg = self._build_msg(protocol, data, tx_flags=tx_flags)
            num = c_ulong(1)
            ret = self._PassThruWriteMsgs(channel_id, byref(msg), byref(num), timeout)
            self._check(ret, "PassThruWriteMsgs")

    def read_msgs(self, channel_id: int, count: int = 1, timeout: int = 1000) -> list[bytes]:
        if self._is_serial:
            ch = self._channels.get(channel_id)
            if ch is None:
                return []
            import time as _time
            deadline = _time.time() + timeout / 1000.0
            results = []
            while _time.time() < deadline and len(results) < count:
                data = self._serial.read(256, max(50, timeout // 2))
                if data:
                    text = data.decode("ascii", errors="replace").strip()
                    if text and ">" not in text:
                        # Parse hex response
                        cleaned = text.replace("\r", "").replace("\n", "").replace(" ", "")
                        if cleaned and len(cleaned) >= 2:
                            try:
                                frame = bytes.fromhex(cleaned)
                                results.append(frame)
                            except ValueError:
                                pass
                _time.sleep(0.005)
            return results
        else:
            msgs = (PASSTHRU_MSG * count)()
            num = c_ulong(count)
            ret = self._PassThruReadMsgs(channel_id, msgs, byref(num), timeout)
            if ret == J2534Error.ERR_BUFFER_EMPTY or ret == J2534Error.ERR_TIMEOUT:
                return []
            self._check(ret, "PassThruReadMsgs")
            result = []
            for i in range(num.value):
                result.append(bytes(msgs[i].Data[: msgs[i].DataSize]))
            return result

    def start_periodic_msg(self, channel_id: int, data: bytes, protocol: Protocol,
                           interval_ms: int, tx_flags: int = 0) -> int:
        if self._is_serial:
            return 0  # Not supported — call write_msg periodically instead
        else:
            msg = self._build_msg(protocol, data, tx_flags=tx_flags)
            msg_id = c_ulong()
            ret = self._PassThruStartPeriodicMsg(channel_id, byref(msg), byref(msg_id), interval_ms)
            self._check(ret, "PassThruStartPeriodicMsg")
            return msg_id.value

    def stop_periodic_msg(self, channel_id: int, msg_id: int):
        if self._is_serial:
            pass
        else:
            ret = self._PassThruStopPeriodicMsg(channel_id, msg_id)
            self._check(ret, "PassThruStopPeriodicMsg")

    def set_config(self, channel_id: int, params: dict[int, int]):
        if self._is_serial:
            pass  # Not needed for ELM327
        else:
            configs = (SCONFIG * len(params))()
            for i, (param, value) in enumerate(params.items()):
                configs[i].Parameter = param
                configs[i].Value = value
            config_list = SCONFIG_LIST(NumOfParams=len(params), ConfigPtr=configs)
            ret = self._PassThruIoctl(channel_id, IoctlID.SET_CONFIG, byref(config_list), None)
            self._check(ret, "SetConfig")

    def get_config(self, channel_id: int, params: list[int]) -> dict[int, int]:
        if self._is_serial:
            return {}
        else:
            configs = (SCONFIG * len(params))()
            for i, param in enumerate(params):
                configs[i].Parameter = param
            config_list = SCONFIG_LIST(NumOfParams=len(params), ConfigPtr=configs)
            ret = self._PassThruIoctl(channel_id, IoctlID.GET_CONFIG, byref(config_list), None)
            self._check(ret, "GetConfig")
            return {configs[i].Parameter: configs[i].Value for i in range(len(params))}

    def clear_rx_buffer(self, channel_id: int):
        if self._is_serial:
            self._serial.flush()
        else:
            ret = self._PassThruIoctl(channel_id, IoctlID.CLEAR_RX_BUFFER, None, None)
            self._check(ret, "ClearRxBuffer")

    def clear_tx_buffer(self, channel_id: int):
        if self._is_serial:
            self._serial.flush()
        else:
            ret = self._PassThruIoctl(channel_id, IoctlID.CLEAR_TX_BUFFER, None, None)
            self._check(ret, "ClearTxBuffer")

    # ── ELM327 protocol helpers ──

    def _elm_cmd(self, serial: _WinSerial, cmd: str, timeout_ms: int = 1000) -> str:
        """Send an AT command and return the response (stripped)."""
        serial.flush()
        serial.write((cmd + "\r").encode("ascii"))
        import time as _time
        result = bytearray()
        deadline = _time.time() + timeout_ms / 1000.0
        while _time.time() < deadline:
            chunk = serial.read(256, 50)
            if chunk:
                result.extend(chunk)
                text = bytes(result).decode("ascii", errors="replace")
                if ">" in text:
                    break
                _time.sleep(0.01)
            elif result:
                break
            else:
                _time.sleep(0.01)
        text = bytes(result).decode("ascii", errors="replace")
        # Strip the command echo and prompt, keep meaningful lines
        lines = []
        for line in text.replace("\r", "\n").split("\n"):
            line = line.strip()
            if not line or line == ">" or line == "OK":
                continue
            # Remove echo of the command itself
            if line.upper() == cmd.upper():
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    def _elm_init(self, serial: _WinSerial, baudrate: int = 115200):
        """Initialize ELM327 adapter with standard settings."""
        # Try higher baud rate first, fall back
        serial.flush()
        # Reset
        serial.write(b"AT Z\r")
        import time as _time
        _time.sleep(0.5)
        serial.read(256, 200)  # Consume startup message

        cmds = [
            "AT E0",   # Echo off
            "AT L0",   # Linefeed off
            "AT H0",   # Headers off
            "AT SP 6",  # ISO 15765-4 CAN 11-bit 500kbps
            "AT AT 2",  # Adaptive timing on
            "AT ST FF",  # Max timeout
        ]
        for cmd in cmds:
            self._elm_cmd(serial, cmd, 500)

    def clear_filters(self, channel_id: int):
        ret = self._PassThruIoctl(channel_id, IoctlID.CLEAR_MSG_FILTERS, None, None)
        self._check(ret, "ClearMsgFilters")

    def _build_msg(self, protocol: int, data: bytes, tx_flags: int = 0) -> PASSTHRU_MSG:
        msg = PASSTHRU_MSG()
        msg.ProtocolID = protocol
        msg.TxFlags = tx_flags
        msg.DataSize = len(data)
        msg.ExtraDataIndex = len(data)
        for i, b in enumerate(data):
            msg.Data[i] = b
        return msg

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()
