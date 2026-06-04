from dataclasses import dataclass
from enum import IntEnum
from typing import Optional
from core.j2534 import Protocol, ConnectFlag


class FordNetwork(IntEnum):
    HS_CAN = 1
    MS_CAN = 2
    HS_CAN_EXT = 3   # 29-bit HS-CAN (J1939-style addressing)
    ISO = 4          # ISO 9141 / KWP2000 K-line (pre-CAN K-line vehicles)
    SCP = 5          # J1850 PWM (legacy Ford pre-2003)
    # Multi-bus support for newer Ford platforms (Gen 3 architecture +).
    # A vehicle commonly exposes HS-CAN + MS-CAN + one or more of these.
    HS_CAN_2 = 6
    HS_CAN_3 = 7
    HS_CAN_4 = 8
    HS_CAN_5 = 9
    MS_CAN_2 = 10
    CAN_FD = 11      # CAN-FD (variable data-phase rate, up to 8 Mbps)
    CAN_FD_2 = 12
    CAN_FD_3 = 13
    CAN_FD_4 = 14
    # Pre-CAN / legacy protocols (mostly OBD-II 1996-2007 era Ford).
    ISO9141 = 15        # K-line @ 10.4 kbps, ISO 9141-2 (5-baud init)
    KWP2000_SLOW = 16   # K-line ISO 14230-4, 5-baud address init
    KWP2000_FAST = 17   # K-line ISO 14230-4, fast init (25/50 ms)
    J1850_PWM = 18      # Ford pre-2003 SCP — pins 2/10, 41.6 kbps
    J1850_VPW = 19      # GM/Chrysler — pin 2, 10.4 kbps (accessible via shared J2534)
    J1939 = 20          # Heavy truck/bus 29-bit CAN @ 250 kbps


@dataclass
class NetworkConfig:
    name: str
    network: FordNetwork
    protocol: Protocol
    baudrate: int
    flags: int = 0
    tx_id: int = 0x7E0
    rx_id: int = 0x7E8
    obd_tx: int = 0x7DF
    can_id_bits: int = 11


FORD_HS_CAN = NetworkConfig(
    name="Ford HS CAN",
    network=FordNetwork.HS_CAN,
    protocol=Protocol.ISO15765,
    baudrate=500000,
    tx_id=0x7E0,
    rx_id=0x7E8,
    obd_tx=0x7DF,
)

FORD_MS_CAN = NetworkConfig(
    name="Ford MS CAN",
    network=FordNetwork.MS_CAN,
    protocol=Protocol.ISO15765,
    baudrate=125000,
    tx_id=0x7E0,
    rx_id=0x7E8,
    obd_tx=0x7DF,
)

FORD_HS_CAN_29BIT = NetworkConfig(
    name="Ford HS CAN 29-bit",
    network=FordNetwork.HS_CAN_EXT,
    protocol=Protocol.ISO15765,
    baudrate=500000,
    flags=ConnectFlag.CAN_29BIT_ID,
    tx_id=0x18DA00FF,
    rx_id=0x18DAFFEE,
    obd_tx=0x18DB33F1,
    can_id_bits=29,
)

# Secondary/tertiary HS-CAN buses on newer multi-bus platforms (Gen 3 EE).
# Same 500 kbps, same 11-bit framing — the bus is physically distinct but the
# addressing scheme is identical, so the dataclass differs only by name+enum.
FORD_HS_CAN_2 = NetworkConfig(name="Ford HS CAN 2", network=FordNetwork.HS_CAN_2,
                              protocol=Protocol.ISO15765, baudrate=500000)
FORD_HS_CAN_3 = NetworkConfig(name="Ford HS CAN 3", network=FordNetwork.HS_CAN_3,
                              protocol=Protocol.ISO15765, baudrate=500000)
FORD_HS_CAN_4 = NetworkConfig(name="Ford HS CAN 4", network=FordNetwork.HS_CAN_4,
                              protocol=Protocol.ISO15765, baudrate=500000)
FORD_HS_CAN_5 = NetworkConfig(name="Ford HS CAN 5", network=FordNetwork.HS_CAN_5,
                              protocol=Protocol.ISO15765, baudrate=500000)
FORD_MS_CAN_2 = NetworkConfig(name="Ford MS CAN 2", network=FordNetwork.MS_CAN_2,
                              protocol=Protocol.ISO15765, baudrate=125000)

