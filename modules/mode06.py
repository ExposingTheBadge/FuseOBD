"""OBD-II Mode $06 — On-Board Monitoring (emissions self-test results).

Wire format (CAN, ISO 15031-5):

    request:  06 <MID>
    response: 46 <MID> <TID> <UAS> <result_hi> <result_lo> <min_hi> <min_lo> <max_hi> <max_lo>

  MID   = Monitor ID — which sub-system was tested (catalyst, EGR, O2 sensor, etc.)
  TID   = Test ID    — which specific test within that monitor
  UAS   = Unit And Scaling — selector into the SAE J1979 unit table
                            (determines how to scale result/min/max)
  result/min/max — 16-bit raw values, scaled per UAS

This module gives names to the MIDs and the well-known TIDs so the
scanner UI and AI Mechanic can label them. Coverage is the J1979
public set plus the additional TIDs observed in an external Ford-
diagnostic reference; expand as new test IDs are seen in the field.

Use case: catalyst efficiency monitoring (MID 0x21 / TID 0x80-0x88),
O2 sensor response monitoring (MID 0x01-0x08), EGR / EVAP / misfire
diagnostics — emissions warranty work, post-repair monitor readiness
checks, and pre-inspection sanity checks.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Mode06Monitor:
    mid: int
    name: str
    category: str = ""      # 'O2','Catalyst','EGR','EVAP','Misfire','Heater','Other'
    notes: str = ""


# ── Monitor IDs (SAE J1979 + extensions) ─────────────────────────────────────

MODE06_MONITORS: dict[int, Mode06Monitor] = {
    # ── O2 sensor monitors (Bank 1) ──
    0x01: Mode06Monitor(0x01, "O2 Sensor Monitor B1S1", "O2"),
    0x02: Mode06Monitor(0x02, "O2 Sensor Monitor B1S2", "O2"),
    0x03: Mode06Monitor(0x03, "O2 Sensor Monitor B1S3", "O2"),
    0x04: Mode06Monitor(0x04, "O2 Sensor Monitor B1S4", "O2"),
    # ── O2 sensor monitors (Bank 2) ──
    0x05: Mode06Monitor(0x05, "O2 Sensor Monitor B2S1", "O2"),
    0x06: Mode06Monitor(0x06, "O2 Sensor Monitor B2S2", "O2"),
    0x07: Mode06Monitor(0x07, "O2 Sensor Monitor B2S3", "O2"),
    0x08: Mode06Monitor(0x08, "O2 Sensor Monitor B2S4", "O2"),

    # ── Catalyst monitors ──
    0x21: Mode06Monitor(0x21, "Catalyst Monitor Bank 1", "Catalyst"),
    0x22: Mode06Monitor(0x22, "Catalyst Monitor Bank 2", "Catalyst"),

    # ── EGR / VVT ──
    0x31: Mode06Monitor(0x31, "EGR Monitor Bank 1",      "EGR"),
    0x32: Mode06Monitor(0x32, "EGR Monitor Bank 2",      "EGR"),
    0x35: Mode06Monitor(0x35, "VVT Monitor Bank 1",      "EGR"),
    0x36: Mode06Monitor(0x36, "VVT Monitor Bank 2",      "EGR"),
    0x37: Mode06Monitor(0x37, "EGR Cooler Monitor",      "EGR"),

    # ── Secondary air ──
    0x39: Mode06Monitor(0x39, "Secondary Air Monitor",   "Other"),

    # ── EVAP monitors ──
    0x3C: Mode06Monitor(0x3C, "EVAP Monitor (Cap Off / 0.090\")", "EVAP",
                        notes="Largest leak — coarse check"),
    0x3D: Mode06Monitor(0x3D, "EVAP Monitor (0.040\")",  "EVAP",
                        notes="Medium leak threshold"),
    0x3E: Mode06Monitor(0x3E, "EVAP Monitor (0.020\")",  "EVAP",
                        notes="Tight-seal small leak"),
    0x3F: Mode06Monitor(0x3F, "EVAP Monitor (Purge Flow)", "EVAP"),

    # ── O2 sensor heaters (Bank 1) ──
    0x41: Mode06Monitor(0x41, "O2 Heater Monitor B1S1",  "Heater"),
    0x42: Mode06Monitor(0x42, "O2 Heater Monitor B1S2",  "Heater"),
    0x43: Mode06Monitor(0x43, "O2 Heater Monitor B1S3",  "Heater"),
    0x44: Mode06Monitor(0x44, "O2 Heater Monitor B1S4",  "Heater"),
    # ── O2 sensor heaters (Bank 2) ──
    0x45: Mode06Monitor(0x45, "O2 Heater Monitor B2S1",  "Heater"),
    0x46: Mode06Monitor(0x46, "O2 Heater Monitor B2S2",  "Heater"),
    0x47: Mode06Monitor(0x47, "O2 Heater Monitor B2S3",  "Heater"),
    0x48: Mode06Monitor(0x48, "O2 Heater Monitor B2S4",  "Heater"),

    # ── PCV / engine oil / pressure ──
    0x71: Mode06Monitor(0x71, "PCV System Monitor",      "Other"),
    0x72: Mode06Monitor(0x72, "Engine Cooling System",   "Other"),
    0x73: Mode06Monitor(0x73, "Cold Start Emission Reduction", "Other"),

    # ── Misfire monitors ──
    0xA1: Mode06Monitor(0xA1, "Misfire Monitor — General Data", "Misfire"),
    0xA2: Mode06Monitor(0xA2, "Misfire — Cylinder 1",    "Misfire"),
    0xA3: Mode06Monitor(0xA3, "Misfire — Cylinder 2",    "Misfire"),
    0xA4: Mode06Monitor(0xA4, "Misfire — Cylinder 3",    "Misfire"),
    0xA5: Mode06Monitor(0xA5, "Misfire — Cylinder 4",    "Misfire"),
    0xA6: Mode06Monitor(0xA6, "Misfire — Cylinder 5",    "Misfire"),
    0xA7: Mode06Monitor(0xA7, "Misfire — Cylinder 6",    "Misfire"),
    0xA8: Mode06Monitor(0xA8, "Misfire — Cylinder 7",    "Misfire"),
    0xA9: Mode06Monitor(0xA9, "Misfire — Cylinder 8",    "Misfire"),
    0xAA: Mode06Monitor(0xAA, "Misfire — Cylinder 9",    "Misfire"),
    0xAB: Mode06Monitor(0xAB, "Misfire — Cylinder 10",   "Misfire"),
    0xAC: Mode06Monitor(0xAC, "Misfire — Cylinder 11",   "Misfire"),
    0xAD: Mode06Monitor(0xAD, "Misfire — Cylinder 12",   "Misfire"),
}


# ── Well-known TIDs per MID ──────────────────────────────────────────────────
# (MID, TID) -> human-readable description. Not exhaustive — populated from
# SAE J1979 + observed Ford catalyst / O2 monitor test IDs.
MODE06_TID_NAMES: dict[tuple[int, int], str] = {
    # O2 sensor tests (apply to MIDs 0x01-0x08)
    (0x01, 0x01): "Rich-to-Lean Threshold Voltage",
    (0x01, 0x02): "Lean-to-Rich Threshold Voltage",
    (0x01, 0x03): "Low Sensor Voltage for Switch Time",
    (0x01, 0x04): "High Sensor Voltage for Switch Time",
    (0x01, 0x05): "Rich-to-Lean Switch Time",
    (0x01, 0x06): "Lean-to-Rich Switch Time",
    (0x01, 0x07): "Minimum Sensor Voltage (Test Cycle)",
    (0x01, 0x08): "Maximum Sensor Voltage (Test Cycle)",
    (0x01, 0x09): "Time Between Sensor Transitions",
    (0x01, 0x0A): "Sensor Period",

    # Catalyst tests (apply to MIDs 0x21/0x22)
    (0x21, 0x80): "Catalyst Switch Ratio",
    (0x21, 0x81): "Catalyst Switch Count Front O2",
    (0x21, 0x82): "Catalyst Switch Count Rear O2",
    (0x21, 0x83): "Catalyst Oxygen Storage Capacity",
    (0x21, 0x84): "Catalyst Light-Off Time",

    # EGR tests
    (0x31, 0x80): "EGR Steady-State Flow Test",
    (0x31, 0x81): "EGR Position-Based Flow Test",
    (0x31, 0x82): "EGR Manifold Pressure Differential",

    # EVAP tests
    (0x3C, 0x80): "EVAP 0.040\" Leak Check Pressure",
    (0x3D, 0x80): "EVAP 0.020\" Leak Check Pressure",
    (0x3F, 0x80): "EVAP Purge Flow Rate",

    # Misfire (apply to all 0xA2-0xAD per-cylinder MIDs)
    (0xA2, 0x0B): "Misfire Counts (current drive)",
    (0xA2, 0x0C): "Misfire Counts (last 10 drives)",
}


def monitor_name(mid: int) -> str:
    m = MODE06_MONITORS.get(mid)
    return m.name if m else f"Monitor 0x{mid:02X}"


def test_name(mid: int, tid: int) -> str:
    """Look up the test name. Falls back to a per-MID generic if the
    specific TID isn't catalogued, then to a raw hex label."""
    if (mid, tid) in MODE06_TID_NAMES:
        return MODE06_TID_NAMES[(mid, tid)]
    # O2 sensors share the same TID set across all 8 MIDs
    if mid in (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08):
        return MODE06_TID_NAMES.get((0x01, tid), f"O2 Test 0x{tid:02X}")
    if mid in (0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xAB, 0xAC, 0xAD):
        return MODE06_TID_NAMES.get((0xA2, tid), f"Misfire Test 0x{tid:02X}")
    return f"Test 0x{tid:02X}"


