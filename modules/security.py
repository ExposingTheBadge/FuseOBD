import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, Callable
from core.uds import UDSClient, UDSException, UDSSession, NRC
from core.vehicle import VehicleConnection
from core.protocols import FordModule, FORD_MODULES
from utils.ford_crypto import keygen_mk1, FORD_KEYBAG, FORD_MODULE_KEYS


FORD_SESSIONS = {
    "Default (0x01)": 0x01,
    "Programming (0x02)": 0x02,
    "Extended (0x03)": 0x03,
    "Standard Diag (0x81)": 0x81,
    "ECU Programming (0x85)": 0x85,
    "ECU Adjustment (0x87)": 0x87,
    "EOL Extended (0xFE)": 0xFE,
    "Supplier Specific (0xFA)": 0xFA,
}


# Recommended session per security level — many modules reject SecurityAccess
# unless they're already in an extended/programming session. This map drives
# the unlock() convenience wrapper below; callers can still override.
SECURITY_LEVEL_REQUIRED_SESSION = {
    0x01: 0x03,  # L1 read-only unlock → extended session
    0x03: 0x03,  # L2 (Ford labels it 0x03/0x04) → extended session
    0x11: 0x03,  # As-Built write → extended session
    0x13: 0x02,  # variant → programming session
    0x21: 0x02,  # programming-tier seed → programming session
    0x61: 0x02,  # supplier-specific → programming
}


class KeyAlgorithm(IntEnum):
    """Which seed→key algorithm a given module / level uses.

    UNKNOWN means "try every algorithm" (slowest). Otherwise the unlock
    routine routes directly to the right keygen — this is what keeps the
    brute-force flow tractable when a module has 30+ candidate keys."""
    UNKNOWN = 0
    MK1_LFSR = 1       # The Galois LFSR documented in utils.ford_crypto.keygen_mk1
    PATS_1_2 = 2       # PATS 1/2 outcode-incode (Ford 1996-2005)
    PATS_3   = 3       # PATS 3 — module ID mixed in
    PATS_4_5 = 4       # PATS 4/5 — S-box / extended schedule


# Map module-address (request CAN ID, e.g. 0x7E0 for PCM) -> {level: algo}.
# Modules not listed default to MK1_LFSR (the most common Ford algorithm).
MODULE_ALGORITHMS: dict[int, dict[int, KeyAlgorithm]] = {
    0x7E0: {0x01: KeyAlgorithm.MK1_LFSR, 0x03: KeyAlgorithm.MK1_LFSR},   # PCM
    0x7E1: {0x01: KeyAlgorithm.MK1_LFSR},                                # TCM
    0x720: {0x01: KeyAlgorithm.MK1_LFSR, 0x03: KeyAlgorithm.MK1_LFSR,
            0x11: KeyAlgorithm.MK1_LFSR},                                # ABS / IPC
    0x726: {0x01: KeyAlgorithm.MK1_LFSR, 0x11: KeyAlgorithm.MK1_LFSR},   # RCM / BCM
    0x727: {0x01: KeyAlgorithm.MK1_LFSR},                                # ACM
    0x731: {0x01: KeyAlgorithm.MK1_LFSR, 0x11: KeyAlgorithm.MK1_LFSR},   # DDM
    0x760: {0x01: KeyAlgorithm.MK1_LFSR, 0x03: KeyAlgorithm.MK1_LFSR,
            0x11: KeyAlgorithm.MK1_LFSR},                                # GWM
    0x767: {0x01: KeyAlgorithm.MK1_LFSR},                                # APIM (older)
    0x781: {0x01: KeyAlgorithm.MK1_LFSR},
    0x7A6: {0x01: KeyAlgorithm.MK1_LFSR, 0x11: KeyAlgorithm.MK1_LFSR},
    0x7E6: {0x01: KeyAlgorithm.MK1_LFSR},                                # SOBDM
}


# After EXCEEDED_ATTEMPTS (NRC 0x36) most Ford modules enforce a back-off
# window before they accept any further requestSeed. The window length is
# module-specific; these are conservative defaults that match observed
# behaviour. Keyed by module address.
DEFAULT_LOCKOUT_SECONDS = 10.0
MODULE_LOCKOUT_SECONDS: dict[int, float] = {
    0x7E0: 10.0,   # PCM
    0x720: 30.0,   # IPC / ABS — observed longer back-off
    0x726: 10.0,   # BCM / RCM
    0x760: 10.0,   # GWM
}


# Track lockouts in-process so the bruteforce loop doesn't keep hammering
# a module that's already in penalty time. Reset on power-cycle (which we
# can't detect from here, so the user has to clear it manually via
# clear_lockouts()).
_lockout_until: dict[int, float] = {}


def is_locked_out(module: FordModule) -> Optional[float]:
    """If the module is in a lockout window, return how many seconds remain.
    Otherwise return None."""
    req_id = 0x700 + module.address
    until = _lockout_until.get(req_id)
    if not until:
        return None
    remaining = until - time.monotonic()
    if remaining <= 0:
        _lockout_until.pop(req_id, None)
        return None
    return remaining


def clear_lockouts():
    """Forget the lockout windows — call after a power cycle / ignition cycle."""
    _lockout_until.clear()


def algorithm_for(module: FordModule, level: int) -> KeyAlgorithm:
    """Return the seed/key algorithm for this (module, level) pair, falling
    back to UNKNOWN if there's no specific entry."""
    req_id = 0x700 + module.address
    return MODULE_ALGORITHMS.get(req_id, {}).get(level, KeyAlgorithm.UNKNOWN)


