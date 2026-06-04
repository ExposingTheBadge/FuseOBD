import ctypes
import ctypes.wintypes
import struct
import winreg
from ctypes import Structure, c_ulong, c_char, c_void_p, POINTER, byref
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


import sys
import os

def get_fuse_dll_path() -> str:
    """Resolve the path to the Zig-built fuse_j2534.dll.

    Search order:
      1. Frozen build: the DLL is bundled at PyInstaller's _MEIPASS root.
      2. Dev: prefer the versioned copy under dist/ (matches frozen layout),
         then the unversioned one in dist/, then the raw zig-out artifact.
    Returning the first that exists keeps `python app.py` working in any
    state of the build (just-after-`zig build`, just-after-`build.py`, or
    full release)."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, 'fuse_j2534.dll')

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    # Read version lazily so a stale import doesn't pin a dead path.
    try:
        from version import VERSION as _ver
    except Exception:
        _ver = None

    candidates = []
    if _ver:
        candidates.append(os.path.join(repo_root, 'dist', f'fuse_j2534-v{_ver}.dll'))
    candidates += [
        os.path.join(repo_root, 'dist', 'fuse_j2534.dll'),
        os.path.join(repo_root, 'zig', 'zig-out', 'bin', 'fuse_j2534.dll'),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    # Fall through to the zig-out path even if missing — the ctypes loader
    # will raise a clear OSError pointing at it.
    return candidates[-1]

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
    port: str = ""        # COM port for USB serial adapters
    host: str = ""        # IP address for WiFi adapters
    tcp_port: int = 35000 # TCP port for WiFi adapters
    is_serial: bool = False
    is_wifi: bool = False


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

    # Phase 3: WiFi (ELM327 over TCP) — skip slow network scan at startup;
    # user adds WiFi adapters manually via the connection panel.
    # Phase 4: Bluetooth SPP — scanned on-demand via the BT button.

    # Deduplicate by dll_path (J2534), port (serial), or host (wifi)
    seen_dll = set()
    seen_port = set()
    seen_host = set()
    unique = []
    for d in devices:
        if d.is_wifi:
            key = (d.host, d.tcp_port)
            if key not in seen_host:
                seen_host.add(key)
                unique.append(d)
        elif d.is_serial:
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


def _parse_voltage(resp: str) -> float:
    """Extract a battery-voltage reading from ATRV/STVR output.

    Tolerates leading garbage from clone adapters by scanning for the
    first decimal number rather than calling float() on the whole string.
    Mirrors the parser at FUN_0054e8c0 in the diagnostic-reference binary.
    """
    if not resp:
        return 0.0
    import re
    m = re.search(r"(\d+(?:\.\d+)?)", resp)
    if not m:
        return 0.0
    try:
        v = float(m.group(1))
    except ValueError:
        return 0.0
    return v if 0.0 < v < 30.0 else 0.0


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
    """Serial port for ELM327 adapters using pyserial (proven, reliable)."""

    def __init__(self, port: str):
        self.port = port
        self._ser = None

    def open(self, baudrate: int = 38400):
        import serial as _serial
        self._ser = _serial.Serial(
            port=self.port,
            baudrate=baudrate,
            bytesize=_serial.EIGHTBITS,
            parity=_serial.PARITY_NONE,
            stopbits=_serial.STOPBITS_ONE,
            timeout=0.5,
            write_timeout=0.5,
            rtscts=False,
            dsrdtr=False,
        )
        # FTDI chips: DTR must be asserted to power the ELM327, latency set to 1ms
        self._ser.dtr = True
        self._ser.rts = False
        try:
            # Reduce FTDI latency timer from 16ms to 1ms for fast CAN
            import ctypes
            ctypes.windll.kernel32.SetCommTimeouts(self._ser._port_handle, ctypes.byref(
                ctypes.create_string_buffer(20)))
        except Exception:
            pass

    def close(self):
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def write(self, data: bytes):
        try:
            from modules import issues_log as _il
            _il.log_tx(f"SERIAL {getattr(self, 'port', '?')}", data)
        except Exception:
            pass
        self._ser.write(data)
        self._ser.flush()

    def read(self, size: int = 256, timeout_ms: int = 1000) -> bytes:
        self._ser.timeout = timeout_ms / 1000.0
        data = self._ser.read(size)
        if data:
            try:
                from modules import issues_log as _il
                _il.log_rx(f"SERIAL {getattr(self, 'port', '?')}", data)
            except Exception:
                pass
        return data

    def read_until(self, timeout_ms: int = 1000) -> bytes:
        self._ser.timeout = timeout_ms / 1000.0
        result = bytearray()
        while True:
            b = self._ser.read(1)
            if not b:
                break
            result.extend(b)
        data = bytes(result)
        if data:
            try:
                from modules import issues_log as _il
                _il.log_rx(f"SERIAL {getattr(self, 'port', '?')}", data)
            except Exception:
                pass
        return data

    def flush(self):
        self._ser.reset_input_buffer()
        self._ser.reset_output_buffer()


class _TcpTransport:
    """TCP socket transport for WiFi ELM327 adapters."""

    def __init__(self, host: str, port: int = 35000):
        self.host = host
        self.port = port
        self._sock = None

    def open(self, baudrate: int = 38400):
        import socket as _socket
        self._sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        self._sock.settimeout(3.0)
        self._sock.connect((self.host, self.port))
        self._sock.settimeout(1.0)

    def close(self):
        if self._sock:
            try:
                self._sock.shutdown(1)
            except Exception:
                pass
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def write(self, data: bytes):
        try:
            from modules import issues_log as _il
            _il.log_tx(f"TCP {self.host}:{self.port}", data)
        except Exception:
            pass
        self._sock.sendall(data)

    def read(self, size: int = 256, timeout_ms: int = 1000) -> bytes:
        self._sock.settimeout(timeout_ms / 1000.0)
        try:
            data = self._sock.recv(size)
        except OSError:
            return b""
        if data:
            try:
                from modules import issues_log as _il
                _il.log_rx(f"TCP {self.host}:{self.port}", data)
            except Exception:
                pass
        return data

    def read_until(self, timeout_ms: int = 1000) -> bytes:
        import time as _time
        self._sock.settimeout(0.05)
        result = bytearray()
        deadline = _time.time() + timeout_ms / 1000.0
        while _time.time() < deadline:
            try:
                chunk = self._sock.recv(256)
                if chunk:
                    result.extend(chunk)
                else:
                    break
            except OSError:
                if result:
                    break
                _time.sleep(0.01)
        data = bytes(result)
        if data:
            try:
                from modules import issues_log as _il
                _il.log_rx(f"TCP {self.host}:{self.port}", data)
            except Exception:
                pass
        return data

    def flush(self):
        # Drain any pending data
        self._sock.settimeout(0.05)
        for _ in range(10):
            try:
                d = self._sock.recv(256)
                if not d:
                    break
            except OSError:
                break


def _ping_wifi_adapter(host: str, port: int = 35000, timeout: float = 2.0) -> bool:
    """Check if a WiFi ELM327 adapter is reachable at host:port."""
    import socket as _socket
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def _enumerate_wifi_adapters() -> list[J2534Device]:
    """Scan common WiFi OBD adapter IP addresses."""
    import socket as _socket
    wifi_subnets = [
        "192.168.0.10",    # Most common ELM327 WiFi default
        "192.168.0.1",     # Some adapters
        "192.168.1.10",
        "10.0.0.1",
        "192.168.4.1",     # ESP32-based adapters
        "192.168.1.1",
    ]
    devices = []
    for ip in wifi_subnets:
        if _ping_wifi_adapter(ip):
            devices.append(J2534Device(
                name=f"WiFi OBD Adapter ({ip})",
                vendor="WiFi/ELM327",
                dll_path=ip,
                host=ip,
                tcp_port=35000,
                is_wifi=True,
            ))
    return devices


def _enumerate_bluetooth_adapters() -> list[J2534Device]:
    """Scan Windows for paired Bluetooth devices that may be OBD adapters.

    BT SPP devices get COM ports (caught by _enumerate_com_ports), but we
    also scan the paired BT device list for adapters that haven't been
    assigned COM ports yet, and check for common OBD BT names/IDs.
    """
    devices = []
    import subprocess
    # Use PowerShell to query paired Bluetooth devices via WinRT
    ps_cmd = (
        'powershell -NoProfile -Command "'
        '[Windows.Devices.Radios.Radio,Windows.System.Profile,ContentType=WindowsRuntime] | Out-Null;'
        '[Windows.Devices.Enumeration.DeviceInformation,Windows.Devices.Enumeration,ContentType=WindowsRuntime] | Out-Null;'
        '$sel = [Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync('
        '[Windows.Devices.Bluetooth.BluetoothDevice]::GetDeviceSelectorFromPairingState($true));'
        '$task = $sel.AsTask(); $task.Wait(5000);'
        'if ($task.IsCompleted) { $devs = $task.Result; foreach ($d in $devs) {'
        'Write-Output "$($d.Name)|$($d.Id)|$($d.Kind)" } }"'
    )
    try:
        result = subprocess.run(ps_cmd, capture_output=True, text=True, timeout=10, shell=True)
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split("|", 2)
            name = parts[0].strip() if len(parts) > 0 else ""
            dev_id = parts[1].strip() if len(parts) > 1 else ""
            if not name:
                continue
            # OBD adapters often have telltale names
            obd_keywords = ["OBD", "ELM", "STN", "OBDII", "OBD2", "V-LINK",
                           "VEEPEAK", "Viecar", "BAFX", "ScanTool", "PLX",
                           "CARISTA", "OBDLink", "VGATE", "iCar", "BlueDriver",
                           "Foseal", "KOBRA", "Panlong", "Lufi", "Tonwon"]
            is_obd = any(kw.lower() in name.lower() for kw in obd_keywords)
            if not is_obd:
                continue
            # Check if this BT device already has a COM port assigned
            already_com = False
            com_devices = _enumerate_com_ports()
            for cd in com_devices:
                cd_name = cd.name.lower()
                if any(kw.lower() in cd_name for kw in obd_keywords):
                    already_com = True
                    break
            if not already_com:
                # Look for COM port in the BT device's services
                bt_com = _find_bt_com_port(name)
                if bt_com:
                    devices.append(J2534Device(
                        name=f"{name} ({bt_com})",
                        vendor="Bluetooth ELM327",
                        dll_path=bt_com,
                        port=bt_com,
                        is_serial=True,
                    ))
                else:
                    # Show as BT device even without COM port (needs pairing)
                    devices.append(J2534Device(
                        name=f"{name} (Bluetooth — pair first)",
                        vendor="Bluetooth ELM327",
                        dll_path="",
                        is_serial=False,
                    ))
    except Exception:
        pass
    return devices


def _find_bt_com_port(device_name: str) -> str:
    """Check if a Bluetooth SPP device has a COM port assigned in registry."""
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"HARDWARE\DEVICEMAP\SERIALCOMM",
                             0, winreg.KEY_READ)
    except OSError:
        return ""

    ports = []
    i = 0
    while True:
        try:
            path, port, _typ = winreg.EnumValue(key, i)
            # Bluetooth SPP COM ports have device paths containing Bth/
            if "Bth" in path or "Bluetooth" in path:
                ports.append((path, port))
            i += 1
        except OSError:
            break
    winreg.CloseKey(key)

    # Walk Enum\BTHENUM to match device to port
    for dev_reg in [r"SYSTEM\CurrentControlSet\Enum\BTHENUM",
                     r"SYSTEM\CurrentControlSet\Enum\BTH"]:
        try:
            bth = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, dev_reg, 0, winreg.KEY_READ)
        except OSError:
            continue
        try:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(bth, i)
                except OSError:
                    break
                i += 1
                try:
                    subk = winreg.OpenKey(bth, sub, 0, winreg.KEY_READ)
                    j = 0
                    while True:
                        try:
                            inst = winreg.EnumKey(subk, j)
                        except OSError:
                            break
                        j += 1
                        try:
                            dev = winreg.OpenKey(subk, inst, 0, winreg.KEY_READ)
                            friendly = ""
                            try:
                                friendly = winreg.QueryValueEx(dev, "FriendlyName")[0]
                            except OSError:
                                pass
                            winreg.CloseKey(dev)
                            if device_name.lower()[:8] in friendly.lower() or \
                               friendly.lower()[:8] in device_name.lower()[:8]:
                                # Found matching BT device, look for COM port child
                                child_path = f"{dev_reg}\\{sub}\\{inst}"
                                port = _find_com_port_child(child_path)
                                if port:
                                    return port
                        except OSError:
                            pass
                    winreg.CloseKey(subk)
                except OSError:
                    pass
        finally:
            winreg.CloseKey(bth)

    # If we found BT COM ports but couldn't match, return the first one
    if ports:
        return ports[0][1]
    return ""


def _find_com_port_child(parent_path: str) -> str:
    """Walk a registry device tree looking for a child with a PortName."""
    try:
        dp_path = f"{parent_path}\\Device Parameters"
        dp = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, dp_path, 0, winreg.KEY_READ)
        try:
            pn = winreg.QueryValueEx(dp, "PortName")[0]
            return pn
        except OSError:
            pass
        winreg.CloseKey(dp)
    except OSError:
        pass

    # Walk children
    try:
        parent = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, parent_path, 0, winreg.KEY_READ)
        k = 0
        while True:
            try:
                child = winreg.EnumKey(parent, k)
            except OSError:
                break
            k += 1
            result = _find_com_port_child(f"{parent_path}\\{child}")
            if result:
                winreg.CloseKey(parent)
                return result
        winreg.CloseKey(parent)
    except OSError:
        return ""
    return ""


class J2534:
    def __init__(self, device: J2534Device):
        self.device = device
        self.device_id: Optional[int] = None
        self._serial: Optional[_WinSerial] = None
        self._tcp: Optional[_TcpTransport] = None
        self._channels: dict[int, dict] = {}
        self._next_channel = 0
        self._is_serial = device.is_serial
        self._is_wifi = device.is_wifi

        if self._is_serial:
            self._stream = _WinSerial(device.port)
        elif self._is_wifi:
            self._stream = _TcpTransport(device.host, device.tcp_port)
        else:
            self.dll = ctypes.CDLL(get_fuse_dll_path())
            self._setup_functions()

    # ── J2534 DLL backend ──

    def _setup_functions(self):
        self._PassThruOpen = self.dll.fuse_j2534_open
        self._PassThruOpen.argtypes = [ctypes.c_char_p]
        self._PassThruOpen.restype = ctypes.c_int

        self._PassThruClose = self.dll.fuse_j2534_close
        self._PassThruClose.argtypes = [ctypes.c_int]
        self._PassThruClose.restype = ctypes.c_int

        self._PassThruConnect = self.dll.fuse_j2534_connect
        self._PassThruConnect.argtypes = [ctypes.c_int, c_ulong, c_ulong, c_ulong]
        self._PassThruConnect.restype = ctypes.c_int

        self._PassThruDisconnect = self.dll.fuse_j2534_disconnect
        self._PassThruDisconnect.argtypes = [ctypes.c_int, c_ulong]
        self._PassThruDisconnect.restype = ctypes.c_int

        self._PassThruReadMsgs = self.dll.fuse_j2534_read_msgs
        self._PassThruReadMsgs.argtypes = [ctypes.c_int, c_ulong, POINTER(PASSTHRU_MSG), POINTER(c_ulong), c_ulong]
        self._PassThruReadMsgs.restype = ctypes.c_int

        self._PassThruWriteMsgs = self.dll.fuse_j2534_write_msgs
        self._PassThruWriteMsgs.argtypes = [ctypes.c_int, c_ulong, POINTER(PASSTHRU_MSG), POINTER(c_ulong), c_ulong]
        self._PassThruWriteMsgs.restype = ctypes.c_int

        self._PassThruReadVersion = self.dll.fuse_j2534_read_version
        self._PassThruReadVersion.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
        self._PassThruReadVersion.restype = ctypes.c_int

        self._PassThruGetLastError = self.dll.fuse_j2534_get_last_error
        self._PassThruGetLastError.argtypes = [ctypes.c_int, ctypes.c_char_p]
        self._PassThruGetLastError.restype = ctypes.c_int

        self._fuse_uds_init = self.dll.fuse_uds_init
        self._fuse_uds_init.argtypes = [ctypes.c_int, c_ulong, c_ulong, c_ulong, c_ulong]
        self._fuse_uds_init.restype = ctypes.c_int

        self._fuse_uds_free = self.dll.fuse_uds_free
        self._fuse_uds_free.argtypes = [ctypes.c_int]
        self._fuse_uds_free.restype = ctypes.c_int

        self._fuse_uds_connect = self.dll.fuse_uds_connect
        self._fuse_uds_connect.argtypes = [ctypes.c_int]
        self._fuse_uds_connect.restype = ctypes.c_int

        self._fuse_uds_disconnect = self.dll.fuse_uds_disconnect
        self._fuse_uds_disconnect.argtypes = [ctypes.c_int]
        self._fuse_uds_disconnect.restype = ctypes.c_int

        self._fuse_uds_request = self.dll.fuse_uds_request
        self._fuse_uds_request.argtypes = [ctypes.c_int, ctypes.c_char_p, c_ulong, ctypes.c_char_p, c_ulong]
        self._fuse_uds_request.restype = ctypes.c_int

    def _check(self, ret: int, context: str = ""):
        if ret < 0:
            err_buf = ctypes.create_string_buffer(256)
            self._PassThruGetLastError(self.handle, err_buf)
            msg = err_buf.value.decode("ascii", errors="replace")
            raise PassThruException(abs(ret), f"{context}: {msg}" if context else msg)

    def open(self):
        if self._is_serial or self._is_wifi:
            if self._is_wifi:
                self._stream.open()
                self._elm_init(self._stream)
                resp = self._elm_cmd(self._stream, "ATI", timeout_ms=1200)
                if resp and len(resp) > 2 and "?" not in resp[:4]:
                    self._elm_init(self._stream)
                    return
                raise ELM327Exception(f"WiFi adapter at {self.device.host} not responding as ELM327")
            else:
                def _log(msg):
                    try:
                        from modules import issues_log as _il
                        _il.log_adapter(f"ELM: {msg}")
                    except Exception:
                        pass
                # Try last-known baud rate first, then fall back to full scan
                _LAST_BAUD = getattr(J2534, '_last_baud', 500000)
                bauds = [_LAST_BAUD] + [b for b in (38400, 115200, 500000, 230400, 9600, 921600) if b != _LAST_BAUD]
                for baud in bauds:
                    try:
                        _log(f'Trying {baud} baud...')
                        self._stream.open(baud)
                        self._elm_init(self._stream)
                        resp = self._elm_cmd(self._stream, "ATI", timeout_ms=600)
                        _log(f'ATI response: {repr(resp[:20])}')
                        if resp and len(resp) > 2 and "?" not in resp[:4]:
                            _log(f'Baud {baud} OK')
                            J2534._last_baud = baud
                            self._elm_init(self._stream)
                            return
                    except Exception as e:
                        _log(f'Baud {baud} failed: {e}')
                    try:
                        self._stream.close()
                    except Exception:
                        pass
                raise ELM327Exception(f"Could not initialize adapter on {self.device.port}")
        else:
            path_bytes = self.device.dll_path.encode('utf-8')
            res = self._PassThruOpen(path_bytes)
            if res < 0:
                raise PassThruException(J2534Error.ERR_FAILED, "Zig DLL failed to open vendor DLL")
            self.handle = res

    def close(self):
        if self._is_serial or self._is_wifi:
            if self._stream:
                self._stream.close()
                self._stream = None
        else:
            if hasattr(self, 'handle') and self.handle >= 0:
                self._PassThruClose(self.handle)
                self.handle = -1
            self.device_id = None

    def read_version(self) -> tuple[str, str, str]:
        if self._is_serial or self._is_wifi:
            fw = self._elm_cmd(self._stream, "ATI")
            # Try STN extended version too
            stn = ""
            try:
                stn = self._elm_cmd(self._stream, "STI")
            except Exception:
                pass
            return (fw.strip(), stn.strip() if stn else "ELM327", "ELM327")
        else:
            fw = ctypes.create_string_buffer(256)
            dll_ver = ctypes.create_string_buffer(256)
            api = ctypes.create_string_buffer(256)
            ret = self._PassThruReadVersion(self.handle, fw, dll_ver, api)
            self._check(ret, "PassThruReadVersion")
            return (
                fw.value.decode("ascii", errors="replace"),
                dll_ver.value.decode("ascii", errors="replace"),
                api.value.decode("ascii", errors="replace"),
            )

    def read_battery_voltage(self) -> float:
        if self._is_serial or self._is_wifi:
            # Try STN command first (more accurate on OBDLink)
            resp = self._elm_cmd(self._stream, "STVR", timeout_ms=400)
            v = _parse_voltage(resp) if resp and "?" not in resp else 0.0
            if v > 0:
                return v
            # Fall back to ELM327 AT RV
            resp = self._elm_cmd(self._stream, "ATRV", timeout_ms=600)
            return _parse_voltage(resp) if resp else 0.0
        else:
            voltage = c_ulong()
            ret = self._PassThruIoctl(self.handle, IoctlID.READ_VBATT, None, byref(voltage))
            self._check(ret, "ReadVBatt")
            return voltage.value / 1000.0

    def connect(self, protocol: Protocol, flags: int = 0, baudrate: int = 500000) -> int:
        if self._is_serial or self._is_wifi:
            # ELM327 can only do one CAN speed at a time — switch if needed.
            # Sequences mirror the diagnostic-reference binary
            # (FUN_0054f650 / FUN_00549830).
            current_baud = getattr(self, '_current_can_baud', None)
            if current_baud != baudrate:
                if baudrate == 500000:
                    self._elm_cmd(self._stream, "ATSP6", 600)   # 11-bit / 500k
                elif baudrate == 125000:
                    # User Protocol B configured for 125k MS-CAN. The "ON"
                    # activation lines were the missing piece — without them
                    # the PPs are written but never applied.
                    for cmd in (
                        "ATPP2ASV38",
                        "ATPP2AON",
                        "ATPP2CSV81",
                        "ATPP2CON",
                        "ATPP2DSV04",
                        "ATPP2DON",
                        "ATTPB",
                    ):
                        self._elm_cmd(self._stream, cmd, 400)
                self._current_can_baud = baudrate
                # Bus changed — drop cached ATSH/ATCRA so the next filter resends
                self._last_sh = None
                self._last_cra = None
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
            res = self._PassThruConnect(self.handle, protocol.value, flags, baudrate)
            if res < 0:
                self._check(res, "PassThruConnect")
            return res

    def disconnect(self, channel_id: int):
        if self._is_serial or self._is_wifi:
            self._channels.pop(channel_id, None)
        else:
            res = self._PassThruDisconnect(self.handle, channel_id)
            self._check(res, "PassThruDisconnect")

    def start_msg_filter(self, channel_id: int, filter_type: FilterType,
                         mask: bytes, pattern: bytes, flow_control: Optional[bytes] = None) -> int:
        if self._is_serial or self._is_wifi:
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
            # Set CAN headers on adapter (mirrors diag-reference FUN_005490f0):
            #   ATSHxxxxxx  — 3-byte tx header (11-bit) or 4-byte (29-bit)
            #   ATCRAxxx    — explicit receive address filter
            # Cache last-set values to skip redundant re-sends.
            if ch["tx_id"] is not None:
                if ch["can_11bit"]:
                    sh_hex = f"{ch['tx_id'] & 0x7FF:06X}"
                else:
                    sh_hex = f"{ch['tx_id'] & 0x1FFFFFFF:08X}"
                if getattr(self, '_last_sh', None) != sh_hex:
                    self._elm_cmd(self._stream, f"ATSH{sh_hex}")
                    self._last_sh = sh_hex
            rx_id = ch.get("rx_id")
            if rx_id is not None:
                if ch["can_11bit"]:
                    cra_hex = f"{rx_id & 0x7FF:03X}"
                else:
                    cra_hex = f"{rx_id & 0x1FFFFFFF:08X}"
                if getattr(self, '_last_cra', None) != cra_hex:
                    self._elm_cmd(self._stream, f"ATCRA{cra_hex}")
                    self._last_cra = cra_hex
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
        if self._is_serial or self._is_wifi:
            pass  # Filters cleared on next connect or at close
        else:
            ret = self._PassThruStopMsgFilter(channel_id, filter_id)
            self._check(ret, "PassThruStopMsgFilter")

    def write_msg(self, channel_id: int, data: bytes, protocol: Protocol = Protocol.ISO15765,
                  tx_flags: int = 0, timeout: int = 1000):
        if self._is_serial or self._is_wifi:
            ch = self._channels.get(channel_id)
            if ch is None:
                raise ELM327Exception(f"Invalid channel {channel_id}")
            # Strip 4-byte CAN ID prefix that J2534 API prepends
            payload = data[4:] if len(data) >= 4 else data

            # In AT SP 6 mode, the ELM327 handles ISO-TP PCI automatically.
            # Do NOT add our own PCI byte — the adapter adds it.
            # Just send the raw service data bytes.

            try:
                from modules import issues_log as _il
                tx = ch.get("tx_id")
                sh = f"{tx:06X}" if isinstance(tx, int) else "?"
                _il.log_protocol(
                    f"CAN TX  ch={channel_id} sh={sh} data={payload.hex().upper()} ({len(payload)}B)"
                )
            except Exception:
                pass

            self._stream.flush()
            hex_data = payload.hex().upper()
            self._stream.write((hex_data + "\r").encode("ascii"))
            import time as _time
            _time.sleep(0.01)
        else:
            msg = self._build_msg(protocol, data, tx_flags=tx_flags)
            num = c_ulong(1)
            ret = self._PassThruWriteMsgs(channel_id, byref(msg), byref(num), timeout)
            self._check(ret, "PassThruWriteMsgs")

    def read_msgs(self, channel_id: int, count: int = 1, timeout: int = 1000) -> list[bytes]:
        if self._is_serial or self._is_wifi:
            ch = self._channels.get(channel_id)
            if ch is None:
                return []
            import time as _time
            def _log(msg):
                try:
                    from modules import issues_log as _il
                    _il.log_protocol(msg)
                except Exception:
                    pass
            deadline = _time.time() + timeout / 1000.0
            results = []
            while _time.time() < deadline and len(results) < count:
                data = self._stream.read(256, max(50, timeout // 2))
                if data:
                    text = data.decode("ascii", errors="replace").strip()
                    if text and ">" not in text and "BUS" not in text.upper() \
                       and "ERROR" not in text.upper() and "NO DATA" not in text.upper():
                        cleaned = text.replace("\r", "").replace("\n", "").replace(" ", "")
                        if cleaned and len(cleaned) >= 2:
                            try:
                                raw = bytes.fromhex(cleaned)
                                _log(f'CAN RX raw: {cleaned}')
                                # ELM327 in AT SP 6 mode strips ISO-TP PCI from
                                # received frames automatically. The raw data is
                                # the actual payload (service response bytes).
                                payload = raw
                                rx_id = ch.get("rx_id")
                                if rx_id is not None:
                                    frame = struct.pack(">I", rx_id & 0x7FF) + payload
                                else:
                                    frame = payload
                                rx_disp = f"{rx_id:06X}" if isinstance(rx_id, int) else "----"
                                _log(f'CAN RX: rx_id={rx_disp} payload={payload.hex().upper()}')
                                results.append(frame)
                            except ValueError:
                                pass
                    elif "NO DATA" in text.upper():
                        _log(f'CAN RX: NO DATA')
                _time.sleep(0.005)
            if not results:
                _log(f'CAN RX: timeout (no response)')
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
        if self._is_serial or self._is_wifi:
            return 0  # Not supported — call write_msg periodically instead
        else:
            msg = self._build_msg(protocol, data, tx_flags=tx_flags)
            msg_id = c_ulong()
            ret = self._PassThruStartPeriodicMsg(channel_id, byref(msg), byref(msg_id), interval_ms)
            self._check(ret, "PassThruStartPeriodicMsg")
            return msg_id.value

    def stop_periodic_msg(self, channel_id: int, msg_id: int):
        if self._is_serial or self._is_wifi:
            pass
        else:
            ret = self._PassThruStopPeriodicMsg(channel_id, msg_id)
            self._check(ret, "PassThruStopPeriodicMsg")

    def set_config(self, channel_id: int, params: dict[int, int]):
        if self._is_serial or self._is_wifi:
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
        if self._is_serial or self._is_wifi:
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
        if self._is_serial or self._is_wifi:
            self._stream.flush()
        else:
            ret = self._PassThruIoctl(channel_id, IoctlID.CLEAR_RX_BUFFER, None, None)
            self._check(ret, "ClearRxBuffer")

    def clear_tx_buffer(self, channel_id: int):
        if self._is_serial or self._is_wifi:
            self._stream.flush()
        else:
            ret = self._PassThruIoctl(channel_id, IoctlID.CLEAR_TX_BUFFER, None, None)
            self._check(ret, "ClearTxBuffer")

    # ── ELM327 protocol helpers ──

    def _elm_cmd(self, stream, cmd: str, timeout_ms: int = 1000) -> str:
        """Send an AT command and return the response (stripped)."""
        stream.flush()
        stream.write((cmd + "\r").encode("ascii"))
        import time as _time
        result = bytearray()
        deadline = _time.time() + timeout_ms / 1000.0
        while _time.time() < deadline:
            chunk = stream.read(256, 50)
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

    def _elm_init(self, stream):
        """Initialize the adapter with the same sequence the diag-reference
        binary uses (decompiled FUN_0054f190 / FUN_005491f0). The wide 0x7xx
        receive filter is the part that lets all Ford modules through —
        without it the ELM only passes whatever auto-receive guessed.
        """
        stream.flush()
        # Reset
        stream.write(b"ATZ\r")
        import time as _time
        _time.sleep(0.8)
        stream.read(256, 300)  # Consume startup message

        for cmd in (
            "ATE0",        # Echo off
            "ATL0",        # Linefeed off
            "ATH0",        # Headers off
            "ATS0",        # Spaces off
            "ATSP6",       # ISO 15765-4 11-bit 500k (HS-CAN)
            "ATAT1",       # Adaptive timing mode 1
            "ATSTFF",      # Max response timeout
            "ATTA30",      # Tester address = 0x30 (diag-reference default)
            "ATCF700",     # CAN filter base = 0x700
            "ATCMF00",     # CAN mask = 0xF00  — together: pass 0x700-0x7FF
        ):
            self._elm_cmd(stream, cmd, 400)
        # Clear header cache and remember the bus we just set up
        self._last_sh = None
        self._last_cra = None
        self._current_can_baud = 500000

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
