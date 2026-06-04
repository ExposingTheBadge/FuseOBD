"""Annotation helper for the bus monitor — turns raw TX/RX byte lines into
human-readable explanations.

Log lines from `modules.issues_log.log_tx` / `log_rx` look like:
    "PCM  6B  22 F1 90 ..."
    "ELM  3B  41 54 53 50 36 0D"   # "ATSP6\r"

The functions here parse the byte block out of the message and produce a
one-line annotation describing the UDS service + DID, OBD-II mode + PID,
or ELM327 AT command being sent. The bus monitor panel renders the
annotation as a dimmer trailing line under the raw bytes.
"""
from __future__ import annotations

import re

from core.ford_dids import FORD_DID_REGISTRY
from core.protocols import FORD_MODULES, FordNetwork


# ── UDS service ID table (ISO 14229-1 §10) ──

_UDS_SERVICES = {
    0x10: "DiagnosticSessionControl",
    0x11: "ECUReset",
    0x14: "ClearDiagnosticInformation",
    0x19: "ReadDTCInformation",
    0x22: "ReadDataByIdentifier",
    0x23: "ReadMemoryByAddress",
    0x24: "ReadScalingDataByIdentifier",
    0x27: "SecurityAccess",
    0x28: "CommunicationControl",
    0x2A: "ReadDataByPeriodicIdentifier",
    0x2C: "DynamicallyDefineDataIdentifier",
    0x2E: "WriteDataByIdentifier",
    0x2F: "InputOutputControlByIdentifier",
    0x31: "RoutineControl",
    0x34: "RequestDownload",
    0x35: "RequestUpload",
    0x36: "TransferData",
    0x37: "RequestTransferExit",
    0x38: "RequestFileTransfer",
    0x3D: "WriteMemoryByAddress",
    0x3E: "TesterPresent",
    0x83: "AccessTimingParameter",
    0x84: "SecuredDataTransmission",
    0x85: "ControlDTCSetting",
    0x86: "ResponseOnEvent",
    0x87: "LinkControl",
}

# Negative Response Codes — ISO 14229-1 Annex A
_UDS_NRCS = {
    0x10: "General reject",
    0x11: "Service not supported",
    0x12: "Subfunction not supported",
    0x13: "Incorrect message length / invalid format",
    0x14: "Response too long",
    0x21: "Busy - repeat request",
    0x22: "Conditions not correct",
    0x24: "Request sequence error",
    0x25: "No response from subnet",
    0x26: "Failure prevents execution of requested action",
    0x31: "Request out of range",
    0x33: "Security access denied",
    0x35: "Invalid key",
    0x36: "Exceeded number of attempts",
    0x37: "Required time delay not expired",
    0x70: "Upload/download not accepted",
    0x71: "Transfer data suspended",
    0x72: "General programming failure",
    0x73: "Wrong block sequence counter",
    0x78: "Request received - response pending",
    0x7E: "Subfunction not supported in active session",
    0x7F: "Service not supported in active session",
}

_UDS_SESSIONS = {
    0x01: "DefaultSession",
    0x02: "ProgrammingSession",
    0x03: "ExtendedDiagnosticSession",
    0x04: "SafetySystemDiagnosticSession",
    0x60: "FordExtendedDiagnostic",
}

_UDS_RESET_TYPES = {
    0x01: "hardReset",
    0x02: "keyOffOnReset",
    0x03: "softReset",
    0x04: "enableRapidPowerShutDown",
    0x05: "disableRapidPowerShutDown",
}

