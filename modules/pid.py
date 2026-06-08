import struct
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable
from core.uds import UDSClient, UDSSession, UDSException
from core.vehicle import VehicleConnection
from core.protocols import FordModule, FORD_MODULES


@dataclass
class PIDDefinition:
    did: int
    name: str
    unit: str
    module: str
    min_val: float = 0
    max_val: float = 0
    formula: str = "raw"
    bytes_count: int = 2
    signed: bool = False
    scale: float = 1.0
    offset: float = 0.0
    description: str = ""


@dataclass
class PIDReading:
    pid: PIDDefinition
    raw_value: int = 0
    value: float = 0.0
    timestamp: float = 0.0

    @property
    def display_value(self) -> str:
        if self.pid.unit in ("", "raw"):
            return f"0x{self.raw_value:04X}"
        if self.value == int(self.value):
            return f"{int(self.value)} {self.pid.unit}"
        return f"{self.value:.1f} {self.pid.unit}"


# ── SAE J1979 OBD-II Mode $01 PIDs (accessed via Ford's 0xF4xx DID alias) ──
# Ford exposes every standard Mode $01 PID as UDS DID 0xF400 + PID, so the same
# UDSClient.read_data_by_id() path that reads ident data also reads live PIDs.
# Coverage is the well-supported subset of J1979 (PIDs 0x01-0x66) — bitmaps and
# rare PIDs use unit="" so display falls back to raw hex. Temperatures convert
# to °F (raw → °C with -40 offset → °F via the combined scale/offset trick:
# value = raw*1.8 - 40 yields °F directly). Speeds convert to mph.
STANDARD_PIDS: list[PIDDefinition] = [
    # ── PID support bitmaps (raw hex) ──
    PIDDefinition(0xF400, "PIDs Supported [01-20]",      "", "PCM", bytes_count=4),
    PIDDefinition(0xF420, "PIDs Supported [21-40]",      "", "PCM", bytes_count=4),
    PIDDefinition(0xF440, "PIDs Supported [41-60]",      "", "PCM", bytes_count=4),
    PIDDefinition(0xF460, "PIDs Supported [61-80]",      "", "PCM", bytes_count=4),

    # ── Monitor / fuel system status (bitmap, display raw) ──
    PIDDefinition(0xF401, "Monitor Status (since clear)","", "PCM", bytes_count=4),
    PIDDefinition(0xF402, "Freeze-Frame DTC",            "", "PCM", bytes_count=2),
    PIDDefinition(0xF403, "Fuel System Status",          "", "PCM", bytes_count=2),

    # ── Engine load / temps / fuel trims ──
    PIDDefinition(0xF404, "Engine Load",                 "%",   "PCM", 0, 100,   bytes_count=1, scale=100/255),
    PIDDefinition(0xF405, "Engine Coolant Temp",         "°F",  "PCM", -40, 419, bytes_count=1, scale=1.8, offset=-40),
    PIDDefinition(0xF406, "Short Term Fuel Trim (B1)",   "%",   "PCM", -100, 99.2, bytes_count=1, scale=100/128, offset=-100),
    PIDDefinition(0xF407, "Long Term Fuel Trim (B1)",    "%",   "PCM", -100, 99.2, bytes_count=1, scale=100/128, offset=-100),
    PIDDefinition(0xF408, "Short Term Fuel Trim (B2)",   "%",   "PCM", -100, 99.2, bytes_count=1, scale=100/128, offset=-100),
    PIDDefinition(0xF409, "Long Term Fuel Trim (B2)",    "%",   "PCM", -100, 99.2, bytes_count=1, scale=100/128, offset=-100),
    PIDDefinition(0xF40A, "Fuel Pressure",               "kPa", "PCM", 0, 765,   bytes_count=1, scale=3),
    PIDDefinition(0xF40B, "Intake Manifold Pressure",    "kPa", "PCM", 0, 255,   bytes_count=1),
    PIDDefinition(0xF40C, "Engine RPM",                  "RPM", "PCM", 0, 16383, bytes_count=2, scale=0.25),
    PIDDefinition(0xF40D, "Vehicle Speed",               "mph", "PCM", 0, 158,   bytes_count=1, scale=0.621371),
    PIDDefinition(0xF40E, "Timing Advance",              "°",   "PCM", -64, 63.5,bytes_count=1, scale=0.5, offset=-64),
    PIDDefinition(0xF40F, "Intake Air Temp",             "°F",  "PCM", -40, 419, bytes_count=1, scale=1.8, offset=-40),
    PIDDefinition(0xF410, "MAF Air Flow Rate",           "g/s", "PCM", 0, 655.35,bytes_count=2, scale=0.01),
    PIDDefinition(0xF411, "Throttle Position",           "%",   "PCM", 0, 100,   bytes_count=1, scale=100/255),
    PIDDefinition(0xF412, "Commanded Secondary Air",     "",    "PCM", bytes_count=1),
    PIDDefinition(0xF413, "O2 Sensors Present (2-bank)", "",    "PCM", bytes_count=1),

    # ── O2 sensors (banks 1-2, sensors 1-4 each) — raw voltage + STFT byte ──
    PIDDefinition(0xF414, "O2 Sensor B1S1 Voltage",      "V",   "PCM", 0, 1.275, bytes_count=2, scale=0.005),
    PIDDefinition(0xF415, "O2 Sensor B1S2 Voltage",      "V",   "PCM", 0, 1.275, bytes_count=2, scale=0.005),
    PIDDefinition(0xF416, "O2 Sensor B1S3 Voltage",      "V",   "PCM", 0, 1.275, bytes_count=2, scale=0.005),
    PIDDefinition(0xF417, "O2 Sensor B1S4 Voltage",      "V",   "PCM", 0, 1.275, bytes_count=2, scale=0.005),
    PIDDefinition(0xF418, "O2 Sensor B2S1 Voltage",      "V",   "PCM", 0, 1.275, bytes_count=2, scale=0.005),
    PIDDefinition(0xF419, "O2 Sensor B2S2 Voltage",      "V",   "PCM", 0, 1.275, bytes_count=2, scale=0.005),
    PIDDefinition(0xF41A, "O2 Sensor B2S3 Voltage",      "V",   "PCM", 0, 1.275, bytes_count=2, scale=0.005),
    PIDDefinition(0xF41B, "O2 Sensor B2S4 Voltage",      "V",   "PCM", 0, 1.275, bytes_count=2, scale=0.005),

    PIDDefinition(0xF41C, "OBD Standard",                "",    "PCM", bytes_count=1),
    PIDDefinition(0xF41D, "O2 Sensors Present (4-bank)", "",    "PCM", bytes_count=1),
    PIDDefinition(0xF41E, "Aux Input Status",            "",    "PCM", bytes_count=1),
    PIDDefinition(0xF41F, "Runtime Since Engine Start",  "s",   "PCM", 0, 65535, bytes_count=2),

    # ── Distance / MIL / fuel-rail ──
    PIDDefinition(0xF421, "Distance With MIL On",        "mi",  "PCM", 0, 40722, bytes_count=2, scale=0.621371),
    PIDDefinition(0xF422, "Fuel Rail Pressure (rel)",    "kPa", "PCM", 0, 5177,  bytes_count=2, scale=0.079),
    PIDDefinition(0xF423, "Fuel Rail Gauge Pressure",    "kPa", "PCM", 0, 655350,bytes_count=2, scale=10),

    # ── Wide-range O2 sensors (equivalence ratio) ──
    PIDDefinition(0xF424, "O2 B1S1 Wide λ",              "",    "PCM", bytes_count=4),
    PIDDefinition(0xF425, "O2 B1S2 Wide λ",              "",    "PCM", bytes_count=4),
    PIDDefinition(0xF426, "O2 B1S3 Wide λ",              "",    "PCM", bytes_count=4),
    PIDDefinition(0xF427, "O2 B1S4 Wide λ",              "",    "PCM", bytes_count=4),
    PIDDefinition(0xF428, "O2 B2S1 Wide λ",              "",    "PCM", bytes_count=4),
    PIDDefinition(0xF429, "O2 B2S2 Wide λ",              "",    "PCM", bytes_count=4),
    PIDDefinition(0xF42A, "O2 B2S3 Wide λ",              "",    "PCM", bytes_count=4),
    PIDDefinition(0xF42B, "O2 B2S4 Wide λ",              "",    "PCM", bytes_count=4),

    # ── EGR / EVAP / fuel tank ──
    PIDDefinition(0xF42C, "Commanded EGR",               "%",   "PCM", 0, 100,   bytes_count=1, scale=100/255),
    PIDDefinition(0xF42D, "EGR Error",                   "%",   "PCM", -100, 99.2,bytes_count=1, scale=100/128, offset=-100),
    PIDDefinition(0xF42E, "Commanded Evap Purge",        "%",   "PCM", 0, 100,   bytes_count=1, scale=100/255),
    PIDDefinition(0xF42F, "Fuel Tank Level",             "%",   "PCM", 0, 100,   bytes_count=1, scale=100/255),
    PIDDefinition(0xF430, "Warm-ups Since Clear",        "",    "PCM", 0, 255,   bytes_count=1),
    PIDDefinition(0xF431, "Distance Since Clear",        "mi",  "PCM", 0, 40722, bytes_count=2, scale=0.621371),
    PIDDefinition(0xF432, "Evap Vapor Pressure",         "Pa",  "PCM", -8192, 8191, bytes_count=2, signed=True, scale=0.25),
    PIDDefinition(0xF433, "Barometric Pressure",         "kPa", "PCM", 0, 255,   bytes_count=1),

    # ── Wide-range O2 sensors (current) ──
    PIDDefinition(0xF434, "O2 B1S1 Wide λ + Current",    "",    "PCM", bytes_count=4),
    PIDDefinition(0xF435, "O2 B1S2 Wide λ + Current",    "",    "PCM", bytes_count=4),
    PIDDefinition(0xF436, "O2 B1S3 Wide λ + Current",    "",    "PCM", bytes_count=4),
    PIDDefinition(0xF437, "O2 B1S4 Wide λ + Current",    "",    "PCM", bytes_count=4),
    PIDDefinition(0xF438, "O2 B2S1 Wide λ + Current",    "",    "PCM", bytes_count=4),
    PIDDefinition(0xF439, "O2 B2S2 Wide λ + Current",    "",    "PCM", bytes_count=4),
    PIDDefinition(0xF43A, "O2 B2S3 Wide λ + Current",    "",    "PCM", bytes_count=4),
    PIDDefinition(0xF43B, "O2 B2S4 Wide λ + Current",    "",    "PCM", bytes_count=4),

    # ── Catalyst temps ──
    PIDDefinition(0xF43C, "Catalyst Temp B1S1",          "°F",  "PCM", -40, 11797,bytes_count=2, scale=0.18, offset=-40),
    PIDDefinition(0xF43D, "Catalyst Temp B2S1",          "°F",  "PCM", -40, 11797,bytes_count=2, scale=0.18, offset=-40),
    PIDDefinition(0xF43E, "Catalyst Temp B1S2",          "°F",  "PCM", -40, 11797,bytes_count=2, scale=0.18, offset=-40),
    PIDDefinition(0xF43F, "Catalyst Temp B2S2",          "°F",  "PCM", -40, 11797,bytes_count=2, scale=0.18, offset=-40),

    # ── Monitor / voltage / load / equivalence / pedal ──
    PIDDefinition(0xF441, "Monitor Status (this cycle)", "",    "PCM", bytes_count=4),
    PIDDefinition(0xF442, "Control Module Voltage",      "V",   "PCM", 0, 65.535,bytes_count=2, scale=0.001),
    PIDDefinition(0xF443, "Absolute Load Value",         "%",   "PCM", 0, 25700, bytes_count=2, scale=100/255),
    PIDDefinition(0xF444, "Commanded Equivalence Ratio", "",    "PCM", 0, 2,     bytes_count=2, scale=2/65536),
    PIDDefinition(0xF445, "Relative Throttle Position",  "%",   "PCM", 0, 100,   bytes_count=1, scale=100/255),
    PIDDefinition(0xF446, "Ambient Air Temp",            "°F",  "PCM", -40, 419, bytes_count=1, scale=1.8, offset=-40),
    PIDDefinition(0xF447, "Absolute Throttle Pos B",     "%",   "PCM", 0, 100,   bytes_count=1, scale=100/255),
    PIDDefinition(0xF448, "Absolute Throttle Pos C",     "%",   "PCM", 0, 100,   bytes_count=1, scale=100/255),
    PIDDefinition(0xF449, "Accel Pedal Position D",      "%",   "PCM", 0, 100,   bytes_count=1, scale=100/255),
    PIDDefinition(0xF44A, "Accel Pedal Position E",      "%",   "PCM", 0, 100,   bytes_count=1, scale=100/255),
    PIDDefinition(0xF44B, "Accel Pedal Position F",      "%",   "PCM", 0, 100,   bytes_count=1, scale=100/255),
    PIDDefinition(0xF44C, "Commanded Throttle Actuator", "%",   "PCM", 0, 100,   bytes_count=1, scale=100/255),
    PIDDefinition(0xF44D, "Time Run With MIL On",        "min", "PCM", 0, 65535, bytes_count=2),
    PIDDefinition(0xF44E, "Time Since Codes Cleared",    "min", "PCM", 0, 65535, bytes_count=2),
    PIDDefinition(0xF44F, "Max Sensor Reference Values", "",    "PCM", bytes_count=4),
    PIDDefinition(0xF450, "Max MAF Sensor Air Flow",     "g/s", "PCM", 0, 2550,  bytes_count=4, scale=10),
    PIDDefinition(0xF451, "Fuel Type",                   "",    "PCM", bytes_count=1),
    PIDDefinition(0xF452, "Ethanol Fuel %",              "%",   "PCM", 0, 100,   bytes_count=1, scale=100/255),
    PIDDefinition(0xF453, "Absolute Evap Vapor Pressure","kPa", "PCM", 0, 327.675,bytes_count=2, scale=0.005),
    PIDDefinition(0xF454, "Evap Vapor Pressure (signed)","Pa",  "PCM", -32767, 32767, bytes_count=2, signed=True),
    PIDDefinition(0xF455, "STFT (secondary O2 B1+B3)",   "%",   "PCM", -100, 99.2,bytes_count=2, scale=100/128, offset=-100),
    PIDDefinition(0xF456, "LTFT (secondary O2 B1+B3)",   "%",   "PCM", -100, 99.2,bytes_count=2, scale=100/128, offset=-100),
    PIDDefinition(0xF457, "STFT (secondary O2 B2+B4)",   "%",   "PCM", -100, 99.2,bytes_count=2, scale=100/128, offset=-100),
    PIDDefinition(0xF458, "LTFT (secondary O2 B2+B4)",   "%",   "PCM", -100, 99.2,bytes_count=2, scale=100/128, offset=-100),
    PIDDefinition(0xF459, "Fuel Rail Absolute Pressure", "kPa", "PCM", 0, 655350,bytes_count=2, scale=10),
    PIDDefinition(0xF45A, "Relative Accel Pedal Pos",    "%",   "PCM", 0, 100,   bytes_count=1, scale=100/255),
    PIDDefinition(0xF45B, "Hybrid Battery Remaining",    "%",   "PCM", 0, 100,   bytes_count=1, scale=100/255),
    PIDDefinition(0xF45C, "Engine Oil Temperature",      "°F",  "PCM", -40, 419, bytes_count=1, scale=1.8, offset=-40),
    PIDDefinition(0xF45D, "Fuel Injection Timing",       "°",   "PCM", -210, 301.992,bytes_count=2, scale=1/128, offset=-210),
    PIDDefinition(0xF45E, "Engine Fuel Rate",            "L/h", "PCM", 0, 3212.75,bytes_count=2, scale=0.05),
    PIDDefinition(0xF45F, "Emission Requirements",       "",    "PCM", bytes_count=1),

    # ── Torque / aux IO ──
    PIDDefinition(0xF461, "Driver Demand % Torque",      "%",   "PCM", -125, 130,bytes_count=1, offset=-125),
    PIDDefinition(0xF462, "Actual Engine % Torque",      "%",   "PCM", -125, 130,bytes_count=1, offset=-125),
    PIDDefinition(0xF463, "Engine Reference Torque",     "Nm",  "PCM", 0, 65535, bytes_count=2),
    PIDDefinition(0xF464, "Engine % Torque Data",        "",    "PCM", bytes_count=5),
    PIDDefinition(0xF465, "Auxiliary I/O Status",        "",    "PCM", bytes_count=2),
    PIDDefinition(0xF466, "Mass Air Flow Sensor",        "g/s", "PCM", 0, 2047.96,bytes_count=5, scale=0.03125),
]

