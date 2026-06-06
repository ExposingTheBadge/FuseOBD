"""Multilingual DTC description loader.

Bundled translation files (`codes_<lang>.properties`) lifted from
fr3ts0n/AndrOBD under GPL-3.0. Format: one line per DTC,
`P0001=description text` (Java .properties syntax). Empty / very
small files are skipped.

Public API:

    list_languages()                  -> list[str]      # ['de', 'fr', ...]
    load(lang)                        -> dict[str,str]  # {code: description}
    translate(code, lang)             -> str | None     # convenience lookup

The loader caches each language's parsed dict on first access. English
descriptions live in data/dtc_definitions.py — this module is for
non-English overrides only.
"""
from __future__ import annotations

import os
from typing import Optional

_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE: dict[str, dict[str, str]] = {}


def list_languages() -> list[str]:
    """Return the language codes for which we have a translation file
    with meaningful content (>1 KB; tiny stub files are excluded)."""
    out = []
    try:
        for name in sorted(os.listdir(_DIR)):
            if not name.startswith("codes_") or not name.endswith(".properties"):
                continue
            path = os.path.join(_DIR, name)
            try:
                if os.path.getsize(path) < 1024:
                    continue
            except OSError:
                continue
            out.append(name[len("codes_"):-len(".properties")])
    except OSError:
        pass
    return out


def load(lang: str) -> dict[str, str]:
    """Parse the bundled file for `lang` and return {DTC_code: description}.
    Empty dict when the language isn't bundled or the file is empty."""
    if lang in _CACHE:
        return _CACHE[lang]
    path = os.path.join(_DIR, f"codes_{lang}.properties")
    out: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                # Java .properties separator is '=' (or ':' or space) —
                # AndrOBD's files consistently use '=', so split simply.
                eq = line.find("=")
                if eq <= 0:
                    continue
                key = line[:eq].strip()
                val = line[eq + 1:].strip()
                if not key:
                    continue
                out[key] = val
    except OSError:
        pass
    _CACHE[lang] = out
    return out


def translate(code: str, lang: str) -> Optional[str]:
    """Convenience: translate a single DTC into the given language.
    Returns None when no translation is bundled or the file doesn't
    define the code."""
    return load(lang).get(code)
