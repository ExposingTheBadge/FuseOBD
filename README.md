# Fuse OBD — Ford Utility for Scanning & Engineering

Professional-grade Ford vehicle diagnostics, security access, and AI-powered fault analysis. Open source (GPL-3.0). Free tier covers VIN, DTC read, DTC clear, and a small AI Mechanic allowance; Pro unlocks the full toolset.

## Features

- **Module Scanner** — Discover all ECU modules on HS-CAN and MS-CAN buses (PCM, TCM, ABS, BCM, IPC and 15+ others)
- **Fault Code Reader & Clear** — Read DTCs from every module with active/pending/confirmed status flags
- **AI Mechanic** — Standalone resizable window with a professional chat UI. 30-year master diagnostician persona powered by Claude Opus 4.7. Searches the web for TSBs and forum fixes, AND self-diagnoses both the car *and* the app itself — listing Windows devices, probing for WiFi/Bluetooth/J2534 adapters, reading Fuse OBD's debug log. Maintains a persistent Issues log with two views of every finding: "plain English" and "for nerds"
- **Key Programming (PATS)** — Program new keys, erase lost keys, read key counts for Ford vehicles
- **Factory Settings (As-Built)** — Read/write vehicle configuration. Backup before changes. Enable hidden features
- **Live Data Monitor** — Real-time PID monitoring with graphing (RPM, speed, coolant temp, O2, fuel trims)
- **Security Access** — Brute-force and algorithmic security access for protected modules
- **Vehicle Info & VIN Decode** — NHTSA database lookup for year, make, model, engine, transmission, assembly plant

## Download

Download the latest `FuseOBD.exe` from [Releases](https://github.com/ExposingTheBadge/FuseOBD/releases/latest).

Windows 10/11 x64 required. No installation — just run the exe.

## Requirements

- Windows 10/11 (x64)
- J2534-compatible adapter (VCM2, VXDIAG, Tactrix, etc.)
- AI Mechanic works out of the box for end users — no API key, no environment variables, no setup. It routes through the hosted Fuse OBD service at `https://fuseobd.com` which holds the upstream LLM credentials.
- Power users / developers can override by setting `MOD_ANTHROPIC_AUTH_TOKEN` (and optionally `MOD_ANTHROPIC_BASE_URL`, `MOD_ANTHROPIC_MODEL`) in Windows env vars to bypass the hosted proxy and talk directly to their own upstream.

## Running from Source

```bash
pip install -r requirements.txt
python app.py
```

## Building

```bash
pip install pyinstaller
python build.py
```

Output: `dist/FuseOBD-v{VERSION}.exe`

## License

GNU General Public License v3.0 or later — see [LICENSE](LICENSE).

Fuse OBD links against [PyQt6](https://riverbankcomputing.com/software/pyqt/), which is licensed under the GPL v3. The combined work is distributed under the GPL v3 accordingly.

No affiliation with Ford Motor Company.
