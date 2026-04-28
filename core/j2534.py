import ctypes
import ctypes.wintypes
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


def enumerate_devices() -> list[J2534Device]:
    devices = []
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
    seen = set()
    unique = []
    for d in devices:
        if d.dll_path not in seen:
            seen.add(d.dll_path)
            unique.append(d)
    return unique


class J2534:
    def __init__(self, device: J2534Device):
        self.device = device
        self.dll = ctypes.WinDLL(device.dll_path)
        self.device_id: Optional[int] = None
        self._setup_functions()

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
        dev_id = c_ulong()
        ret = self._PassThruOpen(None, byref(dev_id))
        self._check(ret, "PassThruOpen")
        self.device_id = dev_id.value

    def close(self):
        if self.device_id is not None:
            ret = self._PassThruClose(self.device_id)
            self._check(ret, "PassThruClose")
            self.device_id = None

    def read_version(self) -> tuple[str, str, str]:
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
        voltage = c_ulong()
        ret = self._PassThruIoctl(self.device_id, IoctlID.READ_VBATT, None, byref(voltage))
        self._check(ret, "ReadVBatt")
        return voltage.value / 1000.0

    def connect(self, protocol: Protocol, flags: int = 0, baudrate: int = 500000) -> int:
        channel_id = c_ulong()
        ret = self._PassThruConnect(self.device_id, protocol, flags, baudrate, byref(channel_id))
        self._check(ret, f"PassThruConnect({protocol.name}, {baudrate})")
        return channel_id.value

    def disconnect(self, channel_id: int):
        ret = self._PassThruDisconnect(channel_id)
        self._check(ret, "PassThruDisconnect")

    def start_msg_filter(self, channel_id: int, filter_type: FilterType,
                         mask: bytes, pattern: bytes, flow_control: Optional[bytes] = None) -> int:
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
        ret = self._PassThruStopMsgFilter(channel_id, filter_id)
        self._check(ret, "PassThruStopMsgFilter")

    def write_msg(self, channel_id: int, data: bytes, protocol: Protocol = Protocol.ISO15765,
                  tx_flags: int = 0, timeout: int = 1000):
        msg = self._build_msg(protocol, data, tx_flags=tx_flags)
        num = c_ulong(1)
        ret = self._PassThruWriteMsgs(channel_id, byref(msg), byref(num), timeout)
        self._check(ret, "PassThruWriteMsgs")

    def read_msgs(self, channel_id: int, count: int = 1, timeout: int = 1000) -> list[bytes]:
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
        msg = self._build_msg(protocol, data, tx_flags=tx_flags)
        msg_id = c_ulong()
        ret = self._PassThruStartPeriodicMsg(channel_id, byref(msg), byref(msg_id), interval_ms)
        self._check(ret, "PassThruStartPeriodicMsg")
        return msg_id.value

    def stop_periodic_msg(self, channel_id: int, msg_id: int):
        ret = self._PassThruStopPeriodicMsg(channel_id, msg_id)
        self._check(ret, "PassThruStopPeriodicMsg")

    def set_config(self, channel_id: int, params: dict[int, int]):
        configs = (SCONFIG * len(params))()
        for i, (param, value) in enumerate(params.items()):
            configs[i].Parameter = param
            configs[i].Value = value
        config_list = SCONFIG_LIST(NumOfParams=len(params), ConfigPtr=configs)
        ret = self._PassThruIoctl(channel_id, IoctlID.SET_CONFIG, byref(config_list), None)
        self._check(ret, "SetConfig")

    def get_config(self, channel_id: int, params: list[int]) -> dict[int, int]:
        configs = (SCONFIG * len(params))()
        for i, param in enumerate(params):
            configs[i].Parameter = param
        config_list = SCONFIG_LIST(NumOfParams=len(params), ConfigPtr=configs)
        ret = self._PassThruIoctl(channel_id, IoctlID.GET_CONFIG, byref(config_list), None)
        self._check(ret, "GetConfig")
        return {configs[i].Parameter: configs[i].Value for i in range(len(params))}

    def clear_rx_buffer(self, channel_id: int):
        ret = self._PassThruIoctl(channel_id, IoctlID.CLEAR_RX_BUFFER, None, None)
        self._check(ret, "ClearRxBuffer")

    def clear_tx_buffer(self, channel_id: int):
        ret = self._PassThruIoctl(channel_id, IoctlID.CLEAR_TX_BUFFER, None, None)
        self._check(ret, "ClearTxBuffer")

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
