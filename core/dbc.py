"""Minimal CAN DBC-file parser.

DBC is the de-facto standard format for CAN signal databases — each
file defines messages (CAN ID + DLC + signal layout) with named
signals carrying bit position, scale factor, unit, and value-enum
lookups. Every serious CAN tool consumes them.

This parser is deliberately small (~200 lines, no deps). It supports
the subset FuseOBD actually needs:

  BU_         (network nodes)        -> ignored
  BO_         (message)               -> Message dataclass
  SG_         (signal)                -> Signal dataclass
  VAL_TABLE_  (enum table)            -> dict mapped on Signal.values
  VAL_        (signal-enum binding)   -> dict mapped on Signal.values
  CM_         (comments)              -> ignored

Bundled databases live in data/dbc/ — see data/dbc_manifest.py for
the list. Lifted from commaai/opendbc (MIT license).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional, Union


@dataclass
class Signal:
    name: str
    start_bit: int
    length: int
    byte_order: str    # 'little' (Intel, 1) or 'big' (Motorola, 0)
    is_signed: bool
    factor: float
    offset: float
    minimum: float
    maximum: float
    unit: str
    receivers: tuple[str, ...] = ()
    values: dict[int, str] = field(default_factory=dict)
    comment: str = ""

    def decode(self, data: bytes) -> Union[float, int, str]:
        """Decode this signal's raw value from `data` (the message
        payload). Returns the scaled physical value, or the enum
        string when a VAL_ table is bound and the raw matches."""
        raw = _extract_bits(data, self.start_bit, self.length,
                            self.byte_order, self.is_signed)
        if self.values and raw in self.values:
            return self.values[raw]
        return raw * self.factor + self.offset


@dataclass
class Message:
    frame_id: int      # CAN ID (29-bit if >= 0x800)
    name: str
    length: int        # DLC in bytes
    sender: str
    signals: list[Signal] = field(default_factory=list)
    comment: str = ""

    @property
    def is_extended(self) -> bool:
        # opendbc encodes extended-frame messages with high bit set; some
        # files use plain 11-bit IDs with no marker. We treat anything
        # >= 0x800 as extended unless an ID >0x1FFFFFFF is seen.
        return self.frame_id >= 0x800

    @property
    def can_id(self) -> int:
        # Strip the opendbc extended-frame marker (bit 31).
        return self.frame_id & 0x1FFFFFFF


@dataclass
class Database:
    messages: dict[int, Message] = field(default_factory=dict)
    value_tables: dict[str, dict[int, str]] = field(default_factory=dict)

    def by_id(self, can_id: int) -> Optional[Message]:
        # Match on the masked ID so the caller can pass either 11-bit
        # or 29-bit values without worrying about the extended marker.
        for fid, msg in self.messages.items():
            if (fid & 0x1FFFFFFF) == (can_id & 0x1FFFFFFF):
                return msg
        return None

    def by_name(self, name: str) -> Optional[Message]:
        for m in self.messages.values():
            if m.name == name: return m
        return None

    def decode_frame(self, can_id: int, data: bytes) -> Optional[dict]:
        m = self.by_id(can_id)
        if not m: return None
        out = {}
        for s in m.signals:
            try: out[s.name] = s.decode(data)
            except Exception: out[s.name] = None
        return out


# ── Parser ───────────────────────────────────────────────────────────

_BO_RE = re.compile(r'^BO_\s+(\d+)\s+(\S+?)\s*:\s*(\d+)\s+(\S+)')
_SG_RE = re.compile(
    r'^\s*SG_\s+(\S+?)\s*(?:M|m\d+)?\s*:\s*'    # name
    r'(\d+)\|(\d+)\@(\d)([+-])\s+'                # start|len@order(sign)
    r'\(([^,]+),([^\)]+)\)\s+'                   # (factor, offset)
    r'\[([^|]*)\|([^\]]*)\]\s+'                  # [min|max]
    r'"([^"]*)"\s*(.*)$',                        # "unit" receivers
)
_VAL_TABLE_RE = re.compile(r'^VAL_TABLE_\s+(\S+)\s+(.*?);?\s*$')
_VAL_RE = re.compile(r'^VAL_\s+(\d+)\s+(\S+)\s+(.*?);?\s*$')


def _parse_pairs(s: str) -> dict[int, str]:
    """Parse a sequence of `<int> "string" <int> "string" ...` pairs."""
    pairs: dict[int, str] = {}
    # Walk tokens: alternating int + quoted string
    i = 0
    s = s.strip().rstrip(';').strip()
    while i < len(s):
        # consume int
        m = re.match(r'\s*(-?\d+)', s[i:])
        if not m: break
        num = int(m.group(1)); i += m.end()
        # consume string
        m2 = re.match(r'\s*"([^"]*)"', s[i:])
        if not m2: break
        pairs[num] = m2.group(1)
        i += m2.end()
    return pairs


def parse_dbc(text: str) -> Database:
    db = Database()
    current_msg: Optional[Message] = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.startswith('CM_') or line.startswith('NS_') \
           or line.startswith('BA_') or line.startswith('BU_') \
           or line.startswith('VERSION') or line.startswith('BS_:'):
            continue

        # ── Message ──
        m = _BO_RE.match(line)
        if m:
            fid = int(m.group(1))
            current_msg = Message(
                frame_id=fid,
                name=m.group(2),
                length=int(m.group(3)),
                sender=m.group(4),
            )
            db.messages[fid] = current_msg
            continue

        # ── Signal ──
        sg = _SG_RE.match(line)
        if sg and current_msg is not None:
            order_char = sg.group(4)
            sign_char = sg.group(5)
            try:
                receivers = tuple(sg.group(11).strip().split(',')) if sg.group(11) else ()
            except Exception:
                receivers = ()
            current_msg.signals.append(Signal(
                name=sg.group(1),
                start_bit=int(sg.group(2)),
                length=int(sg.group(3)),
                byte_order='little' if order_char == '1' else 'big',
                is_signed=(sign_char == '-'),
                factor=float(sg.group(6).strip()),
                offset=float(sg.group(7).strip()),
                minimum=float(sg.group(8).strip() or '0'),
                maximum=float(sg.group(9).strip() or '0'),
                unit=sg.group(10),
                receivers=receivers,
            ))
            continue

        # ── Value table (defined separately) ──
        vt = _VAL_TABLE_RE.match(line)
        if vt:
            db.value_tables[vt.group(1)] = _parse_pairs(vt.group(2))
            continue

        # ── Per-signal VAL_ binding: `VAL_ <msg_id> <signal_name> ...` ──
        v = _VAL_RE.match(line)
        if v:
            mid = int(v.group(1))
            sig_name = v.group(2)
            pairs = _parse_pairs(v.group(3))
            msg = db.messages.get(mid)
            if msg:
                for s in msg.signals:
                    if s.name == sig_name:
                        s.values.update(pairs)
                        break
            continue
    return db


def load_file(path: str) -> Database:
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return parse_dbc(f.read())


# ── Bit extraction (Intel + Motorola layouts) ────────────────────────

def _extract_bits(data: bytes, start_bit: int, length: int,
                  byte_order: str, is_signed: bool) -> int:
    """Pull `length` bits starting at `start_bit` from `data` in either
    Intel (little-endian) or Motorola (big-endian) bit order. DBC's
    Motorola scheme uses MSB-numbered bits, so the start_bit is the
    MSB of the signal."""
    if byte_order == 'little':
        # Intel: start_bit is the LSB; bits are read LSB-first
        bit = start_bit
        val = 0
        for i in range(length):
            byte_idx = (bit + i) // 8
            bit_in_byte = (bit + i) % 8
            if byte_idx >= len(data): break
            if data[byte_idx] & (1 << bit_in_byte):
                val |= (1 << i)
    else:
        # Motorola: start_bit is the MSB; walk towards LSB byte-by-byte
        val = 0
        bit = start_bit
        for _ in range(length):
            byte_idx = bit // 8
            bit_in_byte = bit % 8
            if byte_idx >= len(data): break
            if data[byte_idx] & (1 << bit_in_byte):
                val |= 1
            val <<= 1
            # Move to next bit in Motorola order
            bit = bit - 1 if bit_in_byte > 0 else bit + 15
        val >>= 1   # we shifted one too many on the last iteration

    if is_signed and (val & (1 << (length - 1))):
        val -= (1 << length)
    return val
