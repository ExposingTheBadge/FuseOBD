import struct
from dataclasses import dataclass, field
from core.uds import UDSClient, UDSSession, DTCSubFunction, UDSException


DTC_TYPE_PREFIXES = {0: "P", 1: "C", 2: "B", 3: "U"}


@dataclass
class DTC:
    code: str
    status: int
    raw_bytes: bytes = b""

    @property
    def is_confirmed(self) -> bool:
        return bool(self.status & 0x08)

    @property
    def is_pending(self) -> bool:
        return bool(self.status & 0x04)

    @property
    def is_active(self) -> bool:
        return bool(self.status & 0x01)

    @property
    def status_text(self) -> str:
        flags = []
        if self.is_active:
            flags.append("Active")
        if self.is_confirmed:
            flags.append("Confirmed")
        if self.is_pending:
            flags.append("Pending")
        if self.status & 0x40:
            flags.append("Not tested since clear")
        if self.status & 0x20:
            flags.append("Not tested this cycle")
        return ", ".join(flags) if flags else "Stored"


@dataclass
class ModuleDTCs:
    module_name: str
    module_abbrev: str
    dtcs: list[DTC] = field(default_factory=list)
    error: str = ""

    @property
    def count(self) -> int:
        return len(self.dtcs)


def decode_dtc_bytes(raw: bytes) -> str:
    if len(raw) < 3:
        return ""
    byte1 = raw[0]
    byte2 = raw[1]
    prefix = DTC_TYPE_PREFIXES.get((byte1 >> 6) & 0x03, "P")
    digit1 = (byte1 >> 4) & 0x03
    digit2 = byte1 & 0x0F
    digit3 = (byte2 >> 4) & 0x0F
    digit4 = byte2 & 0x0F
    return f"{prefix}{digit1}{digit2:X}{digit3:X}{digit4:X}"


class DTCReader:
    def __init__(self, uds: UDSClient):
        self.uds = uds

    def read_dtcs(self, status_mask: int = 0xFF) -> list[DTC]:
        try:
            self.uds.diagnostic_session(UDSSession.EXTENDED)
        except (UDSException, TimeoutError):
            pass

        resp = self.uds.read_dtc(DTCSubFunction.REPORT_BY_STATUS, status_mask)
        if len(resp) < 2:
            return []

        dtcs = []
        data = resp[1:]
        for i in range(0, len(data) - 2, 4):
            dtc_bytes = data[i : i + 3]
            status = data[i + 3] if i + 3 < len(data) else 0
            code = decode_dtc_bytes(dtc_bytes)
            if code:
                dtcs.append(DTC(code=code, status=status, raw_bytes=dtc_bytes))
        return dtcs

    def clear_dtcs(self, group: int = 0xFFFFFF):
        try:
            self.uds.diagnostic_session(UDSSession.EXTENDED)
        except (UDSException, TimeoutError):
            pass
        self.uds.clear_dtc(group)

    def read_dtc_count(self) -> int:
        resp = self.uds.read_dtc(DTCSubFunction.REPORT_NUMBER_BY_STATUS, 0xFF)
        if len(resp) >= 3:
            return (resp[1] << 8) | resp[2]
        return 0
