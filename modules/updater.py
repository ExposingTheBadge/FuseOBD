"""Silent auto-update checker for Fuse OBD.
Checks GitHub Releases API for new versions. Fails silently if offline."""
import json
import ssl
import urllib.request
import urllib.error
import threading
import os

GITHUB_REPO = "ExposingTheBadge/FuseOBD"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CHECK_TIMEOUT = 5.0  # seconds — fast fail if offline


class UpdateInfo:
    def __init__(self):
        self.available = False
        self.current_version = ""
        self.latest_version = ""
        self.tag_name = ""
        self.download_url = ""
        self.release_notes = ""
        self.release_date = ""
        self.size_mb = 0
        self.file_size = 0
        self.mandatory = False
        self.error = ""


def _parse_build_from_tag(tag: str) -> int:
    """Extract build number from tag like 'v2.0.0.5' -> 5"""
    try:
        parts = tag.lstrip("v").split(".")
        if len(parts) == 4:
            return int(parts[3])
        return 0
    except (ValueError, IndexError):
        return 0


def _parse_version_short(tag: str) -> str:
    """Extract short version from tag like 'v2.0.0.5' -> '2.0.0'"""
    try:
        parts = tag.lstrip("v").split(".")
        if len(parts) >= 3:
            return f"{parts[0]}.{parts[1]}.{parts[2]}"
        return tag.lstrip("v")
    except (ValueError, IndexError):
        return tag.lstrip("v")


def _fetch_json(url: str, timeout: float = CHECK_TIMEOUT) -> dict | None | int:
    """Returns dict on success, None on network error, 404 on not found."""
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={
        "User-Agent": "FuseOBD/2.0",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            if resp.status == 404:
                return 404  # No releases exist yet
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return 404
        return None
    except Exception:
        return None


def check_for_update(current_version: str, current_build: int) -> UpdateInfo:
    """Check GitHub Releases for a newer version."""
    info = UpdateInfo()
    info.current_version = current_version

    data = _fetch_json(GITHUB_API)
    if data is None:
        info.error = "Could not reach GitHub (offline?)"
        return info
    if data == 404:
        # No releases exist yet — that's fine, nothing to update to
        info.error = ""
        return info

    tag = data.get("tag_name", "")
    info.tag_name = tag
    info.latest_version = _parse_version_short(tag)
    info.release_notes = data.get("body", "")
    info.release_date = (data.get("published_at", "") or "")[:10]

    latest_build = _parse_build_from_tag(tag)
    if latest_build > current_build:
        info.available = True

    # Find the exe asset
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if name.endswith(".exe"):
            info.download_url = asset.get("browser_download_url", "")
            info.file_size = asset.get("size", 0)
            info.size_mb = round(info.file_size / (1024 * 1024), 1)
            break

    return info


def check_async(current_version: str, current_build: int, callback: callable):
    """Non-blocking check. Calls callback(UpdateInfo) when done. Fails silently."""
    def _run():
        try:
            result = check_for_update(current_version, current_build)
        except Exception as e:
            result = UpdateInfo()
            result.error = str(e)
        callback(result)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
