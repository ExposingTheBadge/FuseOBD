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
# Captured 2026-06-07 from a FORScan session on a 2006 Lincoln Zephyr
# (CD3 first-model-year). FORScan reads these without any session
# control — they answer in the implicit default session.
DID_FORD_MODULE_HW_PN          = 0xE610  # 24-byte ASCII hardware P/N, Ford
                                         # format "PREFIX-BASE-SUFFIX" or
                                         # "HW-XXXX-XXXXX-XX" — e.g.
                                         # "5G13-14C336-AA", "HW-6E5C-2C219-AE"
DID_FORD_MODULE_CONFIG_FLAGS   = 0xE6F3  # 1-byte config flags (Ford)
DID_FORD_MODULE_ALIVE_PROBE    = 0x0200  # 1-byte "are you there" ping —
                                         # FORScan reads this first against
                                         # every module address as a cheap
                                         # presence check before iterating
                                         # the full DID battery

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

# ── ISO 14229-1 standard DIDs (0xF180-0xF1FF) ──
# Many Ford modules implement a subset of these; the ones not implemented
# return NRC 0x31 (request out of range). They're added here so the DID
# registry has names to display when a module DOES respond to one.
DID_ISO_BOOT_SOFTWARE_ID                = 0xF180  # boot software identification
DID_ISO_APPLICATION_SOFTWARE_ID         = 0xF181  # application software identification
DID_ISO_APPLICATION_DATA_ID             = 0xF182  # application data identification
DID_ISO_BOOT_SOFTWARE_FINGERPRINT       = 0xF183
DID_ISO_APPLICATION_SOFTWARE_FINGERPRINT = 0xF184
DID_ISO_APPLICATION_DATA_FINGERPRINT    = 0xF185
DID_ISO_ACTIVE_DIAG_SESSION             = 0xF186  # current diagnostic session
DID_ISO_SPARE_PART_NUMBER               = 0xF187  # ECU spare-part number
DID_ISO_ECU_SOFTWARE_NUMBER             = 0xF188  # ECU software number
DID_ISO_ECU_SOFTWARE_VERSION            = 0xF189
DID_ISO_SUPPLIER_ID                     = 0xF18A  # system supplier identification
DID_ISO_ECU_MANUFACTURING_DATE          = 0xF18B  # 4 bytes: YY MM DD (BCD)
DID_ISO_ECU_SERIAL_NUMBER               = 0xF18C  # ASCII serial number
DID_ISO_SUPPORTED_FUNCTIONAL_UNITS      = 0xF18D
DID_ISO_ECU_MANUFACTURER                = 0xF18E
DID_ISO_VIN                             = 0xF190  # ASCII VIN (17 chars) — standard
DID_ISO_HARDWARE_PART_NUMBER            = 0xF191
DID_ISO_SYSTEM_SUPPLIER_HW_PART_NUMBER  = 0xF192
DID_ISO_SYSTEM_SUPPLIER_HW_VERSION      = 0xF193
DID_ISO_SYSTEM_SUPPLIER_SW_PART_NUMBER  = 0xF194
DID_ISO_SYSTEM_SUPPLIER_SW_VERSION      = 0xF195
DID_ISO_EXHAUST_REGULATION_OR_TYPE      = 0xF196
DID_ISO_SYSTEM_NAME                     = 0xF197
DID_ISO_REPAIR_SHOP_CODE                = 0xF198
DID_ISO_PROGRAMMING_DATE                = 0xF199  # 4 bytes: YY MM DD (BCD)
DID_ISO_CALIBRATION_REPAIR_SHOP_CODE    = 0xF19A
DID_ISO_CALIBRATION_DATE                = 0xF19B
DID_ISO_CALIBRATION_EQUIPMENT_SW_NUMBER = 0xF19C
DID_ISO_ECU_INSTALLATION_DATE           = 0xF19D
DID_ISO_ODX_FILE                        = 0xF19E
DID_ISO_ENTITY                          = 0xF19F

