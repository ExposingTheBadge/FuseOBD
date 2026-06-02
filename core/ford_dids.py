"""Ford-specific UDS DIDs (Data Identifiers).

Standard ISO 14229 DIDs (0xF1xx) are documented in the UDS spec — but on
Ford vehicles, the ISO DIDs are often empty/unimplemented while Ford-
specific DIDs (0xE2xx / 0xD1xx / 0xC9xx / 0x6xxx) carry the actual data.

Values here are derived from a Ford-diagnostic reverse-engineering
reference; the underlying index is partial, so absence from this
dictionary does not imply a DID does not exist.

Wire format reminder: a Read-Data-By-Identifier request is
``22 <DID_hi> <DID_lo>`` and the positive response is
``62 <DID_hi> <DID_lo> <payload...>``. UDSClient.read_data_by_id()
strips the 0x62 service byte and the 2-byte DID echo, so the bytes
returned are just the payload.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


# ── Ford module identification (preferred over ISO 0xF187/F188/F191) ──
# Verified-from-decompilation against PCM responses.
DID_FORD_SOFTWARE_PART_NUMBER  = 0xE217  # ASCII (8 hex chars), e.g. "01000849"
DID_FORD_CALIBRATION_ID        = 0xE219  # ASCII (4 hex chars), e.g. "0409"
DID_FORD_ASSEMBLY_PART_NUMBER  = 0xE21A  # ASCII (4 chars), e.g. "WM5F" / "2M51"
DID_FORD_MODULE_CONFIG         = 0xE200  # binary configuration data
DID_FORD_CALIBRATION_VERIFY    = 0xC9FE  # CVN — Calibration Verification Number

# ── Vehicle identification (Ford-encoded; NOT ASCII VIN) ──
# These return single-byte brand/platform markers, not VIN characters.
# For the actual ASCII VIN, use ISO DID 0xF190 or OBD Mode 09 PID 02.
DID_FORD_VEHICLE_MARK_1        = 0xD102
DID_FORD_VEHICLE_MARK_2        = 0xD103
DID_FORD_VEHICLE_MARK_3        = 0xD107
DID_FORD_VEHICLE_MARK_4        = 0xD109
DID_FORD_VEHICLE_CONFIGURATION = 0xD128

# ── PCM / TCM telemetry DIDs (verified-from-decompilation) ──
DID_PCM_ODOMETER_USAGE         = 0x6101  # binary; raw usage record
DID_PCM_FUEL_LEVEL_TANK        = 0x6185  # 1 byte percent
DID_VEHICLE_MODE_DATA          = 0x3A42  # platform-dependent
DID_CONFIGURATION_DATA         = 0x3A50  # platform-dependent
DID_TRANSMISSION_DATA_BASE     = 0x5910  # 0x5910-0x5952 range on TCM


@dataclass(frozen=True)
class FordDID:
    """Description record for a Ford DID. Used by reporting/UI code that
    wants to label a DID without baking string copies all over."""
    did: int
    name: str
    units: str = ""
    decoder: Optional[Callable[[bytes], str]] = None
    notes: str = ""

    def decode(self, payload: bytes) -> str:
        if self.decoder is None:
            return payload.hex().upper()
        try:
            return self.decoder(payload)
        except Exception:
            return payload.hex().upper()


def _decode_ascii(data: bytes) -> str:
    return data.decode("ascii", errors="replace").strip("\x00").strip()


def _decode_percent_byte(data: bytes) -> str:
    if not data:
        return ""
    return f"{data[0] * 100 / 255:.1f}%"


FORD_DID_REGISTRY: dict[int, FordDID] = {
    DID_FORD_SOFTWARE_PART_NUMBER: FordDID(
        DID_FORD_SOFTWARE_PART_NUMBER, "Software Part Number",
        decoder=lambda b: b.hex().upper(),
        notes="Verified on PCM (e.g. 01000849)",
    ),
    DID_FORD_CALIBRATION_ID: FordDID(
        DID_FORD_CALIBRATION_ID, "Calibration ID",
        decoder=lambda b: b.hex().upper(),
        notes="Verified on PCM (e.g. 0409)",
    ),
    DID_FORD_ASSEMBLY_PART_NUMBER: FordDID(
        DID_FORD_ASSEMBLY_PART_NUMBER, "Assembly Part Number",
        decoder=_decode_ascii,
        notes="Verified on PCM (e.g. WM5F, 2M51)",
    ),
    DID_FORD_MODULE_CONFIG: FordDID(
        DID_FORD_MODULE_CONFIG, "Module Configuration",
        decoder=lambda b: b.hex().upper(),
    ),
    DID_FORD_CALIBRATION_VERIFY: FordDID(
        DID_FORD_CALIBRATION_VERIFY, "Calibration Verification Number (CVN)",
        decoder=lambda b: b.hex().upper(),
    ),
    DID_PCM_ODOMETER_USAGE: FordDID(
        DID_PCM_ODOMETER_USAGE, "Odometer / Usage",
    ),
    DID_PCM_FUEL_LEVEL_TANK: FordDID(
        DID_PCM_FUEL_LEVEL_TANK, "Fuel Level (Tank)",
        units="%", decoder=_decode_percent_byte,
    ),
}


# Modules-of-interest priority for whole-vehicle ident reads. PCM first
# (it carries the canonical VIN/cal data); body modules next for VIN
# fallback on platforms where PCM doesn't respond to 0xF190.
IDENT_PRIORITY = ("PCM", "IPC", "BCM", "GWM")
