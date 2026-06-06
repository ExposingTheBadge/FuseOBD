"""ISO 14229 UDS service catalog.

Single source of truth for service IDs, their human names, the typical
sub-functions used by Ford modules, and the negative-response codes
ECUs return when something goes wrong. Importing modules pull from
here instead of redefining magic constants per file.

Numbers are from ISO 14229-1:2020 + Ford's deviations / extensions
observed in the field (FEPS, AsBuilt routines, PATS handlers, etc).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Service IDs ──────────────────────────────────────────────────────

class SID:
    """UDS request service IDs (positive response = SID | 0x40)."""
    DIAGNOSTIC_SESSION_CONTROL          = 0x10
    ECU_RESET                           = 0x11
    SECURITY_ACCESS                     = 0x27
    COMMUNICATION_CONTROL               = 0x28
    AUTHENTICATION                      = 0x29     # ISO 14229-1:2020 (replaces 0x27 long term)
    TESTER_PRESENT                      = 0x3E
    ACCESS_TIMING_PARAMETER             = 0x83
    SECURED_DATA_TRANSMISSION           = 0x84
    CONTROL_DTC_SETTING                 = 0x85
    RESPONSE_ON_EVENT                   = 0x86
    LINK_CONTROL                        = 0x87

    READ_DATA_BY_IDENTIFIER             = 0x22
    READ_MEMORY_BY_ADDRESS              = 0x23
    READ_SCALING_DATA_BY_IDENTIFIER     = 0x24
    READ_DATA_BY_PERIODIC_IDENTIFIER    = 0x2A
    DYNAMICALLY_DEFINE_DATA_IDENTIFIER  = 0x2C
    WRITE_DATA_BY_IDENTIFIER            = 0x2E
    WRITE_MEMORY_BY_ADDRESS             = 0x3D

    CLEAR_DIAGNOSTIC_INFORMATION        = 0x14
    READ_DTC_INFORMATION                = 0x19

    INPUT_OUTPUT_CONTROL_BY_IDENTIFIER  = 0x2F
    ROUTINE_CONTROL                     = 0x31

    REQUEST_DOWNLOAD                    = 0x34
    REQUEST_UPLOAD                      = 0x35
    TRANSFER_DATA                       = 0x36
    REQUEST_TRANSFER_EXIT               = 0x37
    REQUEST_FILE_TRANSFER               = 0x38

    NEGATIVE_RESPONSE                   = 0x7F

    # ── KWP2000 / ISO 14230 legacy services that some older Ford
    # modules (and most FCA pre-2014 modules) still implement.
    # Mined from alfa-analysis indexes 2026-06-06 — the AlfaOBD binary
    # services these on pre-UDS K-line buses, and Ford uses overlapping
    # subsets on 1996-2008 ISO9141/KWP modules.
    KWP_START_DIAGNOSTIC_SESSION        = 0x10  # same as UDS, but with KWP sub-functions
    KWP_STOP_DIAGNOSTIC_SESSION         = 0x20
    KWP_ECU_RESET                       = 0x11
    KWP_READ_FREEZE_FRAME_DATA          = 0x12
    KWP_READ_DTC_BY_STATUS              = 0x18
    KWP_READ_ECU_IDENTIFICATION         = 0x1A   # KWP-only; UDS uses 0x22 with F1xx DID
    KWP_READ_DATA_BY_COMMON_ID          = 0x1A
    KWP_READ_DATA_BY_LOCAL_ID           = 0x21   # KWP-only
    KWP_READ_DATA_BY_IDENTIFIER         = 0x22   # same as UDS
    KWP_READ_MEMORY_BY_ADDRESS          = 0x23   # same as UDS
    KWP_STOP_COMMUNICATION              = 0x82
    KWP_START_COMMUNICATION             = 0x81
    KWP_DYNAMICALLY_DEFINE_LOCAL_ID     = 0x2C
    KWP_WRITE_DATA_BY_LOCAL_ID          = 0x3B
    KWP_INPUT_OUTPUT_CONTROL_BY_LOCAL_ID = 0x30
    KWP_START_ROUTINE_BY_LOCAL_ID       = 0x31   # routine by local ID, not DID
    KWP_STOP_ROUTINE_BY_LOCAL_ID        = 0x32
    KWP_REQUEST_ROUTINE_RESULTS_BY_LOCAL_ID = 0x33
    KWP_REQUEST_DOWNLOAD                = 0x34
    KWP_REQUEST_UPLOAD                  = 0x35
    KWP_TRANSFER_DATA                   = 0x36
    KWP_REQUEST_TRANSFER_EXIT           = 0x37
    KWP_WRITE_DATA_BY_COMMON_ID         = 0x2E
    KWP_TESTER_PRESENT                  = 0x3E


# ── Sub-functions ────────────────────────────────────────────────────

class Session:
    """DiagnosticSessionControl (0x10) sub-functions."""
    DEFAULT             = 0x01
    PROGRAMMING         = 0x02
    EXTENDED            = 0x03    # most diagnostic ops live here
    SAFETY_SYSTEM       = 0x04


class ResetType:
    """ECUReset (0x11) sub-functions."""
    HARD                = 0x01
    KEY_OFF_ON          = 0x02
    SOFT                = 0x03
    ENABLE_RAPID_POWER  = 0x04
    DISABLE_RAPID_POWER = 0x05


class DtcSub:
    """ReadDTCInformation (0x19) sub-functions — pick which DTC view we want."""
    REPORT_NUMBER_OF_DTC_BY_STATUS_MASK             = 0x01
    REPORT_DTC_BY_STATUS_MASK                       = 0x02
    REPORT_DTC_SNAPSHOT_IDENTIFICATION              = 0x03
    REPORT_DTC_SNAPSHOT_RECORD_BY_DTC_NUMBER        = 0x04
    REPORT_DTC_STORED_DATA_BY_RECORD_NUMBER         = 0x05
    REPORT_DTC_EXT_DATA_RECORD_BY_DTC_NUMBER        = 0x06
    REPORT_NUMBER_OF_DTC_BY_SEVERITY_MASK_RECORD    = 0x07
    REPORT_DTC_BY_SEVERITY_MASK_RECORD              = 0x08
    REPORT_SEVERITY_INFORMATION_OF_DTC              = 0x09
    REPORT_SUPPORTED_DTC                            = 0x0A
    REPORT_FIRST_TEST_FAILED_DTC                    = 0x0B
    REPORT_FIRST_CONFIRMED_DTC                      = 0x0C
    REPORT_MOST_RECENT_TEST_FAILED_DTC              = 0x0D
    REPORT_MOST_RECENT_CONFIRMED_DTC                = 0x0E
    REPORT_MIRROR_MEMORY_DTC_BY_STATUS_MASK         = 0x0F
    REPORT_MIRROR_MEMORY_DTC_EXT_DATA               = 0x10
    REPORT_NUMBER_OF_MIRROR_MEMORY_DTC_BY_STATUS    = 0x11
    REPORT_NUMBER_OF_EMISSIONS_OBD_DTC_BY_STATUS    = 0x12
    REPORT_EMISSIONS_OBD_DTC_BY_STATUS              = 0x13
    REPORT_DTC_FAULT_DETECTION_COUNTER              = 0x14
    REPORT_DTC_WITH_PERMANENT_STATUS                = 0x15
    REPORT_DTC_EXT_DATA_BY_RECORD_NUMBER            = 0x16
    REPORT_USER_DEF_MEMORY_DTC_BY_STATUS_MASK       = 0x17
    REPORT_USER_DEF_MEMORY_DTC_SNAPSHOT             = 0x18
    REPORT_USER_DEF_MEMORY_DTC_EXT_DATA             = 0x19
    REPORT_WWHOBD_DTC_BY_MASK_RECORD                = 0x42
    REPORT_WWHOBD_DTC_WITH_PERMANENT_STATUS         = 0x55


class DtcStatusMask:
    """ReadDTCInformation status mask byte. OR these together; the ECU
    returns DTCs whose status byte AND mask is non-zero."""
    TEST_FAILED                              = 0x01
    TEST_FAILED_THIS_OPERATION_CYCLE         = 0x02
    PENDING_DTC                              = 0x04
    CONFIRMED_DTC                            = 0x08
    TEST_NOT_COMPLETED_SINCE_LAST_CLEAR      = 0x10
    TEST_FAILED_SINCE_LAST_CLEAR             = 0x20
    TEST_NOT_COMPLETED_THIS_OPERATION_CYCLE  = 0x40
    WARNING_INDICATOR_REQUESTED              = 0x80
    ALL                                      = 0xFF


class RoutineCtl:
    """RoutineControl (0x31) sub-functions."""
    START_ROUTINE   = 0x01
    STOP_ROUTINE    = 0x02
    REQUEST_RESULTS = 0x03


class IOCtl:
    """InputOutputControlByIdentifier (0x2F) sub-functions."""
    RETURN_CONTROL_TO_ECU = 0x00
    RESET_TO_DEFAULT       = 0x01
    FREEZE_CURRENT_STATE   = 0x02
    SHORT_TERM_ADJUSTMENT  = 0x03


class CommCtl:
    """CommunicationControl (0x28) sub-functions."""
    ENABLE_RX_AND_TX                        = 0x00
    ENABLE_RX_DISABLE_TX                    = 0x01
    DISABLE_RX_ENABLE_TX                    = 0x02
    DISABLE_RX_AND_TX                       = 0x03
    ENABLE_RX_DISABLE_TX_WITH_ENHANCED      = 0x04
    ENABLE_RX_AND_TX_WITH_ENHANCED          = 0x05


class CommType:
    """CommunicationControl communicationType bitmap."""
    NORMAL_COMMUNICATION_MESSAGES           = 0x01
    NETWORK_MANAGEMENT_MESSAGES             = 0x02
    BOTH                                    = 0x03


class LinkCtl:
    """LinkControl (0x87) sub-functions."""
    VERIFY_BAUD_RATE_TRANSITION_FIXED       = 0x01
    VERIFY_BAUD_RATE_TRANSITION_SPECIFIC    = 0x02
    TRANSITION_BAUD_RATE                    = 0x03


# ── Negative response codes ──────────────────────────────────────────

class NRC:
    """ISO 14229 negative response codes (sub-byte of 0x7F response)."""
    GENERAL_REJECT                                  = 0x10
    SERVICE_NOT_SUPPORTED                           = 0x11
    SUB_FUNCTION_NOT_SUPPORTED                      = 0x12
    INCORRECT_MESSAGE_LENGTH_OR_INVALID_FORMAT      = 0x13
    RESPONSE_TOO_LONG                               = 0x14
    BUSY_REPEAT_REQUEST                             = 0x21
    CONDITIONS_NOT_CORRECT                          = 0x22
    REQUEST_SEQUENCE_ERROR                          = 0x24
    NO_RESPONSE_FROM_SUBNET_COMPONENT               = 0x25
    FAILURE_PREVENTS_EXECUTION                      = 0x26
    REQUEST_OUT_OF_RANGE                            = 0x31
    SECURITY_ACCESS_DENIED                          = 0x33
    AUTHENTICATION_REQUIRED                         = 0x34
    INVALID_KEY                                     = 0x35
    EXCEEDED_NUMBER_OF_ATTEMPTS                     = 0x36
    REQUIRED_TIME_DELAY_NOT_EXPIRED                 = 0x37
    SECURE_DATA_TRANSMISSION_REQUIRED               = 0x38
    SECURE_DATA_TRANSMISSION_NOT_ALLOWED            = 0x39
    SECURE_DATA_VERIFICATION_FAILED                 = 0x3A
    CERTIFICATE_VERIFICATION_FAILED_INVALID_TIME    = 0x50
    CERTIFICATE_VERIFICATION_FAILED_INVALID_FORMAT  = 0x51
    CERTIFICATE_VERIFICATION_FAILED_INVALID_CONTENT = 0x52
    CERTIFICATE_VERIFICATION_FAILED_INVALID_SIGNATURE = 0x53
    CERTIFICATE_VERIFICATION_FAILED_INVALID_CHAIN_OF_TRUST = 0x54
    CERTIFICATE_VERIFICATION_FAILED_INVALID_TYPE    = 0x55
    UPLOAD_DOWNLOAD_NOT_ACCEPTED                    = 0x70
    TRANSFER_DATA_SUSPENDED                         = 0x71
    GENERAL_PROGRAMMING_FAILURE                     = 0x72
    WRONG_BLOCK_SEQUENCE_COUNTER                    = 0x73
    REQUEST_CORRECTLY_RECEIVED_RESPONSE_PENDING     = 0x78
    SUB_FUNCTION_NOT_SUPPORTED_IN_ACTIVE_SESSION    = 0x7E
    SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION         = 0x7F
    RPM_TOO_HIGH                                    = 0x81
    RPM_TOO_LOW                                     = 0x82
    ENGINE_IS_RUNNING                               = 0x83
    ENGINE_IS_NOT_RUNNING                           = 0x84
    ENGINE_RUN_TIME_TOO_LOW                         = 0x85
    TEMPERATURE_TOO_HIGH                            = 0x86
    TEMPERATURE_TOO_LOW                             = 0x87
    VEHICLE_SPEED_TOO_HIGH                          = 0x88
    VEHICLE_SPEED_TOO_LOW                           = 0x89
    THROTTLE_PEDAL_TOO_HIGH                         = 0x8A
    THROTTLE_PEDAL_TOO_LOW                          = 0x8B
    TRANSMISSION_RANGE_NOT_IN_NEUTRAL               = 0x8C
    TRANSMISSION_RANGE_NOT_IN_GEAR                  = 0x8D
    BRAKE_SWITCHES_NOT_CLOSED                       = 0x8F
    SHIFTER_LEVER_NOT_IN_PARK                       = 0x90
    TORQUE_CONVERTER_CLUTCH_LOCKED                  = 0x91
    VOLTAGE_TOO_HIGH                                = 0x92
    VOLTAGE_TOO_LOW                                 = 0x93


_NRC_NAMES: dict[int, str] = {
    v: k.replace("_", " ").lower()
    for k, v in vars(NRC).items() if not k.startswith("_") and isinstance(v, int)
}

_SID_NAMES: dict[int, str] = {
    v: k.replace("_", " ").lower()
    for k, v in vars(SID).items() if not k.startswith("_") and isinstance(v, int)
}


def nrc_name(code: int) -> str:
    """Return a human-readable name for a negative-response code, or
    the hex string when unknown. Used in error messages so the user
    doesn't see '$7F $22 $35' but 'INVALID_KEY'."""
    return _NRC_NAMES.get(code, f"unknown NRC 0x{code:02X}")


