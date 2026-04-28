import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable
from core.j2534 import J2534, J2534Device, enumerate_devices, PassThruException


class ConnectionPanel(ttk.LabelFrame):
    def __init__(self, parent, on_connect: Callable, on_disconnect: Callable):
        super().__init__(parent, text="Connection", padding=10)
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.devices: list[J2534Device] = []
        self.j2534: Optional[J2534] = None
        self.connected = False
        self._build_ui()

    def _build_ui(self):
        row = ttk.Frame(self)
        row.pack(fill="x", pady=2)

        ttk.Label(row, text="Adapter:").pack(side="left", padx=(0, 5))
        self.device_combo = ttk.Combobox(row, state="readonly", width=40)
        self.device_combo.pack(side="left", padx=(0, 5), fill="x", expand=True)

        self.refresh_btn = ttk.Button(row, text="Refresh", command=self.refresh_devices, width=8)
        self.refresh_btn.pack(side="left", padx=2)

        self.connect_btn = ttk.Button(row, text="Connect", command=self._toggle_connection, width=10)
        self.connect_btn.pack(side="left", padx=2)

        info_row = ttk.Frame(self)
        info_row.pack(fill="x", pady=2)

        self.status_label = tk.Label(
            info_row, text="Disconnected", fg="red",
            font=("Segoe UI", 9, "bold"),
        )
        self.status_label.pack(side="left")

        self.voltage_label = ttk.Label(info_row, text="")
        self.voltage_label.pack(side="right")

        self.version_label = ttk.Label(info_row, text="")
        self.version_label.pack(side="right", padx=(0, 15))

        self.refresh_devices()

    def refresh_devices(self):
        self.devices = enumerate_devices()
        names = [f"{d.name} ({d.vendor})" for d in self.devices]
        self.device_combo["values"] = names
        if names:
            self.device_combo.current(0)

    def _toggle_connection(self):
        if self.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        idx = self.device_combo.current()
        if idx < 0 or idx >= len(self.devices):
            messagebox.showerror("Error", "Select an adapter first")
            return

        device = self.devices[idx]
        try:
            self.j2534 = J2534(device)
            self.j2534.open()

            fw, dll, api = self.j2534.read_version()
            self.version_label.config(text=f"FW: {fw}  API: {api}")

            try:
                voltage = self.j2534.read_battery_voltage()
                self.voltage_label.config(text=f"Battery: {voltage:.1f}V")
            except PassThruException:
                self.voltage_label.config(text="")

            self.connected = True
            self.connect_btn.config(text="Disconnect")
            self.status_label.config(text="Connected", fg="green")
            self.device_combo.config(state="disabled")
            self.refresh_btn.config(state="disabled")

            self.on_connect(self.j2534)

        except Exception as e:
            messagebox.showerror("Connection Failed", str(e))
            if self.j2534:
                try:
                    self.j2534.close()
                except Exception:
                    pass
                self.j2534 = None

    def _disconnect(self):
        self.on_disconnect()
        if self.j2534:
            try:
                self.j2534.close()
            except Exception:
                pass
            self.j2534 = None
        self.connected = False
        self.connect_btn.config(text="Connect")
        self.status_label.config(text="Disconnected", fg="red")
        self.version_label.config(text="")
        self.voltage_label.config(text="")
        self.device_combo.config(state="readonly")
        self.refresh_btn.config(state="normal")
