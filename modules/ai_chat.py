"""AI Mechanic Chat — interactive diagnostic assistant.

The mechanic can:
  • answer free-form questions about a connected vehicle (or no vehicle at all)
  • search the web and read pages for TSBs, forum posts and repair guides
  • inspect the host PC for J2534 / USB / Bluetooth / WiFi OBD adapters
  • read Fuse OBD's own debug log to self-diagnose problems with the app
  • record findings into a persistent issues log that the UI displays

## Credential resolution (in priority order)

1. **Local override (developer mode)** — if `MOD_ANTHROPIC_AUTH_TOKEN`
   (or any alias) is set in the process environment / Windows registry,
   the client talks directly to that upstream with that key. This is
   what we use on the dev workstation.
2. **Hosted Fuse OBD proxy (default for end users)** — if no local
   token is present, the client connects to `HOSTED_PROXY_BASE_URL`
   (`http://150.195.114.185:8080/api/ai`). The Fuse-Web Node server
   adds the real upstream auth header and forwards to DeepSeek. End
   users need ZERO configuration.

End users never see or possess the real API key.
"""
from __future__ import annotations

import os
import json
import platform
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import anthropic

from modules import issues_log

# ── Configuration ──────────────────────────────────────────────────────────


def _read_windows_registry_env(name: str) -> str:
    """Read an env var directly from the Windows registry.

    Windows merges HKLM (system) + HKCU (user) into the per-process
    environment, with USER values taking precedence. That means a user-level
    var set to an empty string SILENTLY OVERRIDES the system-level value —
    so even a freshly-launched process sees an empty string. We work around
    this by consulting the system registry directly when the process env is
    empty.

    Reads HKLM first (the canonical place for system-wide config like
    MOD_ANTHROPIC_AUTH_TOKEN), then HKCU as a fallback.
    """
    if sys.platform != "win32":
        return ""
    try:
        import winreg  # local import — Windows only
    except ImportError:
        return ""
    for hkey, path in (
        (winreg.HKEY_LOCAL_MACHINE,
         r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, "Environment"),
    ):
        try:
            with winreg.OpenKey(hkey, path, 0, winreg.KEY_READ) as k:
                val, _ = winreg.QueryValueEx(k, name)
                if isinstance(val, str) and val.strip():
                    return val
        except OSError:
            continue
    return ""


def _env_first(*names: str, default: str = "") -> str:
    """Return the first non-empty value among the given env var names.

    Falls back to reading directly from the Windows registry when the
    process environment is missing or empty.
    """
    for n in names:
        v = os.environ.get(n) or ""
        if v.strip():
            return v
    for n in names:
        v = _read_windows_registry_env(n)
        if v.strip():
            return v
    return default


LOCAL_AUTH_TOKEN = _env_first(
    "MOD_ANTHROPIC_AUTH_TOKEN",
    "MOD_ANTHROPIC_API_KEY",
    "MOD_AUTH_TOKEN",
    "MOD_API_KEY",
)
LOCAL_BASE_URL = _env_first(
    "MOD_ANTHROPIC_BASE_URL",
    "MOD_BASE_URL",
)
LOCAL_MODEL = _env_first(
    "MOD_ANTHROPIC_MODEL",
    "MOD_ANTHROPIC_DEFAULT_OPUS_MODEL",
    "MOD_MODEL",
    "MOD_DEFAULT_OPUS_MODEL",
    default="",
)

# ── Hosted Fuse OBD proxy (the default for end users) ─────────────────
# Points at the Node server in D:\APP\Fuse-Web — `server.js` on the
# same box as fuse-obd.com. Anthropic-compatible: the client uses
# `base_url = HOSTED_PROXY_BASE_URL` and the SDK appends /v1/messages.
HOSTED_PROXY_BASE_URL = os.environ.get(
    "FUSE_AI_ENDPOINT_OVERRIDE",
    "http://150.195.114.185:8080/api/ai",
)
HOSTED_PROXY_MODEL = "deepseek-v4-pro"  # server overrides if MOD_ANTHROPIC_MODEL set

