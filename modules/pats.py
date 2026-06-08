import struct
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional
from core.uds import UDSClient, UDSSession, UDSException, NRC
from core.vehicle import VehicleConnection
from core.protocols import FordModule, FORD_MODULES, FordNetwork
from utils.ford_crypto import compute_incode, PATSType


class PATSKeyStatus(IntEnum):
    NOT_PROGRAMMED = 0
    PROGRAMMED = 1
    UNKNOWN = -1


@dataclass
class PATSInfo:
    pats_type: int = -1
    min_keys: int = -1
    spare_key: int = -1
    master_key: int = -1
    pats_enabled: int = -1
    unlock_key: int = -1
    unlock_key_mode: int = -1
    anti_scan: int = -1
    timed_delay: int = -1
    cycle_key_time: int = 10
    reset_type: int = -1
    distributed_type: int = -1
    pcm_id: int = 0
    algo_variant: int = 0
    num_keys_programmed: int = -1
    key_slots: list[int] = field(default_factory=list)


PATS_DIDS = {
    "MIN_KEYS": 0x6100,
    "PATS_TYPE": 0x6101,
    "SPAREKEY": 0x6102,
    "TIMEDLAY": 0x6103,
    "UNL_KEY": 0x6104,
    "ANTISCAN": 0x6105,
    "MASTERKEY": 0x6106,
    "PATSENABL": 0x6107,
    "PCMID": 0x6108,
    "PATS_ABS_ALGO": 0x6120,
    "NUM_KEYS": 0x6130,
    # Newer PATS / SecuriLock variants expose additional info DIDs.
    # These are tried opportunistically — modules that don't support them
    # return NRC 0x31 and we move on.
    "KEY_SERIAL_BASE": 0x6131,     # first programmed key transponder serial
    "VEHICLE_AUTH_CODE": 0x6140,   # IDS Authentication Code on later platforms
    "PATS_FLAGS": 0x6150,          # bit-packed: bit0=disabled, bit1=securilock, ...
}


# Routine IDs for PATS operations (UDS 0x31 RoutineControl).
#
# Historically these were inlined Ford-specific magic values; they're
# kept here for backward-compat callers but cross-referenced against
# the canonical UDS routine catalog in data/uds_routines.py. The
# Ford-canonical routine IDs (0xB001 family) ARE distinct from the
# ISO-reserved 0xFF00 family — Ford modules accept both depending on
# firmware vintage. We fall back to the 0xFF00 set when the catalog's
# B-series isn't accepted.
PATS_ROUTINES = {
    "PROGRAM_KEY":  0xFF00,
    "ERASE_KEYS":   0xFF01,
    "PARITY_CHECK": 0xFF02,
    "VERIFY_KEY":   0xFF03,
}


def _routine_spec(routine_id: int):
    """Lazy lookup against the central catalog so the PATS panel can
    show 'B001 — PATS Begin Key Learn (security required)' instead of
    a bare hex constant. Returns None when the catalog doesn't have it
    (e.g. for the legacy 0xFF00 family)."""
    try:
        from data.uds_routines import lookup
        return lookup(routine_id)
    except Exception:
        return None


def is_destructive_routine(routine_id: int) -> bool:
    """Hook the PATS panel calls before invoking a routine — returns
    True for anything the catalog flags as destructive (key erase,
    flash erase, etc) so the UI can require an explicit confirm
    dialog."""
    try:
        from data.uds_routines import is_destructive
        return is_destructive(routine_id)
    except Exception:
        return False


def _try_extended(client: UDSClient) -> bool:
    """Walk Ford-aware session subfunctions in priority order; return
    True on first acceptance, False if every subfunction NRCs. Failure
    is non-fatal — pre-2008 CD3 / U-platform modules NRC all standard
    DSC subfunctions but still answer $22 reads in the implicit
    default session.
    """
    for s in (UDSSession.EXTENDED, UDSSession.FORD_DIAG,
              UDSSession.FORD_LEGACY_C0, UDSSession.FORD_LEGACY_81,
              UDSSession.DEFAULT):
        try:
            client.diagnostic_session(s)
            return True
        except (UDSException, TimeoutError):
            continue
        except Exception:
            continue
    return False


class PATSError(RuntimeError):
    """Raised for PATS-specific failures — wraps NRCs in human terms."""


class PATSConsentRequired(PATSError):
    """Raised by destructive PATS operations when the caller did not pass
    `confirm=True`. The intent is to make 'accidentally erased all keys' a
    multi-step mistake instead of a one-call mistake — see erase_keys()."""


