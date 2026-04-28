import ctypes
import ctypes.wintypes
import sys
import os
import struct
import time
import threading

kernel32 = ctypes.windll.kernel32
ntdll = ctypes.windll.ntdll


def _is_debugger_present() -> bool:
    return bool(kernel32.IsDebuggerPresent())


def _check_remote_debugger() -> bool:
    is_debugged = ctypes.wintypes.BOOL(False)
    handle = kernel32.GetCurrentProcess()
    kernel32.CheckRemoteDebuggerPresent(handle, ctypes.byref(is_debugged))
    return bool(is_debugged.value)


def _check_nt_query_debug_port() -> bool:
    ProcessDebugPort = 7
    debug_port = ctypes.c_ulong(0)
    status = ntdll.NtQueryInformationProcess(
        kernel32.GetCurrentProcess(),
        ProcessDebugPort,
        ctypes.byref(debug_port),
        ctypes.sizeof(debug_port),
        None,
    )
    return status == 0 and debug_port.value != 0


def _check_nt_global_flag() -> bool:
    try:
        peb_offset = 0x60 if ctypes.sizeof(ctypes.c_void_p) == 8 else 0x30
        ntglobalflag_offset = 0xBC if ctypes.sizeof(ctypes.c_void_p) == 8 else 0x68

        class PEB(ctypes.Structure):
            pass

        NtCurrentPeb = ctypes.c_void_p.in_dll(ntdll, "NtCurrentTeb")
        teb_addr = ctypes.cast(NtCurrentPeb, ctypes.c_void_p).value
        if not teb_addr:
            return False

        peb_ptr = ctypes.c_void_p.from_address(teb_addr + peb_offset)
        peb_addr = peb_ptr.value
        if not peb_addr:
            return False

        flags = ctypes.c_ulong.from_address(peb_addr + ntglobalflag_offset).value
        FLG_HEAP_ENABLE_TAIL_CHECK = 0x10
        FLG_HEAP_ENABLE_FREE_CHECK = 0x20
        FLG_HEAP_VALIDATE_PARAMETERS = 0x40
        debug_flags = FLG_HEAP_ENABLE_TAIL_CHECK | FLG_HEAP_ENABLE_FREE_CHECK | FLG_HEAP_VALIDATE_PARAMETERS
        return (flags & debug_flags) != 0
    except Exception:
        return False


def _check_hardware_breakpoints() -> bool:
    CONTEXT_DEBUG_REGISTERS = 0x00010010
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        class CONTEXT64(ctypes.Structure):
            _fields_ = [("padding", ctypes.c_byte * 304), ("Dr0", ctypes.c_ulonglong),
                        ("Dr1", ctypes.c_ulonglong), ("Dr2", ctypes.c_ulonglong),
                        ("Dr3", ctypes.c_ulonglong), ("Dr6", ctypes.c_ulonglong),
                        ("Dr7", ctypes.c_ulonglong)]
        ctx = CONTEXT64()
    else:
        class CONTEXT32(ctypes.Structure):
            _fields_ = [("ContextFlags", ctypes.c_ulong), ("Dr0", ctypes.c_ulong),
                        ("Dr1", ctypes.c_ulong), ("Dr2", ctypes.c_ulong),
                        ("Dr3", ctypes.c_ulong), ("Dr6", ctypes.c_ulong),
                        ("Dr7", ctypes.c_ulong)]
        ctx = CONTEXT32()

    try:
        thread = kernel32.GetCurrentThread()
        ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS
        if kernel32.GetThreadContext(thread, ctypes.byref(ctx)):
            return any([ctx.Dr0, ctx.Dr1, ctx.Dr2, ctx.Dr3])
    except Exception:
        pass
    return False


def _check_parent_process() -> bool:
    DEBUGGERS = {
        "x64dbg.exe", "x32dbg.exe", "ollydbg.exe", "windbg.exe",
        "ida.exe", "ida64.exe", "idaq.exe", "idaq64.exe",
        "devenv.exe", "ghidra.exe", "ghidrarun.exe",
        "processhacker.exe", "procmon.exe", "procmon64.exe",
        "wireshark.exe", "fiddler.exe", "cheatengine-x86_64.exe",
        "httpdebugger.exe", "dnspy.exe", "de4dot.exe",
        "scyllahide.exe", "importrec.exe",
    }
    try:
        import subprocess
        pid = os.getpid()
        result = subprocess.run(
            ["wmic", "process", "where", f"ProcessId={pid}", "get", "ParentProcessId", "/value"],
            capture_output=True, text=True, timeout=3,
        )
        for line in result.stdout.strip().split("\n"):
            if "ParentProcessId=" in line:
                ppid = int(line.split("=")[1].strip())
                result2 = subprocess.run(
                    ["wmic", "process", "where", f"ProcessId={ppid}", "get", "Name", "/value"],
                    capture_output=True, text=True, timeout=3,
                )
                for line2 in result2.stdout.strip().split("\n"):
                    if "Name=" in line2:
                        parent_name = line2.split("=")[1].strip().lower()
                        return parent_name in DEBUGGERS
    except Exception:
        pass
    return False


def _timing_check() -> bool:
    freq = ctypes.c_longlong()
    start = ctypes.c_longlong()
    end = ctypes.c_longlong()
    kernel32.QueryPerformanceFrequency(ctypes.byref(freq))
    kernel32.QueryPerformanceCounter(ctypes.byref(start))

    total = 0
    for i in range(10000):
        total += i

    kernel32.QueryPerformanceCounter(ctypes.byref(end))
    elapsed_us = ((end.value - start.value) * 1_000_000) / freq.value
    return elapsed_us > 50_000


def _erase_pe_header():
    try:
        base = kernel32.GetModuleHandleW(None)
        if base:
            old_protect = ctypes.c_ulong()
            kernel32.VirtualProtect(base, 4096, 0x40, ctypes.byref(old_protect))
            ctypes.memset(base, 0, 4096)
            kernel32.VirtualProtect(base, 4096, old_protect.value, ctypes.byref(old_protect))
    except Exception:
        pass


def _hide_from_debugger():
    THREAD_HIDE_FROM_DEBUGGER = 0x11
    try:
        ntdll.NtSetInformationThread(
            kernel32.GetCurrentThread(),
            THREAD_HIDE_FROM_DEBUGGER,
            None,
            0,
        )
    except Exception:
        pass


_DETECTED = False


def is_tampered() -> bool:
    return _DETECTED


def _background_monitor():
    global _DETECTED
    while True:
        time.sleep(5)
        if _is_debugger_present() or _check_remote_debugger():
            _DETECTED = True
            return


def init_protection():
    global _DETECTED

    checks = [
        _is_debugger_present,
        _check_remote_debugger,
        _check_nt_query_debug_port,
        _check_hardware_breakpoints,
        _check_parent_process,
        _timing_check,
    ]

    for check in checks:
        try:
            if check():
                _DETECTED = True
                break
        except Exception:
            pass

    _hide_from_debugger()

    if getattr(sys, "frozen", False):
        _erase_pe_header()

    monitor = threading.Thread(target=_background_monitor, daemon=True)
    monitor.start()

    return not _DETECTED
