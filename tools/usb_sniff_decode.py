#!/usr/bin/env python3
"""Decode a USBPcap capture of FTDI-based OBD-II traffic.

Use this with apps that talk to an OBDLink / generic ELM327 over a USB
serial (FTDI) link: FORScan, ELMConfig, OBD Doctor, ScanXL, etc.
These apps don't use J2534 — they open the COM port directly and send
ELM327 AT commands. USBPcap captures those bytes at the kernel-USB
layer, and this script reassembles them into a request/response
transcript with UDS service / DID / NRC annotations.

This is a passive sniffer — it never touches the adapter or the car.
It only parses an offline .pcapng file you've already captured with
Wireshark.

ONE-TIME SETUP
--------------
1. Install USBPcap   https://desowin.org/usbpcap/
   Free, MIT-licensed, kernel-mode USB filter. One reboot after
   install.
2. Install Wireshark https://www.wireshark.org/ (USBPcap installs an
   interface that Wireshark picks up automatically).

CAPTURING A SESSION
-------------------
1. Plug your OBDLink (or any FTDI-based adapter) into the same USB
   port you'd normally use.
2. Open Wireshark. In the interface list you'll see "USBPcap1",
   "USBPcap2", etc. — one per USB root hub. Start a capture on each
   and watch which one fires when you wiggle the adapter; that's the
   one your device is on. Stop the others.
3. Optional but recommended Wireshark capture filter:
       usb.device_address == N
   where N is the FTDI device's address. Find it by starting the
   capture, unplugging the adapter, plugging it back in, and looking
   at the URB_CONTROL bursts — `device_address` is shown in the
   packet headers.
4. Start the recording, run the target app (FORScan / ELMConfig /
   OBD Doctor) and do whatever you want to capture — read DTCs, scan
   modules, key programming, anything. Then stop the capture.
5. File → Save As → pcapng → e.g. forscan_zephyr_scan.pcapng

DECODING
--------
    python tools/usb_sniff_decode.py forscan_zephyr_scan.pcapng

Optional flags:
    --device N           filter to a specific USB device address
    -o transcript.txt    write to a file instead of stdout

OUTPUT
------
Each line shows: relative timestamp, USB device address, direction,
the literal ASCII the adapter saw/sent, and a UDS / AT annotation
where applicable:

   +0.012  dev09 → ATSP6                            protocol 6 (ISO 15765-4 CAN 11/500)
   +0.067  dev09 ← OK
   +0.069  dev09 → ATSH 7E0                         set header (tx CAN ID): 7E0
   +0.124  dev09 ← OK
   +0.126  dev09 → 22 F1 90                         ReadDataByIdentifier VIN
   +0.290  dev09 ← 62 F1 90 33 4C 4E 48 4D ...      + ReadDataByIdentifier VIN (17B) — "3LNHM26106R..."

A negative response renders as e.g.:
   +0.412  dev09 ← 7F 22 31                         NEGATIVE ReadDataByIdentifier — requestOutOfRange

LIMITATIONS
-----------
- Captures only USB serial transports. If the app uses Bluetooth SPP
  the bytes go through a different stack — capture that with Microsoft
  Message Analyzer or btmon equivalents.
- Multi-chunk bulk URBs from FTDI (rare at AT-command pacing) have
  one 2-byte modem-status header per 64-/512-byte chunk; this script
  strips only the leading pair. If you see garbled hex inside a long
  response, the chunk-splitter would need to know the FTDI bMaxPacket
  size (64 for FS, 512 for HS).
"""
from __future__ import annotations

import argparse
import struct
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterator, Optional


# ── pcapng minimal reader ────────────────────────────────────────────

PCAPNG_SHB = 0x0A0D0D0A   # Section Header Block
PCAPNG_IDB = 0x00000001   # Interface Description Block
PCAPNG_EPB = 0x00000006   # Enhanced Packet Block
LINKTYPE_USBPCAP = 249


@dataclass
class PcapngPacket:
    iface_id: int
    ts_us: int           # microseconds since epoch (assumes default tsresol)
    data: bytes