FORD_EXTENDED_PIDS: list[PIDDefinition] = [
    PIDDefinition(0x2003, "Trans Fluid Temp", "°F", "TCM", -40, 419, bytes_count=2, scale=0.18, offset=-40),
    PIDDefinition(0x2004, "Current Gear", "", "TCM", 0, 10, bytes_count=1),
    PIDDefinition(0x4210, "Battery State of Charge", "%", "BCM", 0, 100, bytes_count=1),
    PIDDefinition(0x4211, "Battery Voltage", "V", "BCM", 0, 20, bytes_count=2, scale=0.01),
    PIDDefinition(0x2100, "Odometer", "mi", "IPC", 0, 621371, bytes_count=4, scale=0.0621371),
    PIDDefinition(0x2101, "Fuel Level", "%", "IPC", 0, 100, bytes_count=1, scale=100/255),
]


def decode_pid_value(pid: PIDDefinition, data: bytes) -> tuple[int, float]:
    raw_bytes = data[: pid.bytes_count]
    if pid.signed:
        raw = int.from_bytes(raw_bytes, "big", signed=True)
    else:
        raw = int.from_bytes(raw_bytes, "big")
    value = raw * pid.scale + pid.offset
    return raw, value


class PIDMonitor:
    def __init__(self, vehicle: VehicleConnection):
        self.vehicle = vehicle
        self.active_pids: list[PIDDefinition] = []
        self.readings: dict[int, PIDReading] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._callback: Optional[Callable[[dict[int, PIDReading]], None]] = None
        self._interval = 0.1

    def add_pid(self, pid: PIDDefinition):
        with self._lock:
            if pid.did not in [p.did for p in self.active_pids]:
                self.active_pids.append(pid)

    def remove_pid(self, did: int):
        with self._lock:
            self.active_pids = [p for p in self.active_pids if p.did != did]
            self.readings.pop(did, None)

    def clear_pids(self):
        with self._lock:
            self.active_pids.clear()
            self.readings.clear()

    def start(self, callback: Optional[Callable] = None, interval: float = 0.1):
        self._callback = callback
        self._interval = interval
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def read_once(self) -> dict[int, PIDReading]:
        results = {}
        with self._lock:
            pids_to_read = list(self.active_pids)

        for pid in pids_to_read:
            data = None
            # DIDs in the 0xF4XX range are the UDS Mode 22 mapping of
            # SAE J1979 Mode 01 PIDs (DID 0xF40C == Mode 01 PID 0x0C,
            # etc.). On older Ford modules — and most non-Ford
            # vehicles — the directed UDS read to a specific module
            # address returns NRC, but the Mode 01 broadcast to 0x7DF
            # always works because that's the OBD-II compliance path.
            # Try broadcast first for any F4XX PID.
            if 0xF400 <= pid.did <= 0xF4FF:
                try:
                    data = self.vehicle.read_obd_pid_broadcast(pid.did & 0xFF)
                except Exception:
                    data = None
            if data is None:
                module = self._find_module(pid.module)
                if module is None:
                    continue
                try:
                    client = self.vehicle.get_uds_client(module)
                    data = client.read_data_by_id(pid.did)
                except (UDSException, TimeoutError, Exception):
                    data = None
            if data:
                try:
                    raw, value = decode_pid_value(pid, data)
                    reading = PIDReading(
                        pid=pid, raw_value=raw, value=value, timestamp=time.time()
                    )
                    results[pid.did] = reading
                except Exception:
                    pass

        with self._lock:
            self.readings.update(results)
        return results

    def _monitor_loop(self):
        while self._running:
            readings = self.read_once()
            if self._callback and readings:
                self._callback(readings)
            time.sleep(self._interval)

    def _find_module(self, abbrev: str) -> Optional[FordModule]:
        for m in FORD_MODULES:
            if m.abbreviation == abbrev:
                return m
        return None

    def get_all_available_pids(self) -> list[PIDDefinition]:
        return STANDARD_PIDS + FORD_EXTENDED_PIDS

    @property
    def is_running(self) -> bool:
        return self._running
