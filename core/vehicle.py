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
    # Mode 09 PID 04 ("Calibration ID") — one or more ASCII calibration
    # strings, one per responding ECU. Captured 2026-06-07 from a 2006
    # Lincoln Zephyr: PCM returned "ICE7-14C337-AE", TCM returned
    # "6E53-14C336-AA". OBD Auto Doctor and FORScan both read this.
    cal_ids: list[str] = field(default_factory=list)
    # Mode 09 PID 06 ("Calibration Verification Number") — 4-byte
    # CRC-style checksum per ECU. Surface as hex strings.
    cvns: list[str] = field(default_factory=list)


class VehicleConnection:
    def __init__(self, j2534: J2534):
        self.j2534 = j2534
        self.hs_channel: Optional[int] = None
        self.ms_channel: Optional[int] = None
        self.vehicle_info = VehicleInfo()
        self._uds_clients: dict[int, UDSClient] = {}
        # OBD-II compliance listeners enter low-power mode after a few
        # seconds of no diagnostic activity, then NRC / time out the
        # first request after that. A Mode 01 PID 00 broadcast wakes
        # them — both FORScan and OBD Auto Doctor send 0100 before any
        # other broadcast (see scan_obd_auto_doctor.pcapng line 47-49,
        # scan.pcapng line 156-159). Cache the wake state so we only
        # spend the 30-ms wake once per connection.
        self._obd_woken_at_ms = 0.0

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

    def scan_modules(self, callback=None, cancel=None) -> list[ModuleInfo]:
        # Pre-2008 Ford modules (CD3, U-platform, etc.) reject
        # DiagnosticSessionControl with NRC 0x11 — but they happily
        # answer $22 reads in the implicit default session. Skip DSC
        # entirely and use a $22 0200 ping to detect presence: a
        # positive response OR a NRC both mean "module is alive on
        # the bus." Only a true timeout = absent.
        #
        # `cancel` is a gui.qt_helpers.CancelToken (or any object with
        # a `.cancelled` property). When set, the loop exits after the
        # current outstanding request returns — typical worst-case
        # latency is one adapter read (~1.5 s).
        found = []
        for i, module in enumerate(FORD_MODULES):
            if cancel is not None and cancel.cancelled:
                break
            if callback:
                callback(module.name, i, len(FORD_MODULES))
            try:
                client = self.get_uds_client(module)
            except Exception:
                continue

            module_alive = False
            try:
                client.read_data_by_id(0x0200)  # Ford "are you alive?" ping
                module_alive = True
            except UDSException:
                # NRC means the module IS there, it just doesn't expose
                # DID 0x0200. That's still presence.
                module_alive = True
            except (TimeoutError, Exception):
                pass

            if not module_alive:
                self._uds_clients.pop((module.network, module.address), None)
                continue

            info = ModuleInfo(module=module, present=True)

            # Harvest identity. Try Ford-specific DIDs first (these
            # work on older platforms where ISO 14229 doesn't), then
            # fall back to ISO standard DIDs for newer modules.
            for did, attr, decoder in (
                (DID_FORD_ASSEMBLY_PART_NUMBER, "assembly_pn",
                    lambda b: b.decode("ascii", errors="replace").strip("\x00").strip()),
                (DID_FORD_CALIBRATION_ID, "calibration_id",
                    lambda b: b.hex().upper()),
                (DID_FORD_SOFTWARE_PART_NUMBER, "software_pn",
                    lambda b: b.hex().upper()),
                (0xE610, "part_number",   # Module HW P/N (Ford 8-byte ASCII)
                    lambda b: b.decode("ascii", errors="replace").strip("\x00").strip()),
                # ISO 14229 fallbacks
                (0xF187, "part_number",
                    lambda b: b.decode("ascii", errors="replace").strip()),
                (0xF188, "software_pn",
                    lambda b: b.decode("ascii", errors="replace").strip()),
                (0xF191, "hardware_pn",
                    lambda b: b.decode("ascii", errors="replace").strip()),
            ):
                try:
                    data = client.read_data_by_id(did)
                    if data and not getattr(info, attr, None):
                        setattr(info, attr, decoder(data))
                except (UDSException, TimeoutError, Exception):
                    pass

            found.append(info)
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
        # collecting NRCs. _obd_request handles the wake (`01 00`) and
        # STN-adapter message-count suffix; the parser tolerates both
        # the legacy single-frame and the ISO-TP multi-frame response.
        try:
            raw = self._obd_request(b"\x09\x02")
            if raw:
                vin = self._parse_mode09_pid02(raw)
                if vin:
                    self.vehicle_info.vin = vin
                    # While the OBD-II listener is awake and we know
                    # the bus is alive, opportunistically also grab
                    # CalID + CVN. Both come back in well under 100 ms
                    # and they're invaluable for verifying which
                    # calibration is flashed in the PCM.
                    try:
                        self.read_calibration_ids(timeout_ms=600)
                        self.read_cvns(timeout_ms=600)
                    except Exception:
                        pass
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

    # ── OBD-II broadcast helpers ────────────────────────────────────

    # Apps known to be STN-class (vLinker FS, OBDLink SX/EX, ScanTool
    # STN-family). On these, appending a message-count digit to a
    # broadcast request ("09021" instead of "0902") makes the adapter
    # return as soon as N responses are seen instead of waiting the
    # full ATST timeout. Without it the ELM grinds out and the user
    # sees STOPPED — see the FuseOBD log at 20:22:05.422 vs the
    # FORScan capture at +6.872 which returned in 80 ms.
    _STN_ADAPTER_KINDS = {
        "stn1110", "stn1170", "stn2120", "stn2255",
        "obdlink_sx", "obdlink_ex", "obdlink_mxp", "obdlink_lx",
        "vlinker_fs", "vlinker_mcp", "kiwi3",
    }

    def _is_stn_class(self) -> bool:
        """True if the current adapter belongs to the STN family."""
        try:
            ident = getattr(self.j2534, "_identity", None)
            if ident and getattr(ident, "kind", "") in self._STN_ADAPTER_KINDS:
                return True
        except Exception:
            pass
        return False

    def _obd_wake_if_stale(self) -> None:
        """Send `0100` (Mode 01 PID 00) to wake the OBD-II compliance
        listener. Cached: re-runs only if the previous wake is older
        than 30 s, since once an ECU has been woken it stays awake as
        long as we keep talking to it.

        `0100` is a multi-ECU broadcast (both PCM and TCM typically
        answer) so we do NOT append the STN message-count suffix here
        — that would tell the adapter to return after the first reply
        while the bus is still carrying the second one, garbling the
        next request."""
        import time
        now = time.monotonic() * 1000.0
        if now - self._obd_woken_at_ms < 30000.0:
            return
        try:
            self.j2534._elm_cmd(self.j2534._stream, "ATSP6", 600)
            self.j2534._elm_cmd(self.j2534._stream, "ATSH 7DF", 400)
            self.j2534._elm_cmd(self.j2534._stream, "ATAR", 200)
            # Mark headers as dirty for the j2534's start_msg_filter cache.
            self.j2534._last_sh = None
            self.j2534._last_cra = None
            self.j2534._stream.write(b"0100\r")
            # 1500 ms — must exceed ATST (FF→1020 ms). The first reply
            # bytes arrive in ~60 ms but the ELM doesn't emit `>` until
            # ATST elapses after the LAST byte. If we return early, the
            # next command interrupts and the ELM answers "STOPPED".
            self.j2534._elm_read_until_prompt(self.j2534._stream, 1500)
            self._obd_woken_at_ms = now
        except Exception:
            # Wake is best-effort. If it failed, the caller will see
            # the failure on its own request and retry naturally.
            pass

    def _obd_request(self, payload: bytes, timeout_ms: int = 1000) -> Optional[bytes]:
        """Send a raw OBD-II Mode XX PID YY request via broadcast 0x7DF.

        Returns the raw response bytes (with the 0x4N service-echo
        byte still attached so callers can sanity-check the mode),
        or None on failure.

        Wakes the compliance listener with `01 00` first if it hasn't
        been used in the last 30s — without this the first request
        after a quiet period typically returns STOPPED on STN-class
        adapters because the ECU is still asleep."""
        self._obd_wake_if_stale()
        try:
            # Cache the OBD broadcast setup — once SP6 + SH 7DF + AR are
            # programmed they stay valid until a UDS call swaps in a
            # different ATSH for module-directed traffic. Skip the
            # 3-command re-setup whenever the broadcast header is
            # already in place. Saves ~150 ms of serial chatter per
            # monitor tick.
            need_setup = (
                not getattr(self, "_obd_setup_done", False) or
                getattr(self.j2534, "_last_sh", None) != "0007DF"
            )
            if need_setup:
                self.j2534._elm_cmd(self.j2534._stream, "ATSP6", 600)
                self.j2534._elm_cmd(self.j2534._stream, "ATSH 7DF", 400)
                self.j2534._elm_cmd(self.j2534._stream, "ATAR", 200)
                # Drop ATST from 1.02 s (FF) down to 100 ms (19) so the
                # prompt comes back as soon as the last byte arrives.
                # ECUs respond in <60 ms on a healthy bus; the long
                # default was the single biggest live-data bottleneck.
                self.j2534._elm_cmd(self.j2534._stream, "ATST19", 200)
                self.j2534._last_sh = "0007DF"
                self.j2534._last_cra = None
                self._obd_setup_done = True
            hex_cmd = payload.hex().upper()
            # NO STN message-count suffix on Mode 09 broadcasts. The
            # suffix means "lines of output" to the STN, not "ISO-TP
            # messages" — VIN/CalID are multi-frame so suffix="1"
            # returns after only the first frame. Without the suffix
            # the ELM waits ATST after the last frame and returns the
            # fully-assembled message in one go. Verified against the
            # OBD Auto Doctor capture which uses no suffix and gets
            # the full 3-frame VIN in 77 ms.
            self.j2534._stream.write(hex_cmd.encode() + b"\r")
            # ATST 19 means the prompt arrives ~100 ms after the last
            # response byte. Don't over-clamp the read timeout — that
            # was the second half of the live-data bottleneck.
            effective_timeout = max(timeout_ms, 400)
            resp = self.j2534._elm_read_until_prompt(
                self.j2534._stream, effective_timeout,
            )
            if not resp:
                return None
            # STN-family adapters print multi-frame ISO-TP responses
            # in a numbered-line format:
            #     0902               <- request echo
            #     014                <- ISO-TP total length (0x14 = 20)
            #     0:490201334C4E    <- frame index, then payload
            #     1:484D3236313136
            #     2:52363635353632
            # A naive hex-only filter keeps the "0", "1", "2" frame-
            # index digits and corrupts the byte stream. And the "014"
            # length line introduces an odd nibble that fromhex() would
            # truncate from the wrong end (lopping off the last VIN
            # char). Build the byte stream line-by-line: strip the
            # "<idx>:" prefix, drop the request echo, drop the bare
            # length-only line.
            import re
            echo = hex_cmd.upper()
            kept = []
            for line in resp.upper().splitlines():
                line = line.strip().rstrip(">").strip()
                if not line:
                    continue
                # Strip STN frame-index prefix ("0:", "1:", ... "F:").
                m = re.match(r"^[0-9A-F]+:(.*)$", line)
                if m:
                    line = m.group(1).strip()
                if not re.fullmatch(r"[0-9A-F]+", line):
                    continue
                if line == echo or line == echo.rstrip("1"):
                    continue   # request echo (with or without STN count)
                if len(line) <= 3:
                    continue   # ISO-TP length indicator like "014"
                kept.append(line)
            cleaned = "".join(kept)
            if not cleaned or len(cleaned) % 2:
                return None
            try:
                raw = bytes.fromhex(cleaned)
            except ValueError:
                return None
            return raw if raw else None
        except Exception:
            return None

    def _parse_mode09_pid02(self, raw: bytes) -> Optional[str]:
        """Extract a VIN from a Mode 09 PID 02 response. Handles both
        the legacy single-frame form (`49 02 01 <17 ASCII bytes>`) and
        the modern ISO-TP multi-frame form where the same 17 chars are
        spread over a first frame + two consecutive frames."""
        # The ELM, with headers off (FuseOBD default), returns either a
        # bare "49 02 01 <chars>" or a multi-line concatenation that
        # includes the consecutive-frame index bytes (21, 22, ...).
        # In _obd_request we've already stripped headers/whitespace and
        # hex-decoded, but ISO-TP framing bytes may still be present.
        h = raw.hex().upper()
        idx = h.find("490201")
        if idx < 0:
            return None
        body = h[idx + len("490201"):]
        # Strip any consecutive-frame index bytes (0x2N). The VIN is
        # 17 ASCII chars = 34 hex chars; pull the first 17 valid ASCII
        # bytes encountered, skipping bytes in the 0x20-0x2F range that
        # look like CF indices when they appear before a printable run.
        chars: list[str] = []
        i = 0
        while i + 2 <= len(body) and len(chars) < 17:
            b = int(body[i:i+2], 16)
            if 0x30 <= b <= 0x5A or 0x61 <= b <= 0x7A:
                chars.append(chr(b))
            # else: 0x2N consecutive-frame index byte, skip
            i += 2
        vin = "".join(chars)
        return vin if len(vin) == 17 else None

    def read_calibration_ids(self, timeout_ms: int = 1500) -> list[str]:
        """Mode 09 PID 04 — fetch ASCII calibration IDs from every
        ECU that answers. Stores the result on `vehicle_info.cal_ids`
        and also returns it."""
        raw = self._obd_request(b"\x09\x04", timeout_ms=timeout_ms)
        if not raw:
            return []
        h = raw.hex().upper()
        out: list[str] = []
        # Each ECU's response begins with `49 04 <n>` where n is the
        # count of calibration strings, followed by n × 16 ASCII bytes.
        cursor = 0
        while True:
            idx = h.find("4904", cursor)
            if idx < 0:
                break
            cursor = idx + 4
            if cursor + 2 > len(h):
                break
            count = int(h[cursor:cursor+2], 16)
            cursor += 2
            for _ in range(count):
                chunk_hex = h[cursor:cursor + 32]   # 16 bytes
                cursor += 32
                if len(chunk_hex) < 2:
                    break
                try:
                    ascii_bytes = bytes.fromhex(chunk_hex)
                except ValueError:
                    continue
                s = ascii_bytes.decode("ascii", errors="replace").strip("\x00").strip()
                # Filter ISO-TP framing junk (e.g. lone "0" or "0\x14")
                if s and any(c.isalnum() for c in s):
                    out.append(s)
        # Deduplicate while preserving order
        seen = set()
        unique = [s for s in out if not (s in seen or seen.add(s))]
        self.vehicle_info.cal_ids = unique
        return unique

    def read_obd_pid_broadcast(self, pid: int, timeout_ms: int = 1500
                                ) -> Optional[bytes]:
        """SAE J1979 Mode 01 PID XX broadcast read. Returns the raw
        payload bytes (without the 41 XX service-echo header), or
        None if no ECU responded. Works on every OBD-II compliant
        vehicle and is the right path for "live data" PIDs that
        UDS Mode 22 0xF4XX can't reach on pre-2008 modules."""
        if not (0 <= pid <= 0xFF):
            return None
        raw = self._obd_request(bytes([0x01, pid]), timeout_ms=timeout_ms)
        if not raw:
            return None
        # Strip the response service-echo header (41 XX). Multiple
        # ECUs may respond; take the first non-empty payload.
        marker = bytes([0x41, pid])
        idx = raw.find(marker)
        if idx < 0:
            return None
        payload = raw[idx + 2:]
        # Trim trailing zero padding so callers see exactly the
        # bytes the ECU emitted.
        return payload.rstrip(b"\x00") or payload

    def read_obd_dtcs_broadcast(self, mode: int = 0x03,
                                  timeout_ms: int = 2000) -> list[str]:
        """SAE J1979 Mode 03 (stored DTCs) / Mode 07 (pending) / Mode
        0A (permanent) broadcast read. Returns DTC code strings like
        "P0420". Works on every OBD-II compliant vehicle since 1996 —
        the fallback when UDS Mode 19 ReadDTCInformation isn't
        supported (typical of pre-2008 Ford modules)."""
        if mode not in (0x03, 0x07, 0x0A):
            raise ValueError("mode must be 0x03, 0x07, or 0x0A")
        raw = self._obd_request(bytes([mode]), timeout_ms=timeout_ms)
        if not raw:
            return []
        # Response format: 43 <count> <dtc1_hi> <dtc1_lo> <dtc2_hi> ...
        # (Mode 07 → response 47; Mode 0A → response 4A)
        resp_byte = mode + 0x40
        codes: list[str] = []
        cursor = 0
        from modules.dtc import decode_dtc_bytes
        while cursor < len(raw):
            # Find the next response service byte (43/47/4A). Some
            # ELM/STN frames concatenate multiple ECU responses.
            idx = raw.find(bytes([resp_byte]), cursor)
            if idx < 0:
                break
            cursor = idx + 1
            if cursor >= len(raw):
                break
            count = raw[cursor]
            cursor += 1
            for _ in range(count):
                if cursor + 2 > len(raw):
                    break
                pair = raw[cursor:cursor + 2]
                cursor += 2
                if pair == b"\x00\x00":
                    continue
                code = decode_dtc_bytes(pair)
                if code:
                    codes.append(code)
        # Deduplicate while preserving order (same DTC may come back
        # from multiple ECUs).
        seen = set()
        return [c for c in codes if not (c in seen or seen.add(c))]

    def read_cvns(self, timeout_ms: int = 1500) -> list[str]:
        """Mode 09 PID 06 — fetch 4-byte Calibration Verification
        Numbers (CVNs) from every responding ECU. Returns them as
        uppercase hex strings."""
        raw = self._obd_request(b"\x09\x06", timeout_ms=timeout_ms)
        if not raw:
            return []
        h = raw.hex().upper()
        out: list[str] = []
        cursor = 0
        while True:
            idx = h.find("4906", cursor)
            if idx < 0:
                break
            cursor = idx + 4
            if cursor + 2 > len(h):
                break
            count = int(h[cursor:cursor+2], 16)
            cursor += 2
            for _ in range(count):
                cvn_hex = h[cursor:cursor + 8]  # 4 bytes per CVN
                cursor += 8
                if len(cvn_hex) == 8:
                    out.append(cvn_hex)
        seen = set()
        unique = [s for s in out if not (s in seen or seen.add(s))]
        self.vehicle_info.cvns = unique
        return unique

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
