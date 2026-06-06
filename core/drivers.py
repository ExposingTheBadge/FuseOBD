"""Driver detection + install guidance.

Detects whether a connected USB OBD adapter has the correct Windows
USB-to-serial driver bound. When it doesn't, surfaces the right
download link + install hint so the user isn't left guessing why a
plugged-in adapter doesn't show up as a COM port.

This module DOES NOT silently install drivers. Two reasons:

  1. Windows requires admin elevation + a signed .INF for driver
     install. Most adapter vendors don't ship installers we could
     legally redistribute inside FuseOBD.
  2. Auto-installing third-party drivers without an explicit user
     click is exactly the behaviour that makes "OBD scanner apps"
     get flagged by antivirus and SmartScreen. We're not doing it.

What it DOES do:
  - Detect every USB device matching one of the AdapterSpec VID/PIDs
    in data/adapters_db.py, whether or not it currently has a COM
    port bound.
  - Report which adapters are "ready" (have a working COM port) vs
    "needs driver" (USB device present, no COM port → driver missing
    or the wrong one was installed).
  - For each needs-driver entry, surface the vendor's official driver
    download URL.
  - Offer a single click to launch that URL in the user's default
    browser (the connection panel calls open_driver_url() when the
    user clicks Fix).
"""
from __future__ import annotations

import sys
import webbrowser
from dataclasses import dataclass
from typing import Optional

try:
    from data.adapters_db import (
        AdapterSpec, DriverFamily, ADAPTERS, by_vid_pid_str,
    )
except Exception:  # pragma: no cover
    AdapterSpec = object  # type: ignore[assignment]
    DriverFamily = None   # type: ignore[assignment]
    ADAPTERS = ()
    def by_vid_pid_str(_s): return None


@dataclass
class DriverStatus:
    """Outcome of a driver health check for one detected USB device."""
    vid_pid: str                  # registry-style 'VID_0403&PID_6001'
    instance_id: str              # specific device instance
    friendly_name: str            # Windows FriendlyName
    com_port: Optional[str]       # COM3 etc, or None if no port bound
    adapter: Optional[AdapterSpec]  # matched adapter spec, if any
    needs_driver: bool            # True when USB device is present but no COM port

    @property
    def driver_family(self) -> Optional[str]:
        return self.adapter.driver if self.adapter else None

    @property
    def driver_url(self) -> Optional[str]:
        return self.adapter.driver_url if self.adapter else None

    @property
    def status_label(self) -> str:
        if self.com_port and self.adapter:
            return f"{self.adapter.name} ready on {self.com_port}"
        if self.com_port:
            return f"USB serial on {self.com_port} (unknown adapter)"
        if self.adapter:
            return f"{self.adapter.name} present — DRIVER MISSING"
        return f"unrecognized USB device ({self.friendly_name})"


# ── Driver family → human-readable description + downloads ───────────

DRIVER_DESCRIPTIONS = {
    DriverFamily.FTDI_VCP: (
        "FTDI USB-Serial (VCP) driver",
        "Windows 10/11 normally installs this via Windows Update within "
        "30 seconds of plug-in. If your COM port never appears: download "
        "the manual installer from ftdichip.com.",
    ),
    DriverFamily.CH340: (
        "WCH CH340/CH341 USB-Serial driver",
        "Windows 10 1709+ ships this driver. Older Windows or fresh "
        "installs: grab CH341SER from wch-ic.com.",
    ),
    DriverFamily.CP210X: (
        "Silicon Labs CP210x USB-Serial driver",
        "Windows 10 1903+ ships this driver. If missing: get the "
        "Universal Windows Driver from silabs.com.",
    ),
    DriverFamily.PL2303: (
        "Prolific PL2303 USB-Serial driver",
        "Many cheap PL2303 clones use counterfeit chips that the official "
        "Prolific driver REFUSES. Use Prolific driver v3.3.x for clones; "
        "v4.x only works with genuine chips.",
    ),
    DriverFamily.CDC_ACM: (
        "Native USB CDC (no driver install needed)",
        "Windows uses the built-in usbser.sys — no separate driver "
        "needed. If your COM port never appears, check Device Manager "
        "for a yellow-bang on the device.",
    ),
    DriverFamily.VENDOR_J2534: (
        "Vendor-supplied J2534 driver",
        "Pro adapters ship their own .DLL + PassThru registry entries. "
        "Install the vendor's setup package from their website.",
    ),
    DriverFamily.BT_CLASSIC: (
        "Bluetooth Classic SPP",
        "Pair the adapter in Windows Settings → Bluetooth. A virtual "
        "COM port appears automatically once pairing succeeds.",
    ),
    DriverFamily.BT_LE: (
        "Bluetooth Low Energy",
        "BLE adapters generally don't expose a COM port on Windows. "
        "Limited support — try iOS / Android instead.",
    ),
    DriverFamily.WIFI: (
        "WiFi (TCP socket)",
        "No driver needed. Connect your computer to the adapter's "
        "WiFi network and add it as a WiFi adapter in FuseOBD.",
    ),
} if DriverFamily else {}


def describe_driver(family: str) -> tuple[str, str]:
    return DRIVER_DESCRIPTIONS.get(family, (family or "unknown", ""))


def open_driver_url(url: str) -> bool:
    """Open the vendor's driver download page in the user's default
    browser. Returns True on success."""
    if not url: return False
    try:
        return webbrowser.open(url)
    except Exception:
        return False


# ── Detection ────────────────────────────────────────────────────────

def check_all() -> list[DriverStatus]:
    """Walk every USB device the Windows registry knows about, return
    a DriverStatus per detected adapter (whether or not it has a COM
    port bound). Imports usb_devices lazily to avoid pulling Windows-
    only code on import."""
    if sys.platform != "win32":
        return []
    try:
        from core.usb_devices import enumerate_usb
    except Exception:
        return []

    out: list[DriverStatus] = []
    for dev in enumerate_usb():
        spec = by_vid_pid_str(dev.vid_pid)
        # Only emit a row if this device is a recognized adapter, OR
        # if it has a COM port but we can't ID it (still useful to
        # show in the UI as "unknown serial").
        if not spec and not dev.com_port:
            continue
        out.append(DriverStatus(
            vid_pid=dev.vid_pid,
            instance_id=dev.instance_id,
            friendly_name=dev.friendly_name,
            com_port=dev.com_port,
            adapter=spec,
            needs_driver=bool(spec and not dev.com_port),
        ))
    return out


def needs_driver_install() -> list[DriverStatus]:
    """Subset of check_all() — only adapters that have a USB device
    visible but no COM port bound (driver missing or wrong)."""
    return [s for s in check_all() if s.needs_driver]
