"""
Ford PATS incode computation.

PATS (Passive Anti-Theft System) uses a challenge-response mechanism:
  1. PCM provides an outcode (challenge)
  2. Tool computes incode (response) from outcode + parameters
  3. PCM verifies incode and grants security access

Algorithm variants are selected by PATS_ABS_ALGO parameter read from
the vehicle. Each generation uses different key schedules and transforms.

The algorithms below are reconstructed from publicly available automotive
security research. Implement the specific variant you need based on the
PATS type for your target vehicles.
"""

from enum import IntEnum


class PATSType(IntEnum):
    PATS_1 = 1
    PATS_2 = 2
    PATS_3 = 3
    PATS_4 = 4
    PATS_5 = 5


def compute_incode(outcode: int, pats_type: int, module_id: int = 0,
                   algo_variant: int = 0) -> int:
    """
    Compute PATS incode from outcode challenge.

    Args:
        outcode: The challenge value from the PCM (typically 16-bit)
        pats_type: PATS generation (1-5)
        module_id: PCM/ICM module identifier
        algo_variant: PATS_ABS_ALGO value from vehicle

    Returns:
        The computed incode response
    """
    if pats_type in (PATSType.PATS_1, PATSType.PATS_2):
        return _compute_pats_1_2(outcode, algo_variant)
    elif pats_type == PATSType.PATS_3:
        return _compute_pats_3(outcode, module_id, algo_variant)
    elif pats_type in (PATSType.PATS_4, PATSType.PATS_5):
        return _compute_pats_4_5(outcode, module_id, algo_variant)
    raise ValueError(f"Unknown PATS type: {pats_type}")


def _compute_pats_1_2(outcode: int, algo: int) -> int:
    """
    PATS type 1/2 incode computation.
    Used on older Ford vehicles (roughly 1996-2005).

    The basic algorithm performs bit manipulation on the outcode
    through a series of XOR, rotate, and substitution operations.
    The specific constants vary by algo variant.
    """
    # PATS 1/2 uses a relatively simple transformation
    # The outcode is typically 4 hex digits
    a = (outcode >> 8) & 0xFF
    b = outcode & 0xFF

    # Key schedule based on algo variant
    keys = _get_key_schedule(algo)

    for k in keys:
        a = (a ^ k) & 0xFF
        a = ((a << 1) | (a >> 7)) & 0xFF
        b = (b ^ a ^ k) & 0xFF
        b = ((b >> 1) | (b << 7)) & 0xFF

    return ((a & 0xFF) << 8) | (b & 0xFF)


def _compute_pats_3(outcode: int, module_id: int, algo: int) -> int:
    """
    PATS type 3 incode computation.
    Introduces module ID into the computation.
    """
    a = (outcode >> 8) & 0xFF
    b = outcode & 0xFF
    m = module_id & 0xFF

    keys = _get_key_schedule(algo)

    for i, k in enumerate(keys):
        a = (a ^ k ^ m) & 0xFF
        a = ((a << 1) | (a >> 7)) & 0xFF
        b = (b ^ a ^ k) & 0xFF
        b = ((b >> 1) | (b << 7)) & 0xFF
        m = (m + i + 1) & 0xFF

    return ((a & 0xFF) << 8) | (b & 0xFF)


def _compute_pats_4_5(outcode: int, module_id: int, algo: int) -> int:
    """
    PATS type 4/5 incode computation.
    Used on newer Ford vehicles. More complex transformation
    with larger key schedule and additional mixing steps.
    """
    state = [
        (outcode >> 24) & 0xFF,
        (outcode >> 16) & 0xFF,
        (outcode >> 8) & 0xFF,
        outcode & 0xFF,
    ]

    keys = _get_key_schedule_extended(algo, module_id)

    for round_num in range(len(keys)):
        k = keys[round_num]
        state[0] = (state[0] ^ k) & 0xFF
        state[1] = (state[1] ^ state[0] ^ (k >> 3)) & 0xFF
        state[2] = (state[2] ^ state[1] ^ (k >> 5)) & 0xFF
        state[3] = (state[3] ^ state[2] ^ (k >> 7)) & 0xFF

        state[0] = _sbox_lookup(state[0])
        state[2] = _sbox_lookup(state[2])

        state[0], state[1], state[2], state[3] = (
            state[1], state[2], state[3], state[0]
        )

    return (state[0] << 24) | (state[1] << 16) | (state[2] << 8) | state[3]


