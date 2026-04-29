import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from typing import Optional
from core.j2534 import J2534
from core.vehicle import VehicleConnection
from gui.panels.connection import ConnectionPanel
from gui.panels.scanner_panel import ScannerPanel
from gui.panels.dtc_panel import DTCPanel
from gui.panels.pats_panel import PATSPanel
from gui.panels.asbuilt_panel import AsBuiltPanel
from gui.panels.monitor_panel import MonitorPanel
from gui.panels.security_panel import SecurityPanel
from gui.theme import apply_theme, current_theme
from version import VERSION, VERSION_SHORT, APP_NAME, APP_DESC, BUILD
from modules.updater import check_async, UpdateInfo

AUTHOR = "Brent Gordon"
HOMEPAGE = "https://fuse-obd.com"
LICENSE_TEXT = (
    "MIT License\n\n"
    f"Copyright (c) 2026 {AUTHOR}\n\n"
    "Permission is hereby granted, free of charge, to any person obtaining a copy "
    "of this software and associated documentation files (the \"Software\"), to deal "
    "in the Software without restriction, including without limitation the rights "
    "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell "
    "copies of the Software, and to permit persons to whom the Software is "
    "furnished to do so, subject to the following conditions:\n\n"
    "The above copyright notice and this permission notice shall be included in all "
    "copies or substantial portions of the Software.\n\n"
    "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR "
    "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, "
    "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT."
)


class MainWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} v{VERSION} — {APP_DESC}")
        self.root.geometry("1200x750")
        self.root.minsize(900, 600)

        self.vehicle: Optional[VehicleConnection] = None
        self._build_menu()
        self._build_ui()
        apply_theme(self.root, "dark")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Silent auto-update check on startup (no message if offline or up-to-date)
        self.root.after(1500, self._auto_check_updates)

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Check for Updates", command=self._manual_check_updates)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Dark Theme", command=lambda: self._set_theme("dark"))
        view_menu.add_command(label="Light Theme", command=lambda: self._set_theme("light"))
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About Fuse OBD", command=self._show_about)
        help_menu.add_command(label="License", command=self._show_license)
        help_menu.add_separator()
        help_menu.add_command(label="Visit Website", command=lambda: webbrowser.open(HOMEPAGE))
        menubar.add_cascade(label="Help", menu=help_menu)

    def _show_about(self):
        about = tk.Toplevel(self.root)
        about.title(f"About {APP_NAME}")
        about.geometry("420x380")
        about.resizable(False, False)
        about.transient(self.root)
        about.grab_set()

        title = tk.Label(about, text=APP_NAME, font=("Segoe UI", 24, "bold"))
        title.pack(pady=(20, 2))

        subtitle = tk.Label(about, text=APP_DESC, font=("Segoe UI", 11))
        subtitle.pack()

        ver = tk.Label(about, text=f"Version {VERSION}", font=("Segoe UI", 10), fg="gray")
        ver.pack(pady=(5, 15))

        sep = ttk.Separator(about, orient="horizontal")
        sep.pack(fill="x", padx=30)

        creator = tk.Label(about, text=f"Created by {AUTHOR}", font=("Segoe UI", 12, "bold"))
        creator.pack(pady=(15, 5))

        license_lbl = tk.Label(about, text="Free and open source — MIT License", font=("Segoe UI", 10), fg="#2070c0")
        license_lbl.pack(pady=(0, 5))

        features = tk.Label(
            about,
            text=(
                "Module Scanner  |  Fault Reader/Clear  |  AI Mechanic Chat\n"
                "Key Programming (PATS)  |  Factory Settings Read/Write\n"
                "Live PID Monitor  |  Security Access  |  VIN Decoder\n\n"
                "No licensing. No subscriptions. No limits."
            ),
            font=("Segoe UI", 9), fg="gray", justify="center",
        )
        features.pack(pady=(5, 15))

        website = tk.Label(about, text=HOMEPAGE, font=("Segoe UI", 9), fg="#4488ff", cursor="hand2")
        website.pack(pady=(0, 5))
        website.bind("<Button-1>", lambda e: webbrowser.open(HOMEPAGE))

        ttk.Button(about, text="Close", command=about.destroy, width=10).pack(pady=(0, 15))

    def _show_license(self):
        lic_win = tk.Toplevel(self.root)
        lic_win.title("License — Fuse OBD")
        lic_win.geometry("550x400")
        lic_win.transient(self.root)
        lic_win.grab_set()

        text = tk.Text(lic_win, wrap="word", font=("Consolas", 9), padx=15, pady=15)
        scroll = ttk.Scrollbar(lic_win, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        text.insert("1.0", LICENSE_TEXT)
        text.config(state="disabled")

        btn_frame = ttk.Frame(lic_win)
        btn_frame.pack(fill="x", pady=10)
        ttk.Button(btn_frame, text="Close", command=lic_win.destroy, width=10).pack()

    # ── Update system ──

    def _auto_check_updates(self):
        """Silent check on startup. Only notifies if update is available."""
        check_async(VERSION_SHORT, BUILD,
                    lambda info: self.root.after(0, self._on_update_result, info))

    def _manual_check_updates(self):
        """User-initiated check. Always shows result."""
        self.global_status.config(text="Checking for updates...")
        check_async(VERSION_SHORT, BUILD,
                    lambda info: self.root.after(0, self._on_manual_result, info))

    def _on_update_result(self, info: UpdateInfo):
        """Callback for auto-check. Silent if up-to-date or offline."""
        if info.available:
            self._show_update_dialog(info)
        # If not available and no error, or if offline error — stay silent

    def _on_manual_result(self, info: UpdateInfo):
        """Callback for manual check. Always reports status."""
        if info.error:
            self.global_status.config(text=f"Update check failed: {info.error}")
            messagebox.showinfo("Update Check",
                f"Could not reach the update server.\n\n{info.error}\n\n"
                "Check your internet connection and try again, or visit\n"
                f"{HOMEPAGE} to download the latest version.",
                parent=self.root)
        elif info.available:
            self._show_update_dialog(info)
        else:
            self.global_status.config(text=f"Fuse OBD is up to date (v{VERSION})")
            messagebox.showinfo("Update Check",
                f"You're running the latest version of {APP_NAME}.\n\n"
                f"Current: v{VERSION}\nLatest: v{info.latest_version}\n\n"
                f"Released: {info.release_date}",
                parent=self.root)

    def _show_update_dialog(self, info: UpdateInfo):
        """Show update available dialog."""
        self.global_status.config(
            text=f"Update available: v{info.latest_version} (you have v{VERSION})"
        )
        mandatory = "\n\nThis is a MANDATORY update." if info.mandatory else ""
        result = messagebox.askyesno(
            "Update Available",
            f"A new version of {APP_NAME} is available!\n\n"
            f"Your version: v{VERSION}\n"
            f"Latest version: v{info.latest_version}\n"
            f"Released: {info.release_date} ({info.size_mb} MB)\n\n"
            f"{info.release_notes}{mandatory}\n\n"
            "Would you like to visit the download page?",
            parent=self.root,
        )
        if result:
            webbrowser.open(info.download_url or HOMEPAGE)

    # ── UI ──

    def _build_ui(self):
        self.conn_panel = ConnectionPanel(
            self.root, on_connect=self._on_connect, on_disconnect=self._on_disconnect,
        )
        self.conn_panel.pack(fill="x", padx=10, pady=(10, 5))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.scanner_panel = ScannerPanel(self.notebook, self._get_vehicle)
        self.dtc_panel = DTCPanel(self.notebook, self._get_vehicle)
        self.pats_panel = PATSPanel(self.notebook, self._get_vehicle)
        self.asbuilt_panel = AsBuiltPanel(self.notebook, self._get_vehicle)
        self.monitor_panel = MonitorPanel(self.notebook, self._get_vehicle)
        self.security_panel = SecurityPanel(self.notebook, self._get_vehicle)

        self.notebook.add(self.scanner_panel, text="  Scanner  ")
        self.notebook.add(self.dtc_panel, text="  Faults  ")
        self.notebook.add(self.pats_panel, text="  Program Keys  ")
        self.notebook.add(self.asbuilt_panel, text="  Factory Settings  ")
        self.notebook.add(self.monitor_panel, text="  Live Data  ")
        self.notebook.add(self.security_panel, text="  Security Access  ")

        status = ttk.Frame(self.root)
        status.pack(fill="x", padx=10, pady=(0, 5))
        self.global_status = ttk.Label(
            status, text=f"{APP_NAME} v{VERSION} — Free and open source (MIT License)",
        )
        self.global_status.pack(side="left")

    def _on_connect(self, j2534: J2534):
        self.vehicle = VehicleConnection(j2534)
        try:
            self.vehicle.connect_hs_can()
        except Exception as e:
            messagebox.showwarning("HS CAN", f"Could not open HS CAN: {e}")
        try:
            self.vehicle.connect_ms_can()
        except Exception as e:
            messagebox.showwarning("MS CAN", f"Could not open MS CAN: {e}")
        self.global_status.config(text="Connected — ready to scan")

    def _on_disconnect(self):
        self.monitor_panel.stop_monitor()
        if self.vehicle:
            self.vehicle.disconnect_all()
            self.vehicle = None
        self.global_status.config(text=f"{APP_NAME} v{VERSION} — Disconnected")

    def _get_vehicle(self) -> Optional[VehicleConnection]:
        if not self.vehicle:
            messagebox.showwarning("Not Connected", "Connect to a vehicle first")
            return None
        return self.vehicle

    def _set_theme(self, name: str):
        apply_theme(self.root, name)

    def _on_close(self):
        self._on_disconnect()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
