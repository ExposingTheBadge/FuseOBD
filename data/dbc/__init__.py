"""Bundled CAN DBC databases — message + signal definitions.

Each `.dbc` file in this directory was lifted from commaai/opendbc
(MIT license, see LICENSE.opendbc) and ships with the FuseOBD client
so multi-make CAN decoding works offline.

Use core.dbc.load_file() to parse a single file, or load_make()
below for the full catalog of a given manufacturer.
"""
from __future__ import annotations

import os
from typing import Optional

from core import dbc as _dbc


# ── Manifest of bundled databases ────────────────────────────────────
# Add new make/file rows here as you bundle more from opendbc.

CATALOG: list[dict] = [
    # Ford / Lincoln
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


def list_files() -> list[str]:
    return [c["file"] for c in CATALOG]


def list_makes() -> list[str]:
    seen = []
    for c in CATALOG:
        if c["make"] not in seen: seen.append(c["make"])
    return seen
