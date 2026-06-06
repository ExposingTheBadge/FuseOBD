"""Generate data/vag_dtcs.py from AndrOBD's VAG codes.properties.

VW/Audi/SEAT/Škoda use a numeric DTC scheme distinct from SAE J2012:
codes are decimal integers from 0 (no fault) up into the tens of
thousands. AndrOBD's `library/.../prot/vag/res/codes.properties`
catalogs these.

Run once from D:/APP/FuseOBD after fetching the properties file to
$TEMP/androbd_vag_codes.properties.
"""
import os
import re

SRC = os.environ.get('TEMP', '/tmp') + '/androbd_vag_codes.properties'
TARGET = 'data/vag_dtcs.py'

with open(SRC, 'r', encoding='utf-8') as f:
    src = f.read()
pat = re.compile(r'^(\d+)\s*=\s*(.+?)\s*$', re.M)
codes = {}
for m in pat.finditer(src):
    try: cid = int(m.group(1))
    except ValueError: continue
    codes[cid] = m.group(2)
print(f"parsed {len(codes)} VAG codes")

BS = chr(92)
lines = []
for cid in sorted(codes):
    desc = codes[cid].replace(BS, BS+BS).replace('"', BS+'"')
    lines.append(f'    {cid}: "{desc}",')

content = '''"""VW / Audi / SEAT / Skoda numeric DTC catalog.

VAG uses a numeric DTC scheme distinct from SAE J2012. Codes are
decimal integers 0..max — they map to "fault locations" the dealer
tool (VAG-COM / VCDS / ODIS) recognises. Source: fr3ts0n/AndrOBD
under GPL-3.0 (their library bundles a community-curated
translation of the carscantool.de master list).

Lookup:
    >>> from data.vag_dtcs import VAG_CODES
    >>> VAG_CODES[257]
    'ABS Inlet Valve - Left Front (N101)'

Use name(code) for a safe lookup that returns a fallback string when
the code isn\\'t in the table.
"""
from __future__ import annotations


VAG_CODES: dict[int, str] = {
''' + '\n'.join(lines) + '''
}


def name(code: int) -> str:
    s = VAG_CODES.get(code)
    return s if s else f"VAG fault {code} (not in catalog)"


def has(code: int) -> bool:
    return code in VAG_CODES
'''

with open(TARGET, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"wrote {TARGET}: {len(codes)} entries")
