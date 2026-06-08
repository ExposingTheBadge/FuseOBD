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

    def decoded_fields(self, module_abbrev: str) -> list[str]:
        """Return human-readable field annotations for this block (or [])."""
        return [s.decode(self.data) for s in schema_for(module_abbrev, self.did)]


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

    def to_asbuilt_text(self) -> str:
        """Serialize to the standard Ford .ab As-Built text format: a
        commented module header, then ``<DID>: AA-BB-CC`` lines with
        dash-separated 3-byte groups."""
        lines = [f"; {self.module_name} ({self.module_abbrev})"]
        for block in self.blocks:
            parts = []
            data = block.data
            for i in range(0, len(data), 3):
                chunk = data[i : i + 3]
                parts.append(chunk.hex().upper())
            lines.append(f"{block.did:04X}: {'-'.join(parts)}")
        return "\n".join(lines)

    def to_annotated_text(self) -> str:
        """Same as to_asbuilt_text() but also emits any per-field annotations
        from BLOCK_SCHEMAS as additional `;   field: value` comment lines."""
        lines = [f"; {self.module_name} ({self.module_abbrev})"]
        for block in self.blocks:
            parts = []
            data = block.data
            for i in range(0, len(data), 3):
                chunk = data[i : i + 3]
                parts.append(chunk.hex().upper())
            lines.append(f"{block.did:04X}: {'-'.join(parts)}")
            for ann in block.decoded_fields(self.module_abbrev):
                lines.append(f";   {ann}")
        return "\n".join(lines)

    def to_rawt_text(self) -> str:
        """Serialize to the Ford `.rawt` raw-text format — just `<DID>: HEX`
        lines with no dashes, no headers. Used by some VID tools that don't
        understand the annotated `.ab` shape."""
        return "\n".join(f"{b.did:04X}: {b.hex_str}" for b in self.blocks)


ASBUILT_DID_RANGES = {
    # ── Powertrain ──
    "PCM":   [(0xDE00, 0xDE1F)],
    "TCM":   [(0xDE00, 0xDE0F)],

    # ── Chassis / safety ──
    "ABS":   [(0xDE00, 0xDE0F)],
    "RCM":   [(0xDE00, 0xDE07)],
    "PSCM":  [(0xDE00, 0xDE07)],
    "EPAS":  [(0xDE00, 0xDE07)],
    "TBC":   [(0xDE00, 0xDE07)],
    "4X4":   [(0xDE00, 0xDE07)],
    "ACC":   [(0xDE00, 0xDE0F)],
    "AWD":   [(0xDE00, 0xDE07)],
    "EPB":   [(0xDE00, 0xDE07)],
    "RDCM":  [(0xDE00, 0xDE07)],
    "TRM":   [(0xDE00, 0xDE07)],

    # ── Body / convenience ──
    "BCM":   [(0xDE00, 0xDE7F)],  # extended on Gen 3 platforms — was 0xDE3F
    "IPC":   [(0xDE00, 0xDE3F)],
    "SCCM":  [(0xDE00, 0xDE0F)],
    "ACM":   [(0xDE00, 0xDE0F)],
    "FCIM":  [(0xDE00, 0xDE0F)],
    "DDM":   [(0xDE00, 0xDE07)],
    "PDM":   [(0xDE00, 0xDE07)],
    "DSM":   [(0xDE00, 0xDE0F)],
    "SCMP":  [(0xDE00, 0xDE0F)],
    "HVAC":  [(0xDE00, 0xDE0F)],
    "HVACA": [(0xDE00, 0xDE07)],
    "PAM":   [(0xDE00, 0xDE07)],
    "RLDM":  [(0xDE00, 0xDE07)],
    "RRDM":  [(0xDE00, 0xDE07)],
    "LGM":   [(0xDE00, 0xDE07)],
    "TCU":   [(0xDE00, 0xDE0F)],
    "RFA":   [(0xDE00, 0xDE0F)],
    "GPSM":  [(0xDE00, 0xDE0F)],
    "HCM":   [(0xDE00, 0xDE07)],
    "RVC":   [(0xDE00, 0xDE07)],
    "TPMS":  [(0xDE00, 0xDE07)],
    "WACM":  [(0xDE00, 0xDE07)],

    # ── Network / gateway / infotainment ──
    "GWM":   [(0xDE00, 0xDE0F)],
    "GWMx":  [(0xDE00, 0xDE07)],
    "APIM":  [(0xDE00, 0xDE1F)],

    # ── ADAS / driver-assist ──
    "IPMA":  [(0xDE00, 0xDE0F)],
    "FSCM":  [(0xDE00, 0xDE0F)],
    "SODL":  [(0xDE00, 0xDE07)],
    "SODR":  [(0xDE00, 0xDE07)],
    "LKA":   [(0xDE00, 0xDE07)],
    "APA":   [(0xDE00, 0xDE07)],
    "SASM":  [(0xDE00, 0xDE07)],
    "ASSM":  [(0xDE00, 0xDE07)],

    # ── Hybrid / EV ──
    "SOBDM": [(0xDE00, 0xDE0F)],
    "BCCM":  [(0xDE00, 0xDE07)],
    "DCDC":  [(0xDE00, 0xDE07)],
    "HCU":   [(0xDE00, 0xDE0F)],
    "HPCM":  [(0xDE00, 0xDE1F)],
    "BECM":  [(0xDE00, 0xDE0F)],
}

