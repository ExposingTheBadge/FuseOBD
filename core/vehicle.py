import struct
import time
from dataclasses import dataclass, field
from typing import Optional
from core.j2534 import J2534, J2534Device, Protocol, FilterType
from core.protocols import (
    NetworkConfig, FordNetwork, FordModule, FORD_MODULES,
    FORD_HS_CAN, FORD_MS_CAN, FORD_BRANDS,
)
from core.uds import UDSClient, UDSSession, UDSException, NRC


@dataclass
class ModuleInfo:
    module: FordModule
    present: bool = False
    part_number: str = ""
    hardware_pn: str = ""
    software_pn: str = ""
    vin: str = ""
    raw_data: dict = field(default_factory=dict)


@dataclass
class VehicleInfo:
    vin: str = ""
    brand: str = ""
    brand_code: int = 0
    model_year: int = 0
    modules: list[ModuleInfo] = field(default_factory=list)
    battery_voltage: float = 0.0


class VehicleConnection:
    def __init__(self, j2534: J2534):
        self.j2534 = j2534
        self.hs_channel: Optional[int] = None
        self.ms_channel: Optional[int] = None
        self.vehicle_info = VehicleInfo()
        self._uds_clients: dict[int, UDSClient] = {}

    def connect_hs_can(self):
        self.hs_channel = self.j2534.connect(Protocol.ISO15765, 0, 500000)

    def connect_ms_can(self):
        self.ms_channel = self.j2534.connect(Protocol.ISO15765, 0, 125000)

    def disconnect_all(self):
        for client in self._uds_clients.values():
            client.disconnect()
        self._uds_clients.clear()
        if self.hs_channel is not None:
            try:
                self.j2534.disconnect(self.hs_channel)
            except Exception:
                pass
            self.hs_channel = None
        if self.ms_channel is not None:
            try:
                self.j2534.disconnect(self.ms_channel)
            except Exception:
                pass
            self.ms_channel = None

    def get_uds_client(self, module: FordModule) -> UDSClient:
        if module.address in self._uds_clients:
            return self._uds_clients[module.address]
        network = FORD_HS_CAN if module.network == FordNetwork.HS_CAN else FORD_MS_CAN
        client = UDSClient(self.j2534, network, module.tx_id, module.rx_id)
        client.connect()
        self._uds_clients[module.address] = client
        return client

    def scan_modules(self, callback=None) -> list[ModuleInfo]:
        found = []
        for i, module in enumerate(FORD_MODULES):
            if callback:
                callback(module.name, i, len(FORD_MODULES))
            try:
                client = self.get_uds_client(module)
                client.diagnostic_session(UDSSession.DEFAULT)
                info = ModuleInfo(module=module, present=True)
                try:
                    data = client.read_data_by_id(0xF188)
                    info.software_pn = data.decode("ascii", errors="replace").strip()
                except (UDSException, TimeoutError):
                    pass
                try:
                    data = client.read_data_by_id(0xF191)
                    info.hardware_pn = data.decode("ascii", errors="replace").strip()
                except (UDSException, TimeoutError):
                    pass
                try:
                    data = client.read_data_by_id(0xF187)
                    info.part_number = data.decode("ascii", errors="replace").strip()
                except (UDSException, TimeoutError):
                    pass
                found.append(info)
            except Exception:
                client_to_remove = self._uds_clients.pop(module.address, None)
                if client_to_remove:
                    try:
                        client_to_remove.disconnect()
                    except Exception:
                        pass
        self.vehicle_info.modules = found
        return found

    def read_vin(self) -> str:
        for module in FORD_MODULES:
            if module.abbreviation in ("PCM", "BCM", "IPC"):
                try:
                    client = self.get_uds_client(module)
                    data = client.read_data_by_id(0xF190)
                    vin = data.decode("ascii", errors="replace").strip("\x00").strip()
                    if len(vin) == 17:
                        self.vehicle_info.vin = vin
                        return vin
                except Exception:
                    pass
        return ""

    def read_battery_voltage(self) -> float:
        v = self.j2534.read_battery_voltage()
        self.vehicle_info.battery_voltage = v
        return v
