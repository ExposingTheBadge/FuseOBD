import struct
import time
from enum import IntEnum
from typing import Optional
from core.j2534 import J2534, Protocol, FilterType
from core.protocols import NetworkConfig


class UDSService(IntEnum):
    DIAGNOSTIC_SESSION_CONTROL = 0x10
    ECU_RESET = 0x11
    CLEAR_DTC = 0x14
    READ_DTC_INFO = 0x19
    READ_DATA_BY_ID = 0x22
    READ_MEMORY_BY_ADDRESS = 0x23
    SECURITY_ACCESS = 0x27
    COMMUNICATION_CONTROL = 0x28
    WRITE_DATA_BY_ID = 0x2E
    IO_CONTROL = 0x2F
    ROUTINE_CONTROL = 0x31
    REQUEST_DOWNLOAD = 0x34
    TRANSFER_DATA = 0x36
    REQUEST_TRANSFER_EXIT = 0x37
    TESTER_PRESENT = 0x3E


class UDSSession(IntEnum):
    DEFAULT = 0x01
    PROGRAMMING = 0x02
    EXTENDED = 0x03
    FORD_DIAG = 0x85


class DTCSubFunction(IntEnum):
    REPORT_NUMBER_BY_STATUS = 0x01
    REPORT_BY_STATUS = 0x02
    REPORT_SNAPSHOT_ID = 0x03
    REPORT_SNAPSHOT_BY_DTC = 0x04
    REPORT_STORED_DATA = 0x06
    REPORT_PENDING = 0x07
    REPORT_CONFIRMED = 0x0A
    REPORT_SUPPORTED_DTC = 0x0F


class NRC(IntEnum):
    GENERAL_REJECT = 0x10
    SERVICE_NOT_SUPPORTED = 0x11
    SUBFUNCTION_NOT_SUPPORTED = 0x12
    INCORRECT_LENGTH = 0x13
    RESPONSE_TOO_LONG = 0x14
    BUSY_REPEAT = 0x21
    CONDITIONS_NOT_CORRECT = 0x22
    REQUEST_SEQUENCE_ERROR = 0x24
    REQUEST_OUT_OF_RANGE = 0x31
    SECURITY_ACCESS_DENIED = 0x33
    INVALID_KEY = 0x35
    EXCEEDED_ATTEMPTS = 0x36
    TIME_DELAY_NOT_EXPIRED = 0x37
    UPLOAD_DOWNLOAD_NOT_ACCEPTED = 0x70
    TRANSFER_SUSPENDED = 0x71
    GENERAL_PROGRAMMING_FAILURE = 0x72
    RESPONSE_PENDING = 0x78
    SUBFUNCTION_NOT_SUPPORTED_IN_SESSION = 0x7E
    SERVICE_NOT_SUPPORTED_IN_SESSION = 0x7F


class UDSException(Exception):
    def __init__(self, service: int, nrc: int):
        self.service = service
        self.nrc = nrc
        nrc_name = NRC(nrc).name if nrc in NRC._value2member_map_ else f"0x{nrc:02X}"
        svc_name = UDSService(service).name if service in UDSService._value2member_map_ else f"0x{service:02X}"
        super().__init__(f"Negative response to {svc_name}: {nrc_name}")


# Ford / J2534 ISO-TP constants observed in an external Ford-diagnostic
# reverse-engineering reference. The 3001ms upper bound matches the
# MAX_RESPONSE_TIME setting Ford's tool uses — long enough for slow ECU
# operations (BCM config writes, TCM programming sessions) without
# false-timing-out a healthy bus.
DEFAULT_REQUEST_TIMEOUT_MS = 3001
ISO_TP_BLOCK_SIZE_FRAMES   = 200    # max consecutive frames between flow-control