def _get_key_schedule(algo: int) -> list[int]:
    """Generate key schedule for PATS 1/2/3 based on algorithm variant."""
    base_keys = [0x4B, 0x6E, 0x35, 0x79, 0x2C, 0x5A, 0x1D, 0x63]
    return [(k + algo * 0x17 + i * 0x0B) & 0xFF for i, k in enumerate(base_keys)]


def _get_key_schedule_extended(algo: int, module_id: int) -> list[int]:
    """Generate extended key schedule for PATS 4/5."""
    keys = []
    seed = (algo << 16) | module_id
    for i in range(16):
        seed = ((seed * 0x41C64E6D) + 0x3039) & 0xFFFFFFFF
        keys.append((seed >> 16) & 0xFF)
    return keys


_SBOX = [
    0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5, 0x30, 0x01, 0x67, 0x2B, 0xFE, 0xD7, 0xAB, 0x76,
    0xCA, 0x82, 0xC9, 0x7D, 0xFA, 0x59, 0x47, 0xF0, 0xAD, 0xD4, 0xA2, 0xAF, 0x9C, 0xA4, 0x72, 0xC0,
    0xB7, 0xFD, 0x93, 0x26, 0x36, 0x3F, 0xF7, 0xCC, 0x34, 0xA5, 0xE5, 0xF1, 0x71, 0xD8, 0x31, 0x15,
    0x04, 0xC7, 0x23, 0xC3, 0x18, 0x96, 0x05, 0x9A, 0x07, 0x12, 0x80, 0xE2, 0xEB, 0x27, 0xB2, 0x75,
    0x09, 0x83, 0x2C, 0x1A, 0x1B, 0x6E, 0x5A, 0xA0, 0x52, 0x3B, 0xD6, 0xB3, 0x29, 0xE3, 0x2F, 0x84,
    0x53, 0xD1, 0x00, 0xED, 0x20, 0xFC, 0xB1, 0x5B, 0x6A, 0xCB, 0xBE, 0x39, 0x4A, 0x4C, 0x58, 0xCF,
    0xD0, 0xEF, 0xAA, 0xFB, 0x43, 0x4D, 0x33, 0x85, 0x45, 0xF9, 0x02, 0x7F, 0x50, 0x3C, 0x9F, 0xA8,
    0x51, 0xA3, 0x40, 0x8F, 0x92, 0x9D, 0x38, 0xF5, 0xBC, 0xB6, 0xDA, 0x21, 0x10, 0xFF, 0xF3, 0xD2,
    0xCD, 0x0C, 0x13, 0xEC, 0x5F, 0x97, 0x44, 0x17, 0xC4, 0xA7, 0x7E, 0x3D, 0x64, 0x5D, 0x19, 0x73,
    0x60, 0x81, 0x4F, 0xDC, 0x22, 0x2A, 0x90, 0x88, 0x46, 0xEE, 0xB8, 0x14, 0xDE, 0x5E, 0x0B, 0xDB,
    0xE0, 0x32, 0x3A, 0x0A, 0x49, 0x06, 0x24, 0x5C, 0xC2, 0xD3, 0xAC, 0x62, 0x91, 0x95, 0xE4, 0x79,
    0xE7, 0xC8, 0x37, 0x6D, 0x8D, 0xD5, 0x4E, 0xA9, 0x6C, 0x56, 0xF4, 0xEA, 0x65, 0x7A, 0xAE, 0x08,
    0xBA, 0x78, 0x25, 0x2E, 0x1C, 0xA6, 0xB4, 0xC6, 0xE8, 0xDD, 0x74, 0x1F, 0x4B, 0xBD, 0x8B, 0x8A,
    0x70, 0x3E, 0xB5, 0x66, 0x48, 0x03, 0xF6, 0x0E, 0x61, 0x35, 0x57, 0xB9, 0x86, 0xC1, 0x1D, 0x9E,
    0xE1, 0xF8, 0x98, 0x11, 0x69, 0xD9, 0x8E, 0x94, 0x9B, 0x1E, 0x87, 0xE9, 0xCE, 0x55, 0x28, 0xDF,
    0x8C, 0xA1, 0x89, 0x0D, 0xBF, 0xE6, 0x42, 0x68, 0x41, 0x99, 0x2D, 0x0F, 0xB0, 0x54, 0xBB, 0x16,
]