# CAN-FD networks — arbitration phase at 500 kbps, data phase up to 8 Mbps.
# Baudrate here is the arbitration rate; data-phase rate is set on the J2534
# adapter via PassThruIoctl(SET_CONFIG, CAN_DATA_RATE). 2 Mbps is the most
# common Ford CANFD data rate on F-150 / Mustang Mach-E / Bronco platforms.
FORD_CAN_FD   = NetworkConfig(name="Ford CAN FD",   network=FordNetwork.CAN_FD,
                              protocol=Protocol.ISO15765, baudrate=500000)
FORD_CAN_FD_2 = NetworkConfig(name="Ford CAN FD 2", network=FordNetwork.CAN_FD_2,
                              protocol=Protocol.ISO15765, baudrate=500000)
FORD_CAN_FD_3 = NetworkConfig(name="Ford CAN FD 3", network=FordNetwork.CAN_FD_3,
                              protocol=Protocol.ISO15765, baudrate=500000)
FORD_CAN_FD_4 = NetworkConfig(name="Ford CAN FD 4", network=FordNetwork.CAN_FD_4,
                              protocol=Protocol.ISO15765, baudrate=500000)

# Convenience tuple — every CAN network FuseOBD can target. Ordered so the
# physical primaries come first (HS, MS, 29-bit) and the multi-bus secondaries
# follow. Scanner code should iterate this list when probing an unknown vehicle.
FORD_CAN_NETWORKS = (
    FORD_HS_CAN, FORD_MS_CAN, FORD_HS_CAN_29BIT,
    FORD_HS_CAN_2, FORD_HS_CAN_3, FORD_HS_CAN_4, FORD_HS_CAN_5,
    FORD_MS_CAN_2,
    FORD_CAN_FD, FORD_CAN_FD_2, FORD_CAN_FD_3, FORD_CAN_FD_4,
)


# ── Pre-CAN / legacy network configs ──
# These cover the 1996-2007 OBD-II Ford lineup and the early CAN
# transition era. The Protocol enum values come from core.j2534
# (Protocol.ISO9141 / Protocol.ISO14230 / Protocol.J1850PWM / Protocol.J1850VPW).
# Wire pinouts are documented in the comments since the OBD-II DLC has
# different pin usage per protocol.

FORD_ISO9141 = NetworkConfig(
    name="ISO 9141-2 (K-line)",
    network=FordNetwork.ISO9141,
    protocol=Protocol.ISO9141,
    baudrate=10400,
    tx_id=0x68, rx_id=0x6B, obd_tx=0x33,
)
"""K-line @ 10.4 kbps, 5-baud slow init. OBD-II pin 7 (K), optional pin 15 (L).
Common on Ford 1996-2003 (most non-CAN PCMs)."""

FORD_KWP2000_SLOW = NetworkConfig(
    name="KWP2000 5-baud (ISO 14230)",
    network=FordNetwork.KWP2000_SLOW,
    protocol=Protocol.ISO14230,
    baudrate=10400,
    tx_id=0x68, rx_id=0x6B, obd_tx=0x33,
)
"""KWP2000 with 5-baud address init. Same physical layer as ISO 9141 but
adds the standardized service IDs that became UDS. Used on European Ford
and some early Mazda 1999-2005."""

FORD_KWP2000_FAST = NetworkConfig(
    name="KWP2000 Fast Init (ISO 14230)",
    network=FordNetwork.KWP2000_FAST,
    protocol=Protocol.ISO14230,
    baudrate=10400,
    tx_id=0x68, rx_id=0x6B, obd_tx=0x33,
)
"""KWP2000 with 25/50 ms fast init. Same as the slow variant but skips the
slow 5-baud handshake — preferred on modules that support both."""

FORD_J1850_PWM = NetworkConfig(
    name="J1850 PWM (Ford SCP)",
    network=FordNetwork.J1850_PWM,
    protocol=Protocol.J1850PWM,
    baudrate=41600,
    tx_id=0x18DA10F1, rx_id=0x18DAF110, obd_tx=0x18DB33F1,
)
"""Ford Standard Corporate Protocol — 41.6 kbps pulse-width modulated.
OBD-II pins 2 (BUS+) and 10 (BUS-). Used on Ford 1996-2003 (V8 / large
trucks) until the HS-CAN transition. Logical addressing uses 29-bit-style
target/source pairs encoded in the message header."""

