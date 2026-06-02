"""ELM327 / STN1170 baud-rate switching via the ATBRD command.

Background
----------
The ELM327 and STN-based clones default to 38400 baud on the serial /
USB-CDC link between PC and adapter. Reading a few hundred PIDs is
fine at that rate, but full module scans (As-Built reads, DTC pulls
across 20+ modules, ECU programming) can be 5-20× faster on a 500k
or 1M link.

The ATBRD command negotiates a new baud rate. Wire flow per the ELM327
data sheet (§5.6 'Baud Rate Switching'):

  PC → ELM:  AT BRD <hh>          # hh = baud divisor, 4_000_000/hh = target baud
  ELM → PC:  OK                   # at OLD baud
  ELM → PC:  ELM327 v<n.n>        # SAME response, sent at the NEW baud
  PC → ELM:  CR                   # confirmation byte at NEW baud, within 75ms
  ELM → PC:  OK                   # at NEW baud (commit)

If the PC doesn't send the confirmation within 75ms, the ELM reverts
to the old baud — fail-safe behaviour so we never get stranded.

Not every adapter / clone supports ATBRD:
  - Genuine ELM327 v1.4+ : supported
  - STN1170 / OBDLink     : supported up to 2_000_000
  - Many ELM clones       : silently reject (return '?') — must remain at
                            38400/115200. core.j2534_adapters.AdapterCap.
                            HIGH_BAUD marks which adapters we know are good.

Divisor table
-------------
Public ELM datasheet plus values observed in an external Ford-
diagnostic reverse-engineering reference (analysis confirms baud
rates 57.6k / 115.2k / 128k / 256k / 500k / 1M / 2M are all reachable
on STN-class hardware).
"""
from __future__ import annotations

import time
from typing import Optional


# baud rate -> divisor (decimal); divisor written to ELM as 2-hex-digit upper-case
# ELM internal formula: baud = 4_000_000 / divisor
# Cherry-picked the divisors that land closest to each nominal rate.
BAUD_DIVISORS: dict[int, int] = {
    9600:    0x68 * 4,   # 416 — far above the BRD upper limit, only used at init
    38400:   0x68,       # 104   → 38462 baud (default)
    57600:   0x45,       # 69    → 57971 baud
    115200:  0x23,       # 35    → 114286 baud
    128000:  0x1F,       # 31    → 129032 baud
    230400:  0x11,       # 17    → 235294 baud
    256000:  0x10,       # 16    → 250000 baud
    500000:  0x08,       # 8     → 500000 baud (exact)
    1000000: 0x04,       # 4     → 1000000 baud (exact)
    2000000: 0x02,       # 2     → 2000000 baud (exact)
}


class ATBRDError(RuntimeError):
    """Raised when the ELM rejects ATBRD or the confirmation handshake fails."""


def supported_baud_rates() -> list[int]:
    """Baud rates this module knows divisors for, sorted ascending."""
    return sorted(BAUD_DIVISORS)


def divisor_for(baud: int) -> int:
    """Return the ATBRD divisor byte for `baud`. Raises ValueError for
    rates not in the table — caller should pick the nearest supported
    rate beforehand if they need fuzzy matching."""
    if baud not in BAUD_DIVISORS:
        raise ValueError(f"No ATBRD divisor for {baud} baud; supported: {supported_baud_rates()}")
    return BAUD_DIVISORS[baud]


def switch_baud(stream, current_baud: int, target_baud: int,
                set_stream_baud) -> int:
    """Negotiate the serial link to `target_baud` via ATBRD.

    Parameters
    ----------
    stream : pyserial.Serial (or compatible)
        Must have .write(bytes), .read(n, timeout_ms=...), .flush()
    current_baud : int
        The rate the link is at right now. Used to know whether to
        no-op and for error reporting.
    target_baud : int
        Desired rate. Must be in BAUD_DIVISORS.
    set_stream_baud : Callable[[int], None]
        Function the caller provides that updates the host-side serial
        port's baud rate (e.g. ``lambda b: stream.baudrate = b`` for
        pyserial). Called exactly once after the ELM acknowledges the
        switch at the old baud.

    Returns
    -------
    int : the baud the link is now running at (target_baud on success,
          current_baud on graceful failure where we successfully
          reverted).

    Raises
    ------
    ATBRDError : the adapter rejected the command outright (clone or
                 firmware doesn't support ATBRD).
    """
    if target_baud == current_baud:
        return current_baud

    divisor = divisor_for(target_baud)
    stream.flush()
    stream.write(f"ATBRD{divisor:02X}\r".encode())

    # Expect 'OK' (or '?') at the OLD baud
    resp = _read_response(stream, 800)
    if not resp or "?" in resp:
        raise ATBRDError(f"Adapter rejected ATBRD{divisor:02X} (response={resp!r}) "
                         f"— probably a clone; staying at {current_baud}")
    if "OK" not in resp.upper():
        raise ATBRDError(f"Unexpected response to ATBRD{divisor:02X}: {resp!r}")

    # Switch host-side serial baud to the new rate, then read the
    # adapter's banner at the NEW baud as proof-of-life.
    set_stream_baud(target_baud)
    banner = _read_response(stream, 1000)
    if not banner:
        # Adapter didn't echo the banner. Revert and report.
        set_stream_baud(current_baud)
        raise ATBRDError(f"No banner at {target_baud} baud after ATBRD "
                         f"— link reverted to {current_baud}")

    # Confirm within 75ms by sending CR. Adapter commits on receipt.
    stream.write(b"\r")
    commit = _read_response(stream, 200)
    if commit and "OK" in commit.upper():
        return target_baud

    # Adapter didn't ack the commit — fall back. The ELM will have
    # auto-reverted on its end after the 75ms confirmation window
    # expired, so we just need to set our side back.
    set_stream_baud(current_baud)
    raise ATBRDError(f"ATBRD commit timeout at {target_baud}; reverted to {current_baud}")


def _read_response(stream, timeout_ms: int) -> str:
    """Read until '>' prompt (or timeout) and return decoded text."""
    deadline = time.monotonic() + timeout_ms / 1000.0
    buf = bytearray()
    while time.monotonic() < deadline:
        remaining_ms = max(50, int((deadline - time.monotonic()) * 1000))
        chunk = stream.read(256, remaining_ms) if hasattr(stream, "read") else b""
        if chunk:
            buf.extend(chunk)
            if b">" in chunk:
                break
        else:
            time.sleep(0.01)
    return buf.decode("ascii", errors="replace").strip().rstrip(">").strip()
