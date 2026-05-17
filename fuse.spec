# -*- mode: python ; coding: utf-8 -*-
# FUSE PyInstaller spec — single-file protected exe

import os

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('LICENSE', '.'),
        ('drivers', 'drivers'),
        ('fuse.ico', '.'),
    ],
    hiddenimports=[
        'core', 'core.j2534', 'core.protocols', 'core.uds', 'core.vehicle',
        'modules', 'modules.scanner', 'modules.dtc', 'modules.ai_diagnostics', 'modules.ai_chat',
        'modules.vehicle_info', 'modules.updater', 'modules.pats',
        'anthropic', 'httpx', 'anyio', 'sniffio', 'certifi', 'h11', 'httpcore',
        'modules.asbuilt', 'modules.pid', 'modules.security',
        'utils', 'utils.ford_crypto', 'utils.protection',
        'data', 'data.dtc_definitions',
        'gui', 'gui.theme', 'gui.panels', 'gui.panels.connection',
        'gui.panels.scanner_panel', 'gui.panels.dtc_panel',
        'gui.panels.pats_panel', 'gui.panels.asbuilt_panel',
        'gui.panels.monitor_panel', 'gui.panels.security_panel',
        'gui.main_window',
        'version',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'pandas', 'scipy', 'PIL',
        'pytest', 'unittest', 'pip',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FuseOBD',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='fuse.ico' if os.path.exists('fuse.ico') else None,
    version='version_info.txt' if os.path.exists('version_info.txt') else None,
)
