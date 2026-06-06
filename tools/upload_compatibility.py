"""Upload data/compatibility.json to the Fuse-Web compat-manifest endpoint.

Intended to run from CI right after a successful signed release — the
manifest replaces the server's compatible_vehicles list for this
client version. Manual run is fine too.

Usage:
    python tools/upload_compatibility.py
        # uses FUSE_ACCOUNT_BASE_URL (default https://fuseobd.com)
        # and FUSE_ADMIN_TOKEN from env

Requires the admin user's session token (any admin's `fuse_session`
cookie value works) since the endpoint enforces is_admin.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILE = ROOT / "data" / "compatibility.json"
BASE_URL = os.environ.get("FUSE_ACCOUNT_BASE_URL", "https://fuseobd.com").rstrip("/")
TOKEN = os.environ.get("FUSE_ADMIN_TOKEN", "")


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FILE
    if not path.exists():
        print(f"[compat] no manifest at {path} — nothing to upload", file=sys.stderr)
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries") or []
    if not entries:
        print(f"[compat] manifest at {path} has 0 entries — skipping upload")
        return 0
    if not TOKEN:
        print("[compat] FUSE_ADMIN_TOKEN not set — refusing to call the manifest endpoint", file=sys.stderr)
        return 1
    # Stamp the client version from version.py if the manifest doesn't
    # set one explicitly — keeps each build's manifest cleanly tagged.
    if not payload.get("client_version"):
        try:
            from version import VERSION  # type: ignore[import-not-found]
            payload["client_version"] = VERSION
        except Exception:
            pass

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/compat/manifest",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN}",
            "User-Agent": f"FuseOBD-compat-uploader/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            print(f"[compat] {resp.status} {resp.read().decode('utf-8', errors='replace')}")
    except urllib.error.HTTPError as e:
        print(f"[compat] HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"[compat] upload failed: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