class PATSManager:
    def __init__(self, vehicle: VehicleConnection):
        self.vehicle = vehicle
        self.pats_info = PATSInfo()
        self._pcm_client: Optional[UDSClient] = None
        self._icm_client: Optional[UDSClient] = None

    def _get_pcm(self) -> UDSClient:
        if self._pcm_client is None:
            for m in FORD_MODULES:
                if m.abbreviation == "PCM":
                    self._pcm_client = self.vehicle.get_uds_client(m)
                    break
        return self._pcm_client

    def _get_icm(self) -> Optional[UDSClient]:
        if self._icm_client is None:
            for m in FORD_MODULES:
                if m.abbreviation == "IPC":
                    try:
                        self._icm_client = self.vehicle.get_uds_client(m)
                    except Exception:
                        pass
                    break
        return self._icm_client

    def read_pats_info(self) -> PATSInfo:
        pcm = self._get_pcm()
        # CD3-era PCMs NRC standard UDS DSC (7F 10 11/12) but still
        # answer $22 DID reads in the implicit default session. Best-
        # effort the session change and proceed regardless — the DID
        # reads below all have their own try/except.
        _try_extended(pcm)

        info = PATSInfo()

        param_map = [
            ("MIN_KEYS", "min_keys"),
            ("PATS_TYPE", "pats_type"),
            ("SPAREKEY", "spare_key"),
            ("TIMEDLAY", "timed_delay"),
            ("UNL_KEY", "unlock_key"),
            ("ANTISCAN", "anti_scan"),
            ("MASTERKEY", "master_key"),
            ("PATSENABL", "pats_enabled"),
        ]

        for did_name, attr_name in param_map:
            try:
                did = PATS_DIDS[did_name]
                data = pcm.read_data_by_id(did)
                if data:
                    value = int.from_bytes(data[:min(4, len(data))], "big")
                    setattr(info, attr_name, value)
            except (UDSException, TimeoutError):
                pass

        try:
            data = pcm.read_data_by_id(PATS_DIDS["PCMID"])
            if data:
                info.pcm_id = int.from_bytes(data[:min(4, len(data))], "big")
        except (UDSException, TimeoutError):
            pass

        try:
            data = pcm.read_data_by_id(PATS_DIDS["PATS_ABS_ALGO"])
            if data:
                info.algo_variant = int.from_bytes(data[:min(4, len(data))], "big")
        except (UDSException, TimeoutError):
            pass

        try:
            data = pcm.read_data_by_id(PATS_DIDS["NUM_KEYS"])
            if data:
                info.num_keys_programmed = int.from_bytes(data[:min(4, len(data))], "big")
        except (UDSException, TimeoutError):
            pass

        if info.timed_delay == 0:
            info.timed_delay = 10

        if info.master_key == -1 and info.pats_enabled != -1:
            info.master_key = info.pats_enabled

        self.pats_info = info
        return info

    def security_access(self, level: int = 0x01) -> bool:
        pcm = self._get_pcm()
        _try_extended(pcm)

        seed_data = pcm.security_access_seed(level)
        if not seed_data or all(b == 0 for b in seed_data):
            return True

        outcode = int.from_bytes(seed_data[:min(4, len(seed_data))], "big")
        incode = compute_incode(
            outcode,
            self.pats_info.pats_type if self.pats_info.pats_type > 0 else PATSType.PATS_3,
            self.pats_info.pcm_id,
            self.pats_info.algo_variant,
        )

        key_bytes = incode.to_bytes(
            max(2, (incode.bit_length() + 7) // 8), "big"
        )
        pcm.security_access_key(level + 1, key_bytes)
        return True

    def program_key(self, callback=None, confirm: bool = False,
                    timeout_seconds: int = 30) -> bool:
        """Add a new key to the PATS keypool.

        `confirm=True` must be passed explicitly — guards against accidental
        invocation. After the key-learn routine fires, polls NUM_KEYS for up
        to `timeout_seconds` to detect when the new key joins the pool.
        """
        if not confirm:
            raise PATSConsentRequired(
                "program_key() is a destructive PATS operation. Re-call with "
                "confirm=True after confirming with the user. Make sure the "
                "new key transponder is physically ready before confirming."
            )
        if callback:
            callback("Reading PATS configuration...")
        self.read_pats_info()

        if self.pats_info.pats_type == -1:
            raise PATSError("Could not read PATS type from vehicle")

        if callback:
            callback("Requesting security access...")

        try:
            self.security_access()
        except UDSException as e:
            if e.nrc == NRC.TIME_DELAY_NOT_EXPIRED:
                delay = self.pats_info.timed_delay * 60
                if callback:
                    callback(f"Security delay active. Wait {delay}s. Cycle ignition key.")
                raise PATSError(
                    f"PATS security delay active. Turn ignition off, wait "
                    f"{self.pats_info.timed_delay} minutes, turn back on, try again."
                )
            raise

        if callback:
            callback("Security access granted. Starting key learn procedure...")

        pcm = self._get_pcm()
        before = self.read_key_count()
        pcm.routine_control(PATS_ROUTINES["PROGRAM_KEY"], 0x01)

        if callback:
            callback(
                f"Key learn initiated. Cycle ignition with the new key within "
                f"{self.pats_info.cycle_key_time} seconds."
            )

        # Poll NUM_KEYS to see when the new key actually shows up. PATS
        # routines fire-and-forget — there's no positive completion signal
        # other than the count incrementing.
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            time.sleep(1.0)
            current = self.read_key_count()
            if current >= 0 and before >= 0 and current > before:
                if callback:
                    callback(f"Key programmed. NUM_KEYS = {current}")
                return True
            if callback:
                callback(f"Waiting for key learn… ({int(deadline - time.monotonic())}s remaining)")

        if callback:
            callback("Key-learn poll timed out — the new key may still be valid "
                     "if the cycle was completed late. Re-read NUM_KEYS to confirm.")
        return False

    def erase_keys(self, callback=None, confirm: bool = False) -> bool:
        """Erase ALL programmed keys from the keypool — vehicle will not start
        without re-programming at least two new keys afterward.

        `confirm=True` must be passed explicitly. Safety rails:
          - won't run if PATS isn't enabled (no point)
          - won't run if there are fewer keys than min_keys (already locked
            out, escalating only makes it worse)
        """
        if not confirm:
            raise PATSConsentRequired(
                "erase_keys() will WIPE every programmed key. The vehicle will "
                "not start until you program at least min_keys new keys. "
                "Re-call with confirm=True only after the user has confirmed "
                "this destructive operation."
            )
        if callback:
            callback("Reading PATS configuration...")
        self.read_pats_info()

        if self.pats_info.pats_enabled == 0:
            raise PATSError("PATS is disabled — erase_keys() is a no-op and not run.")
        before = self.pats_info.num_keys_programmed
        if 0 <= before < max(2, self.pats_info.min_keys):
            raise PATSError(
                f"Refusing to erase: vehicle already has fewer keys ({before}) "
                f"than min_keys ({self.pats_info.min_keys}). Programming a key "
                f"first is the recovery path; erasing makes the lockout worse."
            )

        if callback:
            callback("Requesting security access for key erase...")
        self.security_access(level=0x03)

        pcm = self._get_pcm()

        if callback:
            callback("Erasing all programmed keys...")
        pcm.routine_control(PATS_ROUTINES["ERASE_KEYS"], 0x01)

        if callback:
            callback("Keys erased. You must program at least 2 new keys before "
                     "the engine will start.")
        return True

    def test_challenge(self, outcode: int) -> int:
        """Diagnostic helper: compute the incode for a given outcode using
        the currently-read PATS type + algo + module ID. Doesn't touch the
        vehicle — purely a local calculation for verifying our algorithm
        against a known good outcode/incode pair from another tool."""
        if self.pats_info.pats_type == -1:
            self.read_pats_info()
        if self.pats_info.pats_type == -1:
            raise PATSError("Cannot test challenge — PATS type unknown")
        return compute_incode(
            outcode,
            self.pats_info.pats_type,
            self.pats_info.pcm_id,
            self.pats_info.algo_variant,
        )

    def read_key_count(self) -> int:
        pcm = self._get_pcm()
        _try_extended(pcm)
        try:
            data = pcm.read_data_by_id(PATS_DIDS["NUM_KEYS"])
            if data:
                return int.from_bytes(data[:min(4, len(data))], "big")
        except (UDSException, TimeoutError):
            pass
        return -1

    @staticmethod
    def pats_type_name(pats_type: int) -> str:
        names = {
            1: "PATS I (1996-2000)",
            2: "PATS II (2000-2005)",
            3: "PATS III (2005-2010)",
            4: "PATS IV (2010-2018)",
            5: "PATS V (2018+)",
        }
        return names.get(pats_type, f"Unknown ({pats_type})")
