from dataclasses import dataclass, field
from core.vehicle import VehicleConnection, ModuleInfo
from core.protocols import FORD_MODULES, FordNetwork


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
                try:
                    data = client.read_data_by_id(0xF187)
                    info.part_number = data.decode("ascii", errors="replace").strip()
                except Exception:
                    pass
                found.append(info)
            except Exception:
                pass
        result.modules = found
        return result