def read_pcapng(path: str) -> Iterator[tuple[int, PcapngPacket]]:
    """Yield (link_type, packet) for each Enhanced Packet Block in a
    pcapng file. Handles multiple sections with different interface
    sets. Only the EPB block type is yielded; SHB / IDB / options /
    statistics blocks are tracked but not surfaced."""
    link_types: list[int] = []
    with open(path, "rb") as f:
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                return
            block_type, block_len = struct.unpack_from("<II", hdr)
            if block_len < 12 or block_len > 0x40_000_000:
                return  # malformed / corrupt
            body = f.read(block_len - 12)
            trailer = f.read(4)
            if len(trailer) < 4:
                return

            if block_type == PCAPNG_SHB:
                if len(body) < 4:
                    return
                magic = struct.unpack_from("<I", body, 0)[0]
                if magic != 0x1A2B3C4D:
                    raise RuntimeError("pcapng byte order not little-endian "
                                       "(0x%08x); BE/swapped files unsupported"
                                       % magic)
                link_types = []
            elif block_type == PCAPNG_IDB:
                if len(body) < 4:
                    continue
                lt = struct.unpack_from("<H", body, 0)[0]
                link_types.append(lt)
            elif block_type == PCAPNG_EPB:
                if len(body) < 20:
                    continue
                iface_id, ts_hi, ts_lo, cap_len, _orig_len = \
                    struct.unpack_from("<IIIII", body, 0)
                ts = (ts_hi << 32) | ts_lo
                pkt_data = body[20:20 + cap_len]
                lt = link_types[iface_id] if iface_id < len(link_types) else 0
                yield lt, PcapngPacket(iface_id=iface_id, ts_us=ts,
                                       data=pkt_data)


# ── USBPcap pseudo-header ────────────────────────────────────────────

# Per https://desowin.org/usbpcap/captureformat.html, USBPCAP_BUFFER_PACKET_HEADER:
#   USHORT       headerLen;     // 0
#   UINT64       irpId;         // 2
#   USBD_STATUS  status;        // 10
#   USHORT       function;      // 14
#   UCHAR        info;          // 16
#   USHORT       bus;           // 17
#   USHORT       device;        // 19
#   UCHAR        endpoint;      // 21  bit7 = direction (1=IN)
#   UCHAR        transfer;      // 22  0=ISOC 1=INT 2=CTRL 3=BULK
#   UINT32       dataLength;    // 23
# = 27 bytes for BULK; CTRL adds 8 more (setup), ISOC adds more still.

TRANSFER_BULK = 3


@dataclass
class UsbBulkPacket:
    ts_us: int
    device_addr: int
    endpoint: int    # raw byte; bit 7 = direction
    is_in: bool
    data: bytes


def parse_usbpcap(pkt: PcapngPacket) -> Optional[UsbBulkPacket]:
    """Return a UsbBulkPacket if pkt is a USB bulk transfer, else None."""
    if len(pkt.data) < 27:
        return None
    header_len = struct.unpack_from("<H", pkt.data, 0)[0]
    if header_len < 27 or header_len > len(pkt.data):
        return None
    _bus, device = struct.unpack_from("<HH", pkt.data, 17)
    endpoint = pkt.data[21]
    transfer = pkt.data[22]
    if transfer != TRANSFER_BULK:
        return None
    return UsbBulkPacket(
        ts_us=pkt.ts_us,
        device_addr=device,
        endpoint=endpoint,
        is_in=bool(endpoint & 0x80),
        data=pkt.data[header_len:],
    )


# ── FTDI byte stream cleanup ─────────────────────────────────────────

def strip_ftdi_status(data: bytes) -> bytes:
    """Strip FTDI's per-bulk 2-byte modem/line status header from a
    device-to-host packet. Returns the payload bytes only.

    FTDI chips prefix every IN bulk transfer with two status bytes:
      data[0] = modem status (CTS / DSR / RI / DCD)
      data[1] = line status (parity error, framing, overrun, break)
    The actual UART bytes follow. Host-to-device transfers have no
    overhead — those pass through untouched."""
    if len(data) < 2:
        return b""
    return data[2:]


# ── AT command + UDS glossaries ──────────────────────────────────────

