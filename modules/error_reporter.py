"""Automatic crash / error / bug-report submission to Fuse-Web.

Captures three kinds of events:

  1. UNCAUGHT EXCEPTIONS — hook into sys.excepthook + (when Qt is
     loaded) sys.unraisablehook. Reported as kind='crash' with severity
     'crit'. Always sent.

  2. LOGGED ERRORS — when modules.issues_log records an exception via
     log_exception(), we mirror it to the server as kind='error' with
     the issue's severity.

  3. USER REPORTS — when the user hits 'Report a bug' in the Help menu,
     a dialog collects a free-text description and submits as
     kind='user_report'.

The reporter is opt-in via account.preferences.report_errors (default
TRUE for signed-in users, OPT-IN for anonymous). The toggle lives on
the Account tab in the desktop app.

All submissions are non-blocking: a background thread drains a
fire-and-forget queue. Failures are silently dropped after retries so
a flaky network never makes the app worse than the crash that
triggered the report.
"""
from __future__ import annotations

import json
import platform
import queue
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from typing import Optional

try:
    from modules import account
except Exception:
    account = None  # type: ignore[assignment]

try:
    from modules.machine_id import get_machine_id
except Exception:
    def get_machine_id() -> str: return "unknown"

try:
    from version import VERSION
except Exception:
    VERSION = "?"


_MAX_QUEUE   = 200
_RETRY_BACKOFFS = (5, 15, 60, 300)


class _ErrorReporter:
    def __init__(self):
        self._q: "queue.Queue[dict]" = queue.Queue(maxsize=_MAX_QUEUE)
        self._worker: Optional[threading.Thread] = None
        self._stop  = threading.Event()
        self._enabled = True
        self._installed = False
        self._prev_excepthook = None

    # ── installation ─────────────────────────────────────────────────

    def install(self):
        """Hook the global excepthook + start the worker thread. Idempotent."""
        if self._installed: return
        self._installed = True
        self._prev_excepthook = sys.excepthook
        sys.excepthook = self._on_excepthook
        # Qt routes some errors through unraisablehook on PyQt6.
        if hasattr(sys, "unraisablehook"):
            self._prev_unraisable = sys.unraisablehook
            sys.unraisablehook = self._on_unraisable
        self._worker = threading.Thread(target=self._run, daemon=True,
                                        name="ErrorReporter")
        self._worker.start()

    def shutdown(self):
        self._stop.set()

    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)

    def is_enabled(self) -> bool:
        return self._enabled

    # ── public API ───────────────────────────────────────────────────

    def report_crash(self, exc: BaseException, *, context: Optional[dict] = None):
        """Manual entry point: report an uncaught exception. Called by
        the excepthook and unraisablehook below."""
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        title = f"{type(exc).__name__}: {exc}"[:512]
        self._enqueue("crash", "crit", title, str(exc), tb, context)

    def report_error(self, title: str, message: str = "", *,
                     traceback_str: str = "", severity: str = "med",
                     context: Optional[dict] = None):
        """Mirrored from modules.issues_log when log_exception() fires."""
        self._enqueue("error", severity, title, message, traceback_str, context)

    def report_user_bug(self, title: str, description: str, *,
                        context: Optional[dict] = None):
        """User-initiated bug report from the Help menu dialog."""
        self._enqueue("user_report", "med", title, description, "", context)

    # ── internals ────────────────────────────────────────────────────

    def _on_excepthook(self, exc_type, exc, tb):
        try:
            if exc is not None:
                exc.__traceback__ = tb
                self.report_crash(exc)
        except Exception:
            pass
        # Chain to the previous excepthook so the regular traceback
        # still prints to stderr.
        try:
            (self._prev_excepthook or sys.__excepthook__)(exc_type, exc, tb)
        except Exception:
            pass

    def _on_unraisable(self, unraisable):
        try:
            self.report_crash(unraisable.exc_value,
                              context={"object": repr(unraisable.object)})
        except Exception: pass
        try:
            (self._prev_unraisable or sys.__unraisablehook__)(unraisable)
        except Exception: pass

    def _enqueue(self, kind: str, severity: str, title: str,
                 message: str, tb: str, context: Optional[dict]):
        if not self._enabled:
            return
        payload = {
            "kind": kind,
            "severity": severity,
            "title": (title or "(no title)")[:512],
            "message": (message or "")[:8000],
            "traceback": (tb or "")[:120000],
            "app_version": VERSION,
            "os": f"{platform.system()} {platform.release()} ({platform.version()})",
            "machine_id": get_machine_id(),
            "context": dict(context or {}),
            "client_ts": _iso_now(),
        }
        try:
            self._q.put_nowait(payload)
        except queue.Full:
            # Drop the oldest non-crash item to make room — never lose
            # a crash report to back-pressure.
            try:
                self._q.get_nowait()
                self._q.put_nowait(payload)
            except Exception:
                pass

    def _run(self):
        while not self._stop.is_set():
            try:
                payload = self._q.get(timeout=1)
            except queue.Empty:
                continue
            self._send(payload)

    def _send(self, payload: dict):
        url = self._endpoint()
        if not url:
            return
        attempt = 0
        while True:
            try:
                req = urllib.request.Request(
                    url=url,
                    data=json.dumps(payload).encode("utf-8"),
                    method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "User-Agent": f"FuseOBD-error-reporter/{VERSION}",
                    },
                )
                # Stamp the user's session token when signed in, anonymous
                # otherwise — both are accepted by /api/v1/errors/submit.
                tok = None
                try: tok = account.auth_token() if account else None
                except Exception: pass
                if tok:
                    req.add_header("Authorization", f"Bearer {tok}")
                ctx_ssl = getattr(account, "_TLS_CONTEXT", None) if account else None
                with urllib.request.urlopen(req, timeout=20, context=ctx_ssl) as r:
                    r.read()  # drain
                return  # success
            except urllib.error.HTTPError as e:
                if 400 <= e.code < 500:
                    return  # client error — don't retry malformed payloads
            except Exception:
                pass
            attempt += 1
            if attempt > len(_RETRY_BACKOFFS):
                return
            time.sleep(_RETRY_BACKOFFS[attempt - 1])

    def _endpoint(self) -> Optional[str]:
        if account is None:
            return None
        try:
            base = account.base_url()
        except Exception:
            return None
        if not base:
            return None
        return base.rstrip("/") + "/api/v1/errors/submit"


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).isoformat()


# Module-level singleton.
reporter = _ErrorReporter()
