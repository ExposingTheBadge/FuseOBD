"""UDS Routine Control (0x31) routine-identifier catalog.

Each ECU advertises a set of routines callable via service 0x31
(start/stop/results). The routine IDs are 2-byte values; the meaning
is manufacturer-specific. This catalog is the union of:

  - ISO 14229-1 standardized routine IDs (Annex F)
  - Ford-specific routines verified through reverse engineering
  - Cross-make routines mined from alfa-analysis decompilation 2026-06-06
    that follow the same SAE / industry conventions Ford uses

Categories follow the ISO Annex F numbering:
  0x0000-0x00FF — ISO/SAE reserved
  0x0100-0xDFFF — vehicle manufacturer specific
  0xE000-0xEFFF — system supplier specific
  0xF000-0xFEFF — ISO/SAE reserved (standardized routines below)
  0xFF00-0xFFFF — vehicle manufacturer specific (extensions)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class UdsRoutine:
    id: int
    name: str
    category: str = ""   # 'iso' | 'ford' | 'mfg'
    notes: str = ""
    requires_security: bool = False
    requires_session: Optional[str] = None  # 'extended' | 'programming' | None


# ── ISO 14229-1 standardized (0xF000-0xFEFF reserved range) ──────────

ROUTINE_ISO = {
    0xFF00: UdsRoutine(0xFF00, "Erase memory",
                       category="iso", requires_session="programming"),
    0xFF01: UdsRoutine(0xFF01, "Check programming dependencies",
                       category="iso", requires_session="programming"),
    0xFF02: UdsRoutine(0xFF02, "Erase mirror memory DTCs",
                       category="iso"),
    0x0201: UdsRoutine(0x0201, "Check programming preconditions",
                       category="iso"),
    0x0202: UdsRoutine(0x0202, "Verify Ownership",
                       category="iso", requires_security=True),
    0x0203: UdsRoutine(0x0203, "Check Pre-Programming Conditions",
                       category="iso"),
    0xE200: UdsRoutine(0xE200, "Erase Flash Memory (supplier)",
                       category="supplier", requires_session="programming",
                       requires_security=True),
    0xE201: UdsRoutine(0xE201, "Check Flash Memory (supplier)",
                       category="supplier"),
}


# ── Ford-specific routines ───────────────────────────────────────────

ROUTINE_FORD = {
    # Module-management
    0x0001: UdsRoutine(0x0001, "Module Programming Begin",
                       category="ford", requires_session="programming",
                       requires_security=True),
    0x0002: UdsRoutine(0x0002, "Module Programming End",
                       category="ford", requires_session="programming"),
    0x0301: UdsRoutine(0x0301, "Erase Flash Memory",
                       category="ford", requires_session="programming",
                       requires_security=True),
    0x0302: UdsRoutine(0x0302, "Check Flash Memory CRC",
                       category="ford"),
    0x0304: UdsRoutine(0x0304, "Check Compatibility",
                       category="ford"),

    # PATS / key learn — verified against modules/pats.py
    0xB001: UdsRoutine(0xB001, "PATS Begin Key Learn",
                       category="ford", requires_security=True,
                       notes="Erases existing keys; ignition must be ON"),
    0xB002: UdsRoutine(0xB002, "PATS End Key Learn",
                       category="ford"),
    0xB003: UdsRoutine(0xB003, "PATS Erase All Keys",
                       category="ford", requires_security=True,
                       notes="Destructive — requires explicit confirm in client"),
    0xB004: UdsRoutine(0xB004, "PATS Verify Key Learn Complete",
                       category="ford"),
    0xB008: UdsRoutine(0xB008, "PATS Read Key Slot Status",
                       category="ford"),

    # As-Built read/write
    0x0210: UdsRoutine(0x0210, "AsBuilt Read Block",
                       category="ford"),
    0x0211: UdsRoutine(0x0211, "AsBuilt Write Block",
                       category="ford", requires_security=True,
                       requires_session="extended"),
    0x0212: UdsRoutine(0x0212, "AsBuilt Verify Checksum",
                       category="ford"),

    # Actuator tests (PCM / TCM)
    0x9001: UdsRoutine(0x9001, "PCM Self-Test",
                       category="ford", requires_session="extended"),
    0x9002: UdsRoutine(0x9002, "TCM Self-Test",
                       category="ford", requires_session="extended"),
    0x9100: UdsRoutine(0x9100, "Output Control — Cooling Fans"),
    0x9101: UdsRoutine(0x9101, "Output Control — EVAP Canister Vent"),
    0x9102: UdsRoutine(0x9102, "Output Control — Fuel Pump"),
    0x9110: UdsRoutine(0x9110, "Output Control — ABS Pump"),
    0x9120: UdsRoutine(0x9120, "Output Control — BCM Lamps"),

    # Calibration
    0xC100: UdsRoutine(0xC100, "Calibrate Steering Angle Sensor",
                       category="ford", requires_session="extended"),
    0xC101: UdsRoutine(0xC101, "Calibrate Throttle Position",
                       category="ford", requires_session="extended"),
    0xC102: UdsRoutine(0xC102, "Calibrate Brake Pedal Travel",
                       category="ford", requires_session="extended"),
    0xC110: UdsRoutine(0xC110, "Reset Adaptive Transmission",
                       category="ford", requires_session="extended"),
    0xC120: UdsRoutine(0xC120, "Reset Tire Pressure Monitor"),
    0xC130: UdsRoutine(0xC130, "Reset Oil Life Monitor"),

    # Service / shop
    0xF000: UdsRoutine(0xF000, "Begin Programming Session",
                       category="ford", requires_session="programming",
                       requires_security=True),
    0xF001: UdsRoutine(0xF001, "End Programming Session",
                       category="ford"),
}


# ── Combined lookup ──────────────────────────────────────────────────

ALL_ROUTINES = {**ROUTINE_ISO, **ROUTINE_FORD}


def lookup(routine_id: int) -> Optional[UdsRoutine]:
    return ALL_ROUTINES.get(routine_id)


def name(routine_id: int) -> str:
    r = ALL_ROUTINES.get(routine_id)
    return r.name if r else f"Unknown routine 0x{routine_id:04X}"


def in_pats_range(routine_id: int) -> bool:
    """B0xx routines are PATS-related — additional safety checks
    apply (consent gate, ignition state, etc)."""
    return 0xB000 <= routine_id <= 0xB0FF


def is_destructive(routine_id: int) -> bool:
    """Routines that erase data or take the module offline. Client UI
    should require an explicit confirm dialog before invoking."""
    r = ALL_ROUTINES.get(routine_id)
    if not r: return False
    n = r.name.lower()
    return any(k in n for k in ("erase", "begin programming", "erase all", "reset adaptive"))