def sid_name(sid: int) -> str:
    """Return a human-readable name for a service ID."""
    return _SID_NAMES.get(sid, f"unknown service 0x{sid:02X}")


# ── Common request builders ──────────────────────────────────────────
#
# These build the raw UDS payload byte sequence. Callers prepend the
# protocol-specific transport framing (CAN header, ISO-TP single/multi-
# frame, etc) — see modules/uds.py for that.

def diagnostic_session_control(session: int = Session.EXTENDED) -> bytes:
    return bytes([SID.DIAGNOSTIC_SESSION_CONTROL, session])

def ecu_reset(kind: int = ResetType.HARD) -> bytes:
    return bytes([SID.ECU_RESET, kind])

def tester_present(suppress_response: bool = False) -> bytes:
    sub = 0x80 if suppress_response else 0x00
    return bytes([SID.TESTER_PRESENT, sub])

def read_data_by_identifier(did: int) -> bytes:
    return bytes([SID.READ_DATA_BY_IDENTIFIER, (did >> 8) & 0xFF, did & 0xFF])

def write_data_by_identifier(did: int, payload: bytes) -> bytes:
    return bytes([SID.WRITE_DATA_BY_IDENTIFIER, (did >> 8) & 0xFF, did & 0xFF]) + bytes(payload)