FORD_J1850_VPW = NetworkConfig(
    name="J1850 VPW (GM/Chrysler)",
    network=FordNetwork.J1850_VPW,
    protocol=Protocol.J1850VPW,
    baudrate=10400,
    tx_id=0x68, rx_id=0x6B, obd_tx=0x33,
)
"""Variable Pulse Width 10.4 kbps. Not native Ford but reachable via the
same J2534 adapter — useful when Fuse is probing an unknown OBD-II vehicle
and we don't yet know the OEM."""

FORD_J1939 = NetworkConfig(
    name="J1939 (29-bit @ 250k)",
    network=FordNetwork.J1939,
    protocol=Protocol.ISO15765,
    baudrate=250000,
    flags=ConnectFlag.CAN_29BIT_ID,
    tx_id=0x18EAFFF9, rx_id=0x18EBFFF9, obd_tx=0x18DB33F1,
    can_id_bits=29,
)
"""SAE J1939 — 29-bit CAN @ 250 kbps. Truck/bus diagnostic standard used by
Ford F-650 / F-750 / F-MAX commercial platforms. PGN-based addressing is
fundamentally different from UDS-on-CAN; this entry mostly exists so
J2534 channels can be opened for sniffing."""


# All non-CAN protocol configs — for unknown-vehicle protocol probing on
# pre-2007 OBD-II ports the scanner should try each in order: ISO9141 →
# KWP_SLOW → KWP_FAST → J1850_PWM → J1850_VPW.
FORD_LEGACY_PROTOCOLS = (
    FORD_ISO9141, FORD_KWP2000_SLOW, FORD_KWP2000_FAST,
    FORD_J1850_PWM, FORD_J1850_VPW,
)


@dataclass(frozen=True)
class ProtocolInit:
    """ELM327 AT command sequence that initialises a given protocol.

    Used by the J2534 wrapper to bring an adapter up on a specific
    protocol before sending the first diagnostic frame. `at_commands`
    is in order; each is sent and the response checked for 'OK' (or
    the protocol-specific positive response).
    """
    network: FordNetwork
    elm_protocol_number: int  # ATSPn argument
    at_commands: tuple[str, ...]
    requires_ignition_cycle: bool = False
    description: str = ""


# Map of FordNetwork → ATSP protocol number (the ELM327 'set protocol'
# argument). Protocols 6-9 are CAN; 1-5 are pre-CAN.
ELM_PROTOCOL_NUMBERS = {
    FordNetwork.J1850_PWM:    1,   # SAE J1850 PWM (41.6 kbps)
    FordNetwork.J1850_VPW:    2,   # SAE J1850 VPW (10.4 kbps)
    FordNetwork.ISO9141:      3,   # ISO 9141-2 (5-baud init, 10.4 kbps)
    FordNetwork.KWP2000_SLOW: 4,   # ISO 14230-4 KWP (5-baud init, 10.4 kbps)
    FordNetwork.KWP2000_FAST: 5,   # ISO 14230-4 KWP (fast init, 10.4 kbps)
    FordNetwork.HS_CAN:       6,   # ISO 15765-4 CAN (11-bit, 500 kbps)
    FordNetwork.HS_CAN_EXT:   7,   # ISO 15765-4 CAN (29-bit, 500 kbps)
    FordNetwork.MS_CAN:       8,   # MS-CAN (Ford-specific)  — adapter dependent
    FordNetwork.J1939:        9,   # ISO 15765-4 CAN (29-bit, 250 kbps)
}


