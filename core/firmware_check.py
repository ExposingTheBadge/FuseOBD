"""Adapter firmware version check.

After a successful connect, we already capture the ATI/STI response in
`gui/panels/connection.py` and classify the adapter via
`core/adapter_id.py#identify()`. This module takes that next step:
compares the firmware version we got against the latest known version
for that model, and (when the adapter is outdated) surfaces a clear
update prompt with the vendor's official download URL.

Data is BAKED-IN — no runtime network calls. The table below is the
"latest known" version FuseOBD shipped with; if the user actually has
a newer one, the check returns OK (we never tell someone their newer
firmware is outdated). When the data in this table goes stale, ship a
new FuseOBD build with bumped versions.

The check is intentionally tolerant: clones that lie about their
version (the ELM327 v2.1 / v2.2 epidemic) get classified UNKNOWN
rather than OUTDATED, so we don't spam users with bogus prompts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FirmwareSpec:
    kind: str            # adapter_id kind (obdlink_mxp, vlinker_fs, …)
    latest: str          # canonical "latest known" version string
    update_url: str      # vendor's firmware download / updater
    notes: str = ""
    trust_version: bool = True
    # When False, the version response is known to be a lie (ELM clones
    # masquerading as v2.1+). For those we never raise OUTDATED.


# ── Known-latest table (per adapter kind) ────────────────────────────
# Updated by hand when shipping a new FuseOBD build. Source: vendor
# release pages as of 2026-06-06.

LATEST: dict[str, FirmwareSpec] = {
    "obdlink_mxp": FirmwareSpec(
        kind="obdlink_mxp", latest="5.4.2",
        update_url="https://www.scantool.net/scantool/downloads/updates/",
        notes="OBDLink MX+: launch the OBDLink desktop app, plug in via USB, run Firmware Update.",
    ),
    "obdlink_ex": FirmwareSpec(
        kind="obdlink_ex", latest="5.4.2",
        update_url="https://www.scantool.net/scantool/downloads/updates/",
    ),
    "obdlink_cx": FirmwareSpec(
        kind="obdlink_cx", latest="2.0.4",
        update_url="https://www.scantool.net/scantool/downloads/updates/",
    ),
    "obdlink_lx": FirmwareSpec(
        kind="obdlink_lx", latest="5.4.0",
        update_url="https://www.scantool.net/scantool/downloads/updates/",
    ),
    "obdlink_sx": FirmwareSpec(
        kind="obdlink_sx", latest="4.3.0",
        update_url="https://www.scantool.net/scantool/downloads/updates/",
    ),
    "vlinker_fs": FirmwareSpec(
        kind="vlinker_fs", latest="1.4",
        update_url="https://www.vgatemall.com/Driver/",
        notes="vLinker FS USB: download the Vgate Firmware Update Tool, connect over USB.",
    ),
    "vlinker_fd": FirmwareSpec(
        kind="vlinker_fd", latest="1.3",
        update_url="https://www.vgatemall.com/Driver/",
    ),
    "vlinker_mcp": FirmwareSpec(
        kind="vlinker_mcp", latest="1.5",
        update_url="https://www.vgatemall.com/Driver/",
    ),
    "vlinker_bmp": FirmwareSpec(
        kind="vlinker_bmp", latest="1.5",
        update_url="https://www.vgatemall.com/Driver/",
    ),
    "kiwi3": FirmwareSpec(
        kind="kiwi3", latest="2.2",
        update_url="https://www.plxdevices.com/kiwi-3-bluetooth-adapter/",
        notes="PLX Kiwi 3 firmware is ELM327 v2.2 — vendor stopped updates in 2018.",
    ),
    # Bare STN chips reported without a vendor wrapper — we can't tell
    # which product they're inside, so just report the chip's latest
    # generic firmware. Update path is vendor-specific anyway.
    "stn2255": FirmwareSpec(
        kind="stn2255", latest="4.2.0",
        update_url="https://www.scantool.net/scantool/downloads/updates/",
    ),
    "stn1170": FirmwareSpec(
        kind="stn1170", latest="4.5.1",
        update_url="https://www.scantool.net/scantool/downloads/updates/",
    ),
    "stn1130": FirmwareSpec(
        kind="stn1130", latest="4.2.0",
        update_url="https://www.scantool.net/scantool/downloads/updates/",
    ),
    "stn1110": FirmwareSpec(
        kind="stn1110", latest="3.4.0",
        update_url="https://www.scantool.net/scantool/downloads/updates/",
    ),
    # Generic ELM clones: version strings are unreliable, no real
    # updates available. Tag trust_version=False so we never raise
    # OUTDATED on a "v2.1" clone that's actually v1.5.
    "elm327": FirmwareSpec(
        kind="elm327", latest="2.3",
        update_url="https://www.elmelectronics.com/products/dsa/elm327/",
        notes="Genuine ELM327 v2.3 is the last release. Clones reporting v2.1+ usually lie.",
        trust_version=False,
    ),
    "clone": FirmwareSpec(
        kind="clone", latest="",
        update_url="",
        notes="Unbranded clone — no firmware updates available.",
        trust_version=False,
    ),
}


# ── Version comparison ──────────────────────────────────────────────

_VER_RE = re.compile(r'(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?')


def _parse_version(s: str) -> Optional[tuple[int, ...]]:
    """Best-effort parse of a dotted version like '5.4.2' or 'r5.4.2'
    or 'v1.4' into a comparable tuple. Returns None on garbage."""
    if not s:
        return None
    m = _VER_RE.search(s)
    if not m:
        return None
    return tuple(int(x) if x else 0 for x in m.groups())


# ── Public API ──────────────────────────────────────────────────────

class Status:
    OK            = "ok"          # adapter is at the latest known version
    OUTDATED      = "outdated"    # adapter is older than the latest known version
    NEWER         = "newer"       # adapter is newer than what we ship knowledge of
    UNKNOWN       = "unknown"     # we don't have data for this adapter / can't parse
    UNTRUSTED     = "untrusted"   # the adapter is known to lie about its version


@dataclass
class FirmwareCheck:
    kind: str
    current: str
    latest: str
    status: str
    update_url: str
    notes: str = ""

    @property
    def needs_update(self) -> bool:
        return self.status == Status.OUTDATED

    @property
    def display(self) -> str:
        if self.status == Status.OK:
            return f"firmware {self.current} — up to date"
        if self.status == Status.OUTDATED:
            return f"firmware {self.current} — UPDATE AVAILABLE (latest {self.latest})"
        if self.status == Status.NEWER:
            return f"firmware {self.current} — newer than what FuseOBD knows about ({self.latest})"
        if self.status == Status.UNTRUSTED:
            return f"firmware {self.current} — clone, version string unreliable"
        return f"firmware {self.current or '?'} — no update info available"


def check(adapter_kind: str, current_version: str) -> FirmwareCheck:
    """Compare a detected adapter against the LATEST table. Always
    returns a FirmwareCheck; status describes the outcome.

    Caller is the connection panel — pass adapter_id.identify() result's
    .kind and .firmware fields straight in."""
    spec = LATEST.get(adapter_kind)
    if not spec:
        return FirmwareCheck(kind=adapter_kind, current=current_version,
                             latest="", status=Status.UNKNOWN, update_url="")
    if not spec.trust_version:
        return FirmwareCheck(kind=adapter_kind, current=current_version,
                             latest=spec.latest, status=Status.UNTRUSTED,
                             update_url=spec.update_url, notes=spec.notes)
    cur = _parse_version(current_version)
    lat = _parse_version(spec.latest)
    if not cur or not lat:
        return FirmwareCheck(kind=adapter_kind, current=current_version,
                             latest=spec.latest, status=Status.UNKNOWN,
                             update_url=spec.update_url, notes=spec.notes)
    if cur < lat:
        status = Status.OUTDATED
    elif cur > lat:
        status = Status.NEWER
    else:
        status = Status.OK
    return FirmwareCheck(kind=adapter_kind, current=current_version,
                         latest=spec.latest, status=status,
                         update_url=spec.update_url, notes=spec.notes)
