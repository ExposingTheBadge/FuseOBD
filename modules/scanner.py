from dataclasses import dataclass, field
from core.vehicle import VehicleConnection, ModuleInfo
from core.protocols import FORD_MODULES, FordNetwork
from core.ford_dids import (
    DID_FORD_SOFTWARE_PART_NUMBER,
    DID_FORD_CALIBRATION_ID,
    DID_FORD_ASSEMBLY_PART_NUMBER,
)


@dataclass
class ScanResult:
    modules: list[ModuleInfo] = field(default_factory=list)
    vin: str = ""
    battery_voltage: float = 0.0
    hs_can_count: int = 0
    ms_can_count: int = 0

    @property
    def total_modules(self) -> int:
        return len(self.modules)

    def get_module(self, abbreviation: str) -> ModuleInfo | None:
        for m in self.modules:
            if m.module.abbreviation == abbreviation:
                return m
        return None


class ModuleScanner:
    def __init__(self, vehicle: VehicleConnection):
        self.vehicle = vehicle

    def full_scan(self, callback=None) -> ScanResult:
        result = ScanResult()
        result.battery_voltage = self.vehicle.read_battery_voltage()
        result.vin = self.vehicle.read_vin()
        result.modules = self.vehicle.scan_modules(callback=callback)
        result.hs_can_count = sum(
            1 for m in result.modules if m.module.network == FordNetwork.HS_CAN
        )
        result.ms_can_count = sum(
            1 for m in result.modules if m.module.network == FordNetwork.MS_CAN
        )
        return result

    def quick_scan(self, module_names: list[str], callback=None) -> ScanResult:
        result = ScanResult()
        result.battery_voltage = self.vehicle.read_battery_voltage()
        targets = [m for m in FORD_MODULES if m.abbreviation in module_names]
        found = []
        for i, module in enumerate(targets):
            if callback:
                callback(module.name, i, len(targets))
            try:
                client = self.vehicle.get_uds_client(module)
                client.diagnostic_session()
                info = ModuleInfo(module=module, present=True)
                # ISO standard part number
                try:
                    data = client.read_data_by_id(0xF187)
                    info.part_number = data.decode("ascii", errors="replace").strip()
                except Exception:
                    pass
                # Ford-specific ident DIDs — most Ford modules return these
                # but leave 0xF187 empty.
                try:
                    data = client.read_data_by_id(DID_FORD_SOFTWARE_PART_NUMBER)
                    if data:
                        info.software_pn = data.hex().upper()
                except Exception:
                    pass
                try:
                    data = client.read_data_by_id(DID_FORD_CALIBRATION_ID)
                    if data:
                        info.calibration_id = data.hex().upper()
                except Exception:
                    pass
                try:
                    data = client.read_data_by_id(DID_FORD_ASSEMBLY_PART_NUMBER)
                    if data:
                        info.assembly_pn = data.decode("ascii", errors="replace").strip("\x00").strip()
                except Exception:
                    pass
                found.append(info)
            except Exception:
                pass
        result.modules = found
        return result
