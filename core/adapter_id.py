"""Adapter identification — turn the raw ATI/STI/@1 response string
into a recognized adapter name + capability hint.

Almost every ELM327-clone reports a different identifier:

  "ELM327 v1.5"            → generic clone (often lying about version)
  "ELM327 v2.2"            → genuine ELM327 (rare) OR clone that lies
  "OBDLink MX+ r5.4.2"     → ScanTool OBDLink MX+ (STN2255-based)
  "OBDLink LX r5.x.x"      → ScanTool OBDLink LX (STN1130)
  "OBDLink SX r4.x.x"      → ScanTool OBDLink SX (STN1110)
  "STN1170 v4.x.x"         → STN1170 chip (vLinker FS, vLinker MC+, etc)
  "STN1110 v3.x.x"         → STN1110 chip (older clones)
  "vLinker FS"             → vLinker FS USB (vendor sometimes ships their
                              own ATI string instead of the underlying STN)
  "Kiwi 3"                 → PLX Devices Kiwi 3 (ELM327 v2.2 firmware)
  "OBDII Bluetooth ..."   → cheap Chinese clone

This module returns:
  AdapterIdentity(
      raw="…",
      kind="elm327|stn1110|stn1170|stn2255|obdlink_mxp|obdlink_lx|obdlink_sx|vlinker_fs|vlinker_mcp|kiwi3|clone|unknown",
      vendor="…",
      model="…",       # human-readable, e.g. "OBDLink MX+"
      firmware="…",    # version string, when present
      chipset="…",     # ELM327 / STN1110 / STN1170 / STN2255 / …
      trust="genuine|likely|clone|unknown",
  )
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class AdapterIdentity:
    raw: str
    kind: str = "unknown"
    vendor: str = ""
    model: str = ""
    firmware: str = ""
    chipset: str = ""
    trust: str = "unknown"

    def label(self) -> str:
        """Human-readable label for the dropdown / status bar."""
        parts = []
        if self.model:
            parts.append(self.model)
        elif self.kind != "unknown":
            parts.append(self.kind)
        if self.firmware:
            parts.append(self.firmware)
        return " ".join(parts).strip() or (self.raw or "Unknown adapter")


# Ordered: more-specific patterns first.
_PATTERNS: list[tuple[re.Pattern, dict]] = [
    # OBDLink family — most distinctive
    (re.compile(r"OBDLink\s+MX\+?\s*(?:r?\s*([\d.]+))?", re.I),
     {"kind": "obdlink_mxp", "vendor": "ScanTool", "model": "OBDLink MX+",
      "chipset": "STN2255", "trust": "genuine"}),
    (re.compile(r"OBDLink\s+EX\s*(?:r?\s*([\d.]+))?", re.I),
     {"kind": "obdlink_ex", "vendor": "ScanTool", "model": "OBDLink EX",
      "chipset": "STN2120", "trust": "genuine"}),
    (re.compile(r"OBDLink\s+CX\s*(?:r?\s*([\d.]+))?", re.I),
     {"kind": "obdlink_cx", "vendor": "ScanTool", "model": "OBDLink CX",
      "chipset": "STN2120", "trust": "genuine"}),
    (re.compile(r"OBDLink\s+LX\s*(?:r?\s*([\d.]+))?", re.I),
     {"kind": "obdlink_lx", "vendor": "ScanTool", "model": "OBDLink LX",
      "chipset": "STN1130", "trust": "genuine"}),
    (re.compile(r"OBDLink\s+SX\s*(?:r?\s*([\d.]+))?", re.I),
     {"kind": "obdlink_sx", "vendor": "ScanTool", "model": "OBDLink SX",
      "chipset": "STN1110", "trust": "genuine"}),
    # vLinker family (Vgate)
    (re.compile(r"vLinker\s+FS\b", re.I),
     {"kind": "vlinker_fs", "vendor": "Vgate", "model": "vLinker FS",
      "chipset": "STN1170", "trust": "genuine"}),
    (re.compile(r"vLinker\s+FD\b", re.I),
     {"kind": "vlinker_fd", "vendor": "Vgate", "model": "vLinker FD",
      "chipset": "STN1170", "trust": "genuine"}),
    (re.compile(r"vLinker\s+MC\+?", re.I),
     {"kind": "vlinker_mcp", "vendor": "Vgate", "model": "vLinker MC+",
      "chipset": "STN1170", "trust": "genuine"}),
    (re.compile(r"vLinker\s+BM\+?", re.I),
     {"kind": "vlinker_bmp", "vendor": "Vgate", "model": "vLinker BM+",
      "chipset": "STN1170", "trust": "genuine"}),
    (re.compile(r"vLinker\b", re.I),
     {"kind": "vlinker_generic", "vendor": "Vgate", "model": "vLinker",
      "chipset": "STN1170", "trust": "likely"}),
    # PLX Kiwi
    (re.compile(r"Kiwi\s*3?", re.I),
     {"kind": "kiwi3", "vendor": "PLX Devices", "model": "Kiwi 3",
      "chipset": "ELM327", "trust": "genuine"}),
    # Bare STN chipset reports — likely a vendor that didn't override
    (re.compile(r"STN2255\s*v?\s*([\d.]+)?", re.I),
     {"kind": "stn2255", "vendor": "ScanTool/clone", "model": "STN2255",
      "chipset": "STN2255", "trust": "likely"}),
    (re.compile(r"STN1170\s*v?\s*([\d.]+)?", re.I),
     {"kind": "stn1170", "vendor": "ScanTool/clone", "model": "STN1170",
      "chipset": "STN1170", "trust": "likely"}),
    (re.compile(r"STN1130\s*v?\s*([\d.]+)?", re.I),
     {"kind": "stn1130", "vendor": "ScanTool/clone", "model": "STN1130",
      "chipset": "STN1130", "trust": "likely"}),
    (re.compile(r"STN1110\s*v?\s*([\d.]+)?", re.I),
     {"kind": "stn1110", "vendor": "ScanTool/clone", "model": "STN1110",
      "chipset": "STN1110", "trust": "likely"}),
    # Generic ELM — clone-or-genuine ambiguous. Trust hint based on
    # the version string: real ELM327 production stopped at v2.3; any
    # clone reporting v2.1+ is suspect but usable.
    (re.compile(r"ELM327\s*v?\s*([\d.]+)?", re.I),
     {"kind": "elm327", "vendor": "Elm Electronics / clone", "model": "ELM327",
      "chipset": "ELM327", "trust": "clone"}),
    # Cheap unbranded
    (re.compile(r"OBDII?\s+Bluetooth", re.I),
     {"kind": "clone", "vendor": "Unbranded", "model": "OBD-II Bluetooth clone",
      "chipset": "ELM327", "trust": "clone"}),
]


def identify(raw: str) -> AdapterIdentity:
    """Best-effort classification. Always returns an AdapterIdentity;
    falls through to kind='unknown' when nothing matches so callers
    can still surface SOMETHING in the UI."""
    if not raw:
        return AdapterIdentity(raw="")
    text = raw.strip()
    for pat, info in _PATTERNS:
        m = pat.search(text)
        if m:
            fw = ""
            if m.groups():
                fw = (m.group(1) or "").strip()
            return AdapterIdentity(raw=text, firmware=fw, **info)
    return AdapterIdentity(raw=text)


# Bauds known to be used by various adapters. The serial baud-scan loop
# tries these in priority order; the index of the previously-successful
# baud is remembered so the second connect is instant.
COMMON_BAUDS = (
    115200,    # ELM327 / OBDLink SX / STN-family factory default
               # over USB (FTDI). Tried first because: (a) the FTDI
               # driver comes up at 115200 by default, (b) FORScan /
               # OBD Auto Doctor / ELMConfig all open at 115200,
               # (c) starting at 500K when the link is actually
               # 115200 burns ~3 seconds on every connect before
               # falling back.
    500000,    # Some Ford-CAN adapters and J2534 PassThru DLLs
               # negotiate 500K on USB; STN-family adapters can also
               # be switched here via ATBRD post-connect for faster
               # bulk reads.
    921600,    # vLinker FS USB / STN1170 high-speed (post-ATBRD)
    1228800,   # newer STN1170 highest speed
    460800,    # OBDLink MX+ / STN2255 fast mode
    230400,    # midrange clones
    38400,     # legacy ELM327 factory default (pre-FTDI clones)
    9600,      # very old / Bluetooth SPP slow mode
)