PROTOCOL_INITS = (
    ProtocolInit(
        network=FordNetwork.ISO9141,
        elm_protocol_number=3,
        at_commands=("ATZ", "ATE0", "ATSP3", "ATSH 68 6A F1", "ATFI"),
        requires_ignition_cycle=True,
        description="K-line slow init — adapter pulses target address at 5 baud, "
                    "then ramps to 10.4 kbps. Requires key-on / ignition cycle on most ECUs.",
    ),
    ProtocolInit(
        network=FordNetwork.KWP2000_SLOW,
        elm_protocol_number=4,
        at_commands=("ATZ", "ATE0", "ATSP4", "ATSH 68 6A F1", "ATFI"),
        requires_ignition_cycle=True,
        description="KWP2000 with 5-baud init — same physical layer as ISO 9141 but with KWP services.",
    ),
    ProtocolInit(
        network=FordNetwork.KWP2000_FAST,
        elm_protocol_number=5,
        at_commands=("ATZ", "ATE0", "ATSP5", "ATSH 68 6A F1", "ATFI"),
        description="KWP2000 fast init — 25 ms low + 25 ms high pulse, no 5-baud handshake.",
    ),
    ProtocolInit(
        network=FordNetwork.J1850_PWM,
        elm_protocol_number=1,
        at_commands=("ATZ", "ATE0", "ATSP1"),
        description="J1850 PWM (Ford SCP) — no init handshake; messages start immediately.",
    ),
    ProtocolInit(
        network=FordNetwork.J1850_VPW,
        elm_protocol_number=2,
        at_commands=("ATZ", "ATE0", "ATSP2"),
        description="J1850 VPW — no init handshake; variable-pulse-width framing.",
    ),
    ProtocolInit(
        network=FordNetwork.HS_CAN,
        elm_protocol_number=6,
        at_commands=("ATZ", "ATE0", "ATSP6", "ATSH 7DF", "ATAR"),
        description="ISO 15765-4 (11-bit, 500 kbps) — the modern Ford default.",
    ),
    ProtocolInit(
        network=FordNetwork.HS_CAN_EXT,
        elm_protocol_number=7,
        at_commands=("ATZ", "ATE0", "ATSP7", "ATSH 18 DB 33 F1", "ATAR"),
        description="ISO 15765-4 (29-bit, 500 kbps) — used for OBD-II broadcast in J1939-style.",
    ),
    ProtocolInit(
        network=FordNetwork.MS_CAN,
        elm_protocol_number=8,
        at_commands=("ATZ", "ATE0", "ATSP8", "ATSH 7DF", "ATAR"),
        description="Ford MS-CAN @ 125 kbps — requires adapter that supports MS-CAN pin switch.",
    ),
    ProtocolInit(
        network=FordNetwork.J1939,
        elm_protocol_number=9,
        at_commands=("ATZ", "ATE0", "ATSP9", "ATSH 18 EA FF F9"),
        description="J1939 commercial-truck CAN — 29-bit @ 250 kbps, PGN addressing.",
    ),
)


def protocol_init_for(network: FordNetwork) -> Optional["ProtocolInit"]:
    """Return the ELM init descriptor for a network, or None if not supported."""
    for p in PROTOCOL_INITS:
        if p.network == network:
            return p
    return None


@dataclass
class FordModule:
    name: str
    abbreviation: str
    address: int        # lower byte of tx CAN ID (tx_id = 0x700 + address for all 11-bit Ford diag)
    network: FordNetwork
    description: str = ""
    verified: bool = False  # True iff this address/network is confirmed against the
                            # external Ford-diagnostic reverse-engineering reference.
                            # Unverified entries are best-effort and may not respond on real vehicles.

    @property
    def tx_id(self) -> int:
        return 0x700 + self.address

    @property
    def rx_id(self) -> int:
        return 0x700 + self.address + 8