def clear_diagnostic_information(group: int = 0xFFFFFF) -> bytes:
    return bytes([SID.CLEAR_DIAGNOSTIC_INFORMATION,
                  (group >> 16) & 0xFF, (group >> 8) & 0xFF, group & 0xFF])

def read_dtc_by_status_mask(mask: int = DtcStatusMask.CONFIRMED_DTC) -> bytes:
    return bytes([SID.READ_DTC_INFORMATION,
                  DtcSub.REPORT_DTC_BY_STATUS_MASK, mask])

def read_dtc_with_permanent_status() -> bytes:
    return bytes([SID.READ_DTC_INFORMATION, DtcSub.REPORT_DTC_WITH_PERMANENT_STATUS])

def read_dtc_snapshot_record(dtc: int, record: int = 0xFF) -> bytes:
    return bytes([SID.READ_DTC_INFORMATION,
                  DtcSub.REPORT_DTC_SNAPSHOT_RECORD_BY_DTC_NUMBER,
                  (dtc >> 16) & 0xFF, (dtc >> 8) & 0xFF, dtc & 0xFF,
                  record])

def security_access_request_seed(level: int = 0x01) -> bytes:
    return bytes([SID.SECURITY_ACCESS, level])

def security_access_send_key(level: int, key: bytes) -> bytes:
    # Send key sub-function is request-seed sub-function + 1.
    return bytes([SID.SECURITY_ACCESS, level + 1]) + bytes(key)