AT_GLOSS = {
    "ATZ":   "soft reset",
    "ATD":   "set defaults",
    "ATE0":  "echo off",      "ATE1": "echo on",
    "ATL0":  "linefeed off",  "ATL1": "linefeed on",
    "ATH0":  "headers off",   "ATH1": "headers on",
    "ATS0":  "spaces off",    "ATS1": "spaces on",
    "ATSP0": "protocol auto",
    "ATSP1": "protocol 1 (J1850 PWM)",
    "ATSP2": "protocol 2 (J1850 VPW)",
    "ATSP3": "protocol 3 (ISO 9141-2)",
    "ATSP4": "protocol 4 (ISO 14230-4 5-baud)",
    "ATSP5": "protocol 5 (ISO 14230-4 fast)",
    "ATSP6": "protocol 6 (ISO 15765-4 CAN 11/500)",
    "ATSP7": "protocol 7 (ISO 15765-4 CAN 29/500)",
    "ATSP8": "protocol 8 (ISO 15765-4 CAN 11/250)",
    "ATSP9": "protocol 9 (ISO 15765-4 CAN 29/250)",
    "ATSPA": "protocol A (SAE J1939 CAN)",
    "ATSPB": "protocol B (user defined CAN)",
    "ATSPC": "protocol C (user defined CAN)",
    "ATI":   "identify (firmware)",
    "ATAT0": "adaptive timing off",
    "ATAT1": "adaptive timing 1",
    "ATAT2": "adaptive timing 2",
    "ATAR":  "auto receive on",
    "ATAL":  "allow long messages",
    "ATMA":  "monitor all CAN (passive sniff)",
    "ATMR":  "monitor receiver",
    "ATMT":  "monitor transmitter",
    "ATRV":  "read battery voltage",
    "ATCAF0": "CAN auto-format off",
    "ATCAF1": "CAN auto-format on",
    "ATCFC0": "CAN flow control off",
    "ATCFC1": "CAN flow control on",
    "ATPC":   "protocol close",
    "ATWS":   "warm start",
    "ATDP":   "describe protocol",
    "ATDPN":  "describe protocol number",
    "ATLP":   "low power mode",
    "ATBI":   "bypass init sequence",
    "STI":   "STN identity",
    "STVR":  "STN voltage read",
    "STDI":  "STN device info",
    "STSN":  "STN serial number",
    "STBRR": "STN baud rate request",
    "STM":   "STN monitor",
    "STPO":  "STN protocol open",
    "STPC":  "STN protocol close",
}

AT_PREFIX_GLOSS = [
    ("ATSH",   "set tx header (CAN ID)"),
    ("ATCRA",  "set rx address filter"),
    ("ATCF",   "set CAN filter base"),
    ("ATCM",   "set CAN mask"),
    ("ATST",   "set response timeout"),
    ("ATTA",   "set tester address"),
    ("ATBRD",  "set baud divisor"),
    ("ATPP",   "set programmable parameter"),
    ("ATIIA",  "set ISO init address"),
    ("ATFI",   "fast init"),
    ("ATSI",   "slow init"),
    ("STPRS",  "STN protocol set"),
    ("STCFCPA","STN flow-control pair add"),
    ("STCSWM", "STN switch CAN mode"),
    ("STBR",   "STN baud rate"),
    ("STFPGA", "STN filter pass-add"),
    ("STFAP",  "STN filter add-pass"),
    ("STFAB",  "STN filter add-block"),
    ("STFAC",  "STN filter clear"),
]

UDS_SERVICES = {
    0x10: "DiagnosticSessionControl",
    0x11: "ECUReset",
    0x14: "ClearDiagnosticInformation",
    0x19: "ReadDTCInformation",
    0x22: "ReadDataByIdentifier",
    0x23: "ReadMemoryByAddress",
    0x24: "ReadScalingDataByIdentifier",
    0x27: "SecurityAccess",
    0x28: "CommunicationControl",
    0x29: "Authentication",
    0x2A: "ReadDataByPeriodicIdentifier",
    0x2C: "DynamicallyDefineDataIdentifier",
    0x2E: "WriteDataByIdentifier",
    0x2F: "InputOutputControlByIdentifier",
    0x31: "RoutineControl",
    0x34: "RequestDownload",
    0x35: "RequestUpload",
    0x36: "TransferData",
    0x37: "RequestTransferExit",
    0x38: "RequestFileTransfer",
    0x3D: "WriteMemoryByAddress",
    0x3E: "TesterPresent",
    0x83: "AccessTimingParameter",
    0x84: "SecuredDataTransmission",
    0x85: "ControlDTCSetting",
    0x86: "ResponseOnEvent",
    0x87: "LinkControl",
}

UDS_DSC_SUBFUNC = {
    0x01: "default",
    0x02: "programming",
    0x03: "extended",
    0x04: "safety",
    0x81: "Ford default-extended (KWP)",
    0x85: "Ford diag",
    0x87: "programming extended",
    0xC0: "Ford legacy startDiag (KWP)",
}

UDS_NRC = {
    0x10: "generalReject",
    0x11: "serviceNotSupported",
    0x12: "subFunctionNotSupported",
    0x13: "incorrectMessageLengthOrInvalidFormat",
    0x14: "responseTooLong",
    0x21: "busyRepeatRequest",
    0x22: "conditionsNotCorrect",
    0x24: "requestSequenceError",
    0x25: "noResponseFromSubnetComponent",
    0x26: "failurePreventsExecution",
    0x31: "requestOutOfRange",
    0x33: "securityAccessDenied",
    0x35: "invalidKey",
    0x36: "exceedNumberOfAttempts",
    0x37: "requiredTimeDelayNotExpired",
    0x70: "uploadDownloadNotAccepted",
    0x71: "transferDataSuspended",
    0x72: "generalProgrammingFailure",
    0x73: "wrongBlockSequenceCounter",
    0x78: "responsePending",
    0x7E: "subFunctionNotSupportedInActiveSession",
    0x7F: "serviceNotSupportedInActiveSession",
}

