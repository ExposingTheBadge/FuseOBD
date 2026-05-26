"""Persistent log of issues + every byte of comms the app sees.

Log location (in order of preference):
  1. Same folder as the EXE (PyInstaller frozen build) or repo root (dev)
  2. %LOCALAPPDATA%/FuseOBD/ as a fallback if the app folder is read-only
     (e.g. installed under Program Files without admin)

Two files live in that folder:
  - fuse_obd.log    — chronological tail of EVERY interesting event:
                      OBD bytes TX/RX, adapter init, connection state,
                      AI Mechanic activity, errors, exceptions.
                      This is the file the user opens when something
                      goes wrong.
  - issues.json     — structured issues that the AI Mechanic surfaces
                      in the right-hand pane of its window.

Each Issue carries two descriptions — a plain-English one ("dummy") and
a technical one ("nerd") — so the user can drill in at whatever depth
they like.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, asdict, field
from typing import Optional


# ── Storage location ──

_DIR_CACHE: Optional[str] = None


def _app_dir() -> str:
    """Folder the user thinks of as 'where the app lives'.

    PyInstaller one-file builds: directory of sys.executable.
    Dev (running app.py): parent of this module's package.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _writable(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _log_dir() -> str:
    """App-folder first, %LOCALAPPDATA% as last resort."""
    global _DIR_CACHE
    if _DIR_CACHE:
        return _DIR_CACHE
    primary = _app_dir()
    if _writable(primary):
        _DIR_CACHE = primary
        return primary
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or tempfile.gettempdir()
    fallback = os.path.join(base, "FuseOBD")
    try:
        os.makedirs(fallback, exist_ok=True)
    except OSError:
        fallback = tempfile.gettempdir()
    _DIR_CACHE = fallback
    return fallback


def issues_log_path() -> str:
    return os.path.join(_log_dir(), "issues.json")


def app_debug_log_path() -> str:
    """Single chronological log file the user opens to see what happened."""
    return os.path.join(_log_dir(), "fuse_obd.log")


_lock = threading.Lock()
_file_lock = threading.Lock()
_session_announced = False


# ── Records ──

KIND_VEHICLE = "vehicle"
KIND_APP = "app"
KIND_CONNECTION = "connection"
KIND_INFO = "info"

SEVERITY_LOW = "low"
SEVERITY_MED = "medium"
SEVERITY_HIGH = "high"
SEVERITY_CRIT = "critical"


@dataclass
class Issue:
    id: str
    timestamp: float
    kind: str
    severity: str
    title: str
    summary_simple: str    # plain English, for non-technical users
    summary_technical: str # for nerds — codes, registers, traces
    source: str = ""       # module/panel/code-path that surfaced it
    context: dict = field(default_factory=dict)

    def time_str(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Issue":
        return cls(
            id=d.get("id") or uuid.uuid4().hex,
            timestamp=float(d.get("timestamp") or time.time()),
            kind=d.get("kind", KIND_INFO),
            severity=d.get("severity", SEVERITY_LOW),
            title=d.get("title", "Issue"),
            summary_simple=d.get("summary_simple", ""),
            summary_technical=d.get("summary_technical", ""),
            source=d.get("source", ""),
            context=d.get("context") or {},
        )


# ── I/O ──

def _read_all() -> list[Issue]:
    path = issues_log_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    out: list[Issue] = []
    for item in data:
        try:
            out.append(Issue.from_dict(item))
        except Exception:
            continue
    return out


def _write_all(items: list[Issue]) -> None:
    path = issues_log_path()
    tmp = path + ".tmp"
    payload = [i.to_dict() for i in items]
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, path)
    except OSError:
        pass


def load_issues(limit: Optional[int] = None) -> list[Issue]:
    with _lock:
        items = _read_all()
    items.sort(key=lambda i: i.timestamp, reverse=True)
    if limit is not None:
        items = items[:limit]
    return items