class UDSClient:
    def __init__(self, j2534: J2534, network: NetworkConfig, tx_id: int, rx_id: int):
        self.j2534 = j2534
        self.network = network
        self.tx_id = tx_id
        self.rx_id = rx_id
        self.channel_id: Optional[int] = None
        self.filter_id: Optional[int] = None
        self.tester_present_id: Optional[int] = None
        self.timeout = DEFAULT_REQUEST_TIMEOUT_MS

    def connect(self):
        self.channel_id = self.j2534.connect(
            self.network.protocol, self.network.flags, self.network.baudrate
        )
        if self.network.can_id_bits == 11:
            mask = struct.pack(">I", 0x7FF)
            pattern = struct.pack(">I", self.rx_id)
            fc = struct.pack(">I", self.tx_id)
        else:
            mask = struct.pack(">I", 0x1FFFFFFF)
            pattern = struct.pack(">I", self.rx_id)
            fc = struct.pack(">I", self.tx_id)
        self.filter_id = self.j2534.start_msg_filter(
            self.channel_id, FilterType.FLOW_CONTROL, mask, pattern, fc
        )

    def disconnect(self):
        if self.tester_present_id is not None:
            try:
                self.j2534.stop_periodic_msg(self.channel_id, self.tester_present_id)
            except Exception:
                pass
            self.tester_present_id = None
        if self.filter_id is not None:
            try:
                self.j2534.stop_msg_filter(self.channel_id, self.filter_id)
            except Exception:
                pass
            self.filter_id = None
        if self.channel_id is not None:
            try:
                self.j2534.disconnect(self.channel_id)
            except Exception:
                pass
            self.channel_id = None

    def send_raw(self, data: bytes):
        id_bytes = struct.pack(">I", self.tx_id)
        self.j2534.write_msg(self.channel_id, id_bytes + data, self.network.protocol, timeout=self.timeout)

    def receive_raw(self, timeout: Optional[int] = None) -> Optional[bytes]:
        t = timeout or self.timeout
        deadline = time.time() + t / 1000.0
        while time.time() < deadline:
            remaining = max(50, int((deadline - time.time()) * 1000))
            msgs = self.j2534.read_msgs(self.channel_id, count=1, timeout=remaining)
            for msg in msgs:
                if len(msg) < 4:
                    continue
                msg_id = struct.unpack(">I", msg[:4])[0]
                if msg_id == self.rx_id:
                    return msg[4:]
        return None

    def request(self, service: int, data: bytes = b"", timeout: Optional[int] = None) -> bytes:
        self.send_raw(bytes([service]) + data)
        while True:
            resp = self.receive_raw(timeout)
            if resp is None:
                raise TimeoutError(f"No response to service 0x{service:02X}")
            if len(resp) == 0:
                continue
            if resp[0] == 0x7F and len(resp) >= 3:
                if resp[2] == NRC.RESPONSE_PENDING:
                    continue
                raise UDSException(resp[1], resp[2])
            if resp[0] == service + 0x40:
                return resp[1:]
        raise TimeoutError(f"No valid response to service 0x{service:02X}")

    def diagnostic_session(self, session: int = UDSSession.EXTENDED):
        self.request(UDSService.DIAGNOSTIC_SESSION_CONTROL, bytes([session]))

    def tester_present(self):
        self.request(UDSService.TESTER_PRESENT, b"\x00")

    def start_tester_present(self, interval_ms: int = 2000):
        id_bytes = struct.pack(">I", self.tx_id)
        tp_data = id_bytes + bytes([UDSService.TESTER_PRESENT, 0x00])
        self.tester_present_id = self.j2534.start_periodic_msg(
            self.channel_id, tp_data, self.network.protocol, interval_ms
        )

    def ecu_reset(self, reset_type: int = 0x01):
        self.request(UDSService.ECU_RESET, bytes([reset_type]))

    def read_data_by_id(self, did: int) -> bytes:
        resp = self.request(UDSService.READ_DATA_BY_ID, struct.pack(">H", did))
        return resp[2:]

    def write_data_by_id(self, did: int, data: bytes):
        self.request(UDSService.WRITE_DATA_BY_ID, struct.pack(">H", did) + data)

    def security_access_seed(self, level: int = 0x01) -> bytes:
        resp = self.request(UDSService.SECURITY_ACCESS, bytes([level]))
        return resp[1:]

    def security_access_key(self, level: int = 0x02, key: bytes = b"") -> bytes:
        resp = self.request(UDSService.SECURITY_ACCESS, bytes([level]) + key)
        return resp[1:]

    def clear_dtc(self, group: int = 0xFFFFFF):
        self.request(UDSService.CLEAR_DTC, struct.pack(">I", group)[1:])

    def read_dtc(self, sub_function: int = DTCSubFunction.REPORT_BY_STATUS,
                 status_mask: int = 0xFF) -> bytes:
        return self.request(UDSService.READ_DTC_INFO, bytes([sub_function, status_mask]))

    def routine_control(self, routine_id: int, control_type: int = 0x01,
                        data: bytes = b"") -> bytes:
        return self.request(
            UDSService.ROUTINE_CONTROL,
            bytes([control_type]) + struct.pack(">H", routine_id) + data,
        )

    def io_control(self, did: int, control_param: int, data: bytes = b"") -> bytes:
        return self.request(
            UDSService.IO_CONTROL,
            struct.pack(">H", did) + bytes([control_param]) + data,
        )

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