# ── Ford-specific DIDs harvested from decompilation ──
# Where the module/format is documented, it's noted on the registry entry below.
DID_FORD_VIN_ALT_BCM            = 0xF110  # ASCII VIN as stored by BCM (separate from PCM 0xF190)
DID_FORD_PATS_DATA              = 0xF110  # On IPC/PATS context: passive anti-theft data block
DID_FORD_VIN_SEGMENT            = 0xF120  # VIN segment on some Ford modules (BCM/IPC)
DID_FORD_MILEAGE                = 0xF188  # Ford-specific mileage value (overlaps ISO; Ford uses it both ways)
DID_FORD_VIN_SEGMENT_A6         = 0xF1A6  # Ford VIN segment / odometer extended
DID_FORD_TOTAL_DISTANCE         = 0xDD01  # Master odometer / total distance (PCM PID 0xA6 equivalent)
DID_FORD_DD00_DIAG              = 0xDD00  # Diagnostic data block
DID_FORD_CAL_PART_1             = 0xDE00  # Ford calibration identifier — base
DID_FORD_CAL_PART_2             = 0xDE01  # Ford calibration identifier — map version
DID_FORD_CAL_PART_3             = 0xDE02  # Ford calibration identifier — data revision
DID_FORD_MEMORY_ADDRESS_PROMPT  = 0xDE05  # Hex-address input prompt (debugging path)
DID_FORD_PROPRIETARY_SECURITY   = 0xDE07  # Ford proprietary security / ID block
DID_IPC_ODOMETER_PRIMARY        = 0x4A47  # IPC odometer DID (primary attempt)
DID_IPC_ODOMETER_FALLBACK       = 0x4A46  # IPC odometer DID (fallback)
DID_PCM_ODOMETER_EXTENDED       = 0x11E2D  # Extended odometer path used by PCM
DID_FORD_BOOTLOADER_INFO        = 0x11C1  # Bootloader information block
DID_FORD_SECURITY_SEED_REQUEST  = 0x114D  # Service $22 path for SecurityAccess seed (some modules)
DID_FORD_SECURITY_KEY_SEND      = 0x1165  # Service $22 path for SecurityAccess key (some modules)
DID_FORD_MODULE_SPECIFIC        = 0x1928  # Module-specific data block

# VIN-character DIDs — Ford splits the 17-character VIN into 4-byte chunks
# on some PCM strategies. Range 0xD102-0xD109 already covered above as marks;
# these are the alternate readout addresses used by the secondary ECU type.
DID_FORD_VIN_CHAR_BASE          = 0x9907  # 0x229907-0x22993E range; one char per DID


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


def _decode_bcd_date(data: bytes) -> str:
    """ISO 14229 manufacturing/programming date format — 4 BCD bytes: YY YY MM DD."""
    if len(data) < 4:
        return data.hex().upper()
    try:
        year = (data[0] >> 4) * 1000 + (data[0] & 0xF) * 100 + (data[1] >> 4) * 10 + (data[1] & 0xF)
        month = (data[2] >> 4) * 10 + (data[2] & 0xF)
        day   = (data[3] >> 4) * 10 + (data[3] & 0xF)
        return f"{year:04d}-{month:02d}-{day:02d}"
    except Exception:
        return data.hex().upper()


