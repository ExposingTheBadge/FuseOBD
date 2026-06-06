"""Bundled CAN DBC databases — message + signal definitions.

Each `.dbc` file in this directory was lifted from commaai/opendbc
(MIT license, see LICENSE.opendbc) and ships with the FuseOBD client
so multi-make CAN decoding works offline.

Use core.dbc.load_file() to parse a single file, or load_make()
below for the full catalog of a given manufacturer.

Coverage as of 2026-06-06: Ford / Lincoln (extensive), Toyota / Lexus,
Hyundai / Kia, Tesla, Volkswagen / Audi, GM (Chevy / Cadillac / Buick),
Chrysler / Jeep / Ram, Mazda, Volvo, Nissan, Rivian.

Notable gaps (not in opendbc):
  - Honda / Acura — Honda used a different CAN scheme and their
    community DBCs weren't open-sourced.
  - Subaru — same situation; openpilot has them but they're not in
    the public opendbc tree.
  - BMW / Mercedes / Porsche — proprietary, not in opendbc.
  - Older pre-2008 vehicles — pre-CAN protocols (ISO9141 / J1850
    PWM / VPW / KWP2000); covered separately by core/protocols.py.
"""
from __future__ import annotations

import os
from typing import Optional

from core import dbc as _dbc


# ── Manifest of bundled databases ────────────────────────────────────

CATALOG: list[dict] = [
    # ── Ford / Lincoln ──
    {"make": "Ford",    "file": "FORD_CADS.dbc",
     "bus": "ADAS",     "notes": "Driver-assist + camera/radar (older)"},
    {"make": "Ford",    "file": "FORD_CADS_64.dbc",
     "bus": "ADAS",     "notes": "Driver-assist + camera/radar (newer, CAN-FD)"},
    {"make": "Ford",    "file": "ford_cgea1_2_bodycan_2011.dbc",
     "bus": "MS-CAN",   "notes": "Body modules — BCM/HVAC/IPC/SYNC (2011+ CGEA1.2)"},
    {"make": "Ford",    "file": "ford_cgea1_2_ptcan_2011.dbc",
     "bus": "HS-CAN",   "notes": "Powertrain — PCM/TCM/ABS (2011+ CGEA1.2)"},
    {"make": "Ford",    "file": "ford_fusion_2018_pt.dbc",
     "bus": "HS-CAN",   "notes": "2018 Fusion powertrain"},
    {"make": "Ford",    "file": "ford_fusion_2018_adas.dbc",
     "bus": "ADAS",     "notes": "2018 Fusion ADAS / IPMA"},
    {"make": "Lincoln", "file": "ford_lincoln_base_pt.dbc",
     "bus": "HS-CAN",   "notes": "Ford/Lincoln base powertrain (largest coverage)"},

    # ── Toyota / Lexus ──
    {"make": "Toyota",  "file": "toyota_2017_ref_pt.dbc",
     "bus": "HS-CAN",   "notes": "2017+ Toyota / Lexus reference powertrain"},
    {"make": "Toyota",  "file": "toyota_tss2_adas.dbc",
     "bus": "ADAS",     "notes": "Toyota Safety Sense 2.0 ADAS bus"},
    {"make": "Toyota",  "file": "toyota_adas.dbc",
     "bus": "ADAS",     "notes": "Earlier Toyota ADAS"},
    {"make": "Toyota",  "file": "toyota_prius_2010_pt.dbc",
     "bus": "HS-CAN",   "notes": "2010 Prius powertrain (hybrid)"},
    {"make": "Toyota",  "file": "toyota_iQ_2009_can.dbc",
     "bus": "HS-CAN",   "notes": "2009 Toyota iQ"},
    {"make": "Toyota",  "file": "toyota_radar_dsu_tssp.dbc",
     "bus": "ADAS",     "notes": "Toyota radar / DSU"},

    # ── Hyundai / Kia ──
    {"make": "Hyundai", "file": "hyundai_2015_ccan.dbc",
     "bus": "HS-CAN",   "notes": "2015+ Hyundai / Kia chassis CAN"},
    {"make": "Hyundai", "file": "hyundai_2015_mcan.dbc",
     "bus": "MS-CAN",   "notes": "2015+ Hyundai / Kia multimedia CAN"},
    {"make": "Hyundai", "file": "hyundai_i30_2014.dbc",
     "bus": "HS-CAN",   "notes": "2014 i30"},
    {"make": "Hyundai", "file": "hyundai_santafe_2007.dbc",
     "bus": "HS-CAN",   "notes": "2007 Santa Fe"},

    # ── Tesla ──
    {"make": "Tesla",   "file": "tesla_can.dbc",
     "bus": "HS-CAN",   "notes": "Tesla vehicle CAN (general)"},
    {"make": "Tesla",   "file": "tesla_model3_party.dbc",
     "bus": "HS-CAN",   "notes": "Model 3 party bus (sensor data)"},
    {"make": "Tesla",   "file": "tesla_model3_vehicle.dbc",
     "bus": "HS-CAN",   "notes": "Model 3 vehicle bus"},
    {"make": "Tesla",   "file": "tesla_powertrain.dbc",
     "bus": "HS-CAN",   "notes": "Tesla powertrain"},

    # ── Volkswagen / Audi ──
    {"make": "Volkswagen", "file": "vw_mqb.dbc",
     "bus": "HS-CAN",   "notes": "MQB platform (Golf 7/8, Tiguan, Atlas, Audi A3/Q3)"},
    {"make": "Volkswagen", "file": "vw_mqbevo.dbc",
     "bus": "HS-CAN",   "notes": "MQB Evo (2020+)"},
    {"make": "Volkswagen", "file": "vw_pq.dbc",
     "bus": "HS-CAN",   "notes": "PQ platform (legacy Golf 5/6, Passat B6/B7, Audi A4 B7)"},

    # ── GM / Chevy / Cadillac / Buick ──
    {"make": "GM",      "file": "gm_global_a_lowspeed.dbc",
     "bus": "MS-CAN",   "notes": "GM Global A platform low-speed bus"},
    {"make": "GM",      "file": "gm_global_a_chassis.dbc",
     "bus": "HS-CAN",   "notes": "GM Global A chassis"},
    {"make": "GM",      "file": "gm_global_a_powertrain_expansion.dbc",
     "bus": "HS-CAN",   "notes": "GM Global A powertrain extension"},
    {"make": "GM",      "file": "gm_global_a_high_voltage_management.dbc",
     "bus": "HS-CAN",   "notes": "GM Global A HV (Bolt EV / Volt)"},
    {"make": "Cadillac","file": "cadillac_ct6_powertrain.dbc",
     "bus": "HS-CAN",   "notes": "Cadillac CT6 PT (2016+)"},
    {"make": "Cadillac","file": "cadillac_ct6_chassis.dbc",
     "bus": "HS-CAN",   "notes": "Cadillac CT6 chassis"},

    # ── Chrysler / Jeep / Ram ──
    {"make": "Chrysler","file": "chrysler_cusw.dbc",
     "bus": "HS-CAN",   "notes": "CUSW platform — Pacifica, Renegade, Compass, etc"},
    {"make": "Chrysler","file": "chrysler_pacifica_2017_hybrid_private_fusion.dbc",
     "bus": "HS-CAN",   "notes": "2017 Pacifica Hybrid private fusion CAN"},

    # ── Mazda ──
    {"make": "Mazda",   "file": "mazda_2017.dbc",
     "bus": "HS-CAN",   "notes": "2017+ Mazda (CX-5, CX-9, Mazda 3/6)"},
    {"make": "Mazda",   "file": "mazda_3_2019.dbc",
     "bus": "HS-CAN",   "notes": "2019 Mazda 3 (4th gen)"},
    {"make": "Mazda",   "file": "mazda_rx8.dbc",
     "bus": "HS-CAN",   "notes": "RX-8"},
    {"make": "Mazda",   "file": "mazda_radar.dbc",
     "bus": "ADAS",     "notes": "Mazda radar"},

    # ── Volvo ──
    {"make": "Volvo",   "file": "volvo_v40_2017_pt.dbc",
     "bus": "HS-CAN",   "notes": "2017 V40 powertrain"},
    {"make": "Volvo",   "file": "volvo_v60_2015_pt.dbc",
     "bus": "HS-CAN",   "notes": "2015 V60 powertrain"},

    # ── Nissan ──
    {"make": "Nissan",  "file": "nissan_xterra_2011.dbc",
     "bus": "HS-CAN",   "notes": "2011 Xterra"},

    # ── Rivian ──
    {"make": "Rivian",  "file": "rivian_primary_actuator.dbc",
     "bus": "HS-CAN",   "notes": "R1T/R1S primary actuator bus"},
    {"make": "Rivian",  "file": "rivian_park_assist_can.dbc",
     "bus": "HS-CAN",   "notes": "R1T/R1S park-assist CAN"},

    # ── Acura (only Honda-family DBC publicly available; Honda proper
    # isn't in opendbc — Honda CAN reverse engineering lives in
    # openpilot's selfdrive/car as Python car-specific code) ──
    {"make": "Acura",   "file": "acura_ilx_2016_nidec.dbc",
     "bus": "HS-CAN",   "notes": "2016 Acura ILX (Honda Nidec EPS platform)"},
]


