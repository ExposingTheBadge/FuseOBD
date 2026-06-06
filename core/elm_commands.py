"""ELM327 + STN extended AT/ST command catalog.

Every AT/ST command FuseOBD might send is defined here so the codebase
has ONE list to grep / maintain instead of magic strings sprinkled
across panels. Categories follow the ELM327 v2.3 datasheet
(elmelectronics.com) and the STN1xxx Family Reference Manual
(scantool.net).

These are pure constants — `core/j2534.py` and `gui/panels/bus_monitor_panel.py`
import and use them rather than rebuilding the strings inline.
"""
from __future__ import annotations


# ── ELM327 — basic control ───────────────────────────────────────────

ATD       = "ATD"        # set all defaults
ATZ       = "ATZ"        # full reset (cold boot)
ATWS      = "ATWS"       # warm start
ATBI      = "ATBI"       # bypass initialization sequence
ATRD      = "ATRD"       # read battery voltage (raw "12.3V")
ATRV      = "ATRV"       # alias for ATRD on most clones
ATI       = "ATI"        # print device identifier (e.g. "ELM327 v2.2")
ATAT      = "ATAT"       # adaptive timing control: ATAT0=off, ATAT1=norm, ATAT2=aggr
ATAT0     = "ATAT0"
ATAT1     = "ATAT1"
ATAT2     = "ATAT2"
ATL0      = "ATL0"       # linefeeds off
ATL1      = "ATL1"       # linefeeds on
ATE0      = "ATE0"       # echo off
ATE1      = "ATE1"       # echo on
ATH0      = "ATH0"       # headers off
ATH1      = "ATH1"       # headers on
ATS0      = "ATS0"       # spaces off (saves chars when parsing)
ATS1      = "ATS1"       # spaces on (more readable)
ATM0      = "ATM0"       # memory off
ATM1      = "ATM1"       # memory on
ATR0      = "ATR0"       # responses off (don't wait for ECU)
ATR1      = "ATR1"       # responses on
ATN0      = "ATN0"       # numeric responses off
ATAR      = "ATAR"       # auto-receive on
ATFE      = "ATFE"       # forget events / clear error state
ATSTFF    = "ATSTFF"     # set timeout to max (0xFF * 4 ms = ~1020 ms)
ATST      = "ATST"       # ATSTxx — set OBD response timeout, xx in hex * 4 ms

# ── Protocol selection ───────────────────────────────────────────────
# ATSPx — set protocol (auto via "0", or specific 1..C):
#   1 = J1850 PWM      (41.6 kbps) — Ford pre-CAN
#   2 = J1850 VPW      (10.4 kbps) — GM/Chrysler pre-CAN
#   3 = ISO 9141-2     (5-baud init, 10.4 kbps)
#   4 = ISO 14230-4 KWP (5-baud init)
#   5 = ISO 14230-4 KWP (fast init)
#   6 = ISO 15765-4 CAN 11-bit 500k  ← Ford / most modern
#   7 = ISO 15765-4 CAN 29-bit 500k
#   8 = ISO 15765-4 CAN 11-bit 250k
#   9 = ISO 15765-4 CAN 29-bit 250k
#   A = SAE J1939     CAN 29-bit 250k — heavy trucks
#   B = User CAN 11-bit (defined via ATPB)
#   C = User CAN 29-bit (defined via ATPB)
ATSP_AUTO    = "ATSP0"
ATSP_J1850P  = "ATSP1"
ATSP_J1850V  = "ATSP2"
ATSP_ISO9141 = "ATSP3"
ATSP_KWP_S   = "ATSP4"
ATSP_KWP_F   = "ATSP5"
ATSP_CAN11_500 = "ATSP6"
ATSP_CAN29_500 = "ATSP7"
ATSP_CAN11_250 = "ATSP8"
ATSP_CAN29_250 = "ATSP9"
ATSP_J1939     = "ATSPA"
ATSP_USER_B    = "ATSPB"
ATSP_USER_C    = "ATSPC"

ATDP   = "ATDP"      # describe current protocol (text)
ATDPN  = "ATDPN"     # describe protocol number (single hex char)

# ATPB <byte1> <byte2> — define User Protocol B parameters
#   byte1 bits: CAN baud divisor / bit-rate prescaler
#   byte2 bits: silent monitoring, normal address mode, etc.
#
# Common combinations for Ford MS-CAN @ 125 kbps via STN1170:
#   ATPB E1 01     — User B = 125 kbps CAN, normal addressing
#   ATPB D0 01     — User B = 250 kbps CAN
ATPB           = "ATPB"

# ── CAN addressing ───────────────────────────────────────────────────

# ATCAF0/1 — automatic ISO-TP formatting
ATCAF0 = "ATCAF0"   # raw frames only — required for raw bus monitor
ATCAF1 = "ATCAF1"   # auto-frame multi-byte messages with PCI bytes

