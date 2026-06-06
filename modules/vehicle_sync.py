"""Real-time vehicle-data streaming from the FuseOBD client to the
Fuse-Web server.

One persistent WebSocket per active scan session. The rest of the app
calls fire-and-forget helpers (`start_session`, `emit_event`,
`emit_sample`, `identify_vehicle`, `end_session`) — every method is
non-blocking and never raises; payloads land in a thread-safe queue
that a dedicated background thread drains onto the socket.

When the server is unreachable or the user isn't signed in, the
streamer silently no-ops so the rest of the app keeps working.

Design notes:
  * Live samples are batched in 100 ms windows so high-rate PID polls
    (50–100 Hz across multiple PIDs) collapse to ~10 send calls/sec.
  * Events ship one-at-a-time so DTCs / key-learn / etc show up on the
    web side immediately.
  * `websocket-client` is used in synchronous mode from the worker
    thread — no asyncio plumbing creeps into the rest of the Qt app.
  * Server URL defaults to the same base the account module uses
    (fuseobd.com). HTTPS automatically upgrades to wss://.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Optional
from urllib.parse import urlparse

try:
    from modules import account
except Exception:
    account = None  # type: ignore[assignment]

try:
    from modules import issues_log
    def _log(msg: str) -> None:
        try: issues_log.log_app_event(f"sync: {msg}")
        except Exception: pass
except Exception:
    def _log(_msg: str) -> None: pass

try:
    from version import VERSION as _CLIENT_VERSION
except Exception:
    _CLIENT_VERSION = "?"


_SAMPLE_BATCH_MS = 100   # flush live samples every ~100ms
_MAX_QUEUE = 50000       # cap so a long disconnect doesn't OOM us
_RECONNECT_BACKOFFS = (1, 2, 5, 10, 30, 60)


def _ws_url_from_base() -> Optional[str]:
    if account is None:
        return None
    try:
        base = account.base_url()
    except Exception:
        return None
    if not base:
        return None
    u = urlparse(base)
    scheme = 'wss' if u.scheme == 'https' else 'ws'
    netloc = u.netloc or u.path  # account.base_url() always has a scheme, but be safe
    return f"{scheme}://{netloc}/ws/ingest"


class VehicleSync:
    """Singleton (per app) WebSocket streamer."""

    def __init__(self):
        self._lock = threading.RLock()
        self._queue: "queue.Queue[dict]" = queue.Queue(maxsize=_MAX_QUEUE)
        self._sample_buf: list[dict] = []
        self._sample_buf_lock = threading.Lock()
        self._sample_flush_timer: Optional[threading.Timer] = None
        self._worker: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._ws = None
        self._session_started_at_ms: Optional[int] = None
        self._connected_evt = threading.Event()
        self._server_session_id: Optional[int] = None
        self._vehicle_id: Optional[int] = None
        self._active = False
        self._adapter_meta: dict = {}

    # ── public API ───────────────────────────────────────────────────

    def is_active(self) -> bool:
        return self._active

    def start_session(self, *, adapter_name: str = "", adapter_vendor: str = "",
                      adapter_port: str = "", protocol: str = "",
                      vehicle_id: Optional[int] = None,
                      extras: Optional[dict] = None) -> None:
        """Open a streaming session. Safe to call when already active —
        previous session is closed first."""
        if not self._can_run():
            return
        if self._active:
            self.end_session()
        self._adapter_meta = {
            "client_version": _CLIENT_VERSION,
            "adapter_name": adapter_name,
            "adapter_vendor": adapter_vendor,
            "adapter_port": adapter_port,
            "protocol": protocol,
            "extras": extras or {},
        }
        self._session_started_at_ms = int(time.time() * 1000)
        self._vehicle_id = vehicle_id
        self._stop.clear()
        self._active = True
        self._connected_evt.clear()
        self._worker = threading.Thread(target=self._run, daemon=True, name="VehicleSync")
        self._worker.start()
        _log(f"session started (vehicle={vehicle_id})")

    def end_session(self, summary: Optional[str] = None) -> None:
        if not self._active:
            return
        self._enqueue({"type": "end", "summary": summary})
        # Flush any pending samples before the end packet.
        self._flush_samples_now()
        self._stop.set()
        # Worker thread closes the socket in its own teardown; give it
        # a beat to push the end message, then drop our reference.
        t = self._worker
        if t and t.is_alive():
            t.join(timeout=2.0)
        self._active = False
        self._server_session_id = None
        self._vehicle_id = None
        self._worker = None
        _log("session ended")

    def identify_vehicle(self, vin: str, defaults: Optional[dict] = None) -> None:
        if not self._active or not vin:
            return
        self._enqueue({"type": "identify_vehicle", "vin": vin, "defaults": defaults or {}})

    def emit_event(self, event_type: str, *, module: str = "", code: str = "",
                   title: str = "", payload: Optional[dict] = None,
                   ts: Optional[float] = None) -> None:
        if not self._active:
            return
        ev = {
            "event_type": event_type,
            "module": module or None,
            "code": code or None,
            "title": title or None,
            "payload": payload or {},
        }
        if ts is not None:
            ev["ts"] = self._iso(ts)
        self._enqueue({"type": "event", "event": ev})

    def emit_sample(self, pid: str, value: Optional[float] = None, *,
                    value_text: Optional[str] = None,
                    unit: str = "", ts_ms: Optional[int] = None) -> None:
        """Live-data sample. Goes into a batch buffer that flushes every
        ~100 ms."""
        if not self._active or self._session_started_at_ms is None:
            return
        sample = {
            "pid": pid,
            "ts_ms": ts_ms if ts_ms is not None else (int(time.time() * 1000) - self._session_started_at_ms),
        }
        if value is not None:
            sample["value"] = float(value)
        if value_text is not None:
            sample["value_text"] = str(value_text)
        if unit:
            sample["unit"] = unit
        with self._sample_buf_lock:
            self._sample_buf.append(sample)
        self._schedule_sample_flush()

    @property
    def server_session_id(self) -> Optional[int]:
        return self._server_session_id

    @property
    def vehicle_id(self) -> Optional[int]:
        return self._vehicle_id

    # ── internals ────────────────────────────────────────────────────

    def _can_run(self) -> bool:
        # Need a signed-in user (to authenticate the socket) and a
        # reachable server URL.
        if account is None or not account.is_signed_in():
            return False
        tok = None
        try: tok = account.auth_token()
        except Exception: pass
        if not tok:
            return False
        if not _ws_url_from_base():
            return False
        return True

    def _enqueue(self, msg: dict) -> None:
        try:
            self._queue.put_nowait(msg)
        except queue.Full:
            # Drop the oldest non-end message to make room. Keeping the
            # most recent ones is more useful when the user looks back.
            try:
                _ = self._queue.get_nowait()
                self._queue.put_nowait(msg)
            except Exception:
                pass

    def _iso(self, ts_seconds: float) -> str:
        # Postgres/Oracle TIMESTAMP WITH TIME ZONE accepts ISO 8601 strings.
        from datetime import datetime, timezone
        return datetime.fromtimestamp(ts_seconds, tz=timezone.utc).isoformat()

    def _schedule_sample_flush(self) -> None:
        if self._sample_flush_timer and self._sample_flush_timer.is_alive():
            return
        t = threading.Timer(_SAMPLE_BATCH_MS / 1000.0, self._flush_samples_now)
        t.daemon = True
        self._sample_flush_timer = t
        t.start()

    def _flush_samples_now(self) -> None:
        with self._sample_buf_lock:
            if not self._sample_buf:
                return
            batch = self._sample_buf
            self._sample_buf = []
        # 5000 sample server cap — chunk if we ever overflow.
        for i in range(0, len(batch), 4000):
            self._enqueue({"type": "samples", "samples": batch[i:i + 4000]})

    # The worker thread reconnects on failure and drains the queue.
    def _run(self) -> None:
        try:
            from websocket import create_connection, WebSocketException  # type: ignore[import-not-found]
        except Exception as e:
            _log(f"websocket-client missing ({e}) — streaming disabled")
            self._active = False
            return

        backoff_idx = 0
        while not self._stop.is_set():
            url = _ws_url_from_base()
            token = None
            try: token = account.auth_token() if account else None
            except Exception: pass
            if not url or not token:
                # Lost auth or server URL — wait a bit and recheck.
                if self._stop.wait(5):
                    break
                continue

            try:
                self._ws = create_connection(url, timeout=10)
                # Server expects the hello first; sample/event messages
                # would be rejected before this lands.
                hello = {
                    "type": "hello",
                    "token": token,
                    "vehicle_id": self._vehicle_id,
                    "meta": self._adapter_meta,
                }
                self._ws.send(json.dumps(hello))
                # Wait for the "ready" frame (or any server message).
                ready_payload = self._ws.recv()
                try:
                    msg = json.loads(ready_payload)
                except Exception:
                    msg = {}
                if msg.get("type") == "ready" and msg.get("session_id"):
                    self._server_session_id = int(msg["session_id"])
                    self._connected_evt.set()
                    _log(f"connected, server session #{self._server_session_id}")
                    backoff_idx = 0
                else:
                    _log(f"hello not acked — got {msg}")
                # If a vehicle id wasn't set yet but we know the VIN, the
                # caller will invoke identify_vehicle() — its message goes
                # through the same queue.
                self._pump()
                # _pump returns when the queue says we should stop OR the
                # socket throws. Either way drop out to reconnect.
            except WebSocketException as e:
                _log(f"ws error: {e}")
            except OSError as e:
                _log(f"ws socket error: {e}")
            except Exception as e:
                _log(f"ws unexpected error: {e}")
            finally:
                try:
                    if self._ws is not None:
                        self._ws.close()
                except Exception:
                    pass
                self._ws = None
                self._connected_evt.clear()

            if self._stop.is_set():
                break

            wait = _RECONNECT_BACKOFFS[min(backoff_idx, len(_RECONNECT_BACKOFFS) - 1)]
            backoff_idx += 1
            if self._stop.wait(wait):
                break

    def _pump(self) -> None:
        """Drain the queue onto the open socket. Returns on stop or send
        failure (caller reconnects)."""
        assert self._ws is not None
        while not self._stop.is_set():
            try:
                msg = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._ws.send(json.dumps(msg))
                if msg.get("type") == "end":
                    return
            except Exception as e:
                # Requeue so the next connect retries the message that
                # failed. Avoid an unbounded requeue loop: if the queue
                # is at capacity drop the message and continue.
                try: self._queue.put_nowait(msg)
                except Exception: pass
                _log(f"send failed, will reconnect: {e}")
                return


# Module-level singleton — every panel imports `sync` and calls methods
# on it directly so we don't have to thread a reference through the
# whole UI tree.
sync = VehicleSync()
