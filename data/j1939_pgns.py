"""SAE J1939 Parameter Group Number (PGN) catalog for heavy trucks.

J1939 is the CAN-based protocol for commercial vehicles — Class 4-8
diesel trucks, buses, off-highway equipment. Our adapter database
(data/adapters_db.py) includes Freightliner / Kenworth / Mack /
Peterbilt / Western Star / International / Volvo Trucks support; this
catalog gives those adapters something meaningful to ask for.

Reference: SAE J1939-71 (Application Layer) + J1939-73 (Diagnostics).

PGN encoding:
  29-bit CAN ID layout:  [3 priority | 1 r | 1 dp | 8 PF | 8 PS | 8 SA]
  When PF < 240: PGN = PF << 8                  (PDU1, destination-specific)
  When PF >= 240: PGN = (PF << 8) | PS         (PDU2, broadcast)

Helpers below convert CAN IDs <-> PGNs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Pgn:
    id: int                 # numeric PGN
    name: str
    rate_ms: Optional[int] = None     # broadcast rate, ms; None = on-request
    spns: tuple[int, ...] = ()        # SPNs typically carried in this PGN
    notes: str = ""


# ── Commonly-monitored PGNs (engine, transmission, vehicle) ──────────

PGN_DM1     = 0xFECA   # 65226 — Active DTCs (broadcast on fault)
PGN_DM2     = 0xFECB   # 65227 — Previously Active DTCs (on-request)
PGN_DM3     = 0xFECC   # 65228 — Clear Previously Active DTCs (command)
PGN_DM11    = 0xFED3   # 65235 — Clear Active DTCs (command)
PGN_DM14    = 0xD800   # 55296 — Memory access request
PGN_DM15    = 0xD700   # 55040 — Memory access response
PGN_DM19    = 0xD300   # 54016 — Calibration information

PGN_EEC1    = 0xF004   # 61444 — Electronic Engine Controller #1 (RPM, torque)
PGN_EEC2    = 0xF003   # 61443 — Throttle position, load
PGN_EEC3    = 0xFEDF   # 65247 — Nominal friction torque
PGN_ET1     = 0xFEEE   # 65262 — Engine Temperature 1
PGN_LFE1    = 0xFEF2   # 65266 — Fuel Economy
PGN_VEP1    = 0xFEF7   # 65271 — Vehicle Electrical Power
PGN_AMB     = 0xFEF5   # 65269 — Ambient Conditions
PGN_AT1     = 0xFE56   # 65110 — Aftertreatment 1 (DEF, DPF)
PGN_AIR1    = 0xFEF6   # 65270 — Inlet/Exhaust Conditions
PGN_EFL_P1  = 0xFEEF   # 65263 — Engine Fluid Level/Pressure 1

PGN_CRUISE  = 0xFEF1   # 65265 — Cruise Control / Vehicle Speed
PGN_TRANS1  = 0xF002   # 61442 — Electronic Transmission Controller #1
PGN_TRANS2  = 0xF005   # 61445 — Electronic Transmission Controller #2

PGN_REQUEST = 0xEA00   # 59904 — Request PGN (used to query on-request PGNs)
PGN_ACK     = 0xE800   # 59392 — Acknowledgement
PGN_TP_CM   = 0xEC00   # 60416 — Transport Protocol Connection Mgmt (BAM/RTS)
PGN_TP_DT   = 0xEB00   # 60160 — Transport Protocol Data Transfer (multi-frame)

PGN_VIN     = 0xFEEC   # 65260 — Vehicle Identification (VIN, ASCII)
PGN_COMP_ID = 0xFEEB   # 65259 — Component Identification (make/model/serial)
PGN_SW_ID   = 0xFEDA   # 65242 — Software Identification


PGNS: dict[int, Pgn] = {
    PGN_DM1:     Pgn(PGN_DM1,     "DM1 — Active DTCs",           rate_ms=1000),
    PGN_DM2:     Pgn(PGN_DM2,     "DM2 — Previously Active DTCs"),
    PGN_DM3:     Pgn(PGN_DM3,     "DM3 — Clear Previously Active DTCs"),
    PGN_DM11:    Pgn(PGN_DM11,    "DM11 — Clear Active DTCs"),
    PGN_DM14:    Pgn(PGN_DM14,    "DM14 — Memory Access Request"),
    PGN_DM15:    Pgn(PGN_DM15,    "DM15 — Memory Access Response"),
    PGN_DM19:    Pgn(PGN_DM19,    "DM19 — Calibration Information"),

    PGN_EEC1:    Pgn(PGN_EEC1,    "EEC1 — Engine RPM / Torque", rate_ms=20,
                     spns=(190, 513, 512, 899)),
    PGN_EEC2:    Pgn(PGN_EEC2,    "EEC2 — Throttle / Load",     rate_ms=50,
                     spns=(91, 92, 558)),
    PGN_EEC3:    Pgn(PGN_EEC3,    "EEC3 — Friction Torque",     rate_ms=250),
    PGN_ET1:     Pgn(PGN_ET1,     "ET1 — Engine Temp 1",        rate_ms=1000,
                     spns=(110, 174, 175)),
    PGN_LFE1:    Pgn(PGN_LFE1,    "LFE1 — Fuel Economy",        rate_ms=100,
                     spns=(183, 184, 250)),
    PGN_VEP1:    Pgn(PGN_VEP1,    "VEP1 — Vehicle Electrical Power", rate_ms=1000,
                     spns=(168,)),
    PGN_AMB:     Pgn(PGN_AMB,     "AMB — Ambient Conditions",    rate_ms=1000,
                     spns=(170, 171)),
    PGN_AT1:     Pgn(PGN_AT1,     "AT1 — Aftertreatment 1",      rate_ms=1000,
                     notes="DEF tank level + DPF status"),
    PGN_AIR1:    Pgn(PGN_AIR1,    "AIR1 — Inlet/Exhaust Cond",  rate_ms=500),
    PGN_EFL_P1:  Pgn(PGN_EFL_P1,  "EFL_P1 — Fluid Level/Pressure 1", rate_ms=500),

    PGN_CRUISE:  Pgn(PGN_CRUISE,  "CCVS — Cruise Control / Vehicle Speed", rate_ms=100,
                     spns=(84, 595, 596)),
    PGN_TRANS1:  Pgn(PGN_TRANS1,  "ETC1 — Electronic Trans Ctrl 1", rate_ms=10),
    PGN_TRANS2:  Pgn(PGN_TRANS2,  "ETC2 — Electronic Trans Ctrl 2", rate_ms=100),

    PGN_REQUEST: Pgn(PGN_REQUEST, "Request PGN",
                     notes="Send to a SA to request any on-request PGN"),
    PGN_ACK:     Pgn(PGN_ACK,     "Acknowledgement"),
    PGN_TP_CM:   Pgn(PGN_TP_CM,   "Transport Protocol — Connection Mgmt"),
    PGN_TP_DT:   Pgn(PGN_TP_DT,   "Transport Protocol — Data Transfer"),

    PGN_VIN:     Pgn(PGN_VIN,     "Vehicle Identification (VIN)"),
    PGN_COMP_ID: Pgn(PGN_COMP_ID, "Component Identification"),
    PGN_SW_ID:   Pgn(PGN_SW_ID,   "Software Identification"),
}


# ── Common Source Addresses (J1939-71 Annex B) ───────────────────────

class SrcAddr:
    ENGINE_1         = 0x00   # most powerful engine on the bus
    ENGINE_2         = 0x01
    TRANSMISSION_1   = 0x03
    TRANSMISSION_2   = 0x04
    BRAKE_ABS        = 0x0B
    INSTRUMENT       = 0x17
    BODY_CONTROLLER  = 0x21
    CAB_CONTROLLER   = 0x49
    TELEMATICS       = 0xFC
    AFTERTREATMENT   = 0x3D
    DIAGNOSTIC_TOOL  = 0xF9   # the bench scanner address
    BROADCAST        = 0xFF


# ── CAN-ID <-> PGN helpers ───────────────────────────────────────────

def can_id_to_pgn(can_id: int) -> tuple[int, int, int]:
    """Decompose a 29-bit J1939 CAN ID into (priority, pgn, source).
    Returns -1 for the dst byte when the PGN is broadcast (PDU2)."""
    priority = (can_id >> 26) & 0x07
    pf = (can_id >> 16) & 0xFF
    ps = (can_id >> 8) & 0xFF
    sa = can_id & 0xFF
    if pf < 240:
        pgn = pf << 8                # PDU1 — destination-specific
        return priority, pgn, sa
    pgn = (pf << 8) | ps             # PDU2 — broadcast
    return priority, pgn, sa


def pgn_to_can_id(pgn: int, src: int = SrcAddr.DIAGNOSTIC_TOOL,
                  dst: int = SrcAddr.BROADCAST, priority: int = 6) -> int:
    """Build a 29-bit J1939 CAN ID. For PDU1 (PF < 240) `dst` becomes
    PS; for PDU2 it's already baked into the PGN."""
    pf = (pgn >> 8) & 0xFF
    if pf < 240:
        return (priority << 26) | (pgn << 8) | ((dst & 0xFF) << 8) | (src & 0xFF)
    return (priority << 26) | (pgn << 8) | (src & 0xFF)


def request_pgn_frame(pgn: int, src: int = SrcAddr.DIAGNOSTIC_TOOL,
                      dst: int = SrcAddr.BROADCAST) -> tuple[int, bytes]:
    """Build a J1939 Request-PGN frame: PGN 0xEA00, payload = target PGN
    little-endian (3 bytes). Returns (can_id, 8-byte payload)."""
    can_id = pgn_to_can_id(PGN_REQUEST, src=src, dst=dst, priority=6)
    body = bytes([pgn & 0xFF, (pgn >> 8) & 0xFF, (pgn >> 16) & 0xFF,
                  0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
    return can_id, body


def name(pgn: int) -> str:
    p = PGNS.get(pgn)
    return p.name if p else f"PGN {pgn} (0x{pgn:04X})"
