import os
import sys
import webbrowser
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QTabWidget, QStatusBar,
    QVBoxLayout, QWidget, QDialog, QLabel, QPushButton, QTextEdit, QFrame,
)

from core.j2534 import J2534
from core.vehicle import VehicleConnection
from gui.panels.connection import ConnectionPanel
from gui.panels.scanner_panel import ScannerPanel
from gui.panels.dtc_panel import DTCPanel
from gui.panels.pats_panel import PATSPanel
from gui.panels.asbuilt_panel import AsBuiltPanel
from gui.panels.monitor_panel import MonitorPanel
from gui.panels.security_panel import SecurityPanel
from gui.theme import apply_theme
from gui.qt_helpers import warn, confirm, info
from version import VERSION, VERSION_SHORT, APP_NAME, APP_DESC, BUILD
from modules.updater import check_async, UpdateInfo


AUTHOR = "Brent Gordon"
HOMEPAGE = "https://fuse-obd.com"
LICENSE_TEXT = (
    f"Fuse OBD — {APP_DESC}\n"
    f"Copyright (C) 2026 {AUTHOR}\n\n"
    "This program is free software: you can redistribute it and/or modify "
    "it under the terms of the GNU General Public License as published by "
    "the Free Software Foundation, either version 3 of the License, or "
    "(at your option) any later version.\n\n"
    "This program is distributed in the hope that it will be useful, "
    "but WITHOUT ANY WARRANTY; without even the implied warranty of "
    "MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the "
    "GNU General Public License for more details.\n\n"
    "You should have received a copy of the GNU General Public License "
    "along with this program. If not, see <https://www.gnu.org/licenses/>.\n\n"
    "This program incorporates PyQt6, which is licensed under the GNU GPL v3. "
    "The full GPL-3.0 text is bundled with this application in the LICENSE file."
)


def _resource_path(name: str) -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", name)


class FuseMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION} — {APP_DESC}")
        self.resize(1200, 750)
        self.setMinimumSize(900, 600)

        icon_path = _resource_path("fuse.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.vehicle: Optional[VehicleConnection] = None

        self._build_menu()
        self._build_ui()

        # Silent auto-update check on startup
        QTimer.singleShot(1500, self._auto_check_updates)

    # ── Menu ──

    def _build_menu(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        act_check = QAction("Check for Updates", self)
        act_check.triggered.connect(self._manual_check_updates)
        file_menu.addAction(act_check)
        file_menu.addSeparator()
        act_exit = QAction("Exit", self)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        view_menu = mb.addMenu("&View")
        act_dark = QAction("Dark Theme", self)
        act_dark.triggered.connect(lambda: self._set_theme("dark"))
        view_menu.addAction(act_dark)
        act_light = QAction("Light Theme", self)
        act_light.triggered.connect(lambda: self._set_theme("light"))
        view_menu.addAction(act_light)

        help_menu = mb.addMenu("&Help")
        act_about = QAction("About Fuse OBD", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)
        act_lic = QAction("License", self)
        act_lic.triggered.connect(self._show_license)
        help_menu.addAction(act_lic)
        help_menu.addSeparator()
        act_web = QAction("Visit Website", self)
        act_web.triggered.connect(lambda: webbrowser.open(HOMEPAGE))
        help_menu.addAction(act_web)

    # ── Layout ──

    def _build_ui(self):
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 5)
        layout.setSpacing(6)

        self.conn_panel = ConnectionPanel(
            self, on_connect=self._on_connect, on_disconnect=self._on_disconnect,
        )
        layout.addWidget(self.conn_panel)

        self.notebook = QTabWidget(self)
        self.scanner_panel = ScannerPanel(self.notebook, self._get_vehicle)
        self.dtc_panel = DTCPanel(self.notebook, self._get_vehicle)
        self.pats_panel = PATSPanel(self.notebook, self._get_vehicle)
        self.asbuilt_panel = AsBuiltPanel(self.notebook, self._get_vehicle)
        self.monitor_panel = MonitorPanel(self.notebook, self._get_vehicle)
        self.security_panel = SecurityPanel(self.notebook, self._get_vehicle)

        self.notebook.addTab(self.scanner_panel, "  Scanner  ")
        self.notebook.addTab(self.dtc_panel, "  Faults  ")
        self.notebook.addTab(self.pats_panel, "  Program Keys  ")
        self.notebook.addTab(self.asbuilt_panel, "  Factory Settings  ")
        self.notebook.addTab(self.monitor_panel, "  Live Data  ")
        self.notebook.addTab(self.security_panel, "  Security Access  ")

        layout.addWidget(self.notebook, stretch=1)
        self.setCentralWidget(central)

        self.global_status = QLabel(f"{APP_NAME} v{VERSION} — Free and open source (GPL-3.0)")
        status_bar = QStatusBar(self)
        status_bar.addWidget(self.global_status, 1)
        self.setStatusBar(status_bar)

    # ── Connection callbacks ──

    def _on_connect(self, j2534: J2534):
        self.vehicle = VehicleConnection(j2534)
        hs_ok = ms_ok = False
        try:
            self.vehicle.connect_hs_can()
            hs_ok = True
        except Exception as e:
            warn(self, "HS CAN", f"Could not open HS CAN: {e}")
        try:
            self.vehicle.connect_ms_can()
            ms_ok = True
        except Exception as e:
            warn(self, "MS CAN", f"Could not open MS CAN: {e}")

        # Verify communication by reading VIN
        try:
            vin = self.vehicle.read_vin()
            if vin and len(vin) == 17:
                self.global_status.setText(f"Connected — VIN: {vin}")
            else:
                self.global_status.setText("Connected — Vehicle not responding (check ignition is ON)")
                warn(self, "No Response",
                     "Adapter connected but vehicle is not responding.\n\n"
                     "Make sure:\n"
                     "  • Ignition is ON (engine running for full scan)\n"
                     "  • OBD connector is fully seated\n"
                     "  • HS-CAN pins (6 & 14) are functional\n\n"
                     "The adapter itself is working — the car isn't talking back.")
        except Exception:
            tag = " ".join(filter(None, [
                "HS-CAN" if hs_ok else "",
                "MS-CAN" if ms_ok else "",
            ])).strip()
            if tag:
                self.global_status.setText(f"Connected ({tag}) — VIN read failed")
            else:
                self.global_status.setText("Connected — no CAN channels available")

        # Enable AI Mechanic button now that vehicle is connected
        self.dtc_panel.ai_btn.setEnabled(True)

    def _on_disconnect(self):
        self.monitor_panel.stop_monitor()
        if self.vehicle:
            self.vehicle.disconnect_all()
            self.vehicle = None
        self.global_status.setText(f"{APP_NAME} v{VERSION} — Disconnected")

    def _get_vehicle(self) -> Optional[VehicleConnection]:
        if not self.vehicle:
            warn(self, "Not Connected", "Connect to a vehicle first")
            return None
        return self.vehicle

    # ── Theme ──

    def _set_theme(self, name: str):
        apply_theme(QApplication.instance(), name)

    # ── Updates ──

    def _auto_check_updates(self):
        check_async(VERSION_SHORT, BUILD,
                    lambda i: QTimer.singleShot(0, lambda: self._on_update_result(i)))

    def _manual_check_updates(self):
        self.global_status.setText("Checking for updates...")
        check_async(VERSION_SHORT, BUILD,
                    lambda i: QTimer.singleShot(0, lambda: self._on_manual_result(i)))

    def _on_update_result(self, i: UpdateInfo):
        if i.available:
            self._show_update_dialog(i)

    def _on_manual_result(self, i: UpdateInfo):
        if i.error:
            self.global_status.setText(f"Update check failed: {i.error}")
            info(self, "Update Check",
                 f"Could not reach the update server.\n\n{i.error}\n\n"
                 "Check your internet connection and try again, or visit\n"
                 f"{HOMEPAGE} to download the latest version.")
        elif i.available:
            self._show_update_dialog(i)
        else:
            self.global_status.setText(f"Fuse OBD is up to date (v{VERSION})")
            info(self, "Update Check",
                 f"You're running the latest version of {APP_NAME}.\n\n"
                 f"Current: v{VERSION}\nLatest: v{i.latest_version}\n\n"
                 f"Released: {i.release_date}")

    def _show_update_dialog(self, i: UpdateInfo):
        self.global_status.setText(
            f"Update available: v{i.latest_version} (you have v{VERSION})"
        )
        mandatory = "\n\nThis is a MANDATORY update." if i.mandatory else ""
        if confirm(self, "Update Available",
                   f"A new version of {APP_NAME} is available!\n\n"
                   f"Your version: v{VERSION}\n"
                   f"Latest version: v{i.latest_version}\n"
                   f"Released: {i.release_date} ({i.size_mb} MB)\n\n"
                   f"{i.release_notes}{mandatory}\n\n"
                   "Would you like to visit the download page?"):
            webbrowser.open(i.download_url or HOMEPAGE)

    # ── About / License dialogs ──

    def _show_about(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"About {APP_NAME}")
        dlg.setFixedSize(420, 380)

        v = QVBoxLayout(dlg)
        v.setContentsMargins(20, 20, 20, 15)

        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 24pt; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)

        subtitle = QLabel(APP_DESC)
        subtitle.setStyleSheet("font-size: 11pt;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(subtitle)

        ver = QLabel(f"Version {VERSION}")
        ver.setStyleSheet("color: gray;")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(ver)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        v.addWidget(sep)

        creator = QLabel(f"Created by {AUTHOR}")
        creator.setStyleSheet("font-size: 12pt; font-weight: bold;")
        creator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(creator)

        lic = QLabel("Free and open source — GNU GPL v3")
        lic.setStyleSheet("color: #2070c0;")
        lic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(lic)

        features = QLabel(
            "Module Scanner  |  Fault Reader/Clear  |  AI Mechanic Chat\n"
            "Key Programming (PATS)  |  Factory Settings Read/Write\n"
            "Live PID Monitor  |  Security Access  |  VIN Decoder\n\n"
            "No licensing. No subscriptions. No limits."
        )
        features.setStyleSheet("color: gray;")
        features.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(features)

        website = QLabel(f'<a href="{HOMEPAGE}" style="color:#4488ff;">{HOMEPAGE}</a>')
        website.setAlignment(Qt.AlignmentFlag.AlignCenter)
        website.setOpenExternalLinks(True)
        v.addWidget(website)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        close_btn.setFixedWidth(100)
        btn_row = QVBoxLayout()
        btn_row.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        v.addLayout(btn_row)

        dlg.exec()

    def _show_license(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("License — Fuse OBD")
        dlg.resize(550, 400)
        v = QVBoxLayout(dlg)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(LICENSE_TEXT)
        text.setStyleSheet('font-family: Consolas, monospace; font-size: 9pt;')
        v.addWidget(text)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        close_btn.setFixedWidth(100)
        v.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        dlg.exec()

    # ── Lifecycle ──

    def closeEvent(self, event):
        self._on_disconnect()
        super().closeEvent(event)


class MainWindow:
    """Compatibility shim so app.py keeps the same entry-point shape."""

    def __init__(self):
        self.app = QApplication.instance() or QApplication(sys.argv)
        apply_theme(self.app, "dark")
        icon_path = _resource_path("fuse.ico")
        if os.path.exists(icon_path):
            self.app.setWindowIcon(QIcon(icon_path))
        self.window = FuseMainWindow()

    def run(self):
        self.window.show()
        sys.exit(self.app.exec())