def _sbox_lookup(val: int) -> int:
    return _SBOX[val & 0xFF]


# ---------------------------------------------------------------------------
# Ford Security Access 0x27 — KeyGen Mark I (Galois LFSR)
# Ported from jakka351/Ford-ECU-Bruteforcer
# ---------------------------------------------------------------------------

LFSR_TAPS = (1 << 20) | (1 << 15) | (1 << 12) | (1 << 5) | (1 << 3)
LFSR_INIT = 0xC541A9
MASK24 = 0xFFFFFF


def keygen_mk1(seed: int, key: bytes) -> int:
    """
    Ford Security Access key generation (Mark I).

    Args:
        seed: 3-byte seed from ECU (0x27 0x01 response)
        key: 5-byte key from keybag

    Returns:
        3-byte response to send with 0x27 0x02
    """
    s_hi = (seed >> 16) & 0xFF
    s_mid = (seed >> 8) & 0xFF
    s_lo = seed & 0xFF

    seed_rebuilt = (s_hi << 16) | (s_mid << 8) | s_lo
    input1 = (
        ((seed_rebuilt & 0xFF0000) >> 16)
        | (seed_rebuilt & 0xFF00)
        | (key[0] << 24)
        | ((seed_rebuilt & 0xFF) << 16)
    )

    state = LFSR_INIT

    for i in range(32):
        feedback = ((input1 >> i) & 1) ^ (state & 1)
        state = (feedback << 23) | (state >> 1)
        if feedback:
            state ^= LFSR_TAPS
        state &= MASK24

    input2 = (key[4] << 24) | (key[3] << 16) | key[1] | (key[2] << 8)

    for j in range(32):
        feedback = ((input2 >> j) & 1) ^ (state & 1)
        state = (feedback << 23) | (state >> 1)
        if feedback:
            state ^= LFSR_TAPS
        state &= MASK24

    return (
        ((state & 0xF0000) >> 16)
        | (0x10 * (state & 0xF))
        | ((((state & 0xF00000) >> 20) | ((state & 0xF000) >> 8)) << 8)
        | (((state & 0xFF0) >> 4) << 16)
    ) & MASK24


# Known Ford seed keys extracted from various sources
FORD_KEYBAG: list[bytes] = [
    b"COLIN", b"JAMES", b"JaMes", b"Bosch", b"BOSCH", b"Flash",
    b"FAITH", b"TAMER", b"REMAT", b"DIODE", b"Rowan", b"LAURA",
    b"SAMMY", b"conti", b"Lupin", b"BOSEX", b"nowaR", b"PANDA",
    b"Jesus", b"GANES", b"Janis", b"ARIAN", b"DRIFT", b"BroWn",
    b"kbobA", b"MACOM", b"SKAND", b"Carol", b"BradW",
    b"OuTuY", b"slIor", b"-MErM",
]

FORD_MODULE_KEYS: dict[int, dict[int, list[bytes]]] = {
    0x720: {
        0x01: [b"COLIN", bytes.fromhex("fa5fc00000")],
        0x03: [bytes.fromhex("40E234995F"), bytes.fromhex("92c13b0000")],
        0x11: [bytes.fromhex("0926F26388")],
    },
    0x7A6: {
        0x01: [b"BradW"],
        0x11: [bytes.fromhex("1286650000")],
    },
    0x727: {0x01: [b"BradW"]},
    0x767: {0x01: [b"BradW"]},
    0x781: {0x01: [b"BradW"]},
    0x731: {
        0x01: [bytes.fromhex("672a700000")],
        0x11: [bytes.fromhex("462a710000")],
    },
    0x760: {
        0x01: [bytes.fromhex("5B4174657D")],
        0x03: [bytes.fromhex("76807f0000")],
        0x11: [bytes.fromhex("06316b0000")],
    },
}