# ── J1979 Unit-And-Scaling (UAS) table — partial ────────────────────────────
# The UAS byte selects how to interpret the raw 16-bit result/min/max values.
# Full table is in SAE J1979 Appendix; covering the common ones here.
UAS_TABLE: dict[int, tuple[str, float]] = {
    # UAS : (unit, scale_factor)  — value = raw * scale
    0x01: ("raw",            1.0),
    0x02: ("RPM",            0.25),
    0x03: ("V",              0.122e-3),     # 0.122mV per count
    0x04: ("V",              0.001),
    0x05: ("s",              0.01),
    0x06: ("ms",             1.0),
    0x07: ("ms",             10.0),
    0x08: ("s",              1.0),
    0x09: ("min",            1.0),
    0x0A: ("h",              1.0),
    0x0B: ("ratio",          1/32768),      # equivalence ratio
    0x0C: ("kPa",            0.0078125),
    0x0D: ("kPa",            0.1),
    0x0E: ("kPa",            1.0),
    0x0F: ("°C",             0.1),
    0x10: ("°C",             1.0),
    0x11: ("°",              0.1),
    0x12: ("Hz",             0.25),
    0x13: ("count",          1.0),
    0x14: ("%",              0.000305),
    0x15: ("%",              0.0039),       # 100/256
    0x16: ("g/s",            0.01),
    0x17: ("inH₂O",          0.0098),
    0x18: ("mA",             0.00305),
    0x19: ("mA",             0.001),
}


def scale_uas(uas: int, raw: int) -> tuple[float, str]:
    """Convert a raw 16-bit Mode $06 value to scaled value + unit
    using the UAS selector. Returns (value, unit). Unknown UAS falls
    back to raw with unit '?'."""
    if uas in UAS_TABLE:
        unit, scale = UAS_TABLE[uas]
        return raw * scale, unit
    return float(raw), "?"
