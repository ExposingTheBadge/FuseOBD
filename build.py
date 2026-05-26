"""
FUSE build script — creates a single protected .exe

Usage:
    python build.py              # standard build
    python build.py --clean      # clean build artifacts first

Requirements:
    pip install pyinstaller
"""
import subprocess
import sys
import os
import shutil
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(SCRIPT_DIR, "dist")
BUILD_DIR = os.path.join(SCRIPT_DIR, "build")
SPEC_FILE = os.path.join(SCRIPT_DIR, "fuse.spec")


def clean():
    for d in [DIST_DIR, BUILD_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"Removed {d}")


def check_deps():
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def bump_build():
    version_py = os.path.join(SCRIPT_DIR, "version.py")
    with open(version_py, "r") as f:
        content = f.read()

    ns = {}
    exec(content, ns)
    major, minor, patch, build_num = ns["MAJOR"], ns["MINOR"], ns["PATCH"], ns["BUILD"]
    build_num += 1

    app_name = ns.get("APP_NAME", "Fuse OBD")
    app_desc = ns.get("APP_DESC", "Ford Utility for Scanning & Engineering")
    ver = f"{major}.{minor}.{patch}.{build_num}"
    ver_short = f"{major}.{minor}.{patch}"

    with open(version_py, "w") as f:
        f.write(f"MAJOR = {major}\n")
        f.write(f"MINOR = {minor}\n")
        f.write(f"PATCH = {patch}\n")
        f.write(f"BUILD = {build_num}\n")
        f.write(f'\nVERSION = "{ver}"\n')
        f.write(f'VERSION_SHORT = "{ver_short}"\n')
        f.write(f'\nAPP_NAME = "{app_name}"\n')
        f.write(f'APP_DESC = "{app_desc}"\n')

    version_info = os.path.join(SCRIPT_DIR, "version_info.txt")
    with open(version_info, "w") as f:
        f.write(f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, {build_num}),
    prodvers=({major}, {minor}, {patch}, {build_num}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'Brent Gordon'),
        StringStruct(u'FileDescription', u'{app_name} - {app_desc}'),
        StringStruct(u'FileVersion', u'{ver}'),
        StringStruct(u'InternalName', u'FuseOBD'),
        StringStruct(u'LegalCopyright', u'Copyright (C) 2026 Brent Gordon - GPL-3.0-or-later'),
        StringStruct(u'OriginalFilename', u'FuseOBD.exe'),
        StringStruct(u'ProductName', u'{app_name}'),
        StringStruct(u'ProductVersion', u'{ver}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
""")

    return ver


def build():
    check_deps()
    ver = bump_build()

    print(f"Building FuseOBD.exe v{ver} ...")
    print("  Runtime protection: anti-debug, anti-dump, timing checks, hw breakpoint detection")
    print("  Mode: single-file, no console, windowed traceback disabled")
    print()

    if os.path.exists(SPEC_FILE):
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--clean", "--noconfirm",
            SPEC_FILE,
        ]
    else:
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            "--noconsole",
            "--name", "FuseOBD",
            "--add-data", f"LICENSE{os.pathsep}.",
            "--hidden-import", "core",
            "--hidden-import", "core.j2534",
            "--hidden-import", "core.protocols",
            "--hidden-import", "core.uds",
            "--hidden-import", "core.vehicle",
            "--hidden-import", "modules",
            "--hidden-import", "modules.scanner",
            "--hidden-import", "modules.dtc",
            "--hidden-import", "modules.ai_diagnostics",
            "--hidden-import", "modules.ai_chat",
            "--hidden-import", "modules.issues_log",
            "--hidden-import", "modules.machine_id",
            "--hidden-import", "modules.ai_tools",
            "--hidden-import", "gui.panels.bus_monitor_panel",
            "--hidden-import", "modules.vehicle_info",
            "--hidden-import", "modules.updater",
            "--hidden-import", "modules.pats",
            "--hidden-import", "modules.asbuilt",
            "--hidden-import", "modules.pid",
            "--hidden-import", "utils",
            "--hidden-import", "utils.ford_crypto",
            "--hidden-import", "utils.protection",
            "--hidden-import", "gui",
            "--hidden-import", "gui.panels",
            "--hidden-import", "gui.panels.connection",
            "--hidden-import", "gui.panels.scanner_panel",
            "--hidden-import", "gui.panels.dtc_panel",
            "--hidden-import", "gui.panels.pats_panel",
            "--hidden-import", "gui.panels.asbuilt_panel",
            "--hidden-import", "gui.panels.monitor_panel",
            "--hidden-import", "gui.panels.security_panel",
            "--hidden-import", "gui.main_window",
            "--hidden-import", "gui.ai_mechanic_window",
            "--hidden-import", "gui.theme",
            "--hidden-import", "gui.qt_helpers",
            "--collect-submodules", "PyQt6",
            "--exclude-module", "tkinter",
            "--exclude-module", "PyQt5",
            "--exclude-module", "PySide6",
            "--clean",
            "--noconfirm",
            os.path.join(SCRIPT_DIR, "app.py"),
        ]

        icon_path = os.path.join(SCRIPT_DIR, "fuse.ico")
        if os.path.exists(icon_path):
            cmd.insert(-1, "--icon")
            cmd.insert(-1, icon_path)

        version_path = os.path.join(SCRIPT_DIR, "version_info.txt")
        if os.path.exists(version_path):
            cmd.insert(-1, "--version-file")
            cmd.insert(-1, version_path)

    subprocess.check_call(cmd, cwd=SCRIPT_DIR)

    exe_path = os.path.join(DIST_DIR, "FuseOBD.exe")
    if os.path.exists(exe_path):
        # Stamp the version into the filename for distribution.
        # Updater still finds it because it scans for any .exe asset.
        versioned_name = f"FuseOBD-v{ver}.exe"
        versioned_path = os.path.join(DIST_DIR, versioned_name)
        if os.path.exists(versioned_path):
            os.remove(versioned_path)
        os.rename(exe_path, versioned_path)
        size_mb = os.path.getsize(versioned_path) / (1024 * 1024)
        print(f"\nBuild complete: {versioned_path}")
        print(f"Size: {size_mb:.1f} MB")
    else:
        print("\nBuild may have failed — exe not found at expected path")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build FuseOBD.exe")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts first")
    args = parser.parse_args()

    if args.clean:
        clean()

    build()
