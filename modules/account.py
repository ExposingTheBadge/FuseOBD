"""Fuse OBD client-side account & session management.

Talks to the Fuse-Web server at FUSE_ACCOUNT_BASE_URL (defaults to the
public hosted proxy). Stores the session token in the app's local data
directory, encrypted with Windows DPAPI when available so other users
on the machine can't read it, falling back to a 0o600 file on
non-Windows systems.

Public API:
    register(email, password)      -> User
    login(email, password)         -> User
    logout()
    current_user(force=False)      -> User | None
    request_upgrade(note)
    refresh()                      -> User | None  (re-pulls /auth/me)
    auth_token()                   -> str | None  (for AI proxy header)
    base_url()                     -> str         (server URL the app uses)
    is_signed_in()                 -> bool
    has_feature(name)              -> bool
    quota_remaining()              -> int | None  (None = unlimited)

All network failures raise AccountError. UI code is expected to catch
and surface a friendly message.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Optional

try:
    from modules import issues_log
    def _log(msg: str) -> None:
        try: issues_log.log_ai(msg)
        except Exception: pass
except Exception:
    def _log(_msg: str) -> None: pass

try:
    from modules.machine_id import get_machine_id
except Exception:
    def get_machine_id() -> str: return "unknown"

try:
    from version import VERSION
except Exception:
    VERSION = "?"


# Public hosted server URL — same machine that runs the AI proxy.
# Users can override with FUSE_ACCOUNT_BASE_URL to talk to a self-hosted
# instance / local dev server.
DEFAULT_BASE_URL = os.environ.get(
    "FUSE_ACCOUNT_BASE_URL",
    "https://fuseobd.com",
).rstrip("/")

# Token cache file — stored in the app's local data directory.
def _data_dir() -> str:
    # Prefer a folder next to the EXE so the user can find/clear it.
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    return base

_TOKEN_FILE = os.path.join(_data_dir(), ".fuse_session")


class AccountError(Exception):
    """Raised when an auth request fails. ``code`` is the HTTP status (or
    -1 on network errors). ``message`` is safe to show to the user."""
    def __init__(self, message: str, code: int = -1):
        super().__init__(message)
        self.code = code
        self.message = message


# ───────────────────────── DPAPI / secure token storage ─────────────────────

def _dpapi_protect(plaintext: bytes) -> Optional[bytes]:
    if platform.system() != "Windows":
        return None
    try:
        import win32crypt  # type: ignore[import-not-found]
        # CryptProtectData binds the blob to the current user account.
        return win32crypt.CryptProtectData(plaintext, "fuse-obd-session", None, None, None, 0)
    except Exception:
        return None


def _dpapi_unprotect(ciphertext: bytes) -> Optional[bytes]:
    if platform.system() != "Windows":
        return None
    try:
        import win32crypt  # type: ignore[import-not-found]
        _desc, data = win32crypt.CryptUnprotectData(ciphertext, None, None, None, 0)
        return data
    except Exception:
        return None


def _save_token_blob(payload: dict) -> None:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    enc = _dpapi_protect(raw)
    try:
        with open(_TOKEN_FILE, "wb") as f:
            if enc is not None:
                f.write(b"FUSEDPAPIv1\n")
                f.write(enc)
            else:
                f.write(b"FUSEPLAIN1\n")
                f.write(raw)
        if platform.system() != "Windows":
            try: os.chmod(_TOKEN_FILE, 0o600)
            except OSError: pass
    except OSError as e:
        _log(f"account: failed to persist session token: {e}")


def _load_token_blob() -> Optional[dict]:
    try:
        with open(_TOKEN_FILE, "rb") as f:
            raw = f.read()
    except (OSError, FileNotFoundError):
        return None
    if not raw:
        return None
    if raw.startswith(b"FUSEDPAPIv1\n"):
        data = _dpapi_unprotect(raw[len(b"FUSEDPAPIv1\n"):])
        if not data: return None
    elif raw.startswith(b"FUSEPLAIN1\n"):
        data = raw[len(b"FUSEPLAIN1\n"):]
    else:
        # legacy / unknown blob
        data = raw
    try:
        return json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _clear_token_blob() -> None:
    try:
        if os.path.exists(_TOKEN_FILE):
            os.remove(_TOKEN_FILE)
    except OSError as e:
        _log(f"account: failed to remove session token: {e}")


# ───────────────────────── module state ─────────────────────────────────────

_state_lock = threading.Lock()
_session_token: Optional[str] = None
_cached_user: Optional[dict] = None
_cached_at: float = 0.0
_CACHE_TTL = 60.0  # seconds — refresh /auth/me at most once a minute


def base_url() -> str:
    return DEFAULT_BASE_URL


def _http(method: str, path: str, body: Optional[dict] = None, token: Optional[str] = None,
          timeout: float = 12.0) -> tuple[int, dict]:
    url = f"{base_url()}{path}"
    headers = {
        "Accept": "application/json",
        "x-fuse-client": f"FuseOBD/{VERSION}",
        "x-fuse-machine-id": get_machine_id(),
        "x-fuse-os": f"{platform.system()}-{platform.release()}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, {"raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try:
            return e.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return e.code, {"error": raw or e.reason or "HTTP error"}
    except urllib.error.URLError as e:
        raise AccountError(f"Cannot reach Fuse OBD server: {e.reason}", -1)
    except Exception as e:
        raise AccountError(f"Network error: {e}", -1)


def _set_session(token: str, user: dict) -> None:
    global _session_token, _cached_user, _cached_at
    with _state_lock:
        _session_token = token
        _cached_user = user
        _cached_at = time.time()
    _save_token_blob({"token": token, "saved_at": time.time()})


def _load_session_from_disk() -> Optional[str]:
    blob = _load_token_blob()
    if not blob or not blob.get("token"):
        return None
    return str(blob["token"])


def boot() -> None:
    """Called once at app startup. Loads the saved token and tries
    /auth/me to verify it's still valid. Safe to call from a worker
    thread — never raises."""
    global _session_token
    tok = _load_session_from_disk()
    if not tok:
        return
    with _state_lock:
        _session_token = tok
    try:
        refresh()
    except Exception as e:
        _log(f"account: boot refresh failed ({e}) — token kept for retry")


def auth_token() -> Optional[str]:
    return _session_token


def is_signed_in() -> bool:
    return bool(_session_token and _cached_user)


def current_user(force: bool = False) -> Optional[dict]:
    if not _session_token:
        return None
    if not force and _cached_user and (time.time() - _cached_at) < _CACHE_TTL:
        return _cached_user
    try:
        return refresh()
    except AccountError:
        return _cached_user  # serve stale rather than nothing


def refresh() -> Optional[dict]:
    global _cached_user, _cached_at, _session_token
    if not _session_token:
        return None
    status, body = _http("GET", "/api/v1/auth/me", token=_session_token)
    if status == 200 and isinstance(body, dict) and body.get("user"):
        with _state_lock:
            _cached_user = body["user"]
            _cached_at = time.time()
        return _cached_user
    if status == 401:
        # token invalidated upstream — drop it
        with _state_lock:
            _session_token = None
            _cached_user = None
        _clear_token_blob()
        return None
    raise AccountError(_err_message(body, "Unable to refresh account"), status)


def register(email: str, password: str) -> dict:
    status, body = _http("POST", "/api/v1/auth/register",
                         {"email": email, "password": password,
                          "machine_id": get_machine_id()})
    if status == 200 and body.get("ok"):
        _set_session(body["token"], body["user"])
        _log(f"account: registered {email}")
        return body["user"]
    raise AccountError(_err_message(body, "Registration failed"), status)


def change_password(current_password: str, new_password: str) -> None:
    """Change the signed-in user's password. Raises AccountError on
    failure (wrong current password, weak new password, network)."""
    if not _session_token:
        raise AccountError("Sign in first.", 401)
    status, body = _http("POST", "/api/v1/auth/change-password",
                         {"current_password": current_password,
                          "new_password": new_password},
                         token=_session_token)
    if status == 200 and body.get("ok"):
        _log("account: password changed")
        # Re-pull /me so cached `must_change_password` flag flips off
        try: refresh()
        except Exception: pass
        return
    raise AccountError(_err_message(body, "Could not change password"), status)


def revoke_other_sessions() -> int:
    """Boots every other session for this user (keeps the current one).
    Returns number of sessions revoked."""
    if not _session_token:
        raise AccountError("Sign in first.", 401)
    status, body = _http("POST", "/api/v1/auth/revoke-sessions",
                         {"keep_current": True},
                         token=_session_token)
    if status == 200 and body.get("ok"):
        n = int(body.get("revoked") or 0)
        _log(f"account: revoked {n} other session(s)")
        return n
    raise AccountError(_err_message(body, "Could not revoke sessions"), status)


def must_change_password() -> bool:
    """True if the server has flagged this user as needing to change
    their password before continuing (typically after an admin reset)."""
    u = _cached_user
    return bool(u and u.get("must_change_password"))


def google_available() -> bool:
    """Returns True if the server has Google OAuth configured."""
    try:
        status, body = _http("GET", "/api/v1/auth/google/config", timeout=4.0)
        return status == 200 and bool(body.get("configured"))
    except AccountError:
        return False


def google_begin() -> dict:
    """Kick off a desktop Google sign-in. Returns {device_code, authorize_url,
    poll_interval_ms, expires_in_ms}. The caller should open the browser to
    ``authorize_url`` and then poll google_poll(device_code) until it
    resolves."""
    status, body = _http("POST", "/api/v1/auth/desktop/begin", {})
    if status != 200 or "device_code" not in body:
        raise AccountError(_err_message(body, "Could not start Google sign-in"), status)
    return body


def google_poll(device_code: str) -> Optional[dict]:
    """Poll for a desktop Google sign-in completion. Returns:
        None  → still pending
        dict  → signed in (session is now stored)
    Raises AccountError on expired/cancelled."""
    status, body = _http("GET",
                         f"/api/v1/auth/desktop/poll?device_code={device_code}")
    if status == 200 and body.get("status") == "complete":
        _set_session(body["token"], body["user"])
        _log(f"account: signed in via Google ({body['user'].get('email')})")
        return body["user"]
    if status == 200 and body.get("status") == "pending":
        return None
    if status == 404 or body.get("status") == "expired":
        raise AccountError("Sign-in window expired. Please try again.", 410)
    raise AccountError(_err_message(body, "Google sign-in failed"), status)


def login(email: str, password: str) -> dict:
    status, body = _http("POST", "/api/v1/auth/login",
                         {"email": email, "password": password,
                          "machine_id": get_machine_id()})
    if status == 200 and body.get("ok"):
        _set_session(body["token"], body["user"])
        _log(f"account: signed in {email}")
        return body["user"]
    raise AccountError(_err_message(body, "Sign-in failed"), status)


def logout() -> None:
    global _session_token, _cached_user, _cached_at
    token = _session_token
    with _state_lock:
        _session_token = None
        _cached_user = None
        _cached_at = 0.0
    _clear_token_blob()
    if token:
        try: _http("POST", "/api/v1/auth/logout", token=token)
        except Exception: pass
    _log("account: signed out")


def billing_config() -> Optional[dict]:
    """Public — returns server's /api/v1/billing/config response with
    plan prices, currency, computed annual discount, and whether Stripe
    checkout is wired up. Returns None on network failure."""
    try:
        status, body = _http("GET", "/api/v1/billing/config")
        if status == 200 and isinstance(body, dict):
            return body
    except Exception:
        pass
    return None


def begin_checkout(interval: str) -> Optional[str]:
    """Asks the server for a Stripe Checkout URL. Returns the URL on
    success, raises AccountError otherwise. `interval` must be
    'monthly' or 'yearly'."""
    if interval not in ("monthly", "yearly"):
        raise AccountError("interval must be 'monthly' or 'yearly'.", 400)
    if not _session_token:
        raise AccountError("Sign in first.", 401)
    status, body = _http("POST", "/api/v1/billing/checkout",
                         {"interval": interval}, token=_session_token)
    if status == 200 and body.get("checkout_url"):
        return body["checkout_url"]
    raise AccountError(_err_message(body, "Could not start checkout"), status)


def begin_paypal_subscribe(interval: str) -> Optional[str]:
    """Asks the server to create a PayPal subscription. Returns the
    PayPal approval URL the user should be redirected to. Same shape as
    begin_checkout(), but uses the PayPal processor on the server side.
    Once approved, PayPal redirects the browser to
    /api/v1/billing/paypal/return which flips the user's tier to Pro."""
    if interval not in ("monthly", "yearly"):
        raise AccountError("interval must be 'monthly' or 'yearly'.", 400)
    if not _session_token:
        raise AccountError("Sign in first.", 401)
    status, body = _http("POST", "/api/v1/billing/paypal/subscribe",
                         {"interval": interval}, token=_session_token)
    if status == 200 and body.get("approval_url"):
        return body["approval_url"]
    raise AccountError(_err_message(body, "Could not start PayPal subscription"), status)


def has_feature(name: str) -> bool:
    u = _cached_user
    if not u:
        return False
    features = u.get("features") or {}
    return bool(features.get(name, False))


def quota_remaining() -> Optional[int]:
    u = _cached_user
    if not u:
        return 0
    q = u.get("ai_quota") or {}
    return q.get("remaining")  # None = unlimited


def tier_id() -> str:
    u = _cached_user
    if not u: return "anonymous"
    return u.get("tier") or "free"


def is_admin() -> bool:
    u = _cached_user
    return bool(u and u.get("is_admin"))


def _err_message(body: dict, default: str) -> str:
    if not isinstance(body, dict):
        return default
    msg = body.get("error")
    if isinstance(msg, str) and msg.strip():
        return msg
    msg = body.get("message")
    if isinstance(msg, str) and msg.strip():
        return msg
    # nested Anthropic-style {error: {message}}
    nested = body.get("error")
    if isinstance(nested, dict) and isinstance(nested.get("message"), str):
        return nested["message"]
    return default
