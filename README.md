# Fuse OBD — Ford Utility for Scanning & Engineering

Professional-grade Ford vehicle diagnostics, security access, and AI-powered fault analysis. Free and open source.

## Features

- **Module Scanner** — Discover all ECU modules on HS-CAN and MS-CAN buses (PCM, TCM, ABS, BCM, IPC and 15+ others)
- **Fault Code Reader & Clear** — Read DTCs from every module with active/pending/confirmed status flags
- **AI Mechanic Chat** — Powered by Claude Opus 4.7 and DeepSeek v4. Real-time mechanic diagnosis with web search for TSBs and forum fixes. Identifies root causes from cascading failure chains
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
- AI features require `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL` set in Windows system environment variables

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

Output: `dist/FuseOBD.exe`

## License

MIT License — see [LICENSE](LICENSE)

No affiliation with Ford Motor Company.