def add_issue(
    *,
    title: str,
    summary_simple: str,
    summary_technical: str,
    kind: str = KIND_INFO,
    severity: str = SEVERITY_LOW,
    source: str = "",
    context: Optional[dict] = None,
) -> Issue:
    issue = Issue(
        id=uuid.uuid4().hex,
        timestamp=time.time(),
        kind=kind,
        severity=severity,
        title=title.strip() or "Untitled",
        summary_simple=summary_simple.strip(),
        summary_technical=summary_technical.strip(),
        source=source.strip(),
        context=context or {},
    )
    with _lock:
        items = _read_all()
        # Soft dedupe: same kind + same title within last 60s → skip.
        cutoff = issue.timestamp - 60.0
        for existing in items:
            if (existing.kind == issue.kind
                    and existing.title == issue.title
                    and existing.timestamp >= cutoff):
                return existing
        items.append(issue)
        # Cap at 1000 most-recent entries to keep the file sane.
        items.sort(key=lambda i: i.timestamp, reverse=True)
        items = items[:1000]
        _write_all(items)
    _emit_event("add", issue)
    return issue


def clear_issues() -> None:
    with _lock:
        _write_all([])
    _emit_event("clear", None)


def remove_issue(issue_id: str) -> bool:
    with _lock:
        items = _read_all()
        new_items = [i for i in items if i.id != issue_id]
        if len(new_items) == len(items):
            return False
        _write_all(new_items)
    _emit_event("remove", issue_id)
    return True


# ── App debug logging ──
#
# Single chronological log file: fuse_obd.log (next to the EXE).
# Categories use a 4-letter tag for fast grep:
#
#   [APP ] generic app events / lifecycle
#   [ERR ] caught exceptions / errors
#   [ADPT] adapter discovery / init / open / close
#   [CONN] connection state changes (vehicle handshake, module wakeup)
#   [TX  ] bytes sent to the adapter / vehicle
#   [RX  ] bytes received from the adapter / vehicle
#   [PROT] protocol-level events (CAN frames, ISO-TP, UDS sessions)
#   [AI  ] AI Mechanic activity (turns, tools, latency, model)
#   [HTTP] outbound HTTP/HTTPS calls (updater, AI proxy)
#   [GUI ] window open/close, button clicks worth tracing
#
# Lines all start with "YYYY-MM-DD HH:MM:SS.mmm [TAG ] " for easy parsing.

_MAX_LOG_BYTES = 16 * 1024 * 1024  # 16 MB cap; rotated to fuse_obd.log.1
_log_warned_once = False


def _now() -> str:
    t = time.time()
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)) + f".{int((t % 1) * 1000):03d}"


def _rotate_if_needed(path: str) -> None:
    try:
        if os.path.exists(path) and os.path.getsize(path) > _MAX_LOG_BYTES:
            backup = path + ".1"
            try:
                if os.path.exists(backup):
                    os.remove(backup)
            except OSError:
                pass
            os.replace(path, backup)
    except OSError:
        pass


def _announce_session(f) -> None:
    """Write a banner the first time the log is touched this run."""
    global _session_announced
    if _session_announced:
        return
    _session_announced = True
    try:
        from version import VERSION
    except Exception:
        VERSION = "?"
    sep = "=" * 76
    banner = (
        f"\n{sep}\n"
        f"  Fuse OBD v{VERSION} — session started {_now()}\n"
        f"  Python {sys.version.split()[0]} on {sys.platform}\n"
        f"  Executable: {sys.executable}\n"
        f"  Log file:   {app_debug_log_path()}\n"
        f"{sep}\n"
    )
    f.write(banner)


def _write_log_line(tag: str, message: str) -> None:
    global _log_warned_once
    path = app_debug_log_path()
    try:
        _rotate_if_needed(path)
        with _file_lock:
            with open(path, "a", encoding="utf-8") as f:
                _announce_session(f)
                f.write(f"{_now()} [{tag:<4}] {message}\n")
    except OSError as e:
        if not _log_warned_once:
            _log_warned_once = True
            sys.stderr.write(f"[issues_log] cannot write {path}: {e}\n")


