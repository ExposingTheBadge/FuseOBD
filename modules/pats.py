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
}


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
        pcm.diagnostic_session(UDSSession.EXTENDED)

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
        pcm.diagnostic_session(UDSSession.EXTENDED)

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

    def program_key(self, callback=None) -> bool:
        if callback:
            callback("Reading PATS configuration...")
        self.read_pats_info()

        if self.pats_info.pats_type == -1:
            raise RuntimeError("Could not read PATS type from vehicle")

        if callback:
            callback("Requesting security access...")

        try:
            self.security_access()
        except UDSException as e:
            if e.nrc == NRC.TIME_DELAY_NOT_EXPIRED:
                delay = self.pats_info.timed_delay * 60
                if callback:
                    callback(f"Security delay active. Wait {delay}s. Cycle ignition key.")
                raise RuntimeError(
                    f"PATS security delay active. Turn ignition off, wait "
                    f"{self.pats_info.timed_delay} minutes, turn back on, try again."
                )
            raise

        if callback:
            callback("Security access granted. Starting key learn procedure...")

        pcm = self._get_pcm()

        pcm.routine_control(0xFF00, 0x01)

        if callback:
            callback(
                f"Key learn initiated. Cycle ignition with the new key within "
                f"{self.pats_info.cycle_key_time} seconds."
            )

        return True

    def erase_keys(self, callback=None) -> bool:
        if callback:
            callback("Reading PATS configuration...")
        self.read_pats_info()

        if callback:
            callback("Requesting security access for key erase...")
        self.security_access(level=0x03)

        pcm = self._get_pcm()

        if callback:
            callback("Erasing all programmed keys...")
        pcm.routine_control(0xFF01, 0x01)

        if callback:
            callback("Keys erased. You must program at least 2 new keys.")
        return True

    def read_key_count(self) -> int:
        pcm = self._get_pcm()
        try:
            pcm.diagnostic_session(UDSSession.EXTENDED)
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
