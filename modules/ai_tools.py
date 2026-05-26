"""Bridge between the AI Mechanic and Fuse OBD's diagnostic engine.

Exposes a **read-only** surface to the AI Mechanic chat session — the
AI can read VIN, scan modules, read DTCs, sample live data, dump
As-Built blocks, and inspect PATS state. It CANNOT clear DTCs,
program keys, write As-Built, or perform SecurityAccess. (Scope was
chosen by the user; see commit history for the discussion.)

The bridge also lets the AI auto-populate the UI fields the user sees
in the main window — e.g. when the AI calls `read_vehicle_info`, the
VIN label and decoded year/make/model panel update by themselves.

Auto-connect is gated: any call to `connect_vehicle` first invokes the
`confirm` callable provided by the main window, which pops a Yes/No
dialog. Only on user OK does the actual connect happen.
"""
from __future__ import annotations

import time
import traceback
from typing import Any, Callable, Optional

from modules import issues_log


# ── Tool schemas (Anthropic Messages API tool format) ────────────────────
#
# Append-only — the AI's behavior depends on the exact wording of these
# descriptions, so changes should be additive.


READ_ONLY_TOOLS: list[dict] = [
    {
        "name": "connect_vehicle",
        "description": (
            "Ask the user for permission to connect to the vehicle via the "
            "currently-selected OBD adapter. Pops a Yes/No dialog. Only "
            "proceeds on user OK. Returns connection status and (on "
            "success) VIN + channel info. Use this when no vehicle is "
            "connected and the user wants you to take a look at the car."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": (
                        "Brief plain-English reason the user is being "
                        "asked to connect (shown in the confirm dialog). "
                        "e.g. 'To read DTCs from your PCM.'"
                    ),
                }
            },
            "required": ["reason"],
        },
    },
    {
        "name": "disconnect_vehicle",
        "description": "Close the adapter session and CAN channels. Safe to call at any time.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_vehicle_info",
        "description": (
            "Read VIN from the vehicle and decode it into year / make / "
            "model / engine / transmission. Populates the VIN field in "
            "the DTC tab and the Vehicle Info pane automatically. "
            "Requires an active vehicle connection."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "scan_modules",
        "description": (
            "Scan every Ford ECU on the bus and report which ones answer, "
            "what protocol they use, and any module-level metadata. "
            "Populates the Scanner tab in the main window. "
            "Set `quick=true` to only scan a known short list."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "quick": {
                    "type": "boolean",
                    "description": "True for a fast subset scan, false (default) for full scan.",
                },
                "modules": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Only used when quick=true — abbreviations of modules to scan "
                        "(e.g. ['PCM','BCM','ABS'])."
                    ),
                },
            },
        },
    },
    {
        "name": "read_dtcs",
        "description": (
            "Read DTCs from every responding module (or a specific list) "
            "and populate the DTC table in the DTC tab. Returns each "
            "code, description, severity, and module that reported it. "
            "Read-only — does NOT clear codes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "modules": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of module abbreviations. Default = all responding modules.",
                }
            },
        },
    },
    {
        "name": "list_available_pids",
        "description": (
            "List which live-data PIDs the connected vehicle supports. "
            "Use this before calling read_pids so you only ask for "
            "values the car can actually report."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_pids",
        "description": (
            "One-shot read of a set of live-data PIDs (by DID). Populates "
            "the Live Data / Monitor tab with the current values. Read-only."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Array of PID DIDs (decimal integers, e.g. [0xF40C → 62476]).",
                }
            },
            "required": ["dids"],
        },
    },
    {
        "name": "read_asbuilt",
        "description": (
            "Read As-Built (factory configuration) blocks from a single "
            "module — or every module if `module` is omitted. Updates "
            "the As-Built tab. Read-only — does NOT write."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "module": {
                    "type": "string",
                    "description": "Module abbreviation, e.g. 'PCM'. Omit to read all.",
                }
            },
        },
    },
    {
        "name": "read_pats_info",
        "description": (
            "Read PATS / immobiliser state — number of programmed keys, "
            "PATS hardware type, ignition counter. Read-only — does NOT "
            "program or erase keys."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "unlock_module",
        "description": (
            "Send SecurityAccess (UDS 0x27) to a module using Fuse OBD's "
            "built-in key database — a single deterministic attempt with "
            "Ford's known key for that module + level pair. NOT a "
            "bruteforce. Call this only when a previous read failed with "
            "'security access required' or when you know the module needs "
            "unlock before its DIDs are readable (some PCM and ABS reads). "
            "Read scope only — unlocking does NOT enable writes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "module": {
                    "type": "string",
                    "description": "Module abbreviation (e.g. 'PCM', 'ABS').",
                },
                "level": {
                    "type": "integer",
                    "description": "Security level. 1 (default) is the standard read-unlock.",
                },
            },
            "required": ["module"],
        },
    },
    {
        "name": "get_connection_state",
        "description": (
            "Return current connection state in one call: adapter "
            "selected, channels open, current VIN if known."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


# ── Bridge implementation ────────────────────────────────────────────────


def _safe_call(fn: Callable[[], Any], *, default: str = "") -> Any:
    try:
        return fn()
    except Exception as e:
        tb = traceback.format_exc(limit=4)
        issues_log.log_error(f"AI tool error: {e}", exc=e)
        return f"Error: {e.__class__.__name__}: {e}\n{tb}" if not default else default


class AIToolBridge:
    """Owned by the main window; passed into MechanicChat.

    The bridge holds soft references to the panels so it can refresh
    them after a read. All methods return a `dict` (serialised by the
    chat layer) and ALSO push their results into the appropriate UI
    panel via Qt signals (so the user sees VIN, DTCs, etc. populate
    in real time as the AI works).
    """

    def __init__(
        self,
        *,
        get_vehicle: Callable[[], Any],
        get_j2534: Callable[[], Any],
        connection_panel: Any,
        dtc_panel: Any,
        scanner_panel: Any,
        monitor_panel: Any,
        asbuilt_panel: Any,
        pats_panel: Any,
        confirm: Callable[[str, str], bool],
        run_on_ui: Callable[[Callable[[], None]], None],
    ):
        self._get_vehicle = get_vehicle
        self._get_j2534 = get_j2534
        self._connection_panel = connection_panel
        self._dtc_panel = dtc_panel
        self._scanner_panel = scanner_panel
        self._monitor_panel = monitor_panel
        self._asbuilt_panel = asbuilt_panel
        self._pats_panel = pats_panel
        self._confirm = confirm
        self._run_on_ui = run_on_ui

    # ── connection ──

    def connect_vehicle(self, reason: str) -> dict:
        if self._get_vehicle() is not None:
            return {"status": "already_connected"}
        ok = self._confirm(
            "AI Mechanic — Connect to Vehicle?",
            f"The AI Mechanic wants to connect to your vehicle now.\n\n"
            f"Reason: {reason}\n\n"
            f"This will use the currently-selected adapter and open the "
            f"HS / MS CAN channels. Proceed?",
        )
        if not ok:
            return {"status": "denied_by_user"}
        issues_log.log_ai(f"connect_vehicle approved by user: {reason}")
        # The connection panel exposes the same handler the user's
        # "Connect" button uses. Trigger it on the UI thread.
        done: dict[str, Any] = {}

        def do_it():
            try:
                self._connection_panel._connect()
            except Exception as e:
                done["error"] = f"{e.__class__.__name__}: {e}"
                issues_log.log_error("AI-initiated connect failed", exc=e)

        self._run_on_ui(do_it)
        # Poll briefly for state to settle (UI work is async).
        for _ in range(80):  # up to 8 seconds
            time.sleep(0.1)
            if self._get_vehicle() is not None or "error" in done:
                break
        if "error" in done:
            return {"status": "error", "detail": done["error"]}
        if self._get_vehicle() is None:
            return {"status": "error", "detail": "Connect did not complete (handshake timeout)"}
        return {"status": "connected", **self._connection_summary()}

    def disconnect_vehicle(self) -> dict:
        if self._get_vehicle() is None:
            return {"status": "already_disconnected"}

        def do_it():
            try:
                self._connection_panel._disconnect()
            except Exception as e:
                issues_log.log_error("AI-initiated disconnect failed", exc=e)

        self._run_on_ui(do_it)
        return {"status": "ok"}

    def _connection_summary(self) -> dict:
        v = self._get_vehicle()
        if v is None:
            return {"connected": False}
        info: dict[str, Any] = {
            "connected": True,
            "hs_can": getattr(v, "hs_can", None) is not None,
            "ms_can": getattr(v, "ms_can", None) is not None,
        }
        try:
            info["vin"] = getattr(self._dtc_panel, "vehicle_info", {}).get("vin")
        except Exception:
            pass
        return info

    def get_connection_state(self) -> dict:
        return self._connection_summary()

    # ── reads ──

    def read_vehicle_info(self) -> dict:
        v = self._get_vehicle()
        if v is None:
            return {"status": "not_connected", "hint": "Call connect_vehicle first."}
        try:
            vin = v.read_vin()
        except Exception as e:
            issues_log.log_error("AI read_vehicle_info: VIN read failed", exc=e)
            return {"status": "error", "detail": str(e)}
        if not vin or len(vin) != 17:
            return {"status": "no_vin", "raw": vin or ""}

        # Push VIN into the DTC panel which owns the visible VIN label
        # and the decoded vehicle-info pane.
        self._run_on_ui(lambda: self._dtc_panel._load_vehicle_info(vin))

        # Try a synchronous decode so we can also return decoded fields
        # to the AI right now (UI decodes in its own thread separately).
        decoded: dict = {}
        try:
            from modules.vehicle_info import decode_vin
            decoded = decode_vin(vin) or {}
        except Exception:
            pass
        return {
            "status": "ok",
            "vin": vin,
            "year": decoded.get("year"),
            "make": decoded.get("make"),
            "model": decoded.get("model"),
            "engine": decoded.get("engine"),
            "displacement_l": decoded.get("displacement_l"),
            "cylinders": decoded.get("cylinders"),
            "transmission": decoded.get("transmission"),
            "body": decoded.get("body_class"),
            "built_at": decoded.get("built_at"),
        }

    def scan_modules(self, quick: bool = False,
                     modules: Optional[list[str]] = None) -> dict:
        v = self._get_vehicle()
        if v is None:
            return {"status": "not_connected", "hint": "Call connect_vehicle first."}
        try:
            from modules.scanner import ModuleScanner
            scanner = ModuleScanner(v)
            if quick and modules:
                result = scanner.quick_scan(modules)
            else:
                result = scanner.full_scan()
        except Exception as e:
            issues_log.log_error("AI scan_modules failed", exc=e)
            return {"status": "error", "detail": str(e)}

        # Push results into the scanner panel.
        try:
            self._run_on_ui(
                lambda: self._scanner_panel._populate_results(result.modules)
            )
        except Exception:
            pass

        out_modules = []
        for m in result.modules:
            out_modules.append({
                "abbreviation": getattr(m, "abbreviation", "?"),
                "name": getattr(m, "name", "?"),
                "address": getattr(m, "address", None),
                "protocol": getattr(m, "protocol", None),
                "responding": getattr(m, "responding", True),
            })
        return {
            "status": "ok",
            "total": result.total_modules,
            "modules": out_modules,
        }

    def read_dtcs(self, modules: Optional[list[str]] = None) -> dict:
        v = self._get_vehicle()
        if v is None:
            return {"status": "not_connected", "hint": "Call connect_vehicle first."}
        try:
            # The DTC panel exposes the same flow the Refresh DTCs button
            # uses; using it keeps the UI behaviour identical.
            from modules.scanner import ModuleScanner
            from modules.dtc import DTCReader, ModuleDTCs
            scanner = ModuleScanner(v)
            scan = scanner.full_scan() if not modules else scanner.quick_scan(modules)
            all_dtcs: list[ModuleDTCs] = []
            for m in scan.modules:
                if not getattr(m, "responding", True):
                    continue
                try:
                    uds = v.uds_for_module(m)
                    reader = DTCReader(uds)
                    dtcs = reader.read_dtcs()
                    all_dtcs.append(ModuleDTCs(module_abbrev=m.abbreviation, dtcs=dtcs))
                except Exception as e:
                    issues_log.log_error(f"DTC read failed for {m.abbreviation}", exc=e)
                    continue
        except Exception as e:
            issues_log.log_error("AI read_dtcs failed", exc=e)
            return {"status": "error", "detail": str(e)}

        self._run_on_ui(lambda: self._dtc_panel._populate_results(all_dtcs))

        out = []
        total = 0
        for mod in all_dtcs:
            for dtc in mod.dtcs:
                total += 1
                out.append({
                    "module": mod.module_abbrev,
                    "code": dtc.code,
                    "status": dtc.status_text,
                    "is_confirmed": dtc.is_confirmed,
                    "is_pending": dtc.is_pending,
                    "is_active": dtc.is_active,
                })
        return {"status": "ok", "total": total, "dtcs": out}

    def list_available_pids(self) -> dict:
        v = self._get_vehicle()
        if v is None:
            return {"status": "not_connected"}
        try:
            from modules.pid import PIDMonitor
            mon = PIDMonitor(v)
            pids = mon.get_all_available_pids()
            return {
                "status": "ok",
                "pids": [
                    {"did": p.did, "name": p.name, "unit": getattr(p, "unit", None)}
                    for p in pids
                ],
            }
        except Exception as e:
            issues_log.log_error("AI list_available_pids failed", exc=e)
            return {"status": "error", "detail": str(e)}

    def read_pids(self, dids: list[int]) -> dict:
        v = self._get_vehicle()
        if v is None:
            return {"status": "not_connected"}
        try:
            from modules.pid import PIDMonitor
            mon = PIDMonitor(v)
            all_pids = mon.get_all_available_pids()
            want = set(int(d) for d in dids)
            for p in all_pids:
                if p.did in want:
                    mon.add_pid(p)
            readings = mon.read_once()
        except Exception as e:
            issues_log.log_error("AI read_pids failed", exc=e)
            return {"status": "error", "detail": str(e)}

        # Best-effort UI refresh
        try:
            self._run_on_ui(lambda: self._monitor_panel.refresh_readings(readings))
        except Exception:
            pass

        out = {}
        for did, r in readings.items():
            out[str(did)] = {
                "name": getattr(r.pid, "name", "?"),
                "raw": getattr(r, "raw_value", None),
                "value": getattr(r, "display_value", lambda: None)()
                          if callable(getattr(r, "display_value", None))
                          else getattr(r, "display_value", None),
                "unit": getattr(r.pid, "unit", None),
            }
        return {"status": "ok", "readings": out}

    def read_asbuilt(self, module: Optional[str] = None) -> dict:
        v = self._get_vehicle()
        if v is None:
            return {"status": "not_connected"}
        try:
            from modules.asbuilt import AsBuiltReader
            from modules.scanner import ModuleScanner
            reader = AsBuiltReader(v)
            if module:
                scan = ModuleScanner(v).quick_scan([module])
                target = next((m for m in scan.modules if m.abbreviation == module), None)
                if target is None:
                    return {"status": "module_not_found", "module": module}
                result = [reader.read_module(target)]
            else:
                result = reader.read_all_modules()
        except Exception as e:
            issues_log.log_error("AI read_asbuilt failed", exc=e)
            return {"status": "error", "detail": str(e)}

        try:
            self._run_on_ui(
                lambda: self._asbuilt_panel.set_modules(result)
                if hasattr(self._asbuilt_panel, "set_modules") else None
            )
        except Exception:
            pass

        out = []
        for m in result:
            out.append({
                "module": getattr(m, "module_abbrev", "?"),
                "block_count": len(getattr(m, "blocks", []) or []),
                "forscan": getattr(m, "to_forscan_format", lambda: "")(),
            })
        return {"status": "ok", "modules": out}

    def unlock_module(self, module: str, level: int = 1) -> dict:
        """Single-shot SecurityAccess using Ford's known key for this module.

        Bruteforce is intentionally NOT exposed to the AI even at any-level
        scope — this method tries exactly ONE key per call (the first one
        in Fuse OBD's database for that module + level). If the database
        does not have a key for the requested level, returns
        `status: no_key_in_database` and the user is asked to unlock
        manually.
        """
        v = self._get_vehicle()
        if v is None:
            return {"status": "not_connected"}
        try:
            from core.uds import UDSException
            from modules.security import SecurityAccess, _build_key_list
            from modules.scanner import ModuleScanner
            scan = ModuleScanner(v).quick_scan([module])
            target = next((m for m in scan.modules if m.abbreviation == module), None)
            if target is None or not getattr(target, "responding", False):
                return {"status": "module_not_responding", "module": module}
            keys = _build_key_list(target, level)
            if not keys:
                return {"status": "no_key_in_database", "module": module, "level": level}
            client = v.get_uds_client(target)
            try:
                client.diagnostic_session(0x03)  # extended session
            except UDSException:
                pass
            sec = SecurityAccess(v)
            result = sec.try_single_key(client, level, keys[0])
            if result is None:
                return {"status": "no_seed", "module": module}
            if result.success:
                issues_log.log_ai(
                    f"unlock_module {module} L{level} OK (key={keys[0].hex().upper()})"
                )
                return {
                    "status": "unlocked",
                    "module": module,
                    "level": level,
                }
            return {
                "status": "key_rejected",
                "module": module,
                "level": level,
                "hint": (
                    "The single known key for this module didn't work. "
                    "Tell the user — do NOT call unlock_module again "
                    "in a tight loop; the module will lock you out."
                ),
            }
        except Exception as e:
            issues_log.log_error(f"AI unlock_module failed for {module}", exc=e)
            return {"status": "error", "detail": str(e)}

    def read_pats_info(self) -> dict:
        v = self._get_vehicle()
        if v is None:
            return {"status": "not_connected"}
        try:
            from modules.pats import PATSManager
            pats = PATSManager(v)
            info = pats.read_pats_info()
        except Exception as e:
            issues_log.log_error("AI read_pats_info failed", exc=e)
            return {"status": "error", "detail": str(e)}

        try:
            if hasattr(self._pats_panel, "refresh_info"):
                self._run_on_ui(lambda: self._pats_panel.refresh_info(info))
        except Exception:
            pass

        return {
            "status": "ok",
            "key_count": getattr(info, "key_count", None),
            "pats_type": getattr(info, "pats_type", None),
            "pats_type_name": getattr(info, "pats_type_name", None),
            "ignition_count": getattr(info, "ignition_count", None),
            "in_session": getattr(info, "in_session", None),
        }
