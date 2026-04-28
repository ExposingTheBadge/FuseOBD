from dataclasses import dataclass
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
                if e.nrc == NRC.EXCEEDED_NUMBER_OF_ATTEMPTS:
                    result.error = "Exceeded attempts — module locked, power cycle required"
                    return result
                if e.nrc == NRC.REQUIRED_TIME_DELAY_NOT_EXPIRED:
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

    rx_id = module.address + 0x700
    if rx_id in FORD_MODULE_KEYS:
        module_keys = FORD_MODULE_KEYS[rx_id]
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