def log_app_event(message: str, *, exc: Optional[BaseException] = None) -> None:
    """Generic event line. Kept for backward compat with existing callers."""
    _write_log_line("APP", message)
    if exc is not None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        for line in tb.rstrip().splitlines():
            _write_log_line("ERR", line)


def log_error(message: str, *, exc: Optional[BaseException] = None) -> None:
    _write_log_line("ERR", message)
    if exc is not None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        for line in tb.rstrip().splitlines():
            _write_log_line("ERR", line)


def log_adapter(message: str) -> None:
    _write_log_line("ADPT", message)


def log_connection(message: str) -> None:
    _write_log_line("CONN", message)


def log_protocol(message: str) -> None:
    _write_log_line("PROT", message)


def log_ai(message: str) -> None:
    _write_log_line("AI", message)


def log_http(message: str) -> None:
    _write_log_line("HTTP", message)


def log_gui(message: str) -> None:
    _write_log_line("GUI", message)


def _format_bytes(data: bytes, max_show: int = 64) -> str:
    if not data:
        return "(empty)"
    hex_part = data[:max_show].hex().upper()
    # group bytes in pairs for readability
    grouped = " ".join(hex_part[i:i + 2] for i in range(0, len(hex_part), 2))
    truncated = "" if len(data) <= max_show else f" ...[+{len(data) - max_show}B]"
    try:
        ascii_part = data[:max_show].decode("ascii", errors="replace")
        # collapse control chars to dots so the log stays one line
        ascii_part = "".join(c if 32 <= ord(c) < 127 else "." for c in ascii_part)
    except Exception:
        ascii_part = ""
    return f"{len(data)}B  {grouped}{truncated}  |{ascii_part}|"


def log_tx(target: str, data: bytes) -> None:
    """Every byte sent toward an adapter or vehicle."""
    _write_log_line("TX", f"{target}  {_format_bytes(data)}")


def log_rx(source: str, data: bytes) -> None:
    """Every byte received from an adapter or vehicle."""
    _write_log_line("RX", f"{source}  {_format_bytes(data)}")


def read_app_debug_tail(max_chars: int = 8000) -> str:
    path = app_debug_log_path()
    if not os.path.exists(path):
        return "(no app debug log yet)"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = f.read()
    except OSError as e:
        return f"(could not read app log: {e})"
    if len(data) > max_chars:
        return "...[truncated]...\n" + data[-max_chars:]
    return data


# ── Pub/sub for the UI ──

_listeners: list = []


def subscribe(callback) -> None:
    """Register a UI callback to be invoked whenever the log changes.

    The callback runs in whatever thread mutated the log; UI code should
    marshal back to the main thread itself (e.g. via BasePanel.after).
    """
    if callback not in _listeners:
        _listeners.append(callback)


def unsubscribe(callback) -> None:
    if callback in _listeners:
        _listeners.remove(callback)


def _emit_event(kind: str, payload) -> None:
    for cb in list(_listeners):
        try:
            cb(kind, payload)
        except Exception:
            pass


# ── Helpers used by exception hooks ──

def log_exception(
    title: str,
    exc: BaseException,
    *,
    kind: str = KIND_APP,
    severity: str = SEVERITY_MED,
    source: str = "",
    user_action: str = "",
) -> Issue:
    """Capture a Python exception as an Issue, both for the nerd and the dummy."""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
    log_app_event(f"EXCEPTION {title}: {exc!r}", exc=exc)
    simple = (
        f"Something went wrong in the app: {exc.__class__.__name__}.\n"
        f"Short version: {exc}\n"
        f"You don't have to do anything — Fuse OBD logged it so the AI Mechanic "
        f"can take a look."
    )
    if user_action:
        simple = user_action.rstrip() + "\n\n" + simple
    technical = f"{exc.__class__.__module__}.{exc.__class__.__name__}: {exc}\n\n{tb}"
    return add_issue(
        title=title,
        kind=kind,
        severity=severity,
        summary_simple=simple,
        summary_technical=technical,
        source=source,
        context={"exception_type": exc.__class__.__name__},
    )