# OBD-II Mode $01 PID names — abbreviated subset. Full list lives in modules.pid.
_OBD_MODE01_PIDS = {
    0x00: "PIDs supported [01-20]",
    0x01: "Monitor status since DTC cleared",
    0x03: "Fuel system status",
    0x04: "Calculated engine load",
    0x05: "Engine coolant temperature",
    0x06: "Short-term fuel trim - Bank 1",
    0x07: "Long-term fuel trim - Bank 1",
    0x0B: "Intake manifold absolute pressure",
    0x0C: "Engine RPM",
    0x0D: "Vehicle speed",
    0x0E: "Ignition timing advance",
    0x0F: "Intake air temperature",
    0x10: "MAF air flow rate",
    0x11: "Throttle position",
    0x14: "O2 sensor B1S1",
    0x15: "O2 sensor B1S2",
    0x1C: "OBD standards compliance",
    0x1F: "Run time since engine start",
    0x21: "Distance with MIL on",
    0x2F: "Fuel level input",
    0x33: "Barometric pressure",
    0x3C: "Catalyst temperature B1S1",
    0x46: "Ambient air temperature",
    0x49: "Accelerator pedal position D",
    0x4A: "Accelerator pedal position E",
    0x5C: "Engine oil temperature",
    0xA6: "Odometer",
}

_OBD_MODES = {
    0x01: "Mode $01 - Current data",
    0x02: "Mode $02 - Freeze frame",
    0x03: "Mode $03 - Stored DTCs",
    0x04: "Mode $04 - Clear DTCs",
    0x05: "Mode $05 - O2 sensor monitoring (non-CAN)",
    0x06: "Mode $06 - Test results",
    0x07: "Mode $07 - Pending DTCs",
    0x08: "Mode $08 - Bidirectional control",
    0x09: "Mode $09 - Vehicle information",
    0x0A: "Mode $0A - Permanent DTCs",
}

_MODE09_PIDS = {
    0x00: "PIDs supported",
    0x02: "VIN",
    0x04: "Calibration ID",
    0x06: "CVN",
    0x0A: "ECU name",
    0x0B: "In-use performance tracking",
}

# Map known Ford module addresses (lower byte of 0x7XX) to abbreviations
# so a target like "0x7E0" can be tagged "PCM".
_MODULE_BY_ADDR: dict[int, str] = {}
for _m in FORD_MODULES:
    _MODULE_BY_ADDR.setdefault(0x700 + _m.address, _m.abbreviation)
    # Many Ford diag IDs are stored as just the lower byte (e.g. "E0" not "7E0").
    _MODULE_BY_ADDR.setdefault(_m.address, _m.abbreviation)


_HEX_BYTE_RE = re.compile(r"\b([0-9A-Fa-f]{2})\b")


def _bytes_from_line(message: str) -> bytes:
    """Pull the hex byte block out of a log message.

    The log line shape is "<target>  <length>B  XX XX XX ...  |ASCII|" — we
    isolate the run of 2-hex-char tokens and decode them. The leading length
    prefix `NB` also matches the regex but we skip it because it always has
    a trailing 'B' in the source line; the regex above doesn't anchor so we
    have to strip the length manually.
    """
    # Drop the trailing "|...|" ASCII section if present.
    if "|" in message:
        message = message.split("|", 1)[0]
    # Drop the length prefix like "12B " (digits followed by capital B).
    message = re.sub(r"\b\d+B\b", "", message)
    tokens = _HEX_BYTE_RE.findall(message)
    if not tokens:
        return b""
    try:
        return bytes(int(t, 16) for t in tokens)
    except ValueError:
        return b""


def _module_label_for_target(target: str) -> str:
    """Map a string target like 'PCM' / '0x7E0' / 'E0' to a module label."""
    t = target.strip().upper().lstrip("0X")
    try:
        addr = int(t, 16)
    except ValueError:
        return target  # already a name like "PCM" or "ELM"
    name = _MODULE_BY_ADDR.get(addr) or _MODULE_BY_ADDR.get(addr & 0xFF)
    if name:
        return f"{target} ({name})"
    return target


def decode_at_command(payload: bytes) -> str:
    """ELM327 AT command — turn `41 54 53 50 36 0D` into 'ATSP6'."""
    try:
        text = payload.decode("ascii", errors="replace").rstrip("\r\n").strip()
    except Exception:
        return ""
    if not text.upper().startswith("AT"):
        return ""
    return f"ELM327 command: {text}"


