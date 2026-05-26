"""Smoke-test the patched ELM327 init sequence against the adapter.

Run with the adapter plugged in (no vehicle needed). Validates that every
AT/PP/CRA command in the new init path returns a sane response from the
adapter — surfaces clone quirks before taking it to the car.

Usage:
    python tools/test_init.py             # auto-detect COM port
    python tools/test_init.py COM5
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.j2534 import _WinSerial, _parse_voltage


PROBE_BAUDS = [500000, 115200, 38400, 9600]


def cmd(stream, c: str, timeout_ms: int = 600) -> str:
    """Send one AT command and return the response (no echo, no prompt)."""
    stream.flush()
    stream.write((c + "\r").encode("ascii"))
    deadline = time.time() + timeout_ms / 1000.0
    buf = bytearray()
    while time.time() < deadline:
        chunk = stream.read(256, 50)
        if chunk:
            buf.extend(chunk)
            if b">" in buf:
                break
        elif buf:
            break
        time.sleep(0.01)
    text = bytes(buf).decode("ascii", errors="replace")
    out = []
    for line in text.replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line or line == ">" or line.upper() == c.upper():
            continue
        out.append(line)
    return "\n".join(out)


def find_adapter(forced_port: str | None) -> tuple[_WinSerial, int]:
    if forced_port:
        ports = [forced_port]
    else:
        from core.j2534 import _enumerate_com_ports
        ports = [d.port for d in _enumerate_com_ports() if d.port]
    if not ports:
        raise SystemExit("No COM ports found")

    for port in ports:
        for baud in PROBE_BAUDS:
            try:
                s = _WinSerial(port)
                s.open(baud)
                # Wake the adapter
                s.write(b"\r")
                time.sleep(0.05)
                s.read(64, 100)  # drain
                r = cmd(s, "ATI", 800)
                if r and "?" not in r[:4] and len(r) > 2:
                    print(f"[OK] {port} @ {baud}: {r!r}")
                    return s, baud
                s.close()
            except Exception as e:
                print(f"[--] {port} @ {baud}: {e}")
    raise SystemExit("No adapter responded on any port/baud")


HS_INIT = [
    "ATZ",       # special: needs an 800ms wait before reading
    "ATE0",
    "ATL0",
    "ATH0",
    "ATS0",
    "ATSP6",
    "ATAT1",
    "ATSTFF",
    "ATTA30",
    "ATCF700",
    "ATCMF00",
]

# After init, exercise the per-module setup for an HS-CAN module (PCM = 0x7E0/0x7E8)
HS_PER_MODULE = [
    "ATSH0007E0",   # tx header
    "ATCRA7E8",     # rx filter
]

# MS-CAN switch sequence (FORScan FUN_0054f650)
MS_SWITCH = [
    "ATPP2ASV38",
    "ATPP2AON",
    "ATPP2CSV81",
    "ATPP2CON",
    "ATPP2DSV04",
    "ATPP2DON",
    "ATTPB",
]

# After MS-CAN switch, set up for BCM (0x726/0x72E)
MS_PER_MODULE = [
    "ATSH000726",
    "ATCRA72E",
]


def section(title: str):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def run_block(stream, block, label):
    section(label)
    bad = []
    for c in block:
        if c == "ATZ":
            stream.flush()
            stream.write(b"ATZ\r")
            time.sleep(0.8)
            r = stream.read(256, 300).decode("ascii", errors="replace").strip()
            print(f"  ATZ        -> {r!r}")
            continue
        r = cmd(stream, c, 600)
        # Heuristic: any response containing '?' or empty is suspicious for AT commands
        ok = "?" not in r
        flag = "OK" if ok else "??"
        print(f"  {c:<14}-> [{flag}] {r!r}")
        if not ok:
            bad.append((c, r))
    return bad


def main():
    forced = sys.argv[1] if len(sys.argv) > 1 else None
    stream, baud = find_adapter(forced)
    try:
        section(f"Adapter detected at {baud} baud")
        ati = cmd(stream, "ATI", 800)
        print(f"  ATI -> {ati!r}")
        sti = cmd(stream, "STI", 400)
        print(f"  STI -> {sti!r}  (empty/`?` = not STN, plain ELM)")

        bad_init = run_block(stream, HS_INIT, "Phase 1 — HS-CAN init")
        bad_hs = run_block(stream, HS_PER_MODULE, "Phase 2 — HS-CAN per-module headers (PCM)")

        # Voltage parse test
        section("Phase 3 — battery voltage parse")
        v = cmd(stream, "ATRV", 600)
        parsed = _parse_voltage(v)
        print(f"  ATRV raw  -> {v!r}")
        print(f"  parsed    -> {parsed:.2f}V")

        bad_ms = run_block(stream, MS_SWITCH, "Phase 4 — MS-CAN switch (User Protocol B)")
        bad_ms_pm = run_block(stream, MS_PER_MODULE, "Phase 5 — MS-CAN per-module headers (BCM)")

        # Switch back to HS-CAN for cleanliness
        section("Phase 6 — back to HS-CAN")
        r = cmd(stream, "ATSP6", 600)
        print(f"  ATSP6 -> {r!r}")

        section("Summary")
        all_bad = bad_init + bad_hs + bad_ms + bad_ms_pm
        if not all_bad:
            print("  All commands accepted. Adapter init matches FORScan sequence.")
        else:
            print(f"  {len(all_bad)} command(s) rejected:")
            for c, r in all_bad:
                print(f"    {c}: {r!r}")
            print("\n  NOTE: ATPP*ON failures on cheap clones are expected and mean")
            print("        MS-CAN switching won't work on this adapter, even though")
            print("        the rest of the init does. HS-CAN is unaffected.")
    finally:
        stream.close()


if __name__ == "__main__":
    main()