def _decode_odometer_be(data: bytes) -> str:
    """Ford master odometer — typically 3-4 byte big-endian km value."""
    if not data:
        return ""
    n = int.from_bytes(data[:4], "big")
    return f"{n:,} km"


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
    DID_FORD_MODULE_HW_PN: FordDID(
        DID_FORD_MODULE_HW_PN, "Module Hardware Part Number",
        decoder=_decode_ascii,
        notes="Verified on CD3 PCM/TCM (e.g. 5G13-14C336-AA, HW-6E5C-2C219-AE)",
    ),
    DID_FORD_MODULE_CONFIG_FLAGS: FordDID(
        DID_FORD_MODULE_CONFIG_FLAGS, "Module Configuration Flags",
    ),
    DID_FORD_MODULE_ALIVE_PROBE: FordDID(
        DID_FORD_MODULE_ALIVE_PROBE, "Module Alive Probe",
        notes="FORScan reads this first as a presence check; positive "
              "response means the module is on-bus and accepting $22",
    ),
    DID_PCM_ODOMETER_USAGE: FordDID(
        DID_PCM_ODOMETER_USAGE, "Odometer / Usage",
    ),
    DID_PCM_FUEL_LEVEL_TANK: FordDID(
        DID_PCM_FUEL_LEVEL_TANK, "Fuel Level (Tank)",
        units="%", decoder=_decode_percent_byte,
    ),

    # ── ISO 14229 standard DIDs ──
    DID_ISO_BOOT_SOFTWARE_ID:                FordDID(0xF180, "Boot Software Identification",         decoder=_decode_ascii),
    DID_ISO_APPLICATION_SOFTWARE_ID:         FordDID(0xF181, "Application Software Identification",  decoder=_decode_ascii),
    DID_ISO_APPLICATION_DATA_ID:             FordDID(0xF182, "Application Data Identification",      decoder=_decode_ascii),
    DID_ISO_BOOT_SOFTWARE_FINGERPRINT:       FordDID(0xF183, "Boot Software Fingerprint"),
    DID_ISO_APPLICATION_SOFTWARE_FINGERPRINT: FordDID(0xF184, "Application Software Fingerprint"),
    DID_ISO_APPLICATION_DATA_FINGERPRINT:    FordDID(0xF185, "Application Data Fingerprint"),
    DID_ISO_ACTIVE_DIAG_SESSION:             FordDID(0xF186, "Active Diagnostic Session"),
    DID_ISO_SPARE_PART_NUMBER:               FordDID(0xF187, "Spare Part Number",                    decoder=_decode_ascii),
    DID_ISO_ECU_SOFTWARE_NUMBER:             FordDID(0xF188, "ECU Software Number",                  decoder=_decode_ascii),
    DID_ISO_ECU_SOFTWARE_VERSION:            FordDID(0xF189, "ECU Software Version",                 decoder=_decode_ascii),
    DID_ISO_SUPPLIER_ID:                     FordDID(0xF18A, "System Supplier Identification",       decoder=_decode_ascii),
    DID_ISO_ECU_MANUFACTURING_DATE:          FordDID(0xF18B, "ECU Manufacturing Date",               decoder=_decode_bcd_date),
    DID_ISO_ECU_SERIAL_NUMBER:               FordDID(0xF18C, "ECU Serial Number",                    decoder=_decode_ascii),
    DID_ISO_SUPPORTED_FUNCTIONAL_UNITS:      FordDID(0xF18D, "Supported Functional Units"),
    DID_ISO_ECU_MANUFACTURER:                FordDID(0xF18E, "ECU Manufacturer",                     decoder=_decode_ascii),
    DID_ISO_VIN:                             FordDID(0xF190, "Vehicle Identification Number (VIN)",  decoder=_decode_ascii),
    DID_ISO_HARDWARE_PART_NUMBER:            FordDID(0xF191, "Hardware Part Number",                 decoder=_decode_ascii),
    DID_ISO_SYSTEM_SUPPLIER_HW_PART_NUMBER:  FordDID(0xF192, "System Supplier HW Part Number",       decoder=_decode_ascii),
    DID_ISO_SYSTEM_SUPPLIER_HW_VERSION:      FordDID(0xF193, "System Supplier HW Version",           decoder=_decode_ascii),
    DID_ISO_SYSTEM_SUPPLIER_SW_PART_NUMBER:  FordDID(0xF194, "System Supplier SW Part Number",       decoder=_decode_ascii),
    DID_ISO_SYSTEM_SUPPLIER_SW_VERSION:      FordDID(0xF195, "System Supplier SW Version",           decoder=_decode_ascii),
    DID_ISO_EXHAUST_REGULATION_OR_TYPE:      FordDID(0xF196, "Exhaust Regulation / Type Approval"),
    DID_ISO_SYSTEM_NAME:                     FordDID(0xF197, "System Name / Engine Type",            decoder=_decode_ascii),
    DID_ISO_REPAIR_SHOP_CODE:                FordDID(0xF198, "Repair Shop Code"),
    DID_ISO_PROGRAMMING_DATE:                FordDID(0xF199, "Programming Date",                     decoder=_decode_bcd_date),
    DID_ISO_CALIBRATION_REPAIR_SHOP_CODE:    FordDID(0xF19A, "Calibration Repair Shop Code"),
    DID_ISO_CALIBRATION_DATE:                FordDID(0xF19B, "Calibration Date",                     decoder=_decode_bcd_date),
    DID_ISO_CALIBRATION_EQUIPMENT_SW_NUMBER: FordDID(0xF19C, "Calibration Equipment SW Number",      decoder=_decode_ascii),
    DID_ISO_ECU_INSTALLATION_DATE:           FordDID(0xF19D, "ECU Installation Date",                decoder=_decode_bcd_date),
    DID_ISO_ODX_FILE:                        FordDID(0xF19E, "ODX File Identifier",                  decoder=_decode_ascii),
    DID_ISO_ENTITY:                          FordDID(0xF19F, "Entity Identifier"),

    # ── Ford-specific DIDs ──
    DID_FORD_VIN_ALT_BCM:           FordDID(0xF110, "VIN (BCM / PATS data)",        decoder=_decode_ascii,
                                            notes="ASCII VIN on BCM/IPC; passive anti-theft block when read from PATS-capable module"),
    DID_FORD_VIN_SEGMENT:           FordDID(0xF120, "VIN Segment",                  decoder=_decode_ascii),
    DID_FORD_VIN_SEGMENT_A6:        FordDID(0xF1A6, "VIN Segment / Extended Odometer"),
    DID_FORD_TOTAL_DISTANCE:        FordDID(0xDD01, "Total Distance (Master Odometer)",  units="km",
                                            decoder=_decode_odometer_be,
                                            notes="PCM total-distance counter — equivalent to OBD-II PID 0xA6"),
    DID_FORD_DD00_DIAG:             FordDID(0xDD00, "Diagnostic Data Block"),
    DID_FORD_CAL_PART_1:            FordDID(0xDE00, "Calibration Part 1 (Base)",        decoder=_decode_ascii),
    DID_FORD_CAL_PART_2:            FordDID(0xDE01, "Calibration Part 2 (Map Version)", decoder=_decode_ascii),
    DID_FORD_CAL_PART_3:            FordDID(0xDE02, "Calibration Part 3 (Data Rev)",    decoder=_decode_ascii),
    DID_FORD_PROPRIETARY_SECURITY:  FordDID(0xDE07, "Proprietary Security / ID Block",
                                            notes="Ford-specific — read prior to SecurityAccess on some modules"),
    DID_IPC_ODOMETER_PRIMARY:       FordDID(0x4A47, "IPC Odometer (Primary)",       units="km",
                                            decoder=_decode_odometer_be),
    DID_IPC_ODOMETER_FALLBACK:      FordDID(0x4A46, "IPC Odometer (Fallback)",      units="km",
                                            decoder=_decode_odometer_be),
    DID_FORD_BOOTLOADER_INFO:       FordDID(0x11C1, "Bootloader Info"),
    DID_FORD_MODULE_SPECIFIC:       FordDID(0x1928, "Module-Specific Data Block"),

    # ── Additional ISO + Ford-specific identifiers mined from the
    # alfa-analysis indexes 2026-06-06. Treat as best-effort labels —
    # not every module responds to every DID; absence of a response
    # (NRC 0x31) just means "not implemented on this module."
    0xF100: FordDID(0xF100, "Manufacturer Identification (Group Start)"),
    0xF109: FordDID(0xF109, "Calibration Index Offset"),
    0xF111: FordDID(0xF111, "Programming Counter"),
    0xF128: FordDID(0xF128, "Software Calibration Set Reference"),
    0xF155: FordDID(0xF155, "Diagnostic Trouble Code Status Table"),
    0xF16F: FordDID(0xF16F, "Vehicle Platform Identifier (mfg-specific)"),
    0xF172: FordDID(0xF172, "Hardware / Software Compatibility Block"),
    0xF174: FordDID(0xF174, "Module Activation State"),
    0xF1A8: FordDID(0xF1A8, "Network Configuration Index"),
    0xF1B9: FordDID(0xF1B9, "Software Application Trace"),
    0xF1E0: FordDID(0xF1E0, "Ford Extended DID Range Prefix",
                    notes="Ford uses 0xF1E0-0xF1FF for proprietary extension data"),
    0xF1FF: FordDID(0xF1FF, "Manufacturer Identification (Group End)"),

    # ── AsBuilt block address range (0xF200-0xFBxx). These ARE valid
    # 0x22 ReadDataByIdentifier targets on Ford modules, but the payload
    # is the corresponding factory-config block rather than a single
    # value. See modules/asbuilt.py for the block decode schemas.
    0xF200: FordDID(0xF200, "AsBuilt Block (range start)"),
    0xF300: FordDID(0xF300, "AsBuilt Block — BCM region"),
    0xF301: FordDID(0xF301, "AsBuilt Block — BCM region"),
    0xF372: FordDID(0xF372, "AsBuilt Block — IPC region"),
    0xF400: FordDID(0xF400, "AsBuilt Block — PCM region"),
    0xF472: FordDID(0xF472, "AsBuilt Block — PCM region"),
    0xF572: FordDID(0xF572, "AsBuilt Block — RCM region"),
    0xF58D: FordDID(0xF58D, "AsBuilt Block — RCM detail"),
    0xF672: FordDID(0xF672, "AsBuilt Block — ABS region"),
    0xF680: FordDID(0xF680, "AsBuilt Block — ABS detail"),
    0xF772: FordDID(0xF772, "AsBuilt Block — HVAC region"),
    0xF800: FordDID(0xF800, "AsBuilt Block — APIM/SYNC region"),
    0xF81D: FordDID(0xF81D, "AsBuilt Block — APIM detail"),
    0xF884: FordDID(0xF884, "AsBuilt Block — APIM extended"),
    0xF8E9: FordDID(0xF8E9, "AsBuilt Block — APIM diagnostic"),
    0xF900: FordDID(0xF900, "AsBuilt Block — Gateway region"),
    0xF96F: FordDID(0xF96F, "AsBuilt Block — Gateway routing"),
    0xF9CB: FordDID(0xF9CB, "AsBuilt Block — Gateway diagnostic"),
    0xF9E9: FordDID(0xF9E9, "AsBuilt Block — Gateway extended"),
    0xF9EC: FordDID(0xF9EC, "AsBuilt Block — Gateway extended"),
    0xF9EE: FordDID(0xF9EE, "AsBuilt Block — Gateway extended"),
    0xF9FF: FordDID(0xF9FF, "AsBuilt Block — Gateway region end"),
    0xFB00: FordDID(0xFB00, "Extended AsBuilt — Hybrid/EV region"),
    0xFB35: FordDID(0xFB35, "Extended AsBuilt — Hybrid/EV detail"),
    0xFB5F: FordDID(0xFB5F, "Extended AsBuilt — Hybrid/EV detail"),
    0xFB8D: FordDID(0xFB8D, "Extended AsBuilt — Hybrid/EV detail"),
    0xFE70: FordDID(0xFE70, "OEM Reserved Block (Ford/FCA shared region)"),
}


# Modules-of-interest priority for whole-vehicle ident reads. PCM first
# (it carries the canonical VIN/cal data); body modules next for VIN
# fallback on platforms where PCM doesn't respond to 0xF190.
IDENT_PRIORITY = ("PCM", "IPC", "BCM", "GWM")