def decode_uds(payload: bytes) -> str:
    """Decode a UDS service request or response — first byte is the SID."""
    if not payload:
        return ""
    sid = payload[0]

    # Negative response: 7F <SID> <NRC>
    if sid == 0x7F and len(payload) >= 3:
        svc = _UDS_SERVICES.get(payload[1], f"service ${payload[1]:02X}")
        nrc = _UDS_NRCS.get(payload[2], f"NRC ${payload[2]:02X}")
        return f"UDS Negative Response: {svc} → {nrc}"

    # Positive response: SID | 0x40, e.g. 0x62 = response to 0x22
    if sid & 0x40:
        req_sid = sid & 0xBF
        svc = _UDS_SERVICES.get(req_sid)
        if svc == "ReadDataByIdentifier" and len(payload) >= 3:
            did = (payload[1] << 8) | payload[2]
            data = payload[3:]
            return _format_rdbi_response(did, data)
        if svc == "DiagnosticSessionControl" and len(payload) >= 2:
            return f"UDS+: enter {_UDS_SESSIONS.get(payload[1], f'session ${payload[1]:02X}')}"
        if svc == "SecurityAccess" and len(payload) >= 2:
            sub = payload[1]
            level = (sub + 1) // 2
            if sub & 0x01:
                return f"UDS+: SecurityAccess seed (level {level}) — {len(payload)-2} byte seed"
            return f"UDS+: SecurityAccess key accepted (level {level})"
        if svc:
            return f"UDS+: {svc} ({len(payload)-1}B payload)"
        return f"UDS+: service ${req_sid:02X}"

    # Request frame
    svc = _UDS_SERVICES.get(sid)
    if svc == "DiagnosticSessionControl" and len(payload) >= 2:
        return f"UDS: DiagSessionControl → {_UDS_SESSIONS.get(payload[1], f'session ${payload[1]:02X}')}"
    if svc == "ECUReset" and len(payload) >= 2:
        return f"UDS: ECUReset → {_UDS_RESET_TYPES.get(payload[1], f'subfunc ${payload[1]:02X}')}"
    if svc == "ReadDataByIdentifier" and len(payload) >= 3:
        did = (payload[1] << 8) | payload[2]
        return _format_rdbi_request(did)
    if svc == "WriteDataByIdentifier" and len(payload) >= 3:
        did = (payload[1] << 8) | payload[2]
        name = _did_name(did)
        return f"UDS: WriteDataByIdentifier DID 0x{did:04X} ({name}, {len(payload)-3}B data)"
    if svc == "SecurityAccess" and len(payload) >= 2:
        sub = payload[1]
        return f"UDS: SecurityAccess subfunc 0x{sub:02X} ({'requestSeed' if sub & 1 else 'sendKey'} L{(sub+1)//2})"
    if svc == "RoutineControl" and len(payload) >= 4:
        sub_map = {0x01: "startRoutine", 0x02: "stopRoutine", 0x03: "requestResults"}
        sub = sub_map.get(payload[1], f"subfunc ${payload[1]:02X}")
        rid = (payload[2] << 8) | payload[3]
        return f"UDS: RoutineControl {sub} RID 0x{rid:04X}"
    if svc == "TesterPresent":
        return "UDS: TesterPresent (keep-alive)"
    if svc == "ReadDTCInformation" and len(payload) >= 2:
        sub_map = {0x01: "reportNumberOfDTCByStatusMask", 0x02: "reportDTCByStatusMask",
                   0x04: "reportDTCSnapshot", 0x06: "reportDTCExtData"}
        return f"UDS: ReadDTCInformation {sub_map.get(payload[1], f'subfunc ${payload[1]:02X}')}"
    if svc == "ClearDiagnosticInformation":
        return "UDS: ClearDiagnosticInformation"
    if svc == "ControlDTCSetting" and len(payload) >= 2:
        return f"UDS: ControlDTCSetting → {'on' if payload[1] == 1 else 'off' if payload[1] == 2 else hex(payload[1])}"
    if svc:
        return f"UDS: {svc}"
    return ""


