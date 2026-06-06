"""One-off script: merge pyobd's pcodes dict into data/dtc_definitions.py.
Run once from D:/APP/FuseOBD. Keeps FuseOBD-specific descriptions for any
DTC where the existing entry already had a richer Ford-flavored note."""
import os
import re

PYOBD = os.environ.get('TEMP', '/tmp') + '/obd2_codes.py'
TARGET = 'data/dtc_definitions.py'

with open(PYOBD, 'r', encoding='utf-8') as f:
    pyobd_src = f.read()
pat_a = r'"([PCBU][0-9A-F]{4})"\s*:\s*"((?:[^"\\]|\\.)*)"'
pyobd_codes = {m.group(1): m.group(2) for m in re.finditer(pat_a, pyobd_src)}
print(f"pyobd: {len(pyobd_codes)} codes")

with open(TARGET, 'r', encoding='utf-8') as f:
    fb_src = f.read()
fb_codes = {m.group(1): m.group(2) for m in re.finditer(pat_a, fb_src)}
print(f"FuseOBD: {len(fb_codes)} codes")

missing = sorted(set(pyobd_codes) - set(fb_codes))
print(f"new codes to add: {len(missing)}")

new_lines = []
for code in missing:
    desc = pyobd_codes[code].encode().decode('unicode_escape')
    BS = chr(92)
    desc_safe = desc.replace(BS, BS+BS).replace('"', BS+'"')
    new_lines.append(f'    "{code}": "{desc_safe}",')

close_re = re.compile(r'^}\s*$', re.M)
matches = list(close_re.finditer(fb_src))
if not matches:
    raise SystemExit("could not find closing brace of dict")
close_pos = matches[0].start()
inject = (
    f'\n    # ── Imported from pyobd (barracuda-fsh/pyobd, GPL-2.0+) ──\n'
    f'    # {len(missing)} additional SAE J2012 generic P-codes; merged\n'
    f'    # 2026-06-06. FuseOBD-specific Ford descriptions for the\n'
    f'    # {len(set(pyobd_codes) & set(fb_codes))} overlapping codes were preserved.\n'
)
new_src = fb_src[:close_pos] + inject + '\n'.join(new_lines) + '\n' + fb_src[close_pos:]
with open(TARGET, 'w', encoding='utf-8') as f:
    f.write(new_src)
print(f"wrote {TARGET}: {len(fb_codes)} -> {len(fb_codes) + len(missing)}")
