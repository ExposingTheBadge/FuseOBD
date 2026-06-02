from dataclasses import dataclass
from enum import IntEnum
from core.j2534 import Protocol, ConnectFlag


class FordNetwork(IntEnum):
    HS_CAN = 1
    MS_CAN = 2
    HS_CAN_EXT = 3
    ISO = 4
    SCP = 5


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
]


FORD_BRANDS = {
    0x01: "Ford",
    0x02: "Mazda",
    0x03: "Lincoln",
    0x04: "Mercury",
}