ATSH   = "ATSH"     # ATSH xxx (11-bit) or ATSH xx xx xx xx (29-bit) — TX header
ATCRA  = "ATCRA"    # set CAN receive filter — accept only this ID
ATCRA_CLEAR = "ATCRA"   # ATCRA with no arg clears the filter
ATCF   = "ATCF"     # set CAN filter — ATCF xxx (11-bit) / ATCF xx xx xx xx
ATCM   = "ATCM"     # set CAN mask — works with ATCF, only matching bits compared
ATCMF  = "ATCMF"    # set CAN filter mask 11-bit (legacy alias)
ATCFC0 = "ATCFC0"   # flow control off
ATCFC1 = "ATCFC1"   # flow control on
ATFCSH = "ATFCSH"   # ATFCSH xxx — flow control header
ATFCSD = "ATFCSD"   # ATFCSD bs st — flow control data: blocksize, separation time
ATFCSM = "ATFCSM"   # ATFCSM 1 — fully formatted flow control mode

ATTA   = "ATTA"     # ATTA xx — tester address (used by Ford UDS)

# ── Monitoring ───────────────────────────────────────────────────────

ATMA    = "ATMA"    # monitor all messages (raw bus stream)
ATMR    = "ATMR"    # ATMR xx — monitor messages from this receive address
ATMT    = "ATMT"    # ATMT xx — monitor messages with this transmit ID
ATPC    = "ATPC"    # protocol close — stop monitor / disconnect

# ── ELM v2.x extras ──────────────────────────────────────────────────

ATPP    = "ATPP"    # programmable parameter manipulation (ATPP nn xx)
ATPPS   = "ATPPS"   # describe all programmable parameters

# ── STN-extended (only respond on STN-based adapters) ────────────────

STDI    = "STDI"    # device identifier
STI     = "STI"     # alias for STDI on some firmware revisions
STBR    = "STBR"    # STBR xxxxxxx — set serial UART baud (e.g. STBR 921600)
STSBR   = "STSBR"   # STSBR xxxxxxx — switch UART baud temporarily (until reset)
STBRT   = "STBRT"   # STBRT xxxx — set baud-rate timeout for STSBR
STPBR   = "STPBR"   # query current baud rate
STMA    = "STMA"    # extended monitor — like ATMA but with filters
STMSC   = "STMSC"   # set message count for STMA
STMFC   = "STMFC"   # set MFCH (multi-frame collation header)
STPRS   = "STPRS"   # STPRS xx — preset to a known-good config
STPRX   = "STPRX"   # describe current preset
STCNTO  = "STCNTO"  # set CAN read timeout
STCSR   = "STCSR"   # set CAN sample rate
STCFCP  = "STCFCP"  # CAN flow control pad (default 00..AA)
STFP    = "STFP"    # add CAN pass-filter (STFAP/STFCP for flow control)
STFAP   = "STFAP"   # add CAN ACK filter
STFAC   = "STFAC"   # clear all CAN ACK filters
STFCP   = "STFCP"   # add CAN flow-control filter
STFPC   = "STFPC"   # clear all CAN pass filters
STCMM   = "STCMM"   # CAN monitor mode: 0=normal, 1=silent
STCCP   = "STCCP"   # CAN config priority/mode
STPTOV  = "STPTOV"  # poll timeout override
STIX    = "STIX"    # I/O extras (LED brightness, ground detect)
STVR    = "STVR"    # firmware version
STSLLP  = "STSLLP"  # sleep low-power mode

# ── Composite helper: clean re-init sequence ─────────────────────────
#
# Use this as the canonical "after open or after ATZ" boot sequence.
# Each entry is sent with a short read-back wait; the order is the
# minimum that's known to leave the adapter in a clean, predictable
# state ready for ATSPx + protocol-specific config.

INIT_SEQUENCE = (
    ATZ,        # full reset
    ATE0,       # echo off
    ATL0,       # linefeeds off
    ATS0,       # spaces off (compact responses)
    ATH1,       # headers on (we need module addresses for routing)
    ATCAF0,     # auto-format off; we build ISO-TP ourselves
    ATSTFF,     # max P2 timeout — we'll dial down per-message
    ATAT1,      # adaptive timing — moderate
)


# ── Programmable parameters (ELM v1.4+ / STN) ────────────────────────
# The PP system stores persistent config across resets. Use ATPP nn xx
# to set, ATPP nn ON / ATPP nn OFF to enable/disable. Save with ATPPS.
# Most relevant for Ford:
#   PP 0F  default baud at boot (0=hardware strap, 1..255=user)
#   PP 1A  CAN auto-format default
#   PP 23  Ford MS-CAN preset enable (if available)

PP_BAUD_DEFAULT     = "0F"
PP_CAN_AUTO_FMT     = "1A"
PP_DEFAULT_PROTOCOL = "1F"   # protocol to use when ATSP0 elects