def routine_control(routine_id: int, sub: int = RoutineCtl.START_ROUTINE, params: bytes = b"") -> bytes:
    return bytes([SID.ROUTINE_CONTROL, sub,
                  (routine_id >> 8) & 0xFF, routine_id & 0xFF]) + bytes(params)

def communication_control(ctrl_type: int = CommCtl.DISABLE_RX_AND_TX,
                          comm_type: int = CommType.NORMAL_COMMUNICATION_MESSAGES) -> bytes:
    return bytes([SID.COMMUNICATION_CONTROL, ctrl_type, comm_type])

def control_dtc_setting(off: bool = True) -> bytes:
    """0x85 — disable (off=True) or enable DTC capture during programming."""
    return bytes([SID.CONTROL_DTC_SETTING, 0x02 if off else 0x01])

def link_control_transition(baud_code: int) -> bytes:
    """0x87 — switch baud to a predefined rate. 0x10=PC9600, 0x11=PC19200,
    0x12=PC38400, 0x13=PC57600, 0x14=PC115200, 0x20=CAN125, 0x21=CAN250,
    0x22=CAN500, 0x23=CAN1000."""
    return bytes([SID.LINK_CONTROL, LinkCtl.VERIFY_BAUD_RATE_TRANSITION_FIXED, baud_code])

