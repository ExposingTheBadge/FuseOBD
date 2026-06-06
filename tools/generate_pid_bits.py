"""Generate data/pid_bits.py from AndrOBD's pids.csv.

AndrOBD's catalog (fr3ts0n/AndrOBD, GPL-3.0) is the only public PID
table I've seen that records per-BIT semantics — the standard
Mode $01 catalog only gives one entry per PID byte, but a single PID
byte often packs four or five distinct bits (e.g. PID 0x01 carries
the MIL-on flag in bit 7 alongside the DTC count in bits 0-6, plus
the misfire/fuel/component test-completion flags in bits 8-23).

This module produces per-bit decoders so the live-data panel can
surface each named flag separately.

Run once from D:/APP/FuseOBD after fetching pids.csv to
$TEMP/androbd_pids.csv.
"""
import csv
import os

SRC = os.environ.get('TEMP', '/tmp') + '/androbd_pids.csv'
TARGET = 'data/pid_bits.py'

entries = []
# Force tab delimiter — the file's header includes a literal comma
# inside one of the column names ("mnemonic (openxc mapping?, ..."),
# which throws off csv.Sniffer's auto-detect.
with open(SRC, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f, delimiter='\t')
    for row in reader:
        # Tab-separated header is consistent: svc, pid, ofs, len,
        # bit_offset, bit_length, bit_mask, formula, format, min, max,
        # update_cycle_ms, mnemonic, label, description, ...
        try:
            entries.append({
                'svc': row.get('svc', '').strip(),
                'pid': int(row['pid'], 16) if row.get('pid', '').startswith('0x') else None,
                'ofs': int(row.get('ofs') or 0),
                'len': int(row.get('len') or 1),
                'bit_offset': int(row.get('bit_offset') or 0),
                'bit_length': int(row.get('bit_length') or 0),
                'bit_mask': row.get('bit_mask', '').strip(),
                'formula': row.get('formula', '').strip(),
                'fmt': row.get('format', '').strip(),
                'mnemonic': row.get('mnemonic (openxc mapping?, translations?)') or row.get('mnemonic', '').strip(),
                'label': row.get('label', '').strip(),
                'description': row.get('description', '').strip(),
            })
        except (ValueError, KeyError):
            continue

print(f"parsed {len(entries)} rows")
# Keep only Mode-$01 entries with a valid PID
mode01 = [e for e in entries if e['pid'] is not None and '0x01' in e['svc']]
print(f"{len(mode01)} Mode-$01 rows")

BS = chr(92)

def py_str(s):
    if not s: return '""'
    return '"' + s.replace(BS, BS+BS).replace('"', BS+'"') + '"'

rows_out = []
for e in mode01:
    rows_out.append(
        f'    BitFieldPid(pid=0x{e["pid"]:02X}, ofs={e["ofs"]}, '
        f'bit_offset={e["bit_offset"]}, bit_length={e["bit_length"]}, '
        f'bit_mask={e["bit_mask"] or "0x0"}, formula={py_str(e["formula"])}, '
        f'mnemonic={py_str(e["mnemonic"])}, label={py_str(e["label"])}),'
    )

content = '''"""Per-bit PID decoding schema for OBD-II Mode $01.

Generated from fr3ts0n/AndrOBD\\'s pids.csv (GPL-3.0). Where the
standard Mode $01 catalog (data/obd2_pid_catalog.py) gives one entry
per PID byte, this file expands the bit-packed PIDs into one entry
per named flag/field — useful for PID 0x01 (MIL + DTC count +
monitor-completion flags), PID 0x1C (OBD standard), PID 0x51 (fuel
type), etc.

Each BitFieldPid pulls (bit_offset .. bit_offset+bit_length) out of
byte `ofs` of the payload, optionally re-applies a hex bit_mask, and
runs the named formula.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class BitFieldPid:
    pid: int
    ofs: int            # byte offset into the response payload
    bit_offset: int     # 0-31 within the 4-byte ofs window
    bit_length: int     # 1-32
    bit_mask: int       # additional AND mask after bit-shift
    formula: str        # AndrOBD formula name (ONETOONE, TEST_STATUS_4, ...)
    mnemonic: str       # short key name for UI / API
    label: str          # display label

    def extract(self, payload: Union[bytes, bytearray]) -> int:
        bs = bytes(payload)
        if self.ofs >= len(bs):
            return 0
        # Pull up to 4 bytes starting at ofs to allow up-to-32-bit fields.
        window = 0
        for i in range(min(4, len(bs) - self.ofs)):
            window |= bs[self.ofs + i] << (8 * i)
        val = (window >> self.bit_offset)
        if self.bit_length:
            val &= ((1 << self.bit_length) - 1)
        if self.bit_mask:
            val &= self.bit_mask
        return val


PID_BITS: list[BitFieldPid] = [
''' + '\n'.join(rows_out) + '''
]


# Convenience: group by PID for fast "what fields live in this PID's payload"
def by_pid(pid: int) -> list[BitFieldPid]:
    return [b for b in PID_BITS if b.pid == pid]
'''

with open(TARGET, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"wrote {TARGET}: {len(mode01)} bit-fields")