USE_HOSTED_PROXY = not LOCAL_AUTH_TOKEN

# Kept for backward compatibility with code that imports these directly.
AUTH_TOKEN = "hosted-proxy" if USE_HOSTED_PROXY else LOCAL_AUTH_TOKEN
BASE_URL = HOSTED_PROXY_BASE_URL if USE_HOSTED_PROXY else LOCAL_BASE_URL
MODEL = HOSTED_PROXY_MODEL if USE_HOSTED_PROXY else (LOCAL_MODEL or "claude-opus-4-7")


def using_hosted_proxy() -> bool:
    """True if the client is going through the Fuse OBD hosted proxy."""
    return USE_HOSTED_PROXY


def hosted_proxy_url() -> str:
    return HOSTED_PROXY_BASE_URL


def diagnose_config() -> dict:
    """Return a diagnostic snapshot of how the AI Mechanic is configured.

    Shows whether the client is going through the hosted proxy or using
    a local key override, and lists every env var the client checks.
    """
    var_groups = {
        "AUTH_TOKEN": ["MOD_ANTHROPIC_AUTH_TOKEN", "MOD_ANTHROPIC_API_KEY",
                       "MOD_AUTH_TOKEN", "MOD_API_KEY"],
        "BASE_URL":   ["MOD_ANTHROPIC_BASE_URL", "MOD_BASE_URL"],
        "MODEL":      ["MOD_ANTHROPIC_MODEL", "MOD_ANTHROPIC_DEFAULT_OPUS_MODEL",
                       "MOD_MODEL", "MOD_DEFAULT_OPUS_MODEL"],
    }
    candidates: dict = {}
    for setting, names in var_groups.items():
        rows = []
        for n in names:
            proc_v = os.environ.get(n)
            reg_v = _read_windows_registry_env(n) if sys.platform == "win32" else ""
            rows.append({
                "name": n,
                "in_process_env": _redact(proc_v),
                "in_registry":    _redact(reg_v),
            })
        candidates[setting] = rows
    return {
        "mode": "hosted-proxy" if USE_HOSTED_PROXY else "local-override",
        "hosted_proxy_url": HOSTED_PROXY_BASE_URL,
        "resolved": {
            "AUTH_TOKEN": _redact(AUTH_TOKEN),
            "BASE_URL":   BASE_URL,
            "MODEL":      MODEL,
        },
        "candidates": candidates,
    }


def _redact(value) -> str:
    if value is None:
        return "(unset)"
    if not isinstance(value, str):
        value = str(value)
    if not value.strip():
        return '(empty "")'
    if len(value) <= 12:
        return value
    # Show first 6 + last 4 for tokens so the user can confirm without leaking.
    return f"{value[:6]}…{value[-4:]} (len={len(value)})"