def request_download(addr: int, size: int, addr_len: int = 4, size_len: int = 4,
                     format_id: int = 0x00) -> bytes:
    """0x34 — start a flash download. addr_len/size_len in bytes (1..4)."""
    addr_size_format = (size_len << 4) | addr_len
    addr_bytes = addr.to_bytes(addr_len, "big")
    size_bytes = size.to_bytes(size_len, "big")
    return bytes([SID.REQUEST_DOWNLOAD, format_id, addr_size_format]) + addr_bytes + size_bytes

def request_upload(addr: int, size: int, addr_len: int = 4, size_len: int = 4,
                   format_id: int = 0x00) -> bytes:
    """0x35 — start a flash upload (firmware read-out)."""
    addr_size_format = (size_len << 4) | addr_len
    addr_bytes = addr.to_bytes(addr_len, "big")
    size_bytes = size.to_bytes(size_len, "big")
    return bytes([SID.REQUEST_UPLOAD, format_id, addr_size_format]) + addr_bytes + size_bytes

def transfer_data(block_seq_counter: int, data: bytes = b"") -> bytes:
    return bytes([SID.TRANSFER_DATA, block_seq_counter & 0xFF]) + bytes(data)

def request_transfer_exit(parameter: bytes = b"") -> bytes:
    return bytes([SID.REQUEST_TRANSFER_EXIT]) + bytes(parameter)


# ── Response parsing helpers ─────────────────────────────────────────

@dataclass
class UDSResponse:
    raw: bytes
    is_positive: bool
    sid: int                # original request SID (positive: sid+0x40-0x40)
    payload: bytes          # data bytes after the SID
    nrc: Optional[int]      # set when is_positive is False
    nrc_name: Optional[str] = None

    def __bool__(self) -> bool:
        return self.is_positive

    def __str__(self) -> str:
        if self.is_positive:
            return f"OK {sid_name(self.sid)} {self.payload.hex()}"
        return f"NEG 0x{self.sid:02X} ({sid_name(self.sid)}): {self.nrc_name}"


def parse_response(raw: bytes, request_sid: Optional[int] = None) -> UDSResponse:
    """Parse an ECU response. Handles positive (SID|0x40 + data) and
    negative (0x7F + originalSID + NRC) forms uniformly."""
    if not raw:
        return UDSResponse(raw=raw, is_positive=False, sid=request_sid or 0,
                           payload=b"", nrc=NRC.GENERAL_REJECT,
                           nrc_name="empty response")
    if raw[0] == SID.NEGATIVE_RESPONSE and len(raw) >= 3:
        nrc = raw[2]
        return UDSResponse(raw=raw, is_positive=False, sid=raw[1],
                           payload=b"", nrc=nrc, nrc_name=nrc_name(nrc))
    sid = raw[0] - 0x40
    return UDSResponse(raw=raw, is_positive=True, sid=sid, payload=bytes(raw[1:]),
                       nrc=None)


def is_pending(raw: bytes) -> bool:
    """True iff this is a 'response pending' (0x78) negative response —
    the ECU is asking us to wait, not refusing. Used to extend P2*
    timeout windows during long operations like ClearDTC or routine
    completion."""
    return (len(raw) >= 3 and raw[0] == SID.NEGATIVE_RESPONSE
            and raw[2] == NRC.REQUEST_CORRECTLY_RECEIVED_RESPONSE_PENDING)
