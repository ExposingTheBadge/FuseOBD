"""Merge AndrOBD's English DTC catalog into data/dtc_definitions.py.

AndrOBD (fr3ts0n/AndrOBD, GPL-3.0 — license-compatible with FuseOBD)
ships codes.properties under library/src/main/java/com/fr3ts0n/ecu/
prot/obd/res/ — the broadest community-maintained DTC catalog I've
seen (3,584 codes at 2026-06-06). This merger only adds codes not
already in our dict so prior FuseOBD-specific (Ford-flavored)
descriptions are preserved.

Run once from D:/APP/FuseOBD after fetching codes.properties to
$TEMP/androbd_codes.properties.
"""
import os
import re

SRC = os.environ.get('TEMP', '/tmp') + '/androbd_codes.properties'
TARGET = 'data/dtc_definitions.py'

with open(SRC, 'r', encoding='utf-8') as f:
    androbd = f.read()
src_pat = re.compile(r'^([PBCU][0-9A-F]{4})=(.+?)\s*$', re.M)
androbd_codes = {m.group(1): m.group(2) for m in src_pat.finditer(androbd)}
print(f"AndrOBD: {len(androbd_codes)} codes")

with open(TARGET, 'r', encoding='utf-8') as f:
    fb_src = f.read()
fb_pat = re.compile(r'"([PCBU][0-9A-F]{4})"\s*:\s*"((?:[^"\\]|\\.)*)"')
fb_codes = {m.group(1): m.group(2) for m in fb_pat.finditer(fb_src)}
print(f"FuseOBD currently: {len(fb_codes)} codes")

missing = sorted(set(androbd_codes) - set(fb_codes))
print(f"new codes to add: {len(missing)}")
if not missing:
    raise SystemExit(0)

BS = chr(92)
new_lines = []
for code in missing:
    desc = androbd_codes[code].strip()
    desc_safe = desc.replace(BS, BS+BS).replace('"', BS+'"')
    new_lines.append(f'    "{code}": "{desc_safe}",')

close_re = re.compile(r'^}\s*$', re.M)
matches = list(close_re.finditer(fb_src))
if not matches:
    raise SystemExit("could not find closing brace of dict")
close_pos = matches[0].start()
inject = (
    f'\n    # ── Imported from AndrOBD (fr3ts0n/AndrOBD, GPL-3.0) ──\n'
    f'    # {len(missing)} additional codes from upstream codes.properties.\n'
    f'    # The broadest community-maintained SAE J2012 DTC catalog\n'
    f'    # available. Merged 2026-06-06.\n'
)
new_src = fb_src[:close_pos] + inject + '\n'.join(new_lines) + '\n' + fb_src[close_pos:]
with open(TARGET, 'w', encoding='utf-8') as f:
    f.write(new_src)
print(f"wrote {TARGET}: {len(fb_codes)} -> {len(fb_codes) + len(missing)}")
