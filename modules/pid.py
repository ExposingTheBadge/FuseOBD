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


STANDARD_PIDS: list[PIDDefinition] = [
    PIDDefinition(0xF40C, "Engine RPM", "RPM", "PCM", 0, 16383, bytes_count=2, scale=0.25),
    PIDDefinition(0xF40D, "Vehicle Speed", "mph", "PCM", 0, 158, bytes_count=1, scale=0.621371),
    PIDDefinition(0xF405, "Engine Coolant Temp", "°F", "PCM", -40, 419, bytes_count=1, scale=1.8, offset=-40),
    PIDDefinition(0xF40F, "Intake Air Temp", "°F", "PCM", -40, 419, bytes_count=1, scale=1.8, offset=-40),
    PIDDefinition(0xF404, "Engine Load", "%", "PCM", 0, 100, bytes_count=1, scale=100/255),
    PIDDefinition(0xF411, "Throttle Position", "%", "PCM", 0, 100, bytes_count=1, scale=100/255),
    PIDDefinition(0xF40B, "Intake Manifold Pressure", "kPa", "PCM", 0, 255, bytes_count=1),
    PIDDefinition(0xF40E, "Timing Advance", "°", "PCM", -64, 63.5, bytes_count=1, scale=0.5, offset=-64),
    PIDDefinition(0xF40A, "Fuel Pressure", "kPa", "PCM", 0, 765, bytes_count=1, scale=3),
    PIDDefinition(0xF406, "Short Term Fuel Trim", "%", "PCM", -100, 99.2, bytes_count=1, scale=100/128, offset=-100, signed=True),
    PIDDefinition(0xF407, "Long Term Fuel Trim", "%", "PCM", -100, 99.2, bytes_count=1, scale=100/128, offset=-100, signed=True),
    PIDDefinition(0xF442, "Control Module Voltage", "V", "PCM", 0, 65.535, bytes_count=2, scale=0.001),
    PIDDefinition(0xF446, "Ambient Air Temp", "°F", "PCM", -40, 419, bytes_count=1, scale=1.8, offset=-40),
    PIDDefinition(0xF44F, "Runtime Since Start", "s", "PCM", 0, 65535, bytes_count=2),
    PIDDefinition(0xF431, "Distance Since Clear", "mi", "PCM", 0, 40722, bytes_count=2, scale=0.621371),
    PIDDefinition(0xF41F, "Runtime Since Clear", "s", "PCM", 0, 65535, bytes_count=2),
    PIDDefinition(0xF45C, "Oil Temperature", "°F", "PCM", -40, 410, bytes_count=1, scale=1.8, offset=-40),
    PIDDefinition(0xF449, "Accel Pedal Position", "%", "PCM", 0, 100, bytes_count=1, scale=100/255),
    PIDDefinition(0xF451, "Fuel Type", "", "PCM", bytes_count=1),
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
            module = self._find_module(pid.module)
            if not module:
                continue
            try:
                client = self.vehicle.get_uds_client(module)
                data = client.read_data_by_id(pid.did)
                if data:
                    raw, value = decode_pid_value(pid, data)
                    reading = PIDReading(
                        pid=pid, raw_value=raw, value=value, timestamp=time.time()
                    )
                    results[pid.did] = reading
            except (UDSException, TimeoutError, Exception):
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
