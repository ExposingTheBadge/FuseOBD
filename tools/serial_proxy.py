#!/usr/bin/env python3
"""
ELM327 Serial Proxy — intercepts FORScan ↔ ELM327 communication

Connects to the REAL ELM327 on one COM port, creates a relay through a
virtual COM port pair (com0com), and logs every byte FORScan sends/receives.

SETUP (do once):
  1. Download & install com0com from: https://sourceforge.net/projects/com0com/
  2. Run "Setup Command Prompt" from com0com start menu (as Administrator)
  3. Create a virtual pair:  install PortName=COM10 PortName=COM11
  4. Enable Ports class:      change CNCA0 PortName=COM10 EmuBR=yes AddRT=yes
                              change CNCB0 PortName=COM11 EmuBR=yes AddRT=yes
  5. FORScan connects to COM11, this script connects to COM10 + real ELM327

USAGE:
  python serial_proxy.py <REAL_ELM_PORT> <VIRTUAL_PORT> [baud]

  python serial_proxy.py COM5 COM10 500000
"""

import serial
import threading
import time
import sys
import os
from datetime import datetime

# ── Configuration ────────────────────────────────────────────────────
REAL_PORT = sys.argv[1] if len(sys.argv) > 1 else "COM5"
VIRTUAL_PORT = sys.argv[2] if len(sys.argv) > 2 else "COM10"
BAUD = int(sys.argv[3]) if len(sys.argv) > 3 else 500000
LOG_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Logging ──────────────────────────────────────────────────────────
logfile = os.path.join(LOG_DIR, f"forscan_proxy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

def log(direction: str, raw: bytes):
    """Log raw bytes with direction, timestamp, hex, and ASCII."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    hex_str = raw.hex(" ").upper()
    ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in raw)
    line = f"[{ts}] {direction} | {hex_str}"
    if len(raw) < 128:
        line += f"  |  {ascii_str}"

    # Parse ELM327 frames for readability
    text = raw.decode("ascii", errors="replace").strip()
    if text:
        if text.startswith("AT"):
            line += f"  |  ELM: {text}"
        elif any(c in text for c in "0123456789ABCDEF") and len(text) >= 3:
            # Try to identify CAN frames, responses, etc.
            if ">" in line or text.startswith("7F"):
                line += f"  |  UDS: {text}"
            elif len(text) <= 8:
                line += f"  |  CAN: {text}"
            else:
                line += f"  |  DATA: {text}"

    print(line)
    with open(logfile, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def log_info(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] INFO  | {msg}"
    print(line)
    with open(logfile, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ── Relay Threads ────────────────────────────────────────────────────
def relay(src: serial.Serial, dst: serial.Serial, label: str):
    """Forward all data from src to dst, logging each chunk."""
    buffer = b""
    while True:
        try:
            chunk = src.read(src.in_waiting or 1)
            if chunk:
                buffer += chunk
                dst.write(chunk)
                dst.flush()
                # Log when we see a complete line (ELM327 uses \r as terminator)
                while b"\r" in buffer or b">" in buffer:
                    for delim in [b"\r", b">"]:
                        if delim in buffer:
                            idx = buffer.index(delim) + len(delim)
                            frame = buffer[:idx]
                            buffer = buffer[idx:]
                            if frame.strip():
                                log(label, frame)
                            break
                    # Safety: if no delimiters found, break loop
                    if b"\r" not in buffer and b">" not in buffer:
                        break
                # Also flush buffer if it's been sitting (partial line)
                if len(buffer) > 256:
                    log(label, buffer)
                    buffer = b""
        except (serial.SerialException, OSError) as e:
            log_info(f"{label} relay error: {e}")
            break

# ── Main ─────────────────────────────────────────────────────────────
def main():
    log_info(f"ELM327 Serial Proxy starting...")
    log_info(f"  Real ELM327: {REAL_PORT}")
    log_info(f"  Virtual port: {VIRTUAL_PORT}  →  FORScan connects to paired port")
    log_info(f"  Baud: {BAUD}")
    log_info(f"  Log: {logfile}")

    # Open real ELM327
    log_info(f"Opening {REAL_PORT}...")
    try:
        elm = serial.Serial(REAL_PORT, BAUD, timeout=0.1)
        log_info(f"  {REAL_PORT} opened OK")
    except serial.SerialException as e:
        log_info(f"  ERROR opening {REAL_PORT}: {e}")
        log_info("  Is the ELM327 plugged in? Is another program using it?")
        sys.exit(1)

    # Open virtual port (connected to FORScan via com0com pair)
    log_info(f"Opening {VIRTUAL_PORT}...")
    try:
        fwd = serial.Serial(VIRTUAL_PORT, BAUD, timeout=0.1)
        log_info(f"  {VIRTUAL_PORT} opened OK")
    except serial.SerialException as e:
        log_info(f"  ERROR opening {VIRTUAL_PORT}: {e}")
        log_info("  Did you create the com0com pair?")
        log_info("  Run as admin: install PortName=COM10 PortName=COM11")
        elm.close()
        sys.exit(1)

    log_info("Relay active — waiting for FORScan traffic...")
    log_info("(Press Ctrl+C to stop)")

    # Start relay threads
    t1 = threading.Thread(target=relay, args=(elm, fwd, "FORScan  → ELM"), daemon=True)
    t2 = threading.Thread(target=relay, args=(fwd, elm, "ELM     → FORScan"), daemon=True)
    t1.start()
    t2.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log_info("Shutting down...")
    finally:
        elm.close()
        fwd.close()
        log_info("Done. Log saved to: " + logfile)

if __name__ == "__main__":
    main()
