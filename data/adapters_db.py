"""Baked-in offline adapter library.

Each entry describes one OBD-II adapter model with everything FuseOBD
needs to recognize it on plug-in, drive it correctly, and tell the
user about driver requirements WITHOUT a single network call at
runtime.

Lookup APIs:
  by_vid_pid(vid, pid) -> AdapterSpec | None
  by_ati(ati_string)   -> AdapterSpec | None
  by_name(substring)   -> AdapterSpec | None
  all_with_driver(d)   -> list[AdapterSpec]

The data here was assembled from manufacturer datasheets and the
public USB Vendor/Product ID registry (linux-usb.org/usb.ids), curated
to adapters actually seen in the OBD-II diagnostic community. Add new
entries by appending to ADAPTERS — the lookups are linear scans, so a
~few-hundred-entry table is fine.

Driver families:
  ftdi_vcp     — FTDI Virtual COM Port driver (FT232R/RL, FT2232, FT4232,
                 FT231X). Windows 10+ installs the inbox driver via
                 Windows Update automatically; older Windows or sleeping
                 Update needs the manual driver from ftdichip.com.
  ch340        — QinHeng CH340/CH341/CH343 USB-serial. Driver auto-
                 installs on Win 10 1709+; older needs wch.cn driver.
  cp210x       — Silicon Labs CP2102/CP2104/CP2105/CP2108. Win 10+
                 inbox driver covers most; manual silabs.com installer
                 needed for some.
  pl2303       — Prolific PL2303 (legacy). Driver is finicky; some
                 clones use counterfeit chips that the official Prolific
                 driver REFUSES — needs older v3.3.x install.
  cdc_acm      — Native USB CDC (no third-party driver, Windows handles
                 it via usbser.sys). Modern STN-based adapters use this.
  vendor_j2534 — Pro J2534 adapter — vendor ships its own .DLL +
                 PassThru registry entries. Detected via the registry
                 enumerator, not VID/PID.
  bt_classic   — Bluetooth Classic SPP — pair via Windows Settings,
                 a COM port appears automatically. No "driver" per se.
  bt_le        — Bluetooth Low Energy (BLE) — requires app-side BLE
                 stack; serial-port emulation NOT available on Windows
                 except via vendor-specific drivers.
  wifi         — WiFi-only adapter (ELM327 WiFi clones) — connects via
                 TCP socket, no Windows driver involved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── enums (string-typed for readability in dumps) ────────────────────

class DriverFamily:
    FTDI_VCP    = "ftdi_vcp"
    CH340       = "ch340"
    CP210X      = "cp210x"
    PL2303      = "pl2303"
    CDC_ACM     = "cdc_acm"
    VENDOR_J2534= "vendor_j2534"
    BT_CLASSIC  = "bt_classic"
    BT_LE       = "bt_le"
    WIFI        = "wifi"


class Chipset:
    ELM327      = "ELM327"
    STN1110     = "STN1110"
    STN1130     = "STN1130"
    STN1170     = "STN1170"
    STN2100     = "STN2100"
    STN2120     = "STN2120"
    STN2255     = "STN2255"
    PROPRIETARY = "proprietary"


@dataclass(frozen=True)
class UsbId:
    vid: int        # e.g. 0x0403 for FTDI
    pid: int        # e.g. 0x6001 for FT232R
    notes: str = ""

    def matches(self, vid_pid_str: str) -> bool:
        """Match a Windows registry-style 'VID_0403&PID_6001' string."""
        if not vid_pid_str: return False
        u = vid_pid_str.upper()
        return f"VID_{self.vid:04X}" in u and f"PID_{self.pid:04X}" in u


@dataclass(frozen=True)
class AdapterSpec:
    name: str                                 # display name
    vendor: str                               # who makes it
    chipset: str                              # one of Chipset.*
    driver: str                               # one of DriverFamily.*
    usb_ids: tuple[UsbId, ...] = ()           # all known USB IDs for this adapter
    ati_patterns: tuple[str, ...] = ()        # ATI/STI response substrings (case-insens)
    name_patterns: tuple[str, ...] = ()       # Windows FriendlyName substrings
    default_baud: int = 38400
    supported_bauds: tuple[int, ...] = (38400,)
    connection: tuple[str, ...] = ("usb",)    # usb / bluetooth / ble / wifi
    capabilities: tuple[str, ...] = ()        # tags: hs_can, ms_can, can_fd, j1850, k_line, j1939, ...
    driver_url: str = ""                      # official driver download
    notes: str = ""

    def ati_match(self, ati: str) -> bool:
        if not ati or not self.ati_patterns: return False
        s = ati.lower()
        return any(p.lower() in s for p in self.ati_patterns)


# ── Driver download URLs (kept here so the per-adapter rows stay tidy) ──

URL_FTDI_VCP    = "https://ftdichip.com/drivers/vcp-drivers/"
URL_CH340       = "https://www.wch-ic.com/downloads/CH341SER_EXE.html"
URL_CP210X      = "https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers"
URL_PL2303      = "https://www.prolific.com.tw/US/ShowProduct.aspx?p_id=225&pcid=41"
URL_OBDLINK     = "https://www.scantool.net/scantool/downloads/updates/"
URL_VLINKER     = "https://www.vgatemall.com/Driver/"
URL_TACTRIX     = "https://tactrix.com/openport-driver-installer/"


# ── The library ──────────────────────────────────────────────────────
# Add new adapters here. Ordering doesn't matter — lookups are linear
# but only run on enumeration, not per-poll.

ADAPTERS: tuple[AdapterSpec, ...] = (

    # ─── ScanTool OBDLink family (STN-based, genuine) ───────────────
    AdapterSpec(
        name="OBDLink MX+",
        vendor="ScanTool",
        chipset=Chipset.STN2255,
        driver=DriverFamily.BT_CLASSIC,
        ati_patterns=("OBDLink MX+", "OBDLink MX +"),
        name_patterns=("OBDLink MX+",),
        default_baud=115200,
        supported_bauds=(9600, 38400, 115200, 230400, 460800, 921600, 1228800),
        connection=("bluetooth", "usb"),
        capabilities=("hs_can", "ms_can", "can_fd", "iso9141", "kwp2000",
                      "j1850_vpw", "j1850_pwm", "ford_gateway"),
        driver_url=URL_OBDLINK,
        notes="Best general-purpose ELM-class adapter. Bluetooth + USB.",
    ),
    AdapterSpec(
        name="OBDLink EX",
        vendor="ScanTool",
        chipset=Chipset.STN2120,
        driver=DriverFamily.FTDI_VCP,
        usb_ids=(UsbId(0x0403, 0x6015, "FT231X"),),
        ati_patterns=("OBDLink EX",),
        name_patterns=("OBDLink EX",),
        default_baud=115200,
        supported_bauds=(9600, 38400, 115200, 230400, 460800, 921600),
        capabilities=("hs_can", "ms_can", "can_fd", "iso9141", "kwp2000",
                      "j1850_vpw", "j1850_pwm", "ford_gateway"),
        driver_url=URL_FTDI_VCP,
        notes="USB-only sibling of MX+. Ford/Mazda tuned.",
    ),
    AdapterSpec(
        name="OBDLink CX",
        vendor="ScanTool",
        chipset=Chipset.STN2120,
        driver=DriverFamily.BT_LE,
        ati_patterns=("OBDLink CX",),
        connection=("ble",),
        capabilities=("hs_can", "ms_can", "can_fd", "iso9141", "kwp2000"),
        driver_url=URL_OBDLINK,
        notes="BLE-only — iOS / Android first; Windows BLE support is limited.",
    ),
    AdapterSpec(
        name="OBDLink LX",
        vendor="ScanTool",
        chipset=Chipset.STN1130,
        driver=DriverFamily.BT_CLASSIC,
        ati_patterns=("OBDLink LX",),
        name_patterns=("OBDLink LX",),
        default_baud=115200,
        supported_bauds=(9600, 38400, 115200, 230400, 460800),
        connection=("bluetooth",),
        capabilities=("hs_can", "iso9141", "kwp2000", "j1850_vpw", "j1850_pwm"),
        driver_url=URL_OBDLINK,
        notes="No MS-CAN — use MX+ for Ford-body modules.",
    ),
    AdapterSpec(
        name="OBDLink SX",
        vendor="ScanTool",
        chipset=Chipset.STN1110,
        driver=DriverFamily.FTDI_VCP,
        usb_ids=(UsbId(0x0403, 0x6001, "FT232R"),),
        ati_patterns=("OBDLink SX",),
        name_patterns=("OBDLink SX",),
        default_baud=115200,
        supported_bauds=(9600, 38400, 115200, 230400, 460800),
        capabilities=("hs_can", "iso9141", "kwp2000", "j1850_vpw", "j1850_pwm"),
        driver_url=URL_FTDI_VCP,
        notes="USB cable entry-level — solid for HS-CAN cars.",
    ),

    # ─── Vgate vLinker family (STN1170, genuine) ────────────────────
    AdapterSpec(
        name="vLinker FS USB",
        vendor="Vgate",
        chipset=Chipset.STN1170,
        driver=DriverFamily.FTDI_VCP,
        usb_ids=(UsbId(0x0403, 0x6001, "FT232R/RL"),
                 UsbId(0x0403, 0x6015, "FT231X")),
        ati_patterns=("vLinker FS", "STN1170"),
        name_patterns=("vLinker FS", "USB Serial Port"),
        default_baud=921600,
        supported_bauds=(9600, 38400, 115200, 230400, 460800, 921600, 1228800),
        capabilities=("hs_can", "ms_can", "iso9141", "kwp2000", "j1850_pwm",
                      "ford_feps", "ford_gateway"),
        driver_url=URL_FTDI_VCP,
        notes="Ford-specific USB. FEPS pin support for PCM reflash.",
    ),
    AdapterSpec(
        name="vLinker FD WiFi/BT",
        vendor="Vgate",
        chipset=Chipset.STN1170,
        driver=DriverFamily.WIFI,
        ati_patterns=("vLinker FD",),
        connection=("wifi", "bluetooth"),
        capabilities=("hs_can", "ms_can", "can_fd", "iso9141", "kwp2000"),
        notes="CAN-FD variant. WiFi mode connects on 192.168.0.10:35000 by default.",
    ),
    AdapterSpec(
        name="vLinker MC+",
        vendor="Vgate",
        chipset=Chipset.STN1170,
        driver=DriverFamily.BT_CLASSIC,
        ati_patterns=("vLinker MC+", "vLinker MC +"),
        connection=("bluetooth", "wifi"),
        capabilities=("hs_can", "ms_can", "iso9141", "kwp2000",
                      "j1850_vpw", "j1850_pwm"),
        notes="Bluetooth + WiFi, multi-protocol.",
    ),
    AdapterSpec(
        name="vLinker BM+",
        vendor="Vgate",
        chipset=Chipset.STN1170,
        driver=DriverFamily.BT_CLASSIC,
        ati_patterns=("vLinker BM+",),
        connection=("bluetooth",),
        capabilities=("hs_can", "ms_can", "iso9141", "kwp2000", "k_line"),
        notes="BMW-tuned but works on Ford.",
    ),

    # ─── PLX Devices Kiwi ──────────────────────────────────────────
    AdapterSpec(
        name="PLX Kiwi 3",
        vendor="PLX Devices",
        chipset=Chipset.ELM327,
        driver=DriverFamily.BT_CLASSIC,
        ati_patterns=("Kiwi 3", "Kiwi3"),
        connection=("bluetooth",),
        capabilities=("hs_can", "iso9141", "kwp2000"),
        notes="ELM327 v2.2-compatible Bluetooth, low power.",
    ),

    # ─── Tactrix OpenPort (genuine pro J2534) ──────────────────────
    AdapterSpec(
        name="Tactrix OpenPort 2.0",
        vendor="Tactrix",
        chipset=Chipset.PROPRIETARY,
        driver=DriverFamily.VENDOR_J2534,
        usb_ids=(UsbId(0x0403, 0xCC4D, "OpenPort 2.0"),),
        name_patterns=("OpenPort", "Tactrix"),
        capabilities=("hs_can", "ms_can", "iso9141", "kwp2000",
                      "j1850_vpw", "j1850_pwm", "ford_gateway", "j2534"),
        driver_url=URL_TACTRIX,
        notes="Pro-grade J2534-1 pass-thru. Native MS-CAN with Ford harness.",
    ),

    # ─── Drew Technologies / Opus IVS (Mongoose) ───────────────────
    AdapterSpec(
        name="Mongoose-Plus Ford 2",
        vendor="Drew Technologies",
        chipset=Chipset.PROPRIETARY,
        driver=DriverFamily.VENDOR_J2534,
        ati_patterns=("Mongoose-Plus Ford2", "Mongoose-Plus Ford 2"),
        capabilities=("hs_can", "ms_can", "ford_gateway", "j2534"),
        notes="Ford-specific J2534. Full post-gateway access.",
    ),
    AdapterSpec(
        name="Mongoose JLR",
        vendor="Drew Technologies",
        chipset=Chipset.PROPRIETARY,
        driver=DriverFamily.VENDOR_J2534,
        ati_patterns=("Mongoose JLR",),
        capabilities=("hs_can", "ms_can", "can_fd", "j2534"),
        notes="Jaguar/Land Rover variant; works on Ford/Lincoln too.",
    ),

    # ─── Ford OEM (Bosch VCM II) ───────────────────────────────────
    AdapterSpec(
        name="Ford VCM II",
        vendor="Ford / Bosch",
        chipset=Chipset.PROPRIETARY,
        driver=DriverFamily.VENDOR_J2534,
        ati_patterns=("Ford-VCM-II", "VCM II", "VCM-II"),
        capabilities=("hs_can", "ms_can", "iso9141", "kwp2000",
                      "j1850_pwm", "ford_gateway", "j2534", "ford_oem"),
        notes="Official Ford dealer tool. Best-case coverage.",
    ),

    # ─── Chinese pro J2534 ─────────────────────────────────────────
    AdapterSpec(
        name="VXDIAG VCX NANO Ford",
        vendor="VXDIAG",
        chipset=Chipset.PROPRIETARY,
        driver=DriverFamily.VENDOR_J2534,
        ati_patterns=("VXDIAG", "VCX NANO"),
        capabilities=("hs_can", "ms_can", "j2534"),
        notes="Affordable Ford clone of VCM II — MS-CAN can be flaky.",
    ),
    AdapterSpec(
        name="VNCI Ford",
        vendor="RKW",
        chipset=Chipset.PROPRIETARY,
        driver=DriverFamily.VENDOR_J2534,
        ati_patterns=("RKW - VNCI", "VNCI"),
        capabilities=("hs_can", "ms_can", "can_fd", "iso9141", "kwp2000",
                      "ford_gateway", "j2534"),
        notes="Modern CAN-FD capable Ford-focused pro tool.",
    ),
    AdapterSpec(
        name="SVCI",
        vendor="STIC",
        chipset=Chipset.PROPRIETARY,
        driver=DriverFamily.VENDOR_J2534,
        ati_patterns=("STIC - SVCI", "SVCI"),
        capabilities=("hs_can", "ms_can", "can_fd", "iso9141", "kwp2000",
                      "ford_gateway", "j2534"),
        notes="Multi-brand Chinese pro tool.",
    ),
    AdapterSpec(
        name="UCDS J2534",
        vendor="UCDS",
        chipset=Chipset.PROPRIETARY,
        driver=DriverFamily.VENDOR_J2534,
        ati_patterns=("UCDS-J2534", "UCDS"),
        capabilities=("hs_can", "ms_can", "ford_gateway", "j2534"),
        notes="Russian Ford-focused aftermarket.",
    ),

    # ─── Bare ELM327 clones — FTDI-based ───────────────────────────
    AdapterSpec(
        name="ELM327 USB (FTDI clone)",
        vendor="(generic)",
        chipset=Chipset.ELM327,
        driver=DriverFamily.FTDI_VCP,
        usb_ids=(UsbId(0x0403, 0x6001, "FT232R"),
                 UsbId(0x0403, 0x6010, "FT2232"),
                 UsbId(0x0403, 0x6011, "FT4232"),
                 UsbId(0x0403, 0x6014, "FT232H"),
                 UsbId(0x0403, 0x6015, "FT231X")),
        ati_patterns=("ELM327",),
        default_baud=38400,
        supported_bauds=(9600, 38400, 115200, 230400, 460800),
        capabilities=("hs_can", "iso9141", "kwp2000"),
        driver_url=URL_FTDI_VCP,
        notes="Catch-all for FTDI-chipped clones. ATI usually lies about version.",
    ),
    AdapterSpec(
        name="ELM327 USB (CH340 clone)",
        vendor="(generic)",
        chipset=Chipset.ELM327,
        driver=DriverFamily.CH340,
        usb_ids=(UsbId(0x1A86, 0x7523, "CH340"),
                 UsbId(0x1A86, 0x5523, "CH341"),
                 UsbId(0x1A86, 0x55D3, "CH343")),
        ati_patterns=("ELM327",),
        default_baud=38400,
        supported_bauds=(9600, 38400, 115200, 230400),
        capabilities=("hs_can", "iso9141", "kwp2000"),
        driver_url=URL_CH340,
        notes="Cheapest tier. Slow at high baud, but works for DTC + PIDs.",
    ),
    AdapterSpec(
        name="ELM327 USB (CP210x clone)",
        vendor="(generic)",
        chipset=Chipset.ELM327,
        driver=DriverFamily.CP210X,
        usb_ids=(UsbId(0x10C4, 0xEA60, "CP2102"),
                 UsbId(0x10C4, 0xEA70, "CP2105"),
                 UsbId(0x10C4, 0xEA71, "CP2108")),
        ati_patterns=("ELM327",),
        default_baud=38400,
        supported_bauds=(9600, 38400, 115200, 230400, 460800),
        capabilities=("hs_can", "iso9141", "kwp2000"),
        driver_url=URL_CP210X,
        notes="Silicon Labs USB-serial. Reliable, decent at high baud.",
    ),
    AdapterSpec(
        name="ELM327 USB (Prolific PL2303 clone)",
        vendor="(generic)",
        chipset=Chipset.ELM327,
        driver=DriverFamily.PL2303,
        usb_ids=(UsbId(0x067B, 0x2303, "PL2303"),
                 UsbId(0x067B, 0x23A3, "PL2303GC"),
                 UsbId(0x067B, 0x23B3, "PL2303GB")),
        ati_patterns=("ELM327",),
        default_baud=38400,
        supported_bauds=(9600, 38400, 115200),
        capabilities=("hs_can", "iso9141", "kwp2000"),
        driver_url=URL_PL2303,
        notes="Legacy. Counterfeit chips refuse the official driver — needs v3.3.x.",
    ),

    # ─── Bluetooth Classic ELM327 clones ───────────────────────────
    AdapterSpec(
        name="ELM327 Bluetooth (generic)",
        vendor="(generic)",
        chipset=Chipset.ELM327,
        driver=DriverFamily.BT_CLASSIC,
        ati_patterns=("ELM327", "OBDII Bluetooth"),
        connection=("bluetooth",),
        capabilities=("hs_can", "iso9141", "kwp2000"),
        notes="Pair via Windows Settings; a virtual COM port appears.",
    ),
    AdapterSpec(
        name="BAFX Products Bluetooth",
        vendor="BAFX",
        chipset=Chipset.ELM327,
        driver=DriverFamily.BT_CLASSIC,
        ati_patterns=("BAFX",),
        connection=("bluetooth",),
        capabilities=("hs_can", "iso9141", "kwp2000"),
        notes="Solid budget BT adapter, ELM327 v2.1.",
    ),
    AdapterSpec(
        name="Veepeak Mini",
        vendor="Veepeak",
        chipset=Chipset.ELM327,
        driver=DriverFamily.BT_CLASSIC,
        ati_patterns=("Veepeak",),
        connection=("bluetooth",),
        capabilities=("hs_can", "iso9141", "kwp2000"),
    ),

    # ─── WiFi-only ELM327 clones ───────────────────────────────────
    AdapterSpec(
        name="ELM327 WiFi (generic)",
        vendor="(generic)",
        chipset=Chipset.ELM327,
        driver=DriverFamily.WIFI,
        connection=("wifi",),
        capabilities=("hs_can", "iso9141", "kwp2000"),
        notes="Connects to its own AP; FuseOBD uses 192.168.0.10:35000.",
    ),
    AdapterSpec(
        name="OBDII WiFi (KW902 / KW903)",
        vendor="Konnwei",
        chipset=Chipset.ELM327,
        driver=DriverFamily.WIFI,
        ati_patterns=("KW902", "KW903"),
        connection=("wifi",),
        capabilities=("hs_can", "iso9141", "kwp2000"),
    ),

    # ─── Other named ───────────────────────────────────────────────
    AdapterSpec(
        name="SM2 USB",
        vendor="SMD",
        chipset=Chipset.PROPRIETARY,
        driver=DriverFamily.VENDOR_J2534,
        ati_patterns=("SM2 USB", "SM2-USB"),
        capabilities=("hs_can", "ms_can", "j2534"),
    ),
    AdapterSpec(
        name="Chipsoft J2534",
        vendor="Chipsoft",
        chipset=Chipset.PROPRIETARY,
        driver=DriverFamily.VENDOR_J2534,
        ati_patterns=("CHIPSOFT J2534", "Chipsoft"),
        capabilities=("hs_can", "sw_can", "iso9141", "kwp2000", "j2534"),
        notes="No MS-CAN — uses SW-CAN + GMUART instead.",
    ),
    AdapterSpec(
        name="Bosch 6531",
        vendor="Bosch",
        chipset=Chipset.PROPRIETARY,
        driver=DriverFamily.VENDOR_J2534,
        ati_patterns=("6531-Bosch", "6531"),
        capabilities=("hs_can", "kwp2000", "j2534"),
    ),
    AdapterSpec(
        name="CANtieCAR",
        vendor="(generic)",
        chipset=Chipset.PROPRIETARY,
        driver=DriverFamily.VENDOR_J2534,
        ati_patterns=("CANtieCAR",),
        capabilities=("hs_can", "ms_can", "j2534"),
    ),
)


# ── Lookup APIs ──────────────────────────────────────────────────────

def by_vid_pid(vid: int, pid: int) -> Optional[AdapterSpec]:
    """Match a USB VID+PID against the library. Returns the FIRST match;
    if multiple adapters share a generic chipset USB ID (e.g. lots of
    FT232R clones), prefer the more-specific entries by sorting them
    first in the table above."""
    for a in ADAPTERS:
        for uid in a.usb_ids:
            if uid.vid == vid and uid.pid == pid:
                return a
    return None


def by_vid_pid_str(vid_pid_str: str) -> Optional[AdapterSpec]:
    """Match a Windows registry VID_PID string ('VID_0403&PID_6001...')."""
    for a in ADAPTERS:
        for uid in a.usb_ids:
            if uid.matches(vid_pid_str):
                return a
    return None


def by_ati(ati: str) -> Optional[AdapterSpec]:
    for a in ADAPTERS:
        if a.ati_match(ati):
            return a
    return None


def by_name(query: str) -> list[AdapterSpec]:
    q = (query or "").lower()
    return [a for a in ADAPTERS if q in a.name.lower()]


def all_with_driver(driver: str) -> list[AdapterSpec]:
    return [a for a in ADAPTERS if a.driver == driver]


def all_with_capability(cap: str) -> list[AdapterSpec]:
    return [a for a in ADAPTERS if cap in a.capabilities]
