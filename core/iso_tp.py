"""ISO 15765-2 (ISO-TP) transport-layer constants + helpers.

Reference values for CAN baud rates, frame padding, flow-control
timing, and the single/first/consecutive/flow-control PCI bytes.
Pulled together so call sites stop sprinkling magic constants and
panels have one place to import from.
"""
from __future__ import annotations

from typing import Optional


# ── Bus speeds (Hz) ──────────────────────────────────────────────────
# Verified against ISO 15765-4 and the alfa-analysis grep 2026-06-06.

class CanBaud:
    HS_CAN_500 = 500_000     # ISO 15765-4 mandate for new OBD-II vehicles
    HS_CAN_250 = 250_000     # legacy heavy-truck OBD-II, J1939
    MS_CAN_125 = 125_000     # Ford body / GM low-speed
    SW_CAN_33333 = 33_333    # GM single-wire (informational)
    CAN_FD_1M  = 1_000_000   # CAN-FD nominal arbitration
    CAN_FD_2M  = 2_000_000   # CAN-FD data phase (common)
    CAN_FD_4M  = 4_000_000   # CAN-FD data phase (high-perf)
    CAN_FD_5M  = 5_000_000   # CAN-FD data phase (max)
    CAN_FD_8M  = 8_000_000   # CAN-FD data phase (theoretical)


# Sorted tuple for the baud-scanner to iterate when probing an unknown
# bus. HS-CAN 500k first because it's overwhelmingly the most common.
ALL_BAUDS = (
    CanBaud.HS_CAN_500,
    CanBaud.MS_CAN_125,
    CanBaud.HS_CAN_250,
    CanBaud.CAN_FD_1M,
    CanBaud.CAN_FD_2M,
    CanBaud.CAN_FD_4M,
    CanBaud.CAN_FD_5M,
)


# ── ISO-TP PCI (Protocol Control Information) bytes ─────────────────
# First byte of every ISO-TP frame indicates the frame type and length.

class PciType:
    SINGLE_FRAME       = 0x00   # 0x0L  (L = payload length, 1-7)
    FIRST_FRAME        = 0x10   # 0x1LLL (12-bit length, payload 8+ bytes)
    CONSECUTIVE_FRAME  = 0x20   # 0x2N  (N = sequence number, 0-15, wraps)
    FLOW_CONTROL_FRAME = 0x30   # 0x30 (CTS) / 0x31 (WAIT) / 0x32 (OVFLW)

    FC_CONTINUE_TO_SEND = 0x30  # FS=0
    FC_WAIT             = 0x31  # FS=1
    FC_OVERFLOW         = 0x32  # FS=2


# ── Frame padding ────────────────────────────────────────────────────
# CAN frames are fixed-length (8 bytes classic, up to 64 CAN-FD). When
# the ISO-TP payload is shorter, the remainder is padded. The padding
# byte is bus-specific — Ford modules usually expect 0xCC or 0xAA;
# the FCA alfa-analysis indexes show 0xAA dominant.

PAD_FORD = 0xCC
PAD_FCA  = 0xAA
PAD_GM   = 0xFF
PAD_ISO  = 0xCC   # ISO 15765 reference padding

# ── Default flow-control parameters ─────────────────────────────────
# Sent to a remote ECU in the Flow-Control frame after a First-Frame.
# Block size 0 means "send all consecutive frames without further FC".
# Separation time 0 means "send back-to-back" (the ECU usually clamps
# to its own min-ST anyway).

FC_DEFAULT_BLOCK_SIZE = 0x00
FC_DEFAULT_SEPARATION_TIME = 0x00


# ── Timing parameters (ISO 14229-1 + ISO 15765-2) ────────────────────
# All values in milliseconds. Ford modules generally accept the
# defaults; if a slow module returns 0x78 (response pending) the
# client should extend the P2* window per ISO 14229.

class TimingMs:
    P2_DEFAULT       = 50      # max ECU response time (client wait)
    P2_EXTENDED      = 5000    # ECU sent 0x78 — extend to P2*

    P3_CLIENT        = 5000    # tester-present heartbeat interval

    STMIN_DEFAULT_MS = 0       # min separation between consecutive frames
    STMIN_MAX_MS     = 127     # values 0xF1-0xF9 are sub-ms

    P2_CAN_DEFAULT_MS = 50
    P2_STAR_CAN_DEFAULT_MS = 5000
    P2_KLINE_DEFAULT_MS = 2000   # alfa: "P2=2000ms" on K-line


# ── Helpers ──────────────────────────────────────────────────────────

def make_single_frame(payload: bytes, pad: int = PAD_ISO,
                      frame_size: int = 8) -> bytes:
    """Build an ISO-TP single-frame from payload (1-7 bytes for classic
    CAN; up to frame_size-1 for CAN-FD). Pads to frame_size with `pad`."""
    if len(payload) > frame_size - 1:
        raise ValueError(f"payload too long for single frame ({len(payload)} > {frame_size - 1})")
    out = bytes([PciType.SINGLE_FRAME | len(payload)]) + bytes(payload)
    if len(out) < frame_size:
        out += bytes([pad]) * (frame_size - len(out))
    return out


def make_first_frame(total_len: int, payload_head: bytes,
                     frame_size: int = 8) -> bytes:
    """First frame of a multi-frame ISO-TP message. total_len is the
    full payload length (12-bit, max 4095 classic; CAN-FD extends via
    32-bit FF_DL but we don't emit that here)."""
    if total_len > 0xFFF:
        raise ValueError("total_len exceeds 12-bit FF_DL limit")
    head = bytes([PciType.FIRST_FRAME | ((total_len >> 8) & 0x0F),
                  total_len & 0xFF])
    out = head + bytes(payload_head)[:frame_size - 2]
    if len(out) < frame_size:
        out += bytes([PAD_ISO]) * (frame_size - len(out))
    return out


def make_consecutive_frame(seq: int, chunk: bytes, pad: int = PAD_ISO,
                           frame_size: int = 8) -> bytes:
    out = bytes([PciType.CONSECUTIVE_FRAME | (seq & 0x0F)]) + bytes(chunk)
    if len(out) < frame_size:
        out += bytes([pad]) * (frame_size - len(out))
    return out


def make_flow_control(flag: int = PciType.FC_CONTINUE_TO_SEND,
                      block_size: int = FC_DEFAULT_BLOCK_SIZE,
                      stmin: int = FC_DEFAULT_SEPARATION_TIME,
                      frame_size: int = 8) -> bytes:
    out = bytes([flag, block_size & 0xFF, stmin & 0xFF])
    if len(out) < frame_size:
        out += bytes([PAD_ISO]) * (frame_size - len(out))
    return out


def parse_pci(first_byte: int) -> tuple[int, Optional[int]]:
    """Return (pci_type, length_or_seq). For SINGLE/CONSECUTIVE the
    second value is the payload length or sequence number; for FIRST
    and FLOW the caller needs to parse further bytes."""
    pci = first_byte & 0xF0
    sub = first_byte & 0x0F
    return pci, sub
