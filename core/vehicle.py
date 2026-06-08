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

    def read_vin(self, time_budget_s: float = 15.0) -> str:
        # Time-bound the whole probe. Worst case on a non-responsive bus
        # blocks for ~110 s without this — long enough that the user
        # assumes the app hung. Bail at the deadline and let the caller
        # surface the "No Response" dialog promptly.
        deadline = time.monotonic() + time_budget_s
        vin_dids = [0xF190, 0xF110, 0xF18C]
        # Session subfunction list ordered most→least likely to be
        # accepted. The two FORD_LEGACY_* entries cover pre-2008 CD3 /
        # U-platform PCMs (Zephyr, Fusion, Milan, Edge, Escape) that
        # reject the standard 0x03/0x85 with NRC 0x11.
        sessions = [
            UDSSession.EXTENDED,
            UDSSession.FORD_DIAG,
            UDSSession.FORD_LEGACY_C0,
            UDSSession.FORD_LEGACY_81,
            UDSSession.DEFAULT,
        ]
        priority = ("PCM", "IPC", "BCM", "GWM")

        # ── Method 1: OBD-II Mode 09 PID 02 (broadcast) ──
        # SAE J1979 standard since 1996, supported by every OBD-II-
        # compliant module. Sub-500 ms on most vehicles. Tried first
        # because it works on cars whose modules don't speak full UDS
        # (2006 CD3 / U-platform, most non-Ford vehicles), where the
        # session-based path below would just chew through the budget
        # collecting NRCs. The trade-off is one ATSP6/ATSH 7DF state
        # change up front, which Method 2 has to undo.
        try:
            data = self._obd_request(b"\x09\x02")
            if data and len(data) > 3 and data[0:2] == b"\x49\x02":
                vin = data[3:].decode("ascii", errors="replace").strip("\x00").strip()
                if len(vin) == 17:
                    self.vehicle_info.vin = vin
                    return vin
        except Exception:
            pass

        # ── Method 2: directed UDS reads, per priority module ──
        # For each module: first try DIDs WITHOUT changing session (many
        # Ford modules expose F190 in the implicit default session). Only
        # if that fails do we attempt diagnostic_session control, walking
        # through the candidate subfunctions.
        for module in FORD_MODULES:
            if module.abbreviation not in priority:
                continue
            if time.monotonic() >= deadline:
                break
            try:
                client = self.get_uds_client(module)
            except Exception:
                continue

            # 2a. Bare DID reads (no session change). Works on older Ford
            # modules and on platforms where the module accepts $22 in
            # whatever session it powers up in.
            module_responded = False
            for did in vin_dids:
                if time.monotonic() >= deadline:
                    break
                try:
                    data = client.read_data_by_id(did)
                    module_responded = True
                    vin = data.decode("ascii", errors="replace").strip("\x00").strip()
                    if len(vin) == 17:
                        self.vehicle_info.vin = vin
                        return vin
                except Exception:
                    continue

            # 2b. Session control + DID reads. Skip the inner DID loop
            # the moment a session fails (re-running the same session
            # per DID just wastes the budget).
            for session in sessions:
                if time.monotonic() >= deadline:
                    break
                try:
                    client.diagnostic_session(session)
                except Exception:
                    continue
                module_responded = True
                for did in vin_dids:
                    if time.monotonic() >= deadline:
                        break
                    try:
                        data = client.read_data_by_id(did)
                        vin = data.decode("ascii", errors="replace").strip("\x00").strip()
                        if len(vin) == 17:
                            self.vehicle_info.vin = vin
                            return vin
                    except Exception:
                        continue

            # If nothing at all answered on this module — not the bare
            # reads, not any session — it isn't reachable on this bus.
            # No point grinding through more sessions on it.
            if not module_responded:
                continue

        return ""

    def _obd_request(self, payload: bytes, timeout_ms: int = 1000) -> Optional[bytes]:
        """Send a raw OBD-II request: set broadcast header 0x7DF, send Mode/PID, read 0x7E8."""
        try:
            # Force protocol 6 (ISO 15765-4, 11-bit, 500k) and set OBD broadcast header
            self.j2534._elm_cmd(self.j2534._stream, "ATSP6", 600)
            self.j2534._elm_cmd(self.j2534._stream, "ATSH 7DF", 400)
            self.j2534._elm_cmd(self.j2534._stream, "ATAR", 200)
            # We just changed the ELM's tx-header out from under the
            # j2534's start_msg_filter cache. Invalidate it so any
            # subsequent UDS module call resends ATSH<txid> instead of
            # short-circuiting on a stale "this header is already set".
            self.j2534._last_sh = None
            self.j2534._last_cra = None
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