def _format_rdbi_request(did: int) -> str:
    name = _did_name(did)
    return f"UDS: ReadDataByIdentifier DID 0x{did:04X}" + (f" ({name})" if name else "")


def _format_rdbi_response(did: int, data: bytes) -> str:
    entry = FORD_DID_REGISTRY.get(did)
    if entry and entry.decoder is not None:
        try:
            decoded = entry.decode(data)
            return f"UDS+: RDBI 0x{did:04X} ({entry.name}) = {decoded}"
        except Exception:
            pass
    if entry:
        return f"UDS+: RDBI 0x{did:04X} ({entry.name}) = {data.hex().upper()}"
    return f"UDS+: RDBI 0x{did:04X} = {data.hex().upper()}"


def _did_name(did: int) -> str:
    entry = FORD_DID_REGISTRY.get(did)
    return entry.name if entry else ""


def decode_obd2(payload: bytes) -> str:
    """OBD-II Mode + PID — payload[0] is the mode (or 0x40+mode for response)."""
    if not payload:
        return ""
    b0 = payload[0]
    if b0 & 0x40:
        mode = b0 & 0xBF
        mode_label = _OBD_MODES.get(mode, f"Mode ${mode:02X}")
        if mode == 0x01 and len(payload) >= 2:
            return f"OBD+: {mode_label}, PID 0x{payload[1]:02X} ({_OBD_MODE01_PIDS.get(payload[1], '?')}) = {payload[2:].hex().upper()}"
        if mode == 0x09 and len(payload) >= 2:
            return f"OBD+: {mode_label}, PID 0x{payload[1]:02X} ({_MODE09_PIDS.get(payload[1], '?')})"
        return f"OBD+: {mode_label}"
    if b0 in _OBD_MODES:
        if b0 == 0x01 and len(payload) >= 2:
            return f"OBD: {_OBD_MODES[b0]}, PID 0x{payload[1]:02X} ({_OBD_MODE01_PIDS.get(payload[1], '?')})"
        if b0 == 0x09 and len(payload) >= 2:
            return f"OBD: {_OBD_MODES[b0]}, PID 0x{payload[1]:02X} ({_MODE09_PIDS.get(payload[1], '?')})"
        return f"OBD: {_OBD_MODES[b0]}"
    return ""


def annotate_tx_rx(tag: str, message: str) -> str:
    """Top-level entry — returns a one-line annotation or '' if nothing to say.

    `tag` is "TX" / "RX" / "PROT" / etc. `message` is the full log message
    including target, length prefix, hex bytes, and ASCII section.
    """
    if tag not in ("TX", "RX", "PROT"):
        return ""
    payload = _bytes_from_line(message)
    if not payload:
        return ""

    # Extract the target token (everything before the first run of two spaces).
    target = ""
    head = message.split("  ", 1)[0].strip()
    if head:
        target = head
    target_label = _module_label_for_target(target) if target else ""

    # ELM AT commands look like ASCII starting with 'AT'.
    if 0x41 <= payload[0] <= 0x5A and payload[0:2] == b"AT":
        ann = decode_at_command(payload)
        if ann:
            return ann

    # OBD-II flat frame: first byte is the mode (or 0x40+mode for response).
    if payload[0] in _OBD_MODES or (payload[0] & 0x40 and (payload[0] & 0xBF) in _OBD_MODES):
        ann = decode_obd2(payload)
        if ann:
            return f"{ann}  [{target_label}]" if target_label else ann

    # Default — try UDS.
    ann = decode_uds(payload)
    if ann:
        return f"{ann}  [{target_label}]" if target_label else ann
    return ""
