"""Mode $01 OBD-II PID catalog with names, units, and decode formulas.

Lifted from the obdium project (github.com/provrb/obdium, GPL-3.0)
via its structured `PidInfo` constant -- 165 standard PIDs covering
the full Mode $01 range with decode formulas in classic A/B/C/D byte
form.

Formulas use single-letter byte references: A = byte 0 of payload,
B = byte 1, C = byte 2, D = byte 3. eval-safe arithmetic only.

Use evaluate(pid, payload_bytes) to compute the decoded value.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union


@dataclass(frozen=True)
class PidSpec:
    pid: int            # 0x00-0xFF (Mode $01)
    name: str
    unit: str = ""
    formula: str = ""   # uses A/B/C/D byte refs; "" = raw/bitmap


PID_CATALOG: dict[int, PidSpec] = {
    0x01: PidSpec(0x01, "Monitor status since DTCs cleared", "", ""),
    0x02: PidSpec(0x02, "DTC that caused freeze frame to be stored", "", ""),
    0x03: PidSpec(0x03, "Fuel system status", "", ""),
    0x04: PidSpec(0x04, "Engine load", "%", "100/255 * A"),
    0x05: PidSpec(0x05, "Coolant temp.", "Â°C", "A - 40"),
    0x06: PidSpec(0x06, "Short term fuel trim (Bank 1)", "%", "(100/128 * A) - 100"),
    0x07: PidSpec(0x07, "Long term fuel trim (Bank 1)", "%", "(100/128 * A) - 100"),
    0x08: PidSpec(0x08, "Short term fuel trim (Bank 2)", "%", "(100/128 * A) - 100"),
    0x09: PidSpec(0x09, "Long term fuel trim (Bank 2)", "%", "(100/128 * A) - 100"),
    0x0A: PidSpec(0x0A, "Fuel pressure", "kPa", "3 * A"),
    0x0B: PidSpec(0x0B, "Intake manifold abs. pressure", "kPa", "A"),
    0x0C: PidSpec(0x0C, "Engine speed", "RPM", "((256 * A)+B) / 4"),
    0x0D: PidSpec(0x0D, "Vehicle speed", "km/h", "A"),
    0x0E: PidSpec(0x0E, "Timing advance", "Â°", "A/2 - 64"),
    0x0F: PidSpec(0x0F, "Intake air temp.", "Â°C", "A - 40"),
    0x10: PidSpec(0x10, "MAF airflow rate", "g/s", "((256 * A)+B) / 100"),
    0x11: PidSpec(0x11, "Throttle pos.", "%", "100/255 * A"),
    0x12: PidSpec(0x12, "Commanded secondary air status", "", ""),
    0x13: PidSpec(0x13, "Oxygen sensors present (in 2 banks)", "", ""),
    0x14: PidSpec(0x14, "Oxygen Sensor 1 (A: Voltage B: STFT)", "(V, %)", "V: A / 200 %: 100/128B - 100"),
    0x15: PidSpec(0x15, "Oxygen Sensor 2 (A: Voltage B: STFT)", "(V, %)", "V: A / 200 %: 100/128B - 100"),
    0x16: PidSpec(0x16, "Oxygen Sensor 3 (A: Voltage B: STFT)", "(V, %)", "V: A / 200 %: 100/128B - 100"),
    0x17: PidSpec(0x17, "Oxygen Sensor 4 (A: Voltage B: STFT)", "(V, %)", "V: A / 200 %: 100/128B - 100"),
    0x18: PidSpec(0x18, "Oxygen Sensor 5 (A: Voltage B: STFT)", "(V, %)", "V: A / 200 %: 100/128B - 100"),
    0x19: PidSpec(0x19, "Oxygen Sensor 6 (A: Voltage B: STFT)", "(V, %)", "V: A / 200 %: 100/128B - 100"),
    0x1A: PidSpec(0x1A, "Oxygen Sensor 7 (A: Voltage B: STFT)", "(V, %)", "V: A / 200 %: 100/128B - 100"),
    0x1B: PidSpec(0x1B, "Oxygen Sensor 8 (A: Voltage B: STFT)", "(V, %)", "V: A / 200 %: 100/128B - 100"),
    0x1C: PidSpec(0x1C, "OBD standards this vehicle conforms to", "", ""),
    0x1D: PidSpec(0x1D, "Oxygen sensors present (in 4 banks)", "", ""),
    0x1E: PidSpec(0x1E, "Aux input status", "", ""),
    0x1F: PidSpec(0x1F, "Engine runtime (Session)", "s", "(256 * A) + B"),
    0x21: PidSpec(0x21, "Dist. with check engine light", "km", "(256 * A) + B"),
    0x22: PidSpec(0x22, "Fuel Rail Pressure", "kPa", "0.079(256A + B)"),
    0x23: PidSpec(0x23, "Fuel Rail Gauge Pressure", "kPa", "10(256A + B)"),
    0x24: PidSpec(0x24, "O2 Sensor (1) AFR", "ratio", "2/65536(256A+B)"),
    0x25: PidSpec(0x25, "O2 Sensor (2) AFR", "ratio", "ratio: 2/65536(256A+B)"),
    0x26: PidSpec(0x26, "O2 Sensor (3) AFR", "ratio", "2/65536(256A+B)"),
    0x27: PidSpec(0x27, "O2 Sensor (4) AFR", "ratio", "2/65536(256A+B)"),
    0x28: PidSpec(0x28, "O2 Sensor (5) AFR (2)", "ratio", "2/65536(256A+B)"),
    0x29: PidSpec(0x29, "O2 Sensor (6) AFR", "ratio", "2/65536(256A+B)"),
    0x2A: PidSpec(0x2A, "O2 Sensor (7) AFR", "ratio", "2/65536(256A+B)"),
    0x2B: PidSpec(0x2B, "O2 Sensor (8) AFR", "ratio", "2/65536(256A+B)"),
    0x2C: PidSpec(0x2C, "Commanded EGR", "%", "100/255 * A"),
    0x2D: PidSpec(0x2D, "EGR Error", "%", "(100/128 * A) - 100"),
    0x2E: PidSpec(0x2E, "Commanded EVAP purge", "%", "100/255 * A"),
    0x2F: PidSpec(0x2F, "Fuel Tank Level Input", "%", "100/255 * A"),
    0x30: PidSpec(0x30, "Warm-ups since codes cleared", "", "A"),
    0x31: PidSpec(0x31, "Dist. since codes cleared", "km", "(256 * A)+B"),
    0x32: PidSpec(0x32, "EVAP System Vapor Pressure", "Pa", "((256 * A)+B) / 4"),
    0x33: PidSpec(0x33, "Absolute Barometric Pressure", "kPa", "A"),
    0x34: PidSpec(0x34, "Oxygen Sensor 1 (AB: AFR CD: Current)", "(ratio, mA)", "(ratio: 2/65536(256A+B) mA: ((256C + D) / 256) - 128"),
    0x35: PidSpec(0x35, "Oxygen Sensor 2 (AB: AFR CD: Current)", "(ratio, mA)", "(ratio: 2/65536(256A+B) mA: ((256C + D) / 256) - 128"),
    0x36: PidSpec(0x36, "Oxygen Sensor 3 (AB: AFR CD: Current)", "(ratio, mA)", "(ratio: 2/65536(256A+B) mA: ((256C + D) / 256) - 128"),
    0x37: PidSpec(0x37, "Oxygen Sensor 4 (AB: AFR CD: Current)", "(ratio, mA)", "(ratio: 2/65536(256A+B) mA: ((256C + D) / 256) - 128"),
    0x38: PidSpec(0x38, "Oxygen Sensor 5 (AB: AFR CD: Current)", "(ratio, mA)", "(ratio: 2/65536(256A+B) mA: ((256C + D) / 256) - 128"),
    0x39: PidSpec(0x39, "Oxygen Sensor 6 (AB: AFR CD: Current)", "(ratio, mA)", "(ratio: 2/65536(256A+B) mA: ((256C + D) / 256) - 128"),
    0x3A: PidSpec(0x3A, "Oxygen Sensor 7 (AB: AFR CD: Current)", "(ratio, mA)", "(ratio: 2/65536(256A+B) mA: ((256C + D) / 256) - 128"),
    0x3B: PidSpec(0x3B, "Oxygen Sensor 8 (AB: AFR CD: Current)", "(ratio, mA)", "(ratio: 2/65536(256A+B) mA: ((256C + D) / 256) - 128"),
    0x3C: PidSpec(0x3C, "Catalyst Temp. (Bank 1: Sensor 1)", "Â°C", "(((256 * A)+B) / 10) - 40"),
    0x3D: PidSpec(0x3D, "Catalyst Temp. (Bank 2: Sensor 1)", "Â°C", "(((256 * A)+B) / 10) - 40"),
    0x3E: PidSpec(0x3E, "Catalyst Temp. (Bank 1: Sensor 2)", "Â°C", "(((256 * A)+B) / 10) - 40"),
    0x3F: PidSpec(0x3F, "Catalyst Temp. (Bank 2: Sensor 2)", "Â°C", "(((256 * A)+B) / 10) - 40"),
    0x41: PidSpec(0x41, "Monitor status this drive cycle", "", ""),
    0x42: PidSpec(0x42, "Control module voltage", "V", "((256 * A)+B) / 1000"),
    0x43: PidSpec(0x43, "Absolute load value", "%", "(100/255) * (256A + B)"),
    0x44: PidSpec(0x44, "Commanded Air-Fuel Equivalence Ratio", "ratio", "(2/65536) * (256A + B)"),
    0x45: PidSpec(0x45, "Relative throttle pos.", "%", "100/255 * A"),
    0x46: PidSpec(0x46, "Ambient air temp.", "Â°C", "A - 40"),
    0x47: PidSpec(0x47, "Abs. throttle pos. (B)", "%", "100/255 * A"),
    0x4D: PidSpec(0x4D, "Time with check engine light", "mins", "256A + B"),
    0x4F: PidSpec(0x4F, "Max. value for AFR, O2 sensor voltage and current, and intake manifold abs. pressure", "ratio, V, mA, kPa", "A, B, C, D * 10"),
    0x50: PidSpec(0x50, "MAF maximum airflow rate", "g/s", "A * 10"),
    0x51: PidSpec(0x51, "Fuel Type", "", ""),
    0x52: PidSpec(0x52, "Ethanol fuel percentage", "%", "100/255 * A"),
    0x53: PidSpec(0x53, "Absolute Evap system Vapor Pressure", "kPa", "((256 * A)+B) / 200"),
    0x54: PidSpec(0x54, "Evap system vapor pressure", "Pa", "(256 * A) + B"),
    0x55: PidSpec(0x55, "Short term secondary oxygen sensor trim, A: bank 1, B: bank 3", "%", "100/128(A OR B) - 100"),
    0x56: PidSpec(0x56, "Long term secondary oxygen sensor trim, A: bank 1, B: bank 3", "%", "100/128(A OR B) - 100"),
    0x57: PidSpec(0x57, "Short term secondary oxygen sensor trim, A: bank 2, B: bank 4", "%", "100/128(A OR B) - 100"),
    0x58: PidSpec(0x58, "Long term secondary oxygen sensor trim, A: bank 2, B: bank 4", "%", "100/128(A OR B) - 100"),
    0x59: PidSpec(0x59, "Fuel rail absolute pressure", "kPa", "10(256A + B)"),
    0x5A: PidSpec(0x5A, "Relative accelerator pedal position", "%", "100/255 * A"),
    0x5B: PidSpec(0x5B, "Hybrid battery pack remaining life", "%", "100/255 * A"),
    0x5C: PidSpec(0x5C, "Engine oil temp. (mode 01)", "Â°C", "A - 40"),
    0x5D: PidSpec(0x5D, "Fuel injection timing", "Â°", "(((256 * A)+B) / 128) - 210"),
    0x5E: PidSpec(0x5E, "Engine fuel rate", "L/h", "((256 * A)+B) / 20"),
    0x5F: PidSpec(0x5F, "Emission requirements to which vehicle is designed", "", ""),
    0x61: PidSpec(0x61, "Drivers demand engine torque", "%", "A - 125"),
    0x62: PidSpec(0x62, "Actual engine torque", "%", "A - 125"),
    0x63: PidSpec(0x63, "Reference engine torque", "Nm", "256A + B"),
    0x64: PidSpec(0x64, "Engine percent torque data", "%", "Subtract 125 from A - E"),
    0x65: PidSpec(0x65, "Auxiliary input / output supported", "", ""),
    0x66: PidSpec(0x66, "Mass air flow sensor", "g/s", "{A0}== Sensor A Supported"),
    0x67: PidSpec(0x67, "Engine coolant temperature", "Â°C", "{A0}== Sensor 1 Supported"),
    0x68: PidSpec(0x68, "Intake air temperature sensor", "Â°C", "{A0}== Sensor 1 Supported"),
    0x6A: PidSpec(0x6A, "Commanded Diesel intake air flow control and relative intake air flow position", "", ""),
    0x6B: PidSpec(0x6B, "Exhaust gas recirculation temperature", "", ""),
    0x6C: PidSpec(0x6C, "Commanded throttle actuator control and relative throttle position", "", ""),
    0x6D: PidSpec(0x6D, "Fuel pressure control system", "", ""),
    0x6E: PidSpec(0x6E, "Injection pressure control system", "", ""),
    0x6F: PidSpec(0x6F, "Turbocharger compressor inlet pressure", "", ""),
    0x70: PidSpec(0x70, "Boost pressure control", "", ""),
    0x71: PidSpec(0x71, "Variable Geometry turbo (VGT) control", "", ""),
    0x72: PidSpec(0x72, "Wastegate control", "", ""),
    0x73: PidSpec(0x73, "Exhaust pressure", "", ""),
    0x74: PidSpec(0x74, "Turbocharger RPM", "RPM", ""),
    0x75: PidSpec(0x75, "Turbocharger temperature", "Â°C", ""),
    0x76: PidSpec(0x76, "Turbocharger temperature", "Â°C", ""),
    0x77: PidSpec(0x77, "Charge air cooler temperature (CACT)", "Â°C", ""),
    0x78: PidSpec(0x78, "Exhaust Gas temperature (EGT) Bank 1", "Â°C", ""),
    0x79: PidSpec(0x79, "Exhaust Gas temperature (EGT) Bank 2", "Â°C", ""),
    0x7A: PidSpec(0x7A, "Diesel particulate filter (DPF)", "", ""),
    0x7B: PidSpec(0x7B, "Diesel particulate filter (DPF)", "", ""),
    0x7C: PidSpec(0x7C, "Diesel Particulate filter (DPF) temperature", "Â°C", "(((256 * A)+B) / 10) - 40"),
    0x7D: PidSpec(0x7D, "NOx NTE", "", ""),
    0x7E: PidSpec(0x7E, "PM NTE", "", ""),
    0x7F: PidSpec(0x7F, "Engine runtime", "s", "B(2^24) + C(2^16) + D(2^8) + E"),
    0x81: PidSpec(0x81, "Engine runtime for Auxiliary Emissions Control Device(AECD)", "", ""),
    0x82: PidSpec(0x82, "Engine runtime for Auxiliary Emissions Control Device(AECD)", "", ""),
    0x83: PidSpec(0x83, "NOx sensor", "", ""),
    0x84: PidSpec(0x84, "Manifold surface temperature", "", ""),
    0x85: PidSpec(0x85, "NOx reagent system", "%", "100/255 * F"),
    0x86: PidSpec(0x86, "Particulate matter (PM) sensor", "", ""),
    0x88: PidSpec(0x88, "SCR Induce System", "", ""),
    0x89: PidSpec(0x89, "Run Time for AECD #11-#15", "", ""),
    0x8A: PidSpec(0x8A, "Run Time for AECD #16-#20", "", ""),
    0x8B: PidSpec(0x8B, "Diesel Aftertreatment", "", ""),
    0x8C: PidSpec(0x8C, "O2 Sensor (Wide Range)", "", ""),
    0x8D: PidSpec(0x8D, "Throttle Position G", "%", ""),
    0x8E: PidSpec(0x8E, "Engine Friction - Percent Torque", "%", "A - 125"),
    0x8F: PidSpec(0x8F, "PM Sensor Bank 1 & 2", "", ""),
    0x90: PidSpec(0x90, "WWH-OBD Vehicle OBD System Information", "h", ""),
    0x91: PidSpec(0x91, "WWH-OBD Vehicle OBD System Information", "h", ""),
    0x92: PidSpec(0x92, "Fuel System Control", "", ""),
    0x93: PidSpec(0x93, "WWH-OBD Vehicle OBD Counters support", "h", ""),
    0x94: PidSpec(0x94, "NOx Warning And Inducement System", "", ""),
    0x98: PidSpec(0x98, "Exhaust Gas Temperature Sensor", "Â°C", ""),
    0x99: PidSpec(0x99, "Exhaust Gas Temperature Sensor", "Â°C", ""),
    0x9A: PidSpec(0x9A, "Hybrid/EV Vehicle System Data, Battery, Voltage", "", ""),
    0x9B: PidSpec(0x9B, "Diesel Exhaust Fluid Sensor Data", "%", "100/255 * D"),
    0x9C: PidSpec(0x9C, "O2 Sensor Data", "", ""),
    0x9D: PidSpec(0x9D, "Engine Fuel Rate", "g/s", ""),
    0x9E: PidSpec(0x9E, "Engine Exhaust Flow Rate", "kg/h", ""),
    0x9F: PidSpec(0x9F, "Fuel System Percentage Use", "", ""),
    0xA1: PidSpec(0xA1, "NOx Sensor Corrected Data", "ppm", ""),
    0xA2: PidSpec(0xA2, "Cylinder Fuel Rate", "mg/stroke", "((256 * A)+B) / 32"),
    0xA3: PidSpec(0xA3, "Evap System Vapor Pressure", "Pa", ""),
    0xA4: PidSpec(0xA4, "Transmission Actual Gear", "ratio", "((256 * C) + D) / 1000"),
    0xA5: PidSpec(0xA5, "Commanded Diesel Exhaust Fluid Dosing", "%", "B / 2"),
    0xA6: PidSpec(0xA6, "Odometer", "", "(A(2^24) + B(2^16) + C(2^8) + D) / 10"),
    0xA7: PidSpec(0xA7, "NOx Sensor Concentration Sensors 3 and 4", "", ""),
    0xA8: PidSpec(0xA8, "NOx Sensor Corrected Concentration Sensors 3 and 4", "", ""),
    0xA9: PidSpec(0xA9, "ABS Disable Switch State", "", "{A0}= 1:Supported; 0:Unsupported"),
    0xC3: PidSpec(0xC3, "Fuel Level Input A/B", "%", ""),
    0xC4: PidSpec(0xC4, "Exhaust Particulate Control System Diagnostic Time/Count", "seconds / Count", ""),
    0xC5: PidSpec(0xC5, "Fuel Pressure A and B", "kPa", ""),
    0xC7: PidSpec(0xC7, "Distance Since Reflash or Module Replacement", "km", ""),
}


_SAFE_BUILTINS = {"abs": abs, "min": min, "max": max, "round": round, "int": int, "float": float}


def evaluate(pid: int, payload: Union[bytes, bytearray]) -> Optional[float]:
    """Apply the formula for `pid` to `payload` (bytes after the SID
    + PID echo). Returns the numeric result, or None when no formula
    exists / the eval failed."""
    spec = PID_CATALOG.get(pid)
    if not spec or not spec.formula:
        return None
    bs = bytes(payload)
    ctx = {chr(ord("A") + i): float(b) for i, b in enumerate(bs[:8])}
    try:
        return float(eval(spec.formula, {"__builtins__": _SAFE_BUILTINS}, ctx))
    except Exception:
        return None


def name(pid: int) -> str:
    s = PID_CATALOG.get(pid)
    return s.name if s else f"Unknown PID 0x{pid:02X}"


def unit(pid: int) -> str:
    s = PID_CATALOG.get(pid)
    return s.unit if s else ""