KNOWN_DIDS = {
    0xF110: "VIN (alt)",
    0xF18C: "ECU serial / VIN (Ford alt)",
    0xF187: "vehicle manufacturer spare part number",
    0xF188: "vehicle manufacturer ECU software number",
    0xF189: "vehicle manufacturer ECU software version",
    0xF18A: "system supplier identifier",
    0xF18B: "ECU manufacturing date",
    0xF18E: "repair shop code / programming date",
    0xF190: "VIN",
    0xF191: "vehicle manufacturer ECU hardware number",
    0xF192: "system supplier ECU hardware number",
    0xF193: "system supplier ECU hardware version",
    0xF194: "system supplier ECU software number",
    0xF195: "system supplier ECU software version",
    0xF197: "system name / engine type",
    0xF198: "repair shop code",
    0xF199: "programming date",
    0xF19D: "ECU installation date",
    0xF19E: "ODX file",
    # Ford-specific (Ghidra-recovered, see core/ford_dids.py)
    0xD100: "PCM serial number (Ford)",
    0xD102: "Vehicle Mark 1",
    0xD103: "Vehicle Mark 2",
    0xD107: "Vehicle Mark 3",
    0xD109: "Vehicle Mark 4",
    0xD128: "Vehicle Configuration",
    0xE201: "Strategy part number (Ford)",
    0xE219: "Calibration ID (Ford)",
    0xE21A: "Assembly part number (Ford)",
}


def annotate_at(line: str) -> str:
    """Return a comment suffix for an AT/ST command, or '' if unknown."""
    up = line.upper().strip().replace(" ", "")
    if up in AT_GLOSS:
        return AT_GLOSS[up]
    # Try prefix matches longest-first to avoid ATSH being misread as ATS
    for prefix, gloss in sorted(AT_PREFIX_GLOSS, key=lambda x: -len(x[0])):
        if up.startswith(prefix):
            arg = up[len(prefix):]
            return f"{gloss}: {arg}" if arg else gloss
    return ""


def annotate_uds(hex_line: str) -> str:
    """Annotate a hex-only line if it looks like a UDS request or
    response. Returns '' if it isn't recognizable as UDS."""
    h = hex_line.strip().replace(" ", "")
    if not h or len(h) % 2 or len(h) < 2:
        return ""
    # An all-ASCII line that happens to be even-length and hex-decodable
    # would be misclassified. Require that every char is hex.
    if any(c not in "0123456789ABCDEFabcdef" for c in h):
        return ""
    try:
        b = bytes.fromhex(h)
    except ValueError:
        return ""
    first = b[0]

    # Negative response: 7F <service> <NRC>
    if first == 0x7F and len(b) >= 3:
        svc = UDS_SERVICES.get(b[1], f"service 0x{b[1]:02X}")
        nrc = UDS_NRC.get(b[2], f"NRC 0x{b[2]:02X}")
        return f"NEGATIVE {svc} — {nrc}"

    # Positive response = request SID + 0x40
    if first >= 0x40 and (first - 0x40) in UDS_SERVICES:
        svc_id = first - 0x40
        svc = UDS_SERVICES[svc_id]
        if svc_id == 0x22 and len(b) >= 3:
            did = (b[1] << 8) | b[2]
            name = KNOWN_DIDS.get(did, f"DID 0x{did:04X}")
            payload = b[3:]
            ascii_tail = ""
            if payload and all(32 <= c < 127 for c in payload[:17]):
                try:
                    ascii_tail = " — \"" + payload[:17].decode("ascii") + "\""
                except Exception:
                    pass
            return f"+ {svc} {name} ({len(payload)}B){ascii_tail}"
        if svc_id == 0x10 and len(b) >= 2:
            sub = UDS_DSC_SUBFUNC.get(b[1], f"0x{b[1]:02X}")
            return f"+ {svc} → {sub}"
        if svc_id == 0x27 and len(b) >= 2:
            return f"+ {svc} subfunc 0x{b[1]:02X} ({len(b)-2}B)"
        if svc_id == 0x31 and len(b) >= 4:
            rid = (b[2] << 8) | b[3]
            return f"+ {svc} subfunc 0x{b[1]:02X} RID 0x{rid:04X}"
        if svc_id == 0x19 and len(b) >= 2:
            return f"+ {svc} subfunc 0x{b[1]:02X}"
        return f"+ {svc} ({len(b)-1}B)"

    # Request
    if first in UDS_SERVICES:
        svc = UDS_SERVICES[first]
        if first == 0x22 and len(b) >= 3:
            did = (b[1] << 8) | b[2]
            name = KNOWN_DIDS.get(did, f"DID 0x{did:04X}")
            return f"{svc} {name}"
        if first == 0x10 and len(b) >= 2:
            sub = UDS_DSC_SUBFUNC.get(b[1], f"0x{b[1]:02X}")
            return f"{svc} → {sub}"
        if first == 0x27 and len(b) >= 2:
            return f"{svc} subfunc 0x{b[1]:02X} ({len(b)-2}B)"
        if first == 0x31 and len(b) >= 4:
            rid = (b[2] << 8) | b[3]
            return f"{svc} subfunc 0x{b[1]:02X} RID 0x{rid:04X}"
        if first == 0x19 and len(b) >= 2:
            return f"{svc} subfunc 0x{b[1]:02X}"
        if first == 0x3E and len(b) >= 2:
            return f"{svc} subfunc 0x{b[1]:02X}"
        return f"{svc} ({len(b)-1}B)"

    return ""


