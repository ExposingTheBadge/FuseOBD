import struct
from dataclasses import dataclass, field
from typing import Optional
from core.uds import UDSClient, UDSSession, UDSException
from core.vehicle import VehicleConnection
from core.protocols import FordModule, FORD_MODULES


@dataclass
class AsBuiltBlock:
    did: int
    data: bytes
    hex_str: str = ""

    def __post_init__(self):
        if not self.hex_str:
            self.hex_str = self.data.hex().upper()


@dataclass
class ModuleAsBuilt:
    module_name: str
    module_abbrev: str
    blocks: list[AsBuiltBlock] = field(default_factory=list)
    error: str = ""

    def to_hex_string(self) -> str:
        lines = []
        for block in self.blocks:
            lines.append(f"DID {block.did:04X}: {block.hex_str}")
        return "\n".join(lines)

    def to_forscan_format(self) -> str:
        lines = [f"; {self.module_name} ({self.module_abbrev})"]
        for block in self.blocks:
            parts = []
            data = block.data
            for i in range(0, len(data), 3):
                chunk = data[i : i + 3]
                parts.append(chunk.hex().upper())
            lines.append(f"{block.did:04X}: {'-'.join(parts)}")
        return "\n".join(lines)


ASBUILT_DID_RANGES = {
    "PCM": [(0xDE00, 0xDE1F)],
    "TCM": [(0xDE00, 0xDE0F)],
    "ABS": [(0xDE00, 0xDE0F)],
    "BCM": [(0xDE00, 0xDE3F)],
    "IPC": [(0xDE00, 0xDE1F)],
    "RCM": [(0xDE00, 0xDE07)],
    "APIM": [(0xDE00, 0xDE1F)],
    "ACM": [(0xDE00, 0xDE0F)],
    "DDM": [(0xDE00, 0xDE07)],
    "PDM": [(0xDE00, 0xDE07)],
    "HVAC": [(0xDE00, 0xDE0F)],
    "PAM": [(0xDE00, 0xDE07)],
    "EPAS": [(0xDE00, 0xDE07)],
    "GWM": [(0xDE00, 0xDE0F)],
    "HCM": [(0xDE00, 0xDE07)],
    "TPMS": [(0xDE00, 0xDE07)],
    "RFA": [(0xDE00, 0xDE0F)],
}

DEFAULT_DID_RANGE = (0xDE00, 0xDE0F)


class AsBuiltReader:
    def __init__(self, vehicle: VehicleConnection):
        self.vehicle = vehicle

    def read_module(self, module: FordModule) -> ModuleAsBuilt:
        result = ModuleAsBuilt(
            module_name=module.name,
            module_abbrev=module.abbreviation,
        )

        try:
            client = self.vehicle.get_uds_client(module)
            client.diagnostic_session(UDSSession.EXTENDED)
        except Exception as e:
            result.error = str(e)
            return result

        did_ranges = ASBUILT_DID_RANGES.get(module.abbreviation, [DEFAULT_DID_RANGE])

        for start_did, end_did in did_ranges:
            for did in range(start_did, end_did + 1):
                try:
                    data = client.read_data_by_id(did)
                    if data and any(b != 0 for b in data):
                        result.blocks.append(AsBuiltBlock(did=did, data=data))
                except (UDSException, TimeoutError):
                    break

        return result

    def read_all_modules(self, callback=None) -> list[ModuleAsBuilt]:
        results = []
        modules_to_scan = [
            m for m in FORD_MODULES
            if m.abbreviation in ASBUILT_DID_RANGES
        ]

        for i, module in enumerate(modules_to_scan):
            if callback:
                callback(module.name, i, len(modules_to_scan))
            result = self.read_module(module)
            if result.blocks:
                results.append(result)
        return results

    def write_block(self, module: FordModule, did: int, data: bytes):
        client = self.vehicle.get_uds_client(module)
        client.diagnostic_session(UDSSession.EXTENDED)
        client.write_data_by_id(did, data)

    @staticmethod
    def export_profile(modules: list[ModuleAsBuilt]) -> str:
        lines = ["; FUSE As-Built Profile", ";"]
        for mod in modules:
            lines.append(mod.to_forscan_format())
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def parse_profile(text: str) -> dict[str, list[tuple[int, bytes]]]:
        result = {}
        current_module = None
        for line in text.strip().splitlines():
            line = line.strip()
            if not line or line.startswith(";"):
                if "(" in line and ")" in line:
                    abbrev = line.split("(")[-1].split(")")[0]
                    current_module = abbrev
                    result[current_module] = []
                continue
            if ":" in line and current_module:
                did_str, data_str = line.split(":", 1)
                did = int(did_str.strip(), 16)
                hex_data = data_str.strip().replace("-", "").replace(" ", "")
                data = bytes.fromhex(hex_data)
                result[current_module].append((did, data))
        return result