# Module table — values marked `verified=True` are cross-referenced against an
# external Ford-diagnostic reverse-engineering reference. Several previous addresses
# were wrong by enough that scan_modules() was silently skipping the module on real
# vehicles (no response → exception → except: continue). That reference's index is
# partial, so absence-from-reference ≠ wrong-here; unverified entries are kept as-is.
#
# OBSERVED-BUT-UNIDENTIFIED CAN IDs (from FUN_0068f1b0 ID-equivalence routing) —
# now provisionally added below as unverified entries:
#   0x797 → gateway/router alternate (routine control via gateway)
#   0x7B0 → suspected TCM aux / pre-2010 transmission controller
#   0x791 → REWRITE_TRM service routine (TRM = Transfer Range Module)
#   0x7E6 → SOBDMC (Secondary On-Board Diagnostic Module Compressor) — hybrid/EV
#   0x7F2 → physical UDS target, module unidentified
#   0x7F3 → CAN diagnostic request target, module unidentified
# 0x7C6 stays a code-comment only — it appears to be a receive-side alternate
# (rx ≠ tx+8) which the current FordModule shape can't express cleanly.
FORD_MODULES = [
    # ── Powertrain (HS-CAN, standard OBD2-aligned addressing) ──
    FordModule("Powertrain Control Module", "PCM", 0xE0, FordNetwork.HS_CAN, verified=True),
    FordModule("Transmission Control Module", "TCM", 0xE1, FordNetwork.HS_CAN, verified=True),

    # ── Chassis / safety (HS-CAN) ──
    FordModule("Anti-Lock Brake System", "ABS", 0x20, FordNetwork.HS_CAN, verified=True),
    FordModule("Restraint Control Module", "RCM", 0x26, FordNetwork.HS_CAN, verified=True),
    FordModule("Power Steering Control Module", "PSCM", 0x30, FordNetwork.HS_CAN, verified=True),
    # EPAS is the same physical role as PSCM on later platforms but addressed separately on
    # older ones — only PSCM @ 0x730 is verified directly. Leave EPAS unverified.
    FordModule("Electric Power Steering", "EPAS", 0x62, FordNetwork.HS_CAN),

    # ── Body / convenience (mostly MS-CAN) ──
    # IPC and RCM both live at 0x726/0x720 but on different networks (verified).
    FordModule("Instrument Panel Cluster", "IPC", 0x20, FordNetwork.MS_CAN, verified=True),
    FordModule("Body Control Module", "BCM", 0x26, FordNetwork.MS_CAN, verified=True),
    FordModule("Steering Column Control Module", "SCCM", 0x24, FordNetwork.MS_CAN, verified=True),
    FordModule("Audio Control Module", "ACM", 0x27, FordNetwork.MS_CAN, verified=True),
    FordModule("Front Controls Interface Module", "FCIM", 0xC4, FordNetwork.MS_CAN, verified=True,
               description="Climate-control faceplate"),
    FordModule("Driver Door Module", "DDM", 0x31, FordNetwork.MS_CAN, verified=True),
    FordModule("Passenger Door Module", "PDM", 0x32, FordNetwork.MS_CAN, verified=True),
    FordModule("Driver Seat Module", "DSM", 0x40, FordNetwork.MS_CAN, verified=True,
               description="Power-seat memory; previously listed as SCMD"),

    # ── Network gateway (HS-CAN) ──
    FordModule("Gateway Module A", "GWM", 0x60, FordNetwork.HS_CAN, verified=True),

    # ── SYNC / infotainment ──
    # Verified: APIM is on HS-CAN at 0x7C0, NOT MS-CAN at 0x773 as previously listed.
    FordModule("SYNC / APIM", "APIM", 0xC0, FordNetwork.HS_CAN, verified=True),

    # ── Unverified entries (kept as-is, may or may not be correct per platform) ──
    FordModule("Heating Ventilation AC", "HVAC", 0x33, FordNetwork.MS_CAN),
    FordModule("Parking Aid Module", "PAM", 0x36, FordNetwork.MS_CAN, verified=True),
    FordModule("Rear Left Door Module", "RLDM", 0x42, FordNetwork.MS_CAN),
    FordModule("Rear Right Door Module", "RRDM", 0x43, FordNetwork.MS_CAN),
    FordModule("Trailer Brake Control Module", "TBC", 0x17, FordNetwork.HS_CAN),
    FordModule("4x4 Control Module", "4X4", 0x5A, FordNetwork.HS_CAN),
    FordModule("Adaptive Cruise Control", "ACC", 0x11, FordNetwork.HS_CAN),
    FordModule("Forward Sensing Camera Module", "FSCM", 0x06, FordNetwork.HS_CAN),
    FordModule("Image Processing Module A", "IPMA", 0x76, FordNetwork.MS_CAN),
    FordModule("Global Positioning System Module", "GPSM", 0x75, FordNetwork.MS_CAN),
    FordModule("Headlamp Control Module", "HCM", 0x14, FordNetwork.HS_CAN),
    FordModule("Rear View Camera", "RVC", 0x77, FordNetwork.MS_CAN),
    FordModule("Tire Pressure Monitoring System", "TPMS", 0x65, FordNetwork.HS_CAN),
    FordModule("All Wheel Drive Module", "AWD", 0x5D, FordNetwork.HS_CAN),
    FordModule("Electric Parking Brake", "EPB", 0x64, FordNetwork.HS_CAN),
    FordModule("Battery Energy Control Module", "BECM", 0x07, FordNetwork.HS_CAN),
    FordModule("Hybrid Powertrain Control Module", "HPCM", 0x08, FordNetwork.HS_CAN),
    FordModule("Seat Control Module Passenger", "SCMP", 0x45, FordNetwork.MS_CAN),
    FordModule("Remote Function Actuator", "RFA", 0x74, FordNetwork.MS_CAN),
    FordModule("Rear Differential Control Module", "RDCM", 0x5C, FordNetwork.HS_CAN),
    FordModule("Liftgate Control Module", "LGM", 0x46, FordNetwork.MS_CAN),
    FordModule("Telematic Control Module", "TCU", 0x78, FordNetwork.MS_CAN),

    # ── Hybrid / EV / Secondary OBD ──
    FordModule("Secondary On-Board Diagnostic Module", "SOBDM", 0xE6, FordNetwork.HS_CAN,
               description="Hybrid/EV secondary OBD module — referenced by SOBDMC strings"),
    FordModule("Battery Charger Control Module", "BCCM", 0x09, FordNetwork.HS_CAN,
               description="On-board AC charger control on PHEV / BEV platforms"),
    FordModule("DC-DC Converter Control Module", "DCDC", 0x0A, FordNetwork.HS_CAN,
               description="High-voltage to 12 V DC-DC converter on hybrid/EV"),
    FordModule("Hybrid Control Unit", "HCU", 0x0B, FordNetwork.HS_CAN,
               description="Hybrid powertrain coordinator (distinct from HPCM on some platforms)"),
    FordModule("Transfer Range Module", "TRM", 0x91, FordNetwork.HS_CAN,
               description="AWD/4x4 transfer case range selector; REWRITE_TRM routine target"),

    # ── Orphan addresses recovered from routing/equivalence tables ──
    # These appear in the diagnostic protocol routing logic but the originating
    # reference doesn't label the module. Kept unverified so scan_modules() can
    # probe them; the module name fields are best-effort guesses.
    FordModule("Gateway Alternate", "GWMx", 0x97, FordNetwork.HS_CAN,
               description="Secondary gateway/router CAN ID (0x797) — routine control via gateway"),
    FordModule("Unknown Module @ 0x7B0", "U7B0", 0xB0, FordNetwork.HS_CAN,
               description="Suspected TCM auxiliary / pre-2010 transmission controller variant"),
    FordModule("Unknown Module @ 0x7F2", "U7F2", 0xF2, FordNetwork.HS_CAN,
               description="Physical UDS request target — module unidentified"),
    FordModule("Unknown Module @ 0x7F3", "U7F3", 0xF3, FordNetwork.HS_CAN,
               description="CAN diagnostic request target — module unidentified"),

    # ── ADAS / driver-assist modules (newer platforms) ──
    FordModule("Side Object Detection (Left)", "SODL", 0x10, FordNetwork.HS_CAN,
               description="Blind-spot monitoring, left side"),
    FordModule("Side Object Detection (Right)", "SODR", 0x18, FordNetwork.HS_CAN,
               description="Blind-spot monitoring, right side"),
    FordModule("Lane-Keeping Assist", "LKA", 0x16, FordNetwork.HS_CAN,
               description="Lane-keeping torque actuator (paired with IPMA on later platforms)"),
    FordModule("Active Park Assist", "APA", 0x15, FordNetwork.HS_CAN,
               description="Park-assist controller (Active Park Assist 1.0 / 2.0)"),

    # ── Comfort / climate / lighting (later-platform additions) ──
    FordModule("HVAC Auxiliary", "HVACA", 0x34, FordNetwork.MS_CAN,
               description="Dual-zone / rear auxiliary HVAC controller"),
    FordModule("Steering Angle Sensor", "SASM", 0x37, FordNetwork.HS_CAN,
               description="Standalone steering-angle sensor on platforms that don't bundle it into PSCM/SCCM"),
    FordModule("Wireless Charging Module", "WACM", 0x47, FordNetwork.MS_CAN,
               description="Qi wireless phone charger control"),
    FordModule("Auto Start-Stop Module", "ASSM", 0x48, FordNetwork.HS_CAN,
               description="Idle stop-start controller (separate from PCM on some platforms)"),
]


FORD_BRANDS = {
    0x01: "Ford",
    0x02: "Mazda",
    0x03: "Lincoln",
    0x04: "Mercury",
}
