"""Thin client for the Fuse-Web Claude Code CLI relay.

Lets the AI Mechanic forward a prompt to the server's local `claude`
binary instead of going through DeepSeek. Useful when an admin wants
to consult Claude on a tricky diagnostic, or for any signed-in user
whose account has been routed to the claude_cli upstream by an admin.

Session continuity is handled by the server — we cache the local
session_id between calls so context persists across consults.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Optional

try:
    from modules import account
except Exception:
    account = None  # type: ignore[assignment]


_state_lock = threading.Lock()
_session_id: Optional[int] = None


class ConsultError(Exception):
    def __init__(self, message: str, code: int = 0):
        super().__init__(message)
        self.message = message
        self.code = code


def _http(method: str, path: str, body: Optional[dict] = None,
          timeout: float = 120.0) -> tuple[int, dict]:
    if account is None:
        raise ConsultError("account module unavailable", -1)
    base = account.base_url().rstrip("/")
    token = account.auth_token()
    if not token:
        raise ConsultError("not signed in", 401)
    req = urllib.request.Request(
        url=f"{base}{path}",
        data=json.dumps(body or {}).encode("utf-8") if body is not None else None,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=account._TLS_CONTEXT) as r:
            raw = r.read().decode("utf-8", errors="replace")
            try: return r.status, json.loads(raw)
            except json.JSONDecodeError: return r.status, {"raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try: parsed = json.loads(raw)
        except Exception: parsed = {"error": raw or e.reason or "HTTP error"}
        raise ConsultError(parsed.get("error", str(e)), e.code)
    except urllib.error.URLError as e:
        raise ConsultError(f"cannot reach Fuse OBD server: {e.reason}", -1)


def _ensure_session() -> int:
    global _session_id
    with _state_lock:
        if _session_id is not None:
            return _session_id
        # Try to reuse an existing "AI Mechanic consult" session first.
        try:
            status, data = _http("GET", "/api/v1/claude/sessions")
            for s in (data.get("sessions") or []):
                if (s.get("label") or "").startswith("AI Mechanic consult"):
                    _session_id = int(s["id"])
                    return _session_id
        except ConsultError:
            pass
        # Create a fresh one.
        _, data = _http("POST", "/api/v1/claude/sessions",
                         body={"label": "AI Mechanic consult"})
        sess = data.get("session") or {}
        sid = int(sess.get("id", 0)) or 0
        if not sid:
            raise ConsultError("server didn't return a session id", -1)
        _session_id = sid
        return sid


def availability() -> dict:
    """Quick {available, version, reason} probe."""
    try:
        _, data = _http("GET", "/api/v1/claude/availability", timeout=10)
        return data
    except ConsultError as e:
        return {"available": False, "reason": e.message}


def consult(prompt: str, *, model: Optional[str] = None) -> str:
    """Send `prompt` to Claude Code via the server relay; return the
    assistant's text. Raises ConsultError on failure."""
    if not prompt or not prompt.strip():
        raise ConsultError("prompt is empty", 400)
    sid = _ensure_session()
    body: dict = {"prompt": prompt}
    if model: body["model"] = model
    status, data = _http("POST", f"/api/v1/claude/sessions/{sid}/chat", body=body)
    if not data.get("ok", True):
        raise ConsultError(data.get("error") or "claude relay error", status or 500)
    return data.get("response") or ""


def reset_session() -> None:
    """Forget the cached session id so the next consult() starts a new
    Claude conversation."""
    global _session_id
    with _state_lock:
        _session_id = None