def annotate(line: str) -> str:
    """Pick AT annotation first, fall back to UDS hex annotation."""
    return annotate_at(line) or annotate_uds(line)


# ── Main pipeline ────────────────────────────────────────────────────

def decode(path: str, *, device_addr: Optional[int] = None,
           out=sys.stdout) -> None:
    streams: dict[tuple[int, str], bytearray] = defaultdict(bytearray)
    first_ts: Optional[int] = None
    seen = set()

    def emit(ts_us: int, addr: int, direction: str, text: str):
        nonlocal first_ts
        text = text.replace(">", "").strip()
        if not text:
            return
        arrow = "→" if direction == "out" else "←"
        rel = (ts_us - first_ts) / 1_000_000.0
        ann = annotate(text)
        prefix = f"+{rel:8.3f}  dev{addr:02d} {arrow}"
        if ann:
            print(f"{prefix} {text:<36}    {ann}", file=out)
        else:
            print(f"{prefix} {text}", file=out)

    for link, pkt in read_pcapng(path):
        if link != LINKTYPE_USBPCAP:
            continue
        usb = parse_usbpcap(pkt)
        if usb is None:
            continue
        if device_addr is not None and usb.device_addr != device_addr:
            continue
        seen.add(usb.device_addr)
        if first_ts is None:
            first_ts = usb.ts_us

        body = strip_ftdi_status(usb.data) if usb.is_in else usb.data
        if not body:
            continue

        direction = "in" if usb.is_in else "out"
        key = (usb.device_addr, direction)
        buf = streams[key]
        buf.extend(body)

        # ELM terminates every line with CR. Split on CR; anything past
        # the last CR stays buffered for the next URB.
        while b"\r" in buf:
            line, _, rest = bytes(buf).partition(b"\r")
            buf.clear()
            buf.extend(rest)
            try:
                text = line.decode("ascii")
            except UnicodeDecodeError:
                text = line.decode("ascii", errors="replace")
            emit(usb.ts_us, usb.device_addr, direction, text)

    if first_ts is None:
        print("No USBPcap packets found. Was this captured with the "
              "USBPcap interface in Wireshark?", file=sys.stderr)
        return
    if device_addr is None and len(seen) > 1:
        print(f"\n(saw {len(seen)} USB devices: addresses "
              f"{sorted(seen)}. Pass --device N to filter to one.)",
              file=sys.stderr)


def main():
    p = argparse.ArgumentParser(
        description="Decode a USBPcap capture of FTDI / ELM327 OBD-II "
                    "traffic into an annotated transcript.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("capture", help="Path to a .pcapng file from "
                                   "Wireshark + USBPcap")
    p.add_argument("--device", type=int, default=None,
                   help="Filter to a single USB device address "
                        "(decimal). Use if multiple devices are in the "
                        "capture; the script lists what it saw if you "
                        "don't filter.")
    p.add_argument("-o", "--output", default=None,
                   help="Write transcript to FILE instead of stdout.")
    args = p.parse_args()
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            decode(args.capture, device_addr=args.device, out=f)
        print(f"wrote transcript to {args.output}", file=sys.stderr)
    else:
        decode(args.capture, device_addr=args.device)


if __name__ == "__main__":
    main()