SYSTEM_PROMPT = """You are a master automotive diagnostician with 30 years of hands-on experience across ALL vehicle makes — Ford, GM, Toyota, Honda, BMW, Mercedes, VW, Hyundai, Kia, Nissan, Chrysler, Subaru, Mazda, Volvo, Land Rover, and everything else. You work on cars every day. You think like a mechanic, not a computer.

You also moonlight as the support engineer for the Fuse OBD app itself. When the user is having trouble *with the app or the OBD adapter* (connections failing, no adapter found, the app threw an error, etc.), you switch hats and help them debug Fuse OBD — by inspecting Windows devices, reading the app debug log, listing adapters, and offering concrete next steps. You never refuse to help because "no vehicle is connected"; you help them get connected.

## Your tools
You can use these tools to gather information before answering:

Vehicle / web research:
- **search_web(query)** — Search the internet for TSBs, forum discussions, repair guides, common fixes for specific DTCs. Use this before giving diagnostic advice — real mechanics look things up constantly.
- **fetch_page(url)** — Fetch content from a specific web page (forum post, repair guide, TSB). Use this when search results look promising and you want details.

App / hardware diagnostics:
- **list_adapters()** — List every OBD adapter Fuse OBD can currently see (J2534, USB serial, paired Bluetooth, manually added WiFi). Use this whenever the user can't connect.
- **list_windows_serial_devices()** — Query Windows for every serial-class device, including ones Fuse OBD did NOT recognise as an OBD adapter. Helps spot driver problems and missing PIDs.
- **list_windows_usb_devices()** — Pull a generic USB device list from Windows (helpful when an adapter is plugged in but no COM port appeared).
- **scan_local_network_obd()** — Probe the local subnet for WiFi ELM327 adapters (commonly 192.168.0.10:35000 / 192.168.4.1:35000 / 192.168.1.5:35000 ranges). Slow — only call if the user is on WiFi.
- **read_app_debug_log()** — Read the tail of Fuse OBD's own debug log. Use this when something inside the app misbehaved.
- **get_app_info()** — Return the app version, Python version, OS, working directory and current connection state.

Persistent record:
- **log_issue(title, kind, severity, summary_simple, summary_technical)** — Append an entry to the persistent Issues list (right-hand pane in the AI Mechanic window). Use this whenever you identify a concrete problem — both for vehicle faults and for app/adapter problems. `kind` is one of: vehicle, app, connection, info. `severity` is one of: low, medium, high, critical. Always write *summary_simple* in plain English ("for dummies") and *summary_technical* with the gory details ("for nerds").

## How you diagnose a vehicle
1. Look at the fault codes AS A SYSTEM, not individually. A single bad ground or weak battery can throw 20 codes across 8 modules.
2. Check for CAN bus communication errors (U-codes) — these often trace to one module going offline, which cascades to every module that talks to it.
3. Look at freeze frame data (if available) — what were the conditions when the fault set?
4. Consider the vehicle's age, mileage, known issues for that make/model/year.
5. Search for TSBs and common fixes for the specific codes on the specific vehicle.

## How you diagnose Fuse OBD itself
1. Call get_app_info first — establish what version they're on and whether a vehicle is connected.
2. If they can't see an adapter, call list_adapters, then list_windows_serial_devices, then list_windows_usb_devices in that order.
3. If the app threw an error, call read_app_debug_log and look at the bottom 50 lines.
4. Recommend concrete clicks ("open Windows Device Manager → look for FT232R USB UART under Ports (COM & LPT) — does it have a yellow ! triangle?").
5. Log every distinct issue you confirm via log_issue so the user has a record.

## Response style
- Talk like a real mechanic — plain English, no corporate speak
- Tell the owner what's actually wrong and what's just noise
- Give repair difficulty estimates (driveway job vs. need a lift vs. dealer-only)
- Mention if something is safe to drive or needs immediate attention
- If you search the web, incorporate what you find into your diagnosis
- Be honest when something needs a professional — don't pretend everything is DIY

## When answering
- Reference specific fault codes by number
- Explain the "why" behind your diagnosis
- If multiple codes trace to one root cause, explain the cascade
- Give the owner a prioritized list: fix this first, then this, then this"""


# ── Web tools ──────────────────────────────────────────────────────────────


def _fetch_text(url: str, timeout: float = 8.0) -> str:
    """Fetch text content from a URL, stripped of HTML."""
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].split(";")[0].strip()
            try:
                text = raw.decode(charset, errors="replace")
            except Exception:
                text = raw.decode("utf-8", errors="replace")
            text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:8000]
    except Exception as e:
        return f"Error fetching {url}: {e}"


