"""Anonymous per-machine identifier for Fuse OBD.

Generated once on first run and persisted at:

    %LOCALAPPDATA%\\FuseOBD\\machine_id

The value is a random UUID4 (hex). It is sent to the hosted AI proxy
in the `x-fuse-machine-id` header so the server can rate-limit and
detect abuse without learning anything personally identifiable about
the user. It is NOT tied to hardware in any way; reinstalling Windows
or clearing %LOCALAPPDATA% yields a fresh ID.
"""
from __future__ import annotations

import os
import uuid

from modules.issues_log import _log_dir


_MACHINE_ID_CACHE: str | None = None


def _path() -> str:
    return os.path.join(_log_dir(), "machine_id")


def get_machine_id() -> str:
    global _MACHINE_ID_CACHE
    if _MACHINE_ID_CACHE:
        return _MACHINE_ID_CACHE
    p = _path()
    try:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                data = f.read().strip()
            if data:
                _MACHINE_ID_CACHE = data
                return data
    except OSError:
        pass
    mid = uuid.uuid4().hex
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write(mid)
    except OSError:
        pass
    _MACHINE_ID_CACHE = mid
    return mid
