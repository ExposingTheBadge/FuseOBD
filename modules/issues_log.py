"""Persistent log of issues — vehicle faults, app errors, connection problems.

The log lives at %LOCALAPPDATA%/FuseOBD/issues.json and is appended to
every time the AI Mechanic, or the app itself, encounters something
worth remembering. Each entry carries two descriptions: a plain-English
one ("dummy") and a technical one ("nerd") so the user can drill in at
whatever depth they like.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, asdict, field
from typing import Optional


# ── Storage location ──

def _log_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or tempfile.gettempdir()
    path = os.path.join(base, "FuseOBD")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        path = tempfile.gettempdir()
    return path


def issues_log_path() -> str:
    return os.path.join(_log_dir(), "issues.json")


def app_debug_log_path() -> str:
    """Co-located with the issues log so the AI can read it easily."""
    return os.path.join(_log_dir(), "app_debug.log")


_lock = threading.Lock()


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

def log_app_event(message: str, *, exc: Optional[BaseException] = None) -> None:
    """Append a free-form line to the app debug log.

    Used by error capture so the AI Mechanic can read recent failures.
    """
    try:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n"
        if exc is not None:
            line += "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        with open(app_debug_log_path(), "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


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
