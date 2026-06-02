"""J2534 adapter detection + capability database.

PassThruReadVersion() returns a free-form firmware/device string. FuseOBD
matches that string against the patterns here to figure out:

  - the friendly adapter name to show in the UI / log
  - which CAN variants and link-layer protocols the adapter can actually
    do (so we don't issue MS-CAN ops to an HS-only adapter, then
    misdiagnose the resulting timeout as a vehicle problem)

Patterns are derived from an external Ford-diagnostic reverse-
engineering reference plus public manufacturer documentation. Add
adapters here as they're encountered in the field — `match()` does a
case-insensitive substring scan, so partial strings are fine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntFlag


class AdapterCap(IntFlag):
    """Bitfield of link-layer / protocol capabilities. Use bitwise AND
    against an Adapter.caps to ask 'does this adapter support X?'"""
    HS_CAN       = 1 << 0    # ISO 15765-4 11-bit + 29-bit, up to 500kbps
    MS_CAN       = 1 << 1    # Medium-speed Ford body CAN, 125kbps
    SW_CAN       = 1 << 2    # GM/Chrysler single-wire CAN
    CAN_FD       = 1 << 3    # CAN FD (Flexible Data-rate), up to ~5Mbps
    ISO9141      = 1 << 4    # K-line, slow init
    KWP2000      = 1 << 5    # K-line, fast init
    J1850_VPW    = 1 << 6    # GM/Chrysler legacy
    J1850_PWM    = 1 << 7    # Ford legacy (pre-CAN)
    GW_BYPASS    = 1 << 8    # Can directly address modules behind the Ford gateway
    HIGH_BAUD    = 1 << 9    # Supports ELM327 ATBRD switching to >115.2kbps
    GENUINE      = 1 << 10   # Manufacturer authentic (vs clone) — fewer compat workarounds needed


@dataclass(frozen=True)
class Adapter:
    name: str                        # friendly name shown to the user
    match_patterns: tuple[str, ...]  # substrings searched in PassThruReadVersion output
    caps: AdapterCap
    notes: str = ""

    def matches(self, version_string: str) -> bool:
        v = (version_string or "").lower()
        return any(p.lower() in v for p in self.match_patterns)


# ── Database ──────────────────────────────────────────────────────────
# Order matters: more-specific patterns first. ADAPTERS[-1] is the
# generic ELM327 fallback so any unknown ELM-class device still works.

ADAPTERS: list[Adapter] = [
    # ── OEM / professional (highest confidence) ──
    Adapter(
        name="Ford VCM II",
        match_patterns=("Ford-VCM-II", "VCM II", "VCM-II"),
        caps=AdapterCap.HS_CAN | AdapterCap.MS_CAN | AdapterCap.ISO9141
             | AdapterCap.KWP2000 | AdapterCap.J1850_PWM
             | AdapterCap.GW_BYPASS | AdapterCap.GENUINE,
        notes="Official Ford / Bosch — full module access including post-gateway",
    ),
    Adapter(
        name="Mongoose-Plus Ford 2",
        match_patterns=("Mongoose-Plus Ford2", "Mongoose-Plus Ford 2", "Mongoose Plus Ford"),
        caps=AdapterCap.HS_CAN | AdapterCap.MS_CAN | AdapterCap.GENUINE | AdapterCap.GW_BYPASS,
        notes="Drew Technologies / Opus IVS — Ford-specific J2534",
    ),
    Adapter(
        name="Tactrix OpenPort 2.0",
        match_patterns=("OpenPort 2.0", "Tactrix"),
        caps=AdapterCap.HS_CAN | AdapterCap.MS_CAN | AdapterCap.ISO9141
             | AdapterCap.KWP2000 | AdapterCap.J1850_VPW | AdapterCap.J1850_PWM
             | AdapterCap.GENUINE,
        notes="Multi-protocol; reads MS-CAN with the Ford harness",
    ),

    # ── Professional Russian / Chinese clones ──
    Adapter(
        name="VNCI",
        match_patterns=("RKW - VNCI", "VNCI"),
        caps=AdapterCap.HS_CAN | AdapterCap.MS_CAN | AdapterCap.CAN_FD
             | AdapterCap.ISO9141 | AdapterCap.KWP2000 | AdapterCap.GW_BYPASS,
        notes="RKW VNCI — modern CAN-FD capable",
    ),
    Adapter(
        name="SVCI",
        match_patterns=("STIC - SVCI", "SVCI"),
        caps=AdapterCap.HS_CAN | AdapterCap.MS_CAN | AdapterCap.CAN_FD
             | AdapterCap.ISO9141 | AdapterCap.KWP2000 | AdapterCap.GW_BYPASS,
        notes="STIC SVCI",
    ),
    Adapter(
        name="UCDS J2534",
        match_patterns=("UCDS-J2534", "UCDS"),
        caps=AdapterCap.HS_CAN | AdapterCap.MS_CAN | AdapterCap.GW_BYPASS,
        notes="UCDS — Russian aftermarket Ford-focused",
    ),
    Adapter(
        name="VXDIAG VCX NANO",
        match_patterns=("VXDIAG", "VCX NANO", "VCX-NANO"),
        caps=AdapterCap.HS_CAN | AdapterCap.MS_CAN,
        notes="Multi-brand J2534; MS-CAN sometimes flaky",
    ),

    # ── Specialised CAN-FD enthusiast adapters ──
    Adapter(
        name="vLinker FD",
        match_patterns=("vLinker FD", "vLinker-FD"),
        caps=AdapterCap.HS_CAN | AdapterCap.MS_CAN | AdapterCap.CAN_FD
             | AdapterCap.HIGH_BAUD,
        notes="vLinker FD — Bluetooth/WiFi CAN-FD with Ford MS-CAN support",
    ),

    # ── Other named ──
    Adapter(
        name="SM2 USB",
        match_patterns=("SM2 USB", "SM2-USB"),
        caps=AdapterCap.HS_CAN | AdapterCap.MS_CAN,
    ),
    Adapter(
        name="CANtieCAR",
        match_patterns=("CANtieCAR",),
        caps=AdapterCap.HS_CAN | AdapterCap.MS_CAN,
    ),
    Adapter(
        name="Chipsoft J2534",
        match_patterns=("CHIPSOFT J2534", "Chipsoft"),
        caps=AdapterCap.HS_CAN | AdapterCap.SW_CAN | AdapterCap.ISO9141 | AdapterCap.KWP2000,
        notes="Note: NO MS-CAN — adapter uses SW-CAN + GMUART instead",
    ),
    Adapter(
        name="Bosch 6531",
        match_patterns=("6531-Bosch", "6531"),
        caps=AdapterCap.HS_CAN | AdapterCap.KWP2000,
        notes="Limited — HS-CAN + K-line only",
    ),

    # ── ELM327-class (STN-based + clones) — go last as fallbacks ──
    Adapter(
        name="STN1170 (ScanTool / OBDLink)",
        match_patterns=("STN1170", "STN 1170", "OBDLink"),
        caps=AdapterCap.HS_CAN | AdapterCap.MS_CAN | AdapterCap.ISO9141
             | AdapterCap.KWP2000 | AdapterCap.J1850_VPW | AdapterCap.J1850_PWM
             | AdapterCap.HIGH_BAUD | AdapterCap.GENUINE,
        notes="STN1170-based ELM-compatible — supports MS-CAN via User Protocol B",
    ),
    Adapter(
        name="ELM327",
        match_patterns=("ELM327", "ELM 327", "ELM v"),
        caps=AdapterCap.HS_CAN | AdapterCap.ISO9141 | AdapterCap.KWP2000,
        notes="Generic ELM327 — MS-CAN only with hardware pin modification",
    ),
]


def identify(version_string: str) -> Adapter:
    """Return the best-matching adapter, or a generic ELM327 fallback."""
    for a in ADAPTERS:
        if a.matches(version_string):
            return a
    return ADAPTERS[-1]  # ELM327 fallback


def has_capability(version_string: str, cap: AdapterCap) -> bool:
    """Quick predicate — does the adapter at `version_string` support `cap`?

    Intended use: guard MS-CAN / CAN-FD operations so we skip them on
    adapters that physically cannot do them, instead of issuing the request
    and waiting for a timeout that the user will misread as a dead module.
    """
    return bool(identify(version_string).caps & cap)
