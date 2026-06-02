import struct
import time
from dataclasses import dataclass, field
from typing import Optional
from core.j2534 import J2534, J2534Device, Protocol, FilterType, ConnectFlag
from core.protocols import (
    NetworkConfig, FordNetwork, FordModule, FORD_MODULES,
    FORD_HS_CAN, FORD_MS_CAN, FORD_BRANDS,
)
from core.uds import UDSClient, UDSSession, UDSException, NRC
from core.ford_dids import (
    DID_FORD_SOFTWARE_PART_NUMBER,
    DID_FORD_CALIBRATION_ID,
    DID_FORD_ASSEMBLY_PART_NUMBER,
    DID_FORD_VEHICLE_MARK_1,
    DID_FORD_VEHICLE_MARK_2,
    DID_FORD_VEHICLE_MARK_3,
    DID_FORD_VEHICLE_MARK_4,
    DID_FORD_VEHICLE_CONFIGURATION,
)


@dataclass
class ModuleInfo:
    module: FordModule
    present: bool = False
    part_number: str = ""
    hardware_pn: str = ""
    software_pn: str = ""
    calibration_id: str = ""     # Ford DID 0xE219
    assembly_pn: str = ""        # Ford DID 0xE21A (ASCII, e.g. "WM5F")
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
        # Key by (network, address) — after the verified address corrections, RCM
        # (HS-CAN @ 0x726) and BCM (MS-CAN @ 0x726) share the same lower byte. A plain
        # address key collides between them.
        key = (module.network, module.address)
        if key in self._uds_clients:
            return self._uds_clients[key]
        network = FORD_HS_CAN if module.network == FordNetwork.HS_CAN else FORD_MS_CAN
        client = UDSClient(self.j2534, network, module.tx_id, module.rx_id)
        client.connect()
        self._uds_clients[key] = client
        return client

    def scan_modules(self, callback=None) -> list[ModuleInfo]:
        found = []
        for i, module in enumerate(FORD_MODULES):
            if callback:
                callback(module.name, i, len(FORD_MODULES))
            try:
                client = self.get_uds_client(module)
                client.diagnostic_session(UDSSession.FORD_DIAG)
                info = ModuleInfo(module=module, present=True)

                # ISO 14229 standard ident DIDs — empty on most Ford modules
                # but populated on standards-compliant ones (SYNC4/Sync 3+).
                for did, attr in (
                    (0xF188, "software_pn"),
                    (0xF191, "hardware_pn"),
                    (0xF187, "part_number"),
                ):
                    try:
                        data = client.read_data_by_id(did)
                        setattr(info, attr, data.decode("ascii", errors="replace").strip())
                    except (UDSException, TimeoutError):
                        pass

                # Ford-specific ident DIDs — preferred on PCM and most Ford
                # body modules. Only overwrite the ISO fields if they were
                # empty (don't clobber genuine standards-compliant data).
                try:
                    data = client.read_data_by_id(DID_FORD_SOFTWARE_PART_NUMBER)
                    if data and not info.software_pn:
                        info.software_pn = data.hex().upper()
                except (UDSException, TimeoutError):
                    pass
                try:
                    data = client.read_data_by_id(DID_FORD_CALIBRATION_ID)
                    if data:
                        info.calibration_id = data.hex().upper()
                except (UDSException, TimeoutError):
                    pass
                try:
                    data = client.read_data_by_id(DID_FORD_ASSEMBLY_PART_NUMBER)
                    if data:
                        info.assembly_pn = data.decode("ascii", errors="replace").strip("\x00").strip()
                except (UDSException, TimeoutError):
                    pass

                found.append(info)
            except Exception:
                client_to_remove = self._uds_clients.pop((module.network, module.address), None)
                if client_to_remove:
                    try:
                        client_to_remove.disconnect()
                    except Exception:
                        pass
        self.vehicle_info.modules = found
        return found

    def read_vin(self) -> str:
        # ── Method 1: UDS DIDs (primary — don't disrupt CAN state first) ──
        vin_dids = [0xF190, 0xF110, 0xF18C]
        sessions = [UDSSession.EXTENDED, UDSSession.FORD_DIAG, UDSSession.DEFAULT]
        priority = ("PCM", "IPC", "BCM", "GWM")
        for module in FORD_MODULES:
            if module.abbreviation not in priority:
                continue
            for session in sessions:
                for did in vin_dids:
                    try:
                        client = self.get_uds_client(module)
                        try:
                            client.diagnostic_session(session)
                        except Exception:
                            continue
                        data = client.read_data_by_id(did)
                        vin = data.decode("ascii", errors="replace").strip("\x00").strip()
                        if len(vin) == 17:
                            self.vehicle_info.vin = vin
                            return vin
                    except Exception:
                        continue

        # ── Method 2: OBD Mode 09 PID 02 (fallback — try last since it resets CAN state) ──
        try:
            data = self._obd_request(b"\x09\x02")
            if data and len(data) > 3 and data[0:2] == b"\x49\x02":
                vin = data[3:].decode("ascii", errors="replace").strip("\x00").strip()
                if len(vin) == 17:
                    self.vehicle_info.vin = vin
                    return vin
        except Exception:
            pass
        return ""

    def _obd_request(self, payload: bytes, timeout_ms: int = 1000) -> Optional[bytes]:
        """Send a raw OBD-II request: set broadcast header 0x7DF, send Mode/PID, read 0x7E8."""
        try:
            # Force protocol 6 (ISO 15765-4, 11-bit, 500k) and set OBD broadcast header
            self.j2534._elm_cmd(self.j2534._stream, "ATSP6", 600)
            self.j2534._elm_cmd(self.j2534._stream, "ATSH 7DF", 400)
            self.j2534._elm_cmd(self.j2534._stream, "ATAR", 200)
            # Send the OBD request as hex (e.g., "0902")
            import time
            hex_cmd = payload.hex().upper()
            self.j2534._stream.write(hex_cmd.encode() + b"\r")
            time.sleep(0.05)
            # Read response
            resp = self.j2534._elm_cmd(self.j2534._stream, "", timeout_ms)
            # Parse: should contain "49 02 01 XX XX ..."
            if resp and "49" in resp and "02" in resp:
                parts = resp.strip().replace(" ", "").upper()
                if "490201" in parts:
                    try:
                        vin_hex = parts[parts.index("490201")+6:parts.index("490201")+40]
                        raw = bytes.fromhex(vin_hex)
                        vin = raw.decode("ascii", errors="replace").strip("\x00")
                        if len(vin) >= 17:
                            return vin[:17].encode()
                    except Exception:
                        pass
            return None
        except Exception:
            return None

    def read_battery_voltage(self) -> float:
        v = self.j2534.read_battery_voltage()
        self.vehicle_info.battery_voltage = v
        return v

    def read_vehicle_markers(self) -> dict:
        """Read the five Ford PCM vehicle-marker DIDs (D102, D103, D107,
        D109, D128). These return single-byte platform/configuration
        markers — NOT the ASCII VIN — that the manufacturer uses to
        encode model/option codes. The decoded meaning is platform-
        dependent; surface as raw hex so the AI / report layer can
        cross-reference against per-model lookup tables later.

        Returns {} if PCM doesn't respond. Keys are the DID names from
        core.ford_dids (mark_1..mark_4 + configuration); values are
        hex strings.
        """
        pcm = next((m for m in FORD_MODULES if m.abbreviation == "PCM"), None)
        if pcm is None:
            return {}
        out: dict[str, str] = {}
        try:
            client = self.get_uds_client(pcm)
            try:
                client.diagnostic_session(UDSSession.EXTENDED)
            except Exception:
                pass
            for did, key in (
                (DID_FORD_VEHICLE_MARK_1,        "mark_1"),
                (DID_FORD_VEHICLE_MARK_2,        "mark_2"),
                (DID_FORD_VEHICLE_MARK_3,        "mark_3"),
                (DID_FORD_VEHICLE_MARK_4,        "mark_4"),
                (DID_FORD_VEHICLE_CONFIGURATION, "configuration"),
            ):
                try:
                    data = client.read_data_by_id(did)
                    if data:
                        out[key] = data.hex().upper()
                except (UDSException, TimeoutError):
                    continue
        except Exception:
            return out
        return out
