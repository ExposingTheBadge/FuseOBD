from dataclasses import dataclass
from enum import IntEnum
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