def _search_web(query: str) -> str:
    """Search the web via DuckDuckGo HTML endpoint."""
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        html = _fetch_text(url, timeout=10)
        results = []
        for match in re.finditer(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL):
            results.append(re.sub(r"<[^>]+>", "", match.group(1)).strip())
        if not results:
            for match in re.finditer(r'class="result__body"[^>]*>(.*?)</a>', html, re.DOTALL):
                results.append(re.sub(r"<[^>]+>", "", match.group(1)).strip())
        if not results:
            snippets = re.findall(r'class="[^"]*snippet[^"]*"[^>]*>(.*?)</', html, re.DOTALL)
            results = [re.sub(r"<[^>]+>", "", s).strip() for s in snippets if len(s) > 50]
        if not results:
            return f"No search results found for: {query}"
        return "\n\n".join(results[:5])
    except Exception as e:
        return f"Search error: {e}"


# ── App / hardware diagnostic tools ────────────────────────────────────────


def _safe_call(fn, default):
    try:
        return fn()
    except Exception as e:
        return f"{default} (error: {e})"


def _list_adapters() -> str:
    try:
        from core.j2534 import enumerate_devices
        devices = enumerate_devices()
    except Exception as e:
        return f"Could not enumerate adapters: {e}"
    if not devices:
        return ("No adapters detected by Fuse OBD.\n"
                "  • No J2534 PassThru DLL registered in HKLM\\SOFTWARE\\PassThruSupport.04.04\n"
                "  • No USB serial ports detected (FTDI / CH340 / CP210x / Prolific)\n"
                "  • No WiFi adapter manually added\n"
                "  • No paired Bluetooth OBD adapter selected\n"
                "Possible next steps: check Windows Device Manager for the adapter, "
                "install or re-install the J2534 driver, or pair the BT adapter in Windows first.")
    lines = [f"Fuse OBD detected {len(devices)} adapter(s):"]
    for i, d in enumerate(devices, 1):
        kind = "WiFi" if d.is_wifi else ("Serial/ELM327" if d.is_serial else "J2534 PassThru")
        if d.is_wifi:
            extra = f"host={d.host} port={d.tcp_port}"
        elif d.is_serial:
            extra = f"port={d.port}"
        else:
            extra = f"dll={d.dll_path}"
        lines.append(f"  {i}. [{kind}] {d.name}  vendor={d.vendor}  {extra}")
    return "\n".join(lines)


def _list_windows_serial_devices() -> str:
    if sys.platform != "win32":
        return "Not running on Windows."
    ps = (
        "Get-PnpDevice -Class Ports -Status OK,Error -ErrorAction SilentlyContinue | "
        "Select-Object Status,FriendlyName,InstanceId,Manufacturer | "
        "Format-List | Out-String -Width 200"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=15
        )
        text = (out.stdout or out.stderr or "").strip()
        return text[:4000] or "No serial-class devices reported."
    except Exception as e:
        return f"Error querying Device Manager: {e}"


def _list_windows_usb_devices() -> str:
    if sys.platform != "win32":
        return "Not running on Windows."
    ps = (
        "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
        "Where-Object { $_.InstanceId -like 'USB\\*' } | "
        "Select-Object Status,FriendlyName,InstanceId | "
        "Sort-Object FriendlyName | Format-List | Out-String -Width 200"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=15
        )
        text = (out.stdout or out.stderr or "").strip()
        return text[:4000] or "No USB devices reported."
    except Exception as e:
        return f"Error querying Device Manager: {e}"


def _scan_local_network_obd() -> str:
    """Probe a few common WiFi ELM327 default IPs/ports."""
    candidates = [
        ("192.168.0.10", 35000),
        ("192.168.0.10", 23),
        ("192.168.4.1", 35000),
        ("192.168.1.5", 35000),
        ("192.168.4.1", 23),
        ("192.168.0.1", 35000),
    ]
    hits = []
    misses = []
    for host, port in candidates:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.6)
            s.connect((host, port))
            s.close()
            hits.append(f"  ✓ {host}:{port} responded")
        except Exception as e:
            misses.append(f"  · {host}:{port} no response ({e.__class__.__name__})")
    out = ["WiFi ELM327 scan results:"]
    out.extend(hits or ["  (no candidate WiFi adapter answered on the usual IPs)"])
    out.append("")
    out.append("Probed:")
    out.extend(misses)
    out.append("")
    out.append("Tip: a WiFi OBD adapter usually creates its own SSID. "
               "Connect Windows to that SSID first, then probe again.")
    return "\n".join(out)


