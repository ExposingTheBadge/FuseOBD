import tkinter as tk
from tkinter import ttk
import threading
import time
from core.vehicle import VehicleConnection
from modules.pid import PIDMonitor, PIDReading, PIDDefinition, STANDARD_PIDS, FORD_EXTENDED_PIDS


class MonitorPanel(ttk.Frame):
    def __init__(self, parent, get_vehicle: callable):
        super().__init__(parent)
        self.get_vehicle = get_vehicle
        self.monitor: PIDMonitor | None = None
        self._build_ui()

    def _build_ui(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 5))

        self.start_btn = ttk.Button(toolbar, text="Start Monitor", command=self._toggle_monitor)
        self.start_btn.pack(side="left", padx=2)

        ttk.Label(toolbar, text="Update interval:").pack(side="left", padx=(15, 5))
        self.interval_var = tk.StringVar(value="200")
        interval_combo = ttk.Combobox(
            toolbar, textvariable=self.interval_var,
            values=["50", "100", "200", "500", "1000"], width=6, state="readonly",
        )
        interval_combo.pack(side="left")
        ttk.Label(toolbar, text="ms").pack(side="left", padx=(2, 0))

        self.status_label = ttk.Label(toolbar, text="")
        self.status_label.pack(side="right")

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.LabelFrame(paned, text="Available PIDs", padding=5)
        paned.add(left, weight=1)

        self.avail_tree = ttk.Treeview(left, columns=("name", "unit", "module"), show="headings", height=25)
        self.avail_tree.heading("name", text="Name")
        self.avail_tree.heading("unit", text="Unit")
        self.avail_tree.heading("module", text="Module")
        self.avail_tree.column("name", width=180)
        self.avail_tree.column("unit", width=50, anchor="center")
        self.avail_tree.column("module", width=50, anchor="center")

        avail_scroll = ttk.Scrollbar(left, orient="vertical", command=self.avail_tree.yview)
        self.avail_tree.configure(yscrollcommand=avail_scroll.set)
        self.avail_tree.pack(side="left", fill="both", expand=True)
        avail_scroll.pack(side="right", fill="y")

        btn_frame = ttk.Frame(paned)
        paned.add(btn_frame, weight=0)

        ttk.Button(btn_frame, text="Add >>", command=self._add_pid, width=10).pack(pady=20)
        ttk.Button(btn_frame, text="<< Remove", command=self._remove_pid, width=10).pack(pady=5)
        ttk.Button(btn_frame, text="Add All", command=self._add_all, width=10).pack(pady=20)

        right = ttk.LabelFrame(paned, text="Live Data", padding=5)
        paned.add(right, weight=2)

        self.live_tree = ttk.Treeview(
            right, columns=("name", "value", "raw", "unit"), show="headings", height=25,
        )
        self.live_tree.heading("name", text="Parameter")
        self.live_tree.heading("value", text="Value")
        self.live_tree.heading("raw", text="Raw")
        self.live_tree.heading("unit", text="Unit")
        self.live_tree.column("name", width=180)
        self.live_tree.column("value", width=100, anchor="center")
        self.live_tree.column("raw", width=80, anchor="center")
        self.live_tree.column("unit", width=60, anchor="center")

        live_scroll = ttk.Scrollbar(right, orient="vertical", command=self.live_tree.yview)
        self.live_tree.configure(yscrollcommand=live_scroll.set)
        self.live_tree.pack(side="left", fill="both", expand=True)
        live_scroll.pack(side="right", fill="y")

        # Double-click to add/remove PIDs
        self.avail_tree.bind("<Double-1>", lambda e: self._add_pid())
        self.live_tree.bind("<Double-1>", lambda e: self._remove_pid())

        self._pid_map: dict[str, PIDDefinition] = {}
        self._populate_available()

    def _populate_available(self):
        self._pid_map.clear()
        all_pids = STANDARD_PIDS + FORD_EXTENDED_PIDS
        for pid in all_pids:
            iid = self.avail_tree.insert("", "end", values=(pid.name, pid.unit, pid.module))
            self._pid_map[iid] = pid
    def _add_pid(self):
        sel = self.avail_tree.selection()
        if not sel:
            return
        for iid in sel:
            pid = self._pid_map.get(iid)
            if pid:
                # Check if already in live tree
                existing = {self.live_tree.item(c)["values"][0] for c in self.live_tree.get_children()}
                if pid.name not in existing:
                    self.live_tree.insert("", "end", iid=f"live_{pid.did:04X}",
                                           values=(pid.name, "--", "--", pid.unit))
        # Auto-expand to show added PIDs
        if self.live_tree.get_children():
            self.live_tree.see(self.live_tree.get_children()[0])

    def _remove_pid(self):
        sel = self.live_tree.selection()
        for iid in sel:
            self.live_tree.delete(iid)

    def _add_all(self):
        for iid, pid in self._pid_map.items():
            existing = [self.live_tree.item(c)["values"][0] for c in self.live_tree.get_children()]
            if pid.name not in existing:
                self.live_tree.insert("", "end", iid=f"live_{pid.did:04X}",
                                       values=(pid.name, "--", "--", pid.unit))

    def _toggle_monitor(self):
        if self.monitor and self.monitor.is_running:
            self.monitor.stop()
            self.start_btn.config(text="Start Monitor")
            self.status_label.config(text="Stopped")
            return

        vehicle = self.get_vehicle()
        if not vehicle:
            return

        self.monitor = PIDMonitor(vehicle)

        all_pids = {f"live_{p.did:04X}": p for p in STANDARD_PIDS + FORD_EXTENDED_PIDS}
        for child in self.live_tree.get_children():
            pid = all_pids.get(child)
            if pid:
                self.monitor.add_pid(pid)

        if not self.monitor.active_pids:
            self.status_label.config(text="Add PIDs to monitor first")
            return

        interval = int(self.interval_var.get()) / 1000.0
        self.monitor.start(callback=self._on_readings, interval=interval)
        self.start_btn.config(text="Stop Monitor")
        self.status_label.config(text="Monitoring...")

    def _on_readings(self, readings: dict[int, PIDReading]):
        def update():
            for did, reading in readings.items():
                iid = f"live_{did:04X}"
                try:
                    self.live_tree.item(iid, values=(
                        reading.pid.name,
                        reading.display_value,
                        f"0x{reading.raw_value:04X}",
                        reading.pid.unit,
                    ))
                except tk.TclError:
                    pass
        self.after(0, update)

    def stop_monitor(self):
        if self.monitor and self.monitor.is_running:
            self.monitor.stop()
