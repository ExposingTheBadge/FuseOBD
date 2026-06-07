import os
import sys
import webbrowser
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QTabWidget, QStatusBar,
    QVBoxLayout, QHBoxLayout, QWidget, QDialog, QLabel, QPushButton,
    QTextEdit, QFrame,
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
from gui.panels.bus_monitor_panel import BusMonitorPanel
from gui.panels.account_panel import AccountPanel
from gui.theme import apply_theme, load_preferred_theme, current_theme, toggle_theme
from gui.qt_helpers import warn, confirm, info
from gui.ai_mechanic_window import AIMechanicWindow
from gui.auth_dialog import AuthDialog
from version import VERSION, VERSION_SHORT, APP_NAME, APP_DESC, BUILD
from modules.updater import check_async, UpdateInfo
from modules import issues_log
from modules import account
from modules.vehicle_sync import sync as vehicle_sync


AUTHOR = "Brent Gordon"
HOMEPAGE = "https://fuseobd.com"
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
    # Worker threads emit this with a no-arg callable to run on the UI
    # thread (queued connection). QMainWindow has no Tk-style `after`
    # shim like BasePanel does, so we wire up the same pattern here.
    _run_in_ui = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._run_in_ui.connect(
            lambda fn: fn(),
            Qt.ConnectionType.QueuedConnection,
        )
        self.setWindowTitle(f"{APP_NAME} v{VERSION} — {APP_DESC}")
        self.resize(1200, 750)
        self.setMinimumSize(900, 600)

        icon_path = _resource_path("fuse.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.vehicle: Optional[VehicleConnection] = None
        self._ai_window: Optional[AIMechanicWindow] = None

        self._install_exception_hook()

        # Maps feature key (server-side) -> tab index in self.notebook.
        # Tabs are gated based on whether the signed-in user's tier
        # has the feature unlocked.
        self._feature_tabs: dict[str, int] = {}

        # Load any saved session token off disk and refresh /auth/me
        # in the background so the Account tab + tier-gating know the
        # current state before the user clicks anything.
        try:
            account.boot()
        except Exception as e:
            issues_log.log_app_event(f"account.boot failed: {e}")

        self._build_menu()
        self._build_ui()

        # Apply tier-gating once on startup.
        self._apply_tier_gating()

        # First-run sign-in nudge: if there's no saved session at all,
        # pop the AuthDialog (skippable) so users hit Account-aware flows
        # on the very first launch.
        QTimer.singleShot(800, self._maybe_prompt_signin)

        # Silent auto-update check on startup
        QTimer.singleShot(1500, self._auto_check_updates)

    def _install_exception_hook(self):
        """Capture uncaught exceptions into the persistent issues log so the
        AI Mechanic can read them later AND ship a crash report to the
        Fuse-Web admin triage panel via modules.error_reporter."""
        prev = sys.excepthook
        # Install the dedicated server-side error reporter (idempotent;
        # safe to call here even if other code already kicked it off).
        try:
            from modules.error_reporter import reporter
            reporter.install()
        except Exception:
            pass

        def hook(exc_type, exc, tb):
            try:
                exc.__traceback__ = tb
                issues_log.log_exception(
                    f"Unhandled {exc_type.__name__}",
                    exc,
                    kind=issues_log.KIND_APP,
                    severity=issues_log.SEVERITY_HIGH,
                    source="excepthook",
                )
            except Exception:
                pass
            if prev:
                try:
                    prev(exc_type, exc, tb)
                except Exception:
                    pass

        sys.excepthook = hook

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

        tools_menu = mb.addMenu("&Tools")
        act_ai = QAction("AI Mechanic", self)
        act_ai.setShortcut("Ctrl+M")
        act_ai.triggered.connect(self._open_ai_mechanic)
        tools_menu.addAction(act_ai)
        tools_menu.addSeparator()
        act_log = QAction("Show Issues Log Folder", self)
        act_log.triggered.connect(self._open_log_folder)
        tools_menu.addAction(act_log)

        help_menu = mb.addMenu("&Help")
        act_about = QAction("About Fuse OBD", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)
        act_lic = QAction("License", self)
        act_lic.triggered.connect(self._show_license)
        help_menu.addAction(act_lic)
        help_menu.addSeparator()
        act_bug = QAction("Report a bug…", self)
        act_bug.triggered.connect(self._open_bug_report_dialog)
        help_menu.addAction(act_bug)
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

        # Big AI Mechanic launcher — always visible & always usable, even
        # before an adapter is connected. The window can also help connect.
        self.ai_launch_btn = QPushButton("🔧  AI Mechanic")
        self.ai_launch_btn.setToolTip(
            "Open the AI Mechanic in its own resizable window.\n"
            "Works without a vehicle — it can help find an adapter, "
            "diagnose Fuse OBD itself, and walk you through fixes."
        )
        self.ai_launch_btn.setMinimumHeight(48)
        self.ai_launch_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #cc6a00;"
            "  color: white;"
            "  font-size: 13pt;"
            "  font-weight: bold;"
            "  border: 1px solid #ff8800;"
            "  border-radius: 6px;"
            "  padding: 8px 16px;"
            "}"
            "QPushButton:hover { background-color: #ff8800; }"
            "QPushButton:pressed { background-color: #aa5500; }"
        )
        self.ai_launch_btn.clicked.connect(self._open_ai_mechanic)
        layout.addWidget(self.ai_launch_btn)

        self.notebook = QTabWidget(self)
        self.scanner_panel = ScannerPanel(self.notebook, self._get_vehicle)
        self.dtc_panel = DTCPanel(self.notebook, self._get_vehicle)
        self.pats_panel = PATSPanel(self.notebook, self._get_vehicle)
        self.asbuilt_panel = AsBuiltPanel(self.notebook, self._get_vehicle)
        self.monitor_panel = MonitorPanel(self.notebook, self._get_vehicle)
        self.security_panel = SecurityPanel(self.notebook, self._get_vehicle)
        self.bus_monitor_panel = BusMonitorPanel(self.notebook)
        self.account_panel = AccountPanel(self.notebook)
        self.account_panel.state_changed.connect(self._apply_tier_gating)

        idx_scanner    = self.notebook.addTab(self.scanner_panel,     "  Scanner  ")
        idx_dtc        = self.notebook.addTab(self.dtc_panel,         "  Faults  ")
        idx_pats       = self.notebook.addTab(self.pats_panel,        "  Program Keys  ")
        idx_asbuilt    = self.notebook.addTab(self.asbuilt_panel,     "  Factory Settings  ")
        idx_monitor    = self.notebook.addTab(self.monitor_panel,     "  Live Data  ")
        idx_security   = self.notebook.addTab(self.security_panel,    "  Security Access  ")
        idx_busmon     = self.notebook.addTab(self.bus_monitor_panel, "  Bus Monitor  ")
        _idx_account   = self.notebook.addTab(self.account_panel,     "  Account  ")

        # Feature key -> tab index. Faults stays open for everyone
        # (DTC read + clear are Free-tier features).
        self._feature_tabs = {
            "module_scanner":  idx_scanner,
            "pats":            idx_pats,
            "asbuilt":         idx_asbuilt,
            "live_data":       idx_monitor,
            "security_access": idx_security,
            "bus_monitor":     idx_busmon,
        }
        # Original (unlocked) labels — used to restore after locking.
        self._tab_titles_unlocked = {
            idx: self.notebook.tabText(idx).strip()
            for idx in self._feature_tabs.values()
        }

        layout.addWidget(self.notebook, stretch=1)
        self.setCentralWidget(central)

        self.global_status = QLabel(f"{APP_NAME} v{VERSION} — Open source (GPL-3.0)")
        status_bar = QStatusBar(self)
        status_bar.addWidget(self.global_status, 1)
        self.setStatusBar(status_bar)

    # ── Connection callbacks ──

    def _on_connect(self, j2534: J2534):
        # Adapter is up; the long pole now is HS-CAN init + MS-CAN init +
        # VIN read, which can take 60-90 seconds on a non-responsive
        # vehicle (every UDS call eats its full timeout). Run it on a
        # worker so the UI stays responsive while we probe — otherwise
        # the window appears frozen and users force-quit.
        self.vehicle = VehicleConnection(j2534)
        self.global_status.setText("Connected — probing vehicle…")

        def worker():
            hs_ok = ms_ok = False
            hs_err = ms_err = None
            try:
                self.vehicle.connect_hs_can()
                hs_ok = True
            except Exception as e:
                hs_err = str(e)
            try:
                self.vehicle.connect_ms_can()
                ms_ok = True
            except Exception as e:
                ms_err = str(e)

            # Open a streaming session to the Fuse-Web server so every event
            # and PID poll from here on lands in the user's account history.
            # No-op when the user isn't signed in or the server is down.
            try:
                adapter_name = ""
                adapter_vendor = ""
                adapter_port = ""
                try:
                    dev = j2534.device
                    adapter_name = getattr(dev, "name", "") or ""
                    adapter_vendor = getattr(dev, "vendor", "") or ""
                    adapter_port = getattr(dev, "port", "") or getattr(dev, "host", "") or ""
                except Exception:
                    pass
                vehicle_sync.start_session(
                    adapter_name=adapter_name,
                    adapter_vendor=adapter_vendor,
                    adapter_port=adapter_port,
                    protocol="HS-CAN" if hs_ok else ("MS-CAN" if ms_ok else ""),
                )
            except Exception:
                pass

            vin = ""
            vin_error = False
            try:
                vin = self.vehicle.read_vin() or ""
            except Exception:
                vin_error = True

            self._run_in_ui.emit(lambda: self._on_connect_finished(
                hs_ok, ms_ok, hs_err, ms_err, vin, vin_error,
            ))

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _on_connect_finished(self, hs_ok, ms_ok, hs_err, ms_err,
                              vin, vin_error):
        """UI-thread callback invoked when the connection probe worker
        finishes. All Qt widget access (status text, dialogs) belongs here."""
        if not hs_ok and hs_err:
            warn(self, "HS CAN", f"Could not open HS CAN: {hs_err}")
        if not ms_ok and ms_err:
            warn(self, "MS CAN", f"Could not open MS CAN: {ms_err}")

        if vin and len(vin) == 17:
            self.global_status.setText(f"Connected — VIN: {vin}")
            try:
                vehicle_sync.identify_vehicle(vin)
                vehicle_sync.emit_event("vin", title=f"VIN identified: {vin}",
                                        payload={"vin": vin})
            except Exception:
                pass
        elif vin_error:
            tag = " ".join(filter(None, [
                "HS-CAN" if hs_ok else "",
                "MS-CAN" if ms_ok else "",
            ])).strip()
            if tag:
                self.global_status.setText(f"Connected ({tag}) — VIN read failed")
            else:
                self.global_status.setText("Connected — no CAN channels available")
        else:
            self.global_status.setText("Connected — Vehicle not responding (check ignition is ON)")
            warn(self, "No Response",
                 "Adapter connected but vehicle is not responding.\n\n"
                 "Make sure:\n"
                 "  • Ignition is ON (engine running for full scan)\n"
                 "  • OBD connector is fully seated\n"
                 "  • HS-CAN pins (6 & 14) are functional\n\n"
                 "The adapter itself is working — the car isn't talking back.")

    def _on_disconnect(self):
        self.monitor_panel.stop_monitor()
        if self.vehicle:
            self.vehicle.disconnect_all()
            self.vehicle = None
        try:
            vehicle_sync.end_session()
        except Exception:
            pass
        self.global_status.setText(f"{APP_NAME} v{VERSION} — Disconnected")

    def _get_vehicle(self) -> Optional[VehicleConnection]:
        if not self.vehicle:
            warn(self, "Not Connected", "Connect to a vehicle first")
            return None
        return self.vehicle

    # ── AI Mechanic ──

    def _ai_state_provider(self) -> dict:
        """Snapshot of the host app state that the AI can introspect."""
        state = {
            "vehicle_connected": self.vehicle is not None,
        }
        try:
            if self.vehicle is not None:
                state["channels"] = {
                    "hs_can": getattr(self.vehicle, "hs_can", None) is not None,
                    "ms_can": getattr(self.vehicle, "ms_can", None) is not None,
                }
        except Exception:
            pass
        try:
            conn = self.conn_panel
            state["adapter_connected"] = bool(getattr(conn, "connected", False))
            if conn.devices and conn.device_combo.currentIndex() >= 0:
                idx = conn.device_combo.currentIndex()
                if 0 <= idx < len(conn.devices):
                    d = conn.devices[idx]
                    state["selected_adapter"] = {
                        "name": d.name, "vendor": d.vendor,
                        "port": d.port, "host": d.host,
                        "is_serial": d.is_serial, "is_wifi": d.is_wifi,
                    }
        except Exception:
            pass
        try:
            state["last_vin"] = getattr(self.dtc_panel, "vehicle_info", {}).get("vin")
        except Exception:
            pass
        return state

    def _build_ai_bridge(self):
        """Build the AIToolBridge that gives the AI Mechanic read-only access.

        Scope confirmed by the user:
          - Read-only writes (no clear, no program, no As-Built write)
          - Auto-connect ONLY after explicit user confirm
          - SecurityAccess any-level allowed (reads can need it)
          - Bruteforce remains blocked
        """
        from modules.ai_tools import AIToolBridge

        def _confirm(title: str, message: str) -> bool:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle(title)
            box.setText(message)
            box.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            box.setDefaultButton(QMessageBox.StandardButton.No)
            return box.exec() == QMessageBox.StandardButton.Yes

        def _run_on_ui(fn):
            # Cross-thread invocation onto the GUI thread.
            QTimer.singleShot(0, fn)

        return AIToolBridge(
            get_vehicle=lambda: self.vehicle,
            get_j2534=lambda: getattr(self.conn_panel, "j2534", None),
            connection_panel=self.conn_panel,
            dtc_panel=self.dtc_panel,
            scanner_panel=self.scanner_panel,
            monitor_panel=self.monitor_panel,
            asbuilt_panel=self.asbuilt_panel,
            pats_panel=self.pats_panel,
            confirm=_confirm,
            run_on_ui=_run_on_ui,
        )

    def open_ai_mechanic(self, vehicle_info: Optional[dict] = None,
                         dtc_data: Optional[list] = None):
        """Public entry-point so panels can open the window with context.

        AI Mechanic requires a signed-in account so the server can enforce
        per-user quotas. If the user isn't signed in we prompt them first
        and only open the window if sign-in succeeds.
        """
        if not account.is_signed_in():
            if not self._prompt_signin_for_ai():
                return

        if self._ai_window is None:
            self._ai_window = AIMechanicWindow(
                parent_window=self,
                state_provider=self._ai_state_provider,
                tool_bridge=self._build_ai_bridge(),
                icon=self.windowIcon(),
            )
        self._ai_window.show_with_context(vehicle_info=vehicle_info, dtc_data=dtc_data)

    def _prompt_signin_for_ai(self) -> bool:
        """Show AuthDialog so the user can sign in before chatting with
        the AI Mechanic. Returns True iff the user finished signed-in."""
        dlg = AuthDialog(self)
        dlg.exec()
        self._apply_tier_gating()  # tab gating may need to change
        return account.is_signed_in()

    def _open_ai_mechanic(self):
        self.open_ai_mechanic()

    # ── Account / tier gating ──

    def _maybe_prompt_signin(self):
        """First-run nudge — show the sign-in dialog if there's no saved
        session. The user can dismiss with X if they prefer to browse
        anonymously; that just keeps the AI Mechanic locked until they
        sign in later.

        When the Fuse OBD server is unreachable we suppress the dialog
        and surface a one-shot notice instead — pushing a login form the
        user can't actually use is confusing.
        """
        try:
            if account.is_signed_in():
                return
            if not account.is_server_reachable():
                issues_log.log_app_event(
                    "sign-in nudge skipped: Fuse OBD server unreachable"
                )
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self,
                    "Fuse OBD server unavailable",
                    "Can't reach the Fuse OBD account server right now, so the "
                    "sign-in prompt has been skipped.\n\n"
                    "Free offline features (DTC read/clear, VIN, bus monitor) "
                    "still work. Try signing in from the Account tab once your "
                    "connection is back.",
                )
                return
            dlg = AuthDialog(self)
            dlg.exec()
            self._apply_tier_gating()
        except Exception as e:
            issues_log.log_app_event(f"sign-in dialog error: {e}")

    def _apply_tier_gating(self):
        """Enable Pro-only tabs only if the user's tier includes that
        feature. Free-tier users see lock icons on the locked tabs and
        a tooltip explaining the upgrade path. Also refreshes the AI
        Mechanic launch button's tooltip so users know what they'll get
        before they click."""
        try:
            anon = not account.is_signed_in()
            try:
                if anon:
                    self.ai_launch_btn.setToolTip(
                        "AI Mechanic — requires a free account.\n"
                        "Click to sign in or create one (no credit card)."
                    )
                else:
                    self.ai_launch_btn.setToolTip(
                        "Open the AI Mechanic in its own resizable window.\n"
                        "Works without a vehicle — it can help find an adapter, "
                        "diagnose Fuse OBD itself, and walk you through fixes."
                    )
            except Exception:
                pass
            for feature_key, idx in self._feature_tabs.items():
                unlocked = (not anon) and account.has_feature(feature_key)
                self.notebook.setTabEnabled(idx, unlocked)
                base = self._tab_titles_unlocked.get(idx, "")
                if unlocked:
                    self.notebook.setTabText(idx, f"  {base}  ")
                    self.notebook.setTabToolTip(idx, "")
                else:
                    self.notebook.setTabText(idx, f"  🔒 {base}  ")
                    if anon:
                        self.notebook.setTabToolTip(
                            idx, f"Sign in to use {base}. Open the Account tab to sign in."
                        )
                    else:
                        self.notebook.setTabToolTip(
                            idx, f"{base} is a Pro feature. Upgrade from the Account tab."
                        )
        except Exception as e:
            issues_log.log_app_event(f"tier-gating error: {e}")

    def _open_log_folder(self):
        from modules.issues_log import issues_log_path
        import subprocess as _sp
        folder = os.path.dirname(issues_log_path())
        try:
            if sys.platform == "win32":
                _sp.Popen(["explorer", folder])
            else:
                _sp.Popen(["xdg-open", folder])
        except Exception as e:
            info(self, "Log Folder", f"Logs are stored at:\n{folder}\n\n(Could not open: {e})")

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

        lic = QLabel("Open source — GNU GPL v3")
        lic.setStyleSheet("color: #2070c0;")
        lic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(lic)

        features = QLabel(
            "Free tier: VIN  |  DTC Read  |  DTC Clear  |  AI Mechanic (25 msgs/mo)\n"
            "Pro tier:  Scanner  |  PATS  |  As-Built  |  Live Data\n"
            "           Security Access  |  Bus Monitor  |  Unlimited AI Mechanic"
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

    def _open_bug_report_dialog(self):
        """Help → Report a bug — collect a one-paragraph description
        and ship as kind='user_report' to /api/v1/errors/submit."""
        from PyQt6.QtWidgets import QLineEdit
        dlg = QDialog(self)
        dlg.setWindowTitle("Report a bug — Fuse OBD")
        dlg.resize(560, 380)
        v = QVBoxLayout(dlg)

        lbl = QLabel(
            "Tell us what went wrong. Be as specific as you can — what you "
            "were doing, what you expected, what actually happened. The "
            "app version, OS, and recent logs are attached automatically."
        )
        lbl.setWordWrap(True)
        v.addWidget(lbl)

        title_in = QLineEdit()
        title_in.setPlaceholderText("Short title (e.g. \"crashes when reading DTCs on 2018 F-150\")")
        v.addWidget(title_in)

        body_in = QTextEdit()
        body_in.setPlaceholderText("Steps to reproduce, what you expected, what happened, anything else.")
        v.addWidget(body_in, stretch=1)

        status = QLabel("")
        status.setStyleSheet("color:#aaa; font-size:11px;")
        v.addWidget(status)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(dlg.reject)
        send = QPushButton("Send report")
        row.addWidget(cancel); row.addWidget(send)
        v.addLayout(row)

        def submit():
            title = title_in.text().strip()
            body = body_in.toPlainText().strip()
            if not title:
                status.setText("Title is required.")
                status.setStyleSheet("color:#ff6666; font-size:11px;")
                return
            send.setEnabled(False)
            status.setText("Sending…")
            try:
                from modules.error_reporter import reporter
                # Pre-pack some context the server can use to triage.
                ctx = {
                    "current_panel": getattr(self.notebook, "currentIndex",
                                              lambda: None)(),
                    "vehicle_connected": self.vehicle is not None,
                }
                reporter.report_user_bug(title, body, context=ctx)
                status.setText("Thanks — report queued. The reporter retries on its own if the network is down right now.")
                status.setStyleSheet("color:#16a34a; font-size:11px;")
                QTimer.singleShot(1800, dlg.accept)
            except Exception as e:
                status.setText(f"Couldn't queue the report: {e}")
                status.setStyleSheet("color:#ff6666; font-size:11px;")
                send.setEnabled(True)
        send.clicked.connect(submit)
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
        if self._ai_window is not None:
            try:
                self._ai_window.close()
            except Exception:
                pass
        super().closeEvent(event)


class MainWindow:
    """Compatibility shim so app.py keeps the same entry-point shape."""

    def __init__(self):
        self.app = QApplication.instance() or QApplication(sys.argv)
        apply_theme(self.app, load_preferred_theme())
        icon_path = _resource_path("fuse.ico")
        if os.path.exists(icon_path):
            self.app.setWindowIcon(QIcon(icon_path))
        self.window = FuseMainWindow()

    def run(self):
        self.window.show()
        sys.exit(self.app.exec())