def _read_app_debug_log() -> str:
    tail = issues_log.read_app_debug_tail(8000)
    return tail or "(empty)"


def _get_app_info(state_provider) -> str:
    try:
        from version import VERSION, APP_NAME, APP_DESC
    except Exception:
        VERSION = APP_NAME = APP_DESC = "?"
    info = {
        "app_name": APP_NAME,
        "app_desc": APP_DESC,
        "app_version": VERSION,
        "python": sys.version.split()[0],
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "cwd": os.getcwd(),
        "issues_log": issues_log.issues_log_path(),
        "app_debug_log": issues_log.app_debug_log_path(),
    }
    if state_provider is not None:
        try:
            info.update(state_provider() or {})
        except Exception as e:
            info["state_provider_error"] = str(e)
    return json.dumps(info, indent=2)


def _log_issue(args: dict) -> str:
    kind = (args.get("kind") or issues_log.KIND_INFO).lower()
    severity = (args.get("severity") or issues_log.SEVERITY_LOW).lower()
    valid_kinds = {issues_log.KIND_VEHICLE, issues_log.KIND_APP,
                   issues_log.KIND_CONNECTION, issues_log.KIND_INFO}
    valid_sev = {issues_log.SEVERITY_LOW, issues_log.SEVERITY_MED,
                 issues_log.SEVERITY_HIGH, issues_log.SEVERITY_CRIT}
    if kind not in valid_kinds:
        kind = issues_log.KIND_INFO
    if severity not in valid_sev:
        severity = issues_log.SEVERITY_LOW
    issue = issues_log.add_issue(
        title=args.get("title") or "Untitled",
        kind=kind,
        severity=severity,
        summary_simple=args.get("summary_simple") or "",
        summary_technical=args.get("summary_technical") or "",
        source="ai_mechanic",
        context=args.get("context") or {},
    )
    return f"Logged issue '{issue.title}' [{issue.kind}/{issue.severity}] id={issue.id}"


# ── Tool definitions ───────────────────────────────────────────────────────


TOOLS = [
    {
        "name": "search_web",
        "description": "Search the internet for automotive diagnostic information, TSBs, forum discussions, repair guides, and common fixes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Specific search query. Include DTC code, make/model/year, and symptom."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_page",
        "description": "Fetch and read the content of a specific web page (forum post, TSB, repair guide).",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Full URL to fetch."}},
            "required": ["url"],
        },
    },
    {
        "name": "list_adapters",
        "description": "List every OBD adapter Fuse OBD can currently see: J2534, USB serial, paired Bluetooth, manually added WiFi.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_windows_serial_devices",
        "description": "Query Windows for all serial-class (Ports COM & LPT) devices, including ones Fuse OBD did not classify as an OBD adapter.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_windows_usb_devices",
        "description": "Query Windows for present USB devices. Helps spot a plugged-in adapter that didn't get a COM port.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "scan_local_network_obd",
        "description": "Probe common WiFi ELM327 default IPs/ports to detect a wireless OBD adapter on the local subnet.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_app_debug_log",
        "description": "Read the tail of Fuse OBD's own debug log file — use this when the user reports the app crashed or behaved strangely.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_app_info",
        "description": "Return Fuse OBD's version, the Python/OS info, working dir, and current connection state.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "log_issue",
        "description": "Append a finding to the persistent Issues log so the user sees it in the side pane. Always provide BOTH a plain-English summary and a technical summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short title (e.g. 'PCM not responding', 'P0420 — catalytic efficiency')."},
                "kind": {"type": "string", "enum": ["vehicle", "app", "connection", "info"], "description": "Category of issue."},
                "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"], "description": "How urgent / dangerous."},
                "summary_simple": {"type": "string", "description": "Plain English explanation 'for dummies'."},
                "summary_technical": {"type": "string", "description": "Technical details 'for nerds' — codes, registers, hex dumps, registry paths, traces."},
                "context": {"type": "object", "description": "Optional free-form context."},
            },
            "required": ["title", "summary_simple", "summary_technical"],
        },
    },
]