DEFAULT_DID_RANGE = (0xDE00, 0xDE0F)


# ── Field-level schemas ──
# An As-Built block is a 3-byte (or longer) payload; the meaning of each
# byte depends on the (module, DID) pair. The schema lets the UI / report
# layer pretty-print individual bytes/bits as e.g. "Region: 0x01 = North
# America", "Daytime Running Lamps: enabled (bit 2)".
#
# Schemas are kept conservative — only well-publicized field meanings are
# committed here. Users who decode additional fields on their own platform
# can extend BLOCK_SCHEMAS at runtime; the reader honours it on every read.

@dataclass(frozen=True)
class FieldSchema:
    """Annotation for a single byte or bit field within an As-Built block."""
    byte_index: int        # offset within the block payload (0-based)
    bit_mask: int = 0xFF   # which bits within the byte to read (0xFF = whole byte)
    name: str = ""
    values: dict[int, str] = field(default_factory=dict)   # raw value -> meaning

    def decode(self, payload: bytes) -> str:
        if self.byte_index >= len(payload):
            return f"{self.name}: (offset out of range)"
        raw = payload[self.byte_index] & self.bit_mask
        # Right-shift if the mask is bit-aligned (e.g. 0x04) so the value
        # printed is the bit's logical state rather than raw 0x04.
        if self.bit_mask and self.bit_mask < 0xFF:
            shift = 0
            m = self.bit_mask
            while m and not (m & 1):
                m >>= 1
                shift += 1
            raw = raw >> shift
        label = self.values.get(raw, f"0x{raw:02X}")
        return f"{self.name}: {label}"


# (module_abbrev, did) -> list of FieldSchema entries
BLOCK_SCHEMAS: dict[tuple[str, int], list[FieldSchema]] = {
    # BCM 720-01-01 region byte — first byte of the configuration block
    # commonly encodes the market/region the vehicle is built for.
    ("BCM", 0xDE00): [
        FieldSchema(byte_index=0, name="Market/Region", values={
            0x00: "Unconfigured", 0x01: "North America", 0x02: "Europe",
            0x03: "Asia Pacific", 0x04: "South America", 0x05: "Middle East",
            0x06: "Africa", 0x07: "ROW",
        }),
    ],
    # IPC primary block — units / language byte.
    ("IPC", 0xDE00): [
        FieldSchema(byte_index=0, name="Units",
                    values={0x00: "Metric (km/h, L)", 0x01: "Imperial (mph, gal)", 0x02: "Mixed"}),
    ],
}


def schema_for(module_abbrev: str, did: int) -> list[FieldSchema]:
    """Look up the field schema for a (module, DID) pair. Empty list if none."""
    return BLOCK_SCHEMAS.get((module_abbrev, did), [])


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
        except Exception as e:
            result.error = str(e)
            return result

        # Best-effort extended session — pre-2008 Ford modules NRC every
        # standard DSC subfunction but still respond to $22 reads in the
        # implicit default session. Don't abort the read just because
        # DSC failed; let the actual DID requests speak for themselves.
        for s in (UDSSession.EXTENDED, UDSSession.FORD_DIAG,
                  UDSSession.FORD_LEGACY_C0, UDSSession.FORD_LEGACY_81):
            try:
                client.diagnostic_session(s)
                break
            except Exception:
                continue

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
        # Best-effort DSC — CD3 NRCs every subfunction but writes may
        # still go through. Let the write report its own error.
        for s in (UDSSession.EXTENDED, UDSSession.FORD_DIAG,
                  UDSSession.FORD_LEGACY_C0, UDSSession.FORD_LEGACY_81):
            try:
                client.diagnostic_session(s)
                break
            except Exception:
                continue
        client.write_data_by_id(did, data)

    @staticmethod
    def export_profile(modules: list[ModuleAsBuilt]) -> str:
        lines = ["; FUSE As-Built Profile", ";"]
        for mod in modules:
            lines.append(mod.to_asbuilt_text())
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
