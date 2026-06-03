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

## Zig Native Layer (Planned)

The J2534 / UDS / CAN bus core is being migrated from Python ctypes to a **Zig-compiled native DLL** (`fuse_j2534.dll`). The Python GUI and AI Mechanic remain unchanged — only the hardware interface layer moves to Zig.

### Why

The current [core/j2534.py](core/j2534.py) is ~1,500 lines of `ctypes.Structure`, `c_ulong`, `POINTER`, and `byref` calls — essentially writing C through Python's FFI. This works, but has real costs:

- **Timing:** Python's garbage collector can pause mid-transaction. On a CAN bus doing UDS SecurityAccess with tight P2/P2* windows, a GC pause causes `BUSY_REPEAT` or timeout failures.
- **Safety:** ctypes offers zero compile-time guarantees about struct layouts, pointer validity, or buffer sizes. A wrong `c_ulong` vs `c_ushort` silently corrupts data.
- **Overhead:** Every J2534 call crosses the Python → C boundary via ctypes marshalling.

### Architecture

```
┌─────────────────────────┐
│   PyQt6 GUI (Python)    │  ← unchanged
├─────────────────────────┤
│   ctypes → fuse_j2534   │  ← thin bridge (much simpler than current)
├─────────────────────────┤
│   Zig J2534/UDS/CAN     │  ← NEW: compile-time safe, deterministic timing
├─────────────────────────┤
│   Vendor J2534 DLL      │  ← hardware adapter (Tactrix, VCM2, VXDIAG, etc.)
└─────────────────────────┘
```

### What Zig provides

- **Direct C ABI calls** to vendor J2534 DLLs — no ctypes marshalling overhead
- **Compile-time validated struct layouts** — `PASSTHRU_MSG`, `SCONFIG_LIST`, etc. are verified at build time
- **No GC** — deterministic timing for CAN bus operations, P1/P2 timing parameters respected precisely
- **Bounds-checked slices** — buffer overflows caught at runtime instead of silently corrupting memory
- **Single-command cross-compilation** — build x86 and x86_64 Windows targets from any platform

### Status

🔲 Scaffold `zig/` project with `build.zig`
🔲 Port J2534 protocol enums and struct definitions
🔲 Port `PassThruOpen` / `Connect` / `ReadMsgs` / `WriteMsgs` / `Disconnect` / `Close`
🔲 Port UDS session management and DTC reading
🔲 Python ctypes bridge to new DLL
🔲 Integration tests against real hardware

## License

GNU General Public License v3.0 or later — see [LICENSE](LICENSE).

Fuse OBD links against [PyQt6](https://riverbankcomputing.com/software/pyqt/), which is licensed under the GPL v3. The combined work is distributed under the GPL v3 accordingly.

No affiliation with Ford Motor Company.