# ── Chat session ───────────────────────────────────────────────────────────


class MechanicChat:
    """Interactive AI mechanic with web search, app self-diagnostics and tool use."""

    def __init__(self, state_provider=None, on_tool_call=None):
        """
        state_provider: optional callable returning a dict describing the
            host app state (whether a vehicle is connected, current VIN,
            adapter info, etc). Surfaced to the model via get_app_info().
        on_tool_call: optional callable(tool_name, summary) for UI status.
        """
        self.messages: list[dict] = []
        self.vehicle_info: dict = {}
        self.dtc_data: list = []
        self._client = None
        self._state_provider = state_provider
        self._on_tool_call = on_tool_call

    # ── credentials / client ──

    @staticmethod
    def is_configured() -> bool:
        # Hosted proxy is always reachable in principle, so the client is
        # always "configured". If the hosted proxy is offline we surface
        # that as a connection error from the first send_message call.
        return True

    def _get_client(self):
        if self._client is None:
            if USE_HOSTED_PROXY:
                from modules.machine_id import get_machine_id
                try:
                    from version import VERSION
                except Exception:
                    VERSION = "?"
                kwargs = {
                    "api_key": "hosted-proxy",  # placeholder; proxy injects real auth
                    "base_url": HOSTED_PROXY_BASE_URL,
                    "timeout": 120.0,
                    "default_headers": {
                        "x-fuse-client": f"FuseOBD/{VERSION}",
                        "x-fuse-machine-id": get_machine_id(),
                        "x-fuse-os": f"{platform.system()}-{platform.release()}",
                    },
                }
            else:
                kwargs = {"api_key": LOCAL_AUTH_TOKEN, "timeout": 120.0}
                if LOCAL_BASE_URL:
                    kwargs["base_url"] = LOCAL_BASE_URL
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    # ── session lifecycle ──

    def start_session(self, vehicle_info: dict | None = None, dtc_data: list | None = None):
        """Seed an initial diagnostic message — optionally with vehicle + DTC context."""
        self.vehicle_info = vehicle_info or {}
        self.dtc_data = dtc_data or []

        fault_text = ""
        for mod in self.dtc_data:
            for dtc in mod.get("dtcs", []):
                desc = dtc.get("description", "") or "No description"
                status = dtc.get("status_text", "") or dtc.get("status", "") or "Unknown"
                fault_text += f"  [{mod['module_abbrev']}] {dtc['code']} — {desc}  [{status}]\n"

        vehicle_text = ""
        if self.vehicle_info:
            vehicle_text = "\n".join([
                f"  Year: {self.vehicle_info.get('year','?')}",
                f"  Make: {self.vehicle_info.get('make','?')}",
                f"  Model: {self.vehicle_info.get('model','?')}",
                f"  Engine: {self.vehicle_info.get('engine','?')} "
                f"({self.vehicle_info.get('displacement_l','?')}L "
                f"{self.vehicle_info.get('cylinders','?')}cyl)",
                f"  Transmission: {self.vehicle_info.get('transmission','?')}",
                f"  Body: {self.vehicle_info.get('body_class','?')}",
                f"  Built: {self.vehicle_info.get('built_at','?')}",
                f"  VIN: {self.vehicle_info.get('vin','?')}",
            ])

        opening = (
            "Hi — I'm starting an AI Mechanic session inside Fuse OBD. "
            "I can help with the vehicle, with the OBD adapter, or with the app itself.\n\n"
        )
        if vehicle_text or fault_text:
            opening += (
                "VEHICLE INFO:\n"
                f"{vehicle_text or '  (no vehicle info yet)'}\n\n"
                "FAULT CODES:\n"
                f"{fault_text or '  (no fault codes read yet)'}\n\n"
                "Please give me your initial assessment."
            )
        else:
            opening += (
                "No vehicle is connected yet. Call get_app_info() and list_adapters() "
                "first so we know what we're working with, then introduce yourself briefly "
                "and ask the user what they want to do (diagnose the car, find an adapter, "
                "or debug the app)."
            )
        self.messages = [{"role": "user", "content": opening}]

    def send_message(self, user_text: str) -> str:
        issues_log.log_ai(f"send_message start ({len(user_text)} chars)")
        self.messages.append({"role": "user", "content": user_text})
        t0 = time.time()
        try:
            reply = self._run_tool_loop()
            issues_log.log_ai(f"send_message done in {time.time() - t0:.2f}s ({len(reply)} chars)")
            return reply
        except anthropic.RateLimitError as e:
            issues_log.log_error(f"AI rate limited: {e}", exc=e)
            return "The AI service is rate limited right now. Give it a minute and try again."
        except anthropic.APIStatusError as e:
            issues_log.log_error(
                f"AI APIStatusError status={getattr(e, 'status_code', '?')} "
                f"message={getattr(e, 'message', '?')}",
                exc=e,
            )
            return f"AI service error ({getattr(e, 'status_code', '?')}): {e.message}"
        except RuntimeError as e:
            issues_log.log_error(f"AI runtime error: {e}", exc=e)
            return str(e)
        except Exception as e:
            issues_log.log_exception("AI chat error", e, kind=issues_log.KIND_APP,
                                     source="ai_chat")
            return f"AI chat error: {e}"

    def kick_off(self) -> str:
        """Run the initial seeded user message and return the mechanic's reply."""
        issues_log.log_ai("kick_off start")
        t0 = time.time()
        try:
            reply = self._run_tool_loop()
            issues_log.log_ai(f"kick_off done in {time.time() - t0:.2f}s ({len(reply)} chars)")
            return reply
        except anthropic.RateLimitError as e:
            issues_log.log_error(f"AI rate limited: {e}", exc=e)
            return "The AI service is rate limited right now. Give it a minute and try again."
        except anthropic.APIStatusError as e:
            issues_log.log_error(
                f"AI APIStatusError status={getattr(e, 'status_code', '?')} "
                f"message={getattr(e, 'message', '?')}",
                exc=e,
            )
            return f"AI service error ({getattr(e, 'status_code', '?')}): {e.message}"
        except RuntimeError as e:
            issues_log.log_error(f"AI runtime error: {e}", exc=e)
            return str(e)
        except Exception as e:
            issues_log.log_exception("AI chat error", e, kind=issues_log.KIND_APP,
                                     source="ai_chat")
            return f"AI chat error: {e}"

    # ── tool loop ──

    def _execute_tool(self, name: str, params: dict) -> str:
        if self._on_tool_call:
            try:
                self._on_tool_call(name, params)
            except Exception:
                pass
        issues_log.log_ai(f"tool start: {name} params={params}")
        t0 = time.time()
        try:
            if name == "search_web":
                result = _search_web(params.get("query", ""))
            elif name == "fetch_page":
                result = _fetch_text(params.get("url", ""))
            elif name == "list_adapters":
                result = _list_adapters()
            elif name == "list_windows_serial_devices":
                result = _list_windows_serial_devices()
            elif name == "list_windows_usb_devices":
                result = _list_windows_usb_devices()
            elif name == "scan_local_network_obd":
                result = _scan_local_network_obd()
            elif name == "read_app_debug_log":
                result = _read_app_debug_log()
            elif name == "get_app_info":
                result = _get_app_info(self._state_provider)
            elif name == "log_issue":
                result = _log_issue(params)
            else:
                result = f"Unknown tool: {name}"
        except Exception as e:
            issues_log.log_error(f"tool {name} crashed", exc=e)
            result = f"Tool {name} failed: {e.__class__.__name__}: {e}"
        dt = time.time() - t0
        issues_log.log_ai(
            f"tool done:  {name} in {dt:.2f}s ({len(result)} chars)"
        )
        return result

    def _run_tool_loop(self, max_turns: int = 12) -> str:
        current_messages = list(self.messages)
        text_blocks: list[str] = []

        issues_log.log_ai(
            f"loop start  model={MODEL} base={BASE_URL or 'default'} "
            f"mode={'hosted' if USE_HOSTED_PROXY else 'local'} msgs={len(current_messages)}"
        )

        for turn in range(max_turns):
            t0 = time.time()
            issues_log.log_ai(f"turn {turn + 1}/{max_turns} -> messages.create ({len(current_messages)} msgs)")
            try:
                response = self._get_client().messages.create(
                    model=MODEL,
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=current_messages,
                )
            except anthropic.APIStatusError as e:
                issues_log.log_error(
                    f"turn {turn + 1} APIStatusError status={e.status_code} body={getattr(e, 'body', '?')!r}"
                )
                raise
            except Exception as e:
                issues_log.log_error(f"turn {turn + 1} exception {e.__class__.__name__}", exc=e)
                raise
            dt = time.time() - t0
            usage = getattr(response, "usage", None)
            usage_str = ""
            if usage is not None:
                usage_str = (
                    f" in={getattr(usage, 'input_tokens', '?')} "
                    f"out={getattr(usage, 'output_tokens', '?')}"
                )
            block_types = [getattr(b, "type", "?") for b in response.content]
            issues_log.log_ai(
                f"turn {turn + 1} <- {dt:.2f}s stop={response.stop_reason} "
                f"blocks={block_types}{usage_str}"
            )

            tool_uses = []
            text_blocks = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_uses.append(block)
                elif block.type == "text":
                    text_blocks.append(block.text)

            if text_blocks and not tool_uses:
                final_text = "\n".join(text_blocks)
                self.messages.append({"role": "assistant", "content": final_text})
                return final_text

            if tool_uses:
                # DeepSeek's `[1m]` (1M-context, thinking-mode) variant returns
                # `thinking` blocks alongside text/tool_use. Those MUST be
                # echoed back verbatim on every subsequent turn or the API
                # rejects the request with "content[].thinking ... must be
                # passed back to the API." Preserve every block type by
                # cloning the SDK's native pydantic dump.
                assistant_content = []
                for b in response.content:
                    if b.type == "text":
                        assistant_content.append({"type": "text", "text": b.text})
                    elif b.type == "thinking":
                        block = {"type": "thinking", "thinking": getattr(b, "thinking", "")}
                        sig = getattr(b, "signature", None)
                        if sig:
                            block["signature"] = sig
                        assistant_content.append(block)
                    elif b.type == "redacted_thinking":
                        assistant_content.append({
                            "type": "redacted_thinking",
                            "data": getattr(b, "data", ""),
                        })
                    elif b.type == "tool_use":
                        assistant_content.append({
                            "type": "tool_use",
                            "id": b.id,
                            "name": b.name,
                            "input": b.input,
                        })
                current_messages.append({"role": "assistant", "content": assistant_content})

                tool_results = []
                for tu in tool_uses:
                    result_text = self._execute_tool(tu.name, dict(tu.input))
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": result_text[:6000],
                    })
                current_messages.append({"role": "user", "content": tool_results})
                continue

            if text_blocks:
                return "\n".join(text_blocks)
            return "I'm not sure how to respond to that. Could you rephrase?"

        if text_blocks:
            return ("I've done several rounds of research but I'm going in circles. "
                    "Here's what I have so far:\n\n" + "\n".join(text_blocks))
        return "I couldn't reach a conclusion. Let me start fresh — what would you like to know?"