_DBC_DIR = os.path.dirname(os.path.abspath(__file__))


def file_path(name: str) -> str:
    """Resolve a DBC filename to its absolute path inside the bundle."""
    return os.path.join(_DBC_DIR, name)


def load_make(make: str) -> Optional[_dbc.Database]:
    """Merge every DBC for `make` (case-insensitive) into a single
    Database. Returns None when nothing matches."""
    targets = [c for c in CATALOG if c["make"].lower() == (make or "").lower()]
    if not targets: return None
    merged = _dbc.Database()
    for c in targets:
        try:
            d = _dbc.load_file(file_path(c["file"]))
            merged.messages.update(d.messages)
            merged.value_tables.update(d.value_tables)
        except Exception:
            continue
    return merged


def load_file(name: str) -> Optional[_dbc.Database]:
    """Load a single DBC by filename (e.g. 'ford_fusion_2018_pt.dbc')."""
    try:
        return _dbc.load_file(file_path(name))
    except FileNotFoundError:
        return None


def load_all() -> _dbc.Database:
    """Merge EVERY bundled DBC into one database. Useful for the bus
    monitor when the vehicle make isn't known yet — a CAN ID will
    still resolve as long as some DBC defines it."""
    merged = _dbc.Database()
    for c in CATALOG:
        try:
            d = _dbc.load_file(file_path(c["file"]))
            merged.messages.update(d.messages)
            merged.value_tables.update(d.value_tables)
        except Exception:
            continue
    return merged


def list_files() -> list[str]:
    return [c["file"] for c in CATALOG]


def list_makes() -> list[str]:
    seen = []
    for c in CATALOG:
        if c["make"] not in seen: seen.append(c["make"])
    return seen
