import tkinter as tk
from tkinter import ttk
import threading
from typing import Optional
from core.vehicle import VehicleConnection, ModuleInfo


class ScannerPanel(ttk.Frame):
    def __init__(self, parent, get_vehicle: callable):
        super().__init__(parent)
        self.get_vehicle = get_vehicle
        self._build_ui()

    def _build_ui(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 5))

        self.scan_btn = ttk.Button(toolbar, text="Full Scan", command=self._full_scan)
        self.scan_btn.pack(side="left", padx=2)

        self.vin_label = ttk.Label(toolbar, text="VIN: --", font=("Consolas", 11, "bold"))
        self.vin_label.pack(side="left", padx=15)

        self.count_label = ttk.Label(toolbar, text="")
        self.count_label.pack(side="right", padx=5)

        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", pady=2)

        self.status_label = ttk.Label(self, text="Ready")
        self.status_label.pack(fill="x")

        columns = ("abbrev", "name", "address", "network", "part_number", "software", "hardware")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=20)

        self.tree.heading("abbrev", text="Module")
        self.tree.heading("name", text="Name")
        self.tree.heading("address", text="Address")
        self.tree.heading("network", text="Network")
        self.tree.heading("part_number", text="Part Number")
        self.tree.heading("software", text="Software")
        self.tree.heading("hardware", text="Hardware")

        self.tree.column("abbrev", width=60, anchor="center")
        self.tree.column("name", width=220)
        self.tree.column("address", width=70, anchor="center")
        self.tree.column("network", width=80, anchor="center")
        self.tree.column("part_number", width=140)
        self.tree.column("software", width=140)
        self.tree.column("hardware", width=140)

        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _full_scan(self):
        vehicle = self.get_vehicle()
        if not vehicle:
            return

        self.scan_btn.config(state="disabled")
        self.tree.delete(*self.tree.get_children())
        self.progress["value"] = 0

        def scan_thread():
            try:
                vin = vehicle.read_vin()
                self.after(0, lambda: self.vin_label.config(text=f"VIN: {vin or 'Not found'}"))

                def progress_cb(name, current, total):
                    pct = (current / total) * 100
                    self.after(0, lambda: self.progress.config(value=pct))
                    self.after(0, lambda: self.status_label.config(text=f"Scanning {name}..."))

                modules = vehicle.scan_modules(callback=progress_cb)

                self.after(0, lambda: self._populate_results(modules))
                self.after(0, lambda: self.status_label.config(
                    text=f"Scan complete. Found {len(modules)} modules."
                ))
            except Exception as e:
                self.after(0, lambda: self.status_label.config(text=f"Error: {e}"))
            finally:
                self.after(0, lambda: self.scan_btn.config(state="normal"))
                self.after(0, lambda: self.progress.config(value=100))

        threading.Thread(target=scan_thread, daemon=True).start()

    def _populate_results(self, modules: list[ModuleInfo]):
        self.tree.delete(*self.tree.get_children())
        for m in modules:
            network = "HS CAN" if m.module.network.value <= 2 else "MS CAN"
            self.tree.insert("", "end", values=(
                m.module.abbreviation,
                m.module.name,
                f"0x{m.module.address:02X}",
                network,
                m.part_number or "--",
                m.software_pn or "--",
                m.hardware_pn or "--",
            ))
        self.count_label.config(text=f"{len(modules)} modules found")