@dataclass
class BruteforceResult:
    module: FordModule
    session: int
    security_level: int
    seed: int
    key_found: Optional[bytes] = None
    response: int = 0
    success: bool = False
    error: str = ""
    attempts: int = 0


class SecurityAccess:
    def __init__(self, vehicle: VehicleConnection):
        self.vehicle = vehicle

    def request_seed(self, client: UDSClient, level: int = 0x01) -> Optional[int]:
        data = client.security_access_seed(level)
        if not data or len(data) < 3:
            return None
        return (data[0] << 16) | (data[1] << 8) | data[2]

    def send_key(self, client: UDSClient, level: int, response: int) -> bool:
        key_bytes = bytes([
            (response >> 16) & 0xFF,
            (response >> 8) & 0xFF,
            response & 0xFF,
        ])
        try:
            client.security_access_key(level + 1, key_bytes)
            return True
        except UDSException as e:
            if e.nrc == NRC.INVALID_KEY:
                return False
            raise

    def try_single_key(self, client: UDSClient, level: int,
                       key: bytes) -> Optional[BruteforceResult]:
        seed = self.request_seed(client, level)
        if seed is None or seed == 0:
            return None
        response = keygen_mk1(seed, key)
        success = self.send_key(client, level, response)
        return BruteforceResult(
            module=FordModule("", "", 0, None),
            session=0, security_level=level,
            seed=seed, key_found=key if success else None,
            response=response, success=success,
        )

    def bruteforce_module(self, module: FordModule, session: int = 0x01,
                          level: int = 0x01,
                          callback: Optional[Callable] = None) -> BruteforceResult:
        result = BruteforceResult(
            module=module, session=session, security_level=level, seed=0,
        )

        # If a previous attempt blew the attempt counter, the module is in
        # a lockout window. Bail early instead of hammering it further (and
        # potentially extending the window).
        remaining = is_locked_out(module)
        if remaining is not None:
            result.error = (
                f"Module in lockout window — {remaining:.1f}s remaining. "
                f"Power-cycle the ECU (or wait it out), then call clear_lockouts()."
            )
            return result

        # If caller didn't specify a session, pick the recommended one for
        # the security level. Many modules NRC 0x33 (security access denied)
        # if you try SecurityAccess from default session.
        if session == 0x01 and level in SECURITY_LEVEL_REQUIRED_SESSION:
            session = SECURITY_LEVEL_REQUIRED_SESSION[level]
            result.session = session

        try:
            client = self.vehicle.get_uds_client(module)
            client.diagnostic_session(session)
        except UDSException as e:
            if e.nrc == NRC.CONDITIONS_NOT_CORRECT:
                result.error = "Conditions not correct for this session"
            else:
                result.error = f"Session failed: {e}"
            return result
        except Exception as e:
            result.error = str(e)
            return result

        keys_to_try = _build_key_list(module, level)

        for i, key in enumerate(keys_to_try):
            result.attempts = i + 1
            if callback:
                key_name = key.decode("ascii", errors="replace")
                callback(f"Trying key {i+1}/{len(keys_to_try)}: {key_name}")

            try:
                seed = self.request_seed(client, level)
                if seed is None:
                    result.error = "No seed returned"
                    return result
                if seed == 0:
                    result.success = True
                    result.seed = 0
                    result.key_found = b"(already unlocked)"
                    if callback:
                        callback("Module already unlocked (seed=0)")
                    return result

                result.seed = seed
                response = keygen_mk1(seed, key)
                result.response = response

                if self.send_key(client, level, response):
                    result.success = True
                    result.key_found = key
                    if callback:
                        callback(f"KEY FOUND: {key.decode('ascii', errors='replace')}")
                    return result

            except UDSException as e:
                if e.nrc == NRC.CONDITIONS_NOT_CORRECT:
                    result.error = "Conditions not correct — module rejected request"
                    return result
                if e.nrc == NRC.EXCEEDED_ATTEMPTS:
                    req_id = 0x700 + module.address
                    delay = MODULE_LOCKOUT_SECONDS.get(req_id, DEFAULT_LOCKOUT_SECONDS)
                    _lockout_until[req_id] = time.monotonic() + delay
                    result.error = (
                        f"Exceeded attempts — module locked for ~{delay:.0f}s. "
                        f"Subsequent calls will short-circuit until the window expires."
                    )
                    return result
                if e.nrc == NRC.TIME_DELAY_NOT_EXPIRED:
                    result.error = "Time delay active — wait and retry"
                    return result
            except Exception as e:
                result.error = f"Error on key {i+1}: {e}"
                return result

        result.error = f"No matching key found ({len(keys_to_try)} tried)"
        return result


def _build_key_list(module: FordModule, level: int) -> list[bytes]:
    keys: list[bytes] = []
    seen: set[bytes] = set()

    request_id = module.address + 0x700
    if request_id in FORD_MODULE_KEYS:
        module_keys = FORD_MODULE_KEYS[request_id]
        if level in module_keys:
            for k in module_keys[level]:
                padded = (k + b"\x00" * 5)[:5]
                if padded not in seen:
                    keys.append(padded)
                    seen.add(padded)

    for k in FORD_KEYBAG:
        padded = (k + b"\x00" * 5)[:5]
        if padded not in seen:
            keys.append(padded)
            seen.add(padded)

    return keys
