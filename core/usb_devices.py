"""Windows USB device enumeration with VID/PID extraction.

Walks HKLM\\SYSTEM\\CurrentControlSet\\Enum\\USB to find every USB
device the OS has ever seen, then cross-references HARDWARE\\DEVICEMAP\\
SERIALCOMM to figure out which ones currently have a COM port bound.

Pure-Python via winreg. No SetupAPI / ctypes / extra deps. Used by:
  - core/drivers.py — driver health check (USB device with no COM port
    = bad / missing driver)
  - core/j2534.py — adapter identification BEFORE the user clicks
    Connect, using VID/PID against data/adapters_db.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class UsbDevice:
    vid_pid: str            # 'VID_0403&PID_6001' (Windows registry style)
    instance_id: str        # specific device instance under that VID/PID
    vid: int                # parsed integer VID
    pid: int                # parsed integer PID
    friendly_name: str      # Windows FriendlyName / DeviceDesc
    manufacturer: str       # Mfg property
    service: str            # bound kernel driver service name (FTSER2K, usbser, etc.)
    com_port: Optional[str] # COM port name if currently bound, else None


def _parse_vid_pid(s: str) -> tuple[int, int]:
    """'VID_0403&PID_6001&MI_00' -> (0x0403, 0x6001). Returns (0,0) on
    anything malformed."""
    if not s: return (0, 0)
    vid = pid = 0
    for part in s.upper().split("&"):
        if part.startswith("VID_"):
            try: vid = int(part[4:8], 16)
            except ValueError: pass
        elif part.startswith("PID_"):
            try: pid = int(part[4:8], 16)
            except ValueError: pass
    return (vid, pid)


def enumerate_usb() -> list[UsbDevice]:
    """Return every USB device the registry knows about. Slow ports
    (USB keyboards, mass-storage, etc.) are included — callers filter
    by VID/PID against the adapter library when they only want OBD
    adapters."""
    if sys.platform != "win32":
        return []
    import winreg  # local import keeps non-Windows machines importable

    # ── COM port map: { vid_pid_instance_path -> COMx } ──
    port_map: dict[str, str] = {}
    try:
        sk = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"HARDWARE\DEVICEMAP\SERIALCOMM",
                            0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                dev_path, com_name, _ = winreg.EnumValue(sk, i)
                # dev_path looks like
                # '\Device\VCP0' / '\Device\Serial0' / '\Device\USBSER000'
                port_map[dev_path.lower()] = com_name
                i += 1
            except OSError:
                break
        winreg.CloseKey(sk)
    except OSError:
        pass

    out: list[UsbDevice] = []
    try:
        enum_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                  r"SYSTEM\CurrentControlSet\Enum\USB",
                                  0, winreg.KEY_READ)
    except OSError:
        return out

    try:
        i = 0
        while True:
            try:
                vid_pid_key = winreg.EnumKey(enum_key, i)
                i += 1
            except OSError:
                break
            try:
                vid_sub = winreg.OpenKey(enum_key, vid_pid_key, 0, winreg.KEY_READ)
            except OSError:
                continue
            j = 0
            while True:
                try:
                    instance_key = winreg.EnumKey(vid_sub, j)
                    j += 1
                except OSError:
                    break
                try:
                    inst = winreg.OpenKey(vid_sub, instance_key, 0, winreg.KEY_READ)
                except OSError:
                    continue
                friendly = mfg = svc = ""
                for prop_name, target in (
                    ("FriendlyName", "friendly"),
                    ("DeviceDesc",  "friendly_fb"),
                    ("Mfg",          "mfg"),
                    ("Service",      "svc"),
                ):
                    try:
                        v = winreg.QueryValueEx(inst, prop_name)[0]
                        if target == "friendly" and v: friendly = _clean_inf_ref(v)
                        elif target == "friendly_fb" and not friendly and v:
                            friendly = _clean_inf_ref(v)
                        elif target == "mfg" and v: mfg = _clean_inf_ref(v)
                        elif target == "svc" and v: svc = v
                    except OSError:
                        pass

                # Look for Device Parameters\PortName under this instance
                # (set by usbser / FTSER2K / Silabser when a COM port is
                # actually bound). If present, that IS the COM port.
                com_port = None
                try:
                    dp = winreg.OpenKey(inst, "Device Parameters", 0, winreg.KEY_READ)
                    try:
                        com_port = winreg.QueryValueEx(dp, "PortName")[0]
                    except OSError:
                        pass
                    winreg.CloseKey(dp)
                except OSError:
                    pass

                winreg.CloseKey(inst)

                vid, pid = _parse_vid_pid(vid_pid_key)
                out.append(UsbDevice(
                    vid_pid=vid_pid_key,
                    instance_id=instance_key,
                    vid=vid, pid=pid,
                    friendly_name=friendly or "(no name)",
                    manufacturer=mfg,
                    service=svc,
                    com_port=com_port,
                ))
            winreg.CloseKey(vid_sub)
    finally:
        winreg.CloseKey(enum_key)
    return out


def _clean_inf_ref(s: str) -> str:
    """Strip INF reference prefixes like '@oem211.inf,%foo%;Real Name'
    that appear on raw FriendlyName / DeviceDesc properties."""
    if not s: return s
    if s.startswith("@"):
        parts = s.split(";", 1)
        return parts[1] if len(parts) > 1 else s.lstrip("@")
    return s
