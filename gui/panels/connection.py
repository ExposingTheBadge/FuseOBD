import tkinter as tk
from tkinter import ttk, messagebox
import threading
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

        # WiFi manual entry row
        wifi_row = ttk.Frame(self)
        wifi_row.pack(fill="x", pady=(5, 0))
        ttk.Label(wifi_row, text="WiFi IP:").pack(side="left", padx=(0, 5))
        self.wifi_ip_var = tk.StringVar(value="192.168.0.10")
        self.wifi_ip_entry = ttk.Entry(wifi_row, textvariable=self.wifi_ip_var, width=16)
        self.wifi_ip_entry.pack(side="left", padx=(0, 5))
        ttk.Label(wifi_row, text="Port:").pack(side="left", padx=(0, 5))
        self.wifi_port_var = tk.StringVar(value="35000")
        self.wifi_port_entry = ttk.Entry(wifi_row, textvariable=self.wifi_port_var, width=6)
        self.wifi_port_entry.pack(side="left", padx=(0, 5))
        self.wifi_btn = ttk.Button(wifi_row, text="Add WiFi", command=self._add_wifi_adapter, width=10)
        self.wifi_btn.pack(side="left", padx=2)

        # Bluetooth button
        bt_row = ttk.Frame(self)
        bt_row.pack(fill="x", pady=(5, 0))
        self.bt_btn = ttk.Button(bt_row, text="Bluetooth Devices", command=self._scan_bluetooth, width=20)
        self.bt_btn.pack(side="left", padx=2)

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
        self._update_combo()

    def _update_combo(self):
        names = []
        for d in self.devices:
            if d.is_wifi:
                names.append(f"{d.name} ({d.host}:{d.tcp_port})")
            elif d.is_serial:
                names.append(f"{d.name} ({d.port})")
            else:
                names.append(f"{d.name} ({d.vendor})")
        self.device_combo["values"] = names
        if names:
            self.device_combo.current(0)

    def _add_wifi_adapter(self):
        ip = self.wifi_ip_var.get().strip()
        port_str = self.wifi_port_var.get().strip()
        if not ip:
            messagebox.showerror("Error", "Enter a WiFi IP address")
            return
        try:
            port = int(port_str) if port_str else 35000
        except ValueError:
            port = 35000

        # Check if already in list
        for d in self.devices:
            if d.host == ip and d.tcp_port == port:
                # Select it
                for i, name in enumerate(self.device_combo["values"]):
                    if ip in name:
                        self.device_combo.current(i)
                        return
                return

        from core.j2534 import J2534Device
        device = J2534Device(
            name=f"WiFi OBD ({ip})",
            vendor="WiFi/ELM327",
            dll_path=ip,
            host=ip,
            tcp_port=port,
            is_wifi=True,
        )
        self.devices.append(device)
        self._update_combo()
        self.device_combo.current(len(self.device_combo["values"]) - 1)

    def _scan_bluetooth(self):
        """Open a popup listing all paired Bluetooth devices for selection."""
        self.bt_btn.config(state="disabled", text="Scanning...")
        # Fetch BT devices in background thread (PowerShell call takes ~2-5s)
        def fetch():
            devices = self._list_bluetooth_devices()
            self.after(0, lambda: self._show_bt_popup(devices))

        threading.Thread(target=fetch, daemon=True).start()

    def _list_bluetooth_devices(self) -> list[tuple[str, str]]:
        """Return [(name, device_id), ...] for all paired Bluetooth devices."""
        import subprocess
        ps_cmd = (
            'powershell -NoProfile -Command "'
            '[Windows.Devices.Radios.Radio,Windows.System.Profile,ContentType=WindowsRuntime] | Out-Null;'
            '[Windows.Devices.Enumeration.DeviceInformation,Windows.Devices.Enumeration,ContentType=WindowsRuntime] | Out-Null;'
            'Add-Type -AssemblyName System.Runtime.WindowsRuntime;'
            '$async = [Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync('
            '[Windows.Devices.Bluetooth.BluetoothDevice]::GetDeviceSelectorFromPairingState($true));'
            '$task = $async.AsTask(); $task.Wait(5000);'
            'if ($task.IsCompleted) {'
            '  foreach ($d in $task.Result) { Write-Output \"$($d.Name)|||$($d.Id)\" }'
            '} else { Write-Output \"SCAN_TIMEOUT\" }"'
        )
        devices = []
        try:
            result = subprocess.run(ps_cmd, capture_output=True, text=True, timeout=12, shell=True)
            if result.returncode != 0:
                return [("⚠ PowerShell error", "")]
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if not line or line == "SCAN_TIMEOUT":
                    continue
                if "|||" in line:
                    parts = line.split("|||", 1)
                    name = parts[0].strip()
                    dev_id = parts[1].strip() if len(parts) > 1 else ""
                    if name:
                        devices.append((name, dev_id))
        except subprocess.TimeoutExpired:
            return [("⚠ Scan timed out", "")]
        except FileNotFoundError:
            return [("⚠ PowerShell not available", "")]
        except Exception as e:
            return [(f"⚠ Error: {e}", "")]
        if not devices:
            return [("No paired Bluetooth devices found", "")]
        return devices

    def _show_bt_popup(self, devices: list[tuple[str, str]]):
        """Show popup with paired BT devices for selection."""
        self.bt_btn.config(state="normal", text="Bluetooth Devices")
        popup = tk.Toplevel(self)
        popup.title("Bluetooth Devices")
        popup.geometry("500x400")
        popup.resizable(True, True)
        popup.transient(self)
        popup.grab_set()

        ttk.Label(popup, text="Select a Bluetooth OBD adapter:",
                  font=("Segoe UI", 11, "bold")).pack(pady=(15, 5), padx=20, anchor="w")
        ttk.Label(popup, text="Tip: Pair your adapter in Windows Bluetooth settings first",
                  font=("Segoe UI", 8), foreground="#888888").pack(pady=(0, 5), padx=20, anchor="w")

        # Scrollable list
        frame = ttk.Frame(popup)
        frame.pack(fill="both", expand=True, padx=20, pady=5)
        tree = ttk.Treeview(frame, columns=("name",), show="headings", height=12)
        tree.heading("name", text="Paired Bluetooth Devices")
        tree.column("name", width=440)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        for name, dev_id in devices:
            tag = "error" if name.startswith("⚠") or name.startswith("No") else "device"
            tree.insert("", "end", values=(name,), tags=(tag,))
        tree.tag_configure("error", foreground="#ff4444")

        def on_select():
            sel = tree.selection()
            if not sel:
                return
            name = tree.item(sel[0])["values"][0]
            if name.startswith("⚠") or name.startswith("No"):
                return
            # Check if this BT device has a COM port
            from core.j2534 import J2534Device
            bt_com = _find_bt_com_port(name) if "_find_bt_com_port" in dir() else ""
            if bt_com:
                device = J2534Device(
                    name=f"{name} ({bt_com})",
                    vendor="Bluetooth ELM327",
                    dll_path=bt_com,
                    port=bt_com,
                    is_serial=True,
                )
            else:
                # Device may not have SPP service active — show warning
                if not messagebox.askyesno("No COM Port",
                        f"'{name}' does not have a COM port assigned.\n\n"
                        "Make sure the device is paired AND has 'Serial Port' "
                        "(SPP) service enabled in Windows Bluetooth settings.\n\n"
                        "Try unpair and re-pair if needed.\n\n"
                        "Add it to the list anyway?"):
                    return
                device = J2534Device(
                    name=f"{name} (Bluetooth)",
                    vendor="Bluetooth ELM327",
                    dll_path="",
                    is_serial=False,
                )
            self.devices.append(device)
            self._update_combo()
            self.device_combo.current(len(self.device_combo["values"]) - 1)
            popup.destroy()

        ttk.Button(popup, text="Select", command=on_select, width=12).pack(pady=10)
        ttk.Button(popup, text="Cancel", command=popup.destroy, width=8).pack(pady=(0, 15))
        tree.bind("<Double-1>", lambda e: on_select())

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
        self.connect_btn.config(state="disabled", text="Connecting...")
        self.refresh_btn.config(state="disabled")
        self.device_combo.config(state="disabled")
        self.status_label.config(text="Connecting...", fg="orange")

        def connect_thread():
            try:
                self.j2534 = J2534(device)
                self.j2534.open()

                fw, dll, api = self.j2534.read_version()

                voltage = 0.0
                try:
                    voltage = self.j2534.read_battery_voltage()
                except Exception:
                    voltage = 0.0

                def on_connected():
                    self.version_label.config(text=f"FW: {fw}  API: {api}")
                    if voltage > 0:
                        self.voltage_label.config(text=f"Battery: {voltage:.1f}V")
                    self.connected = True
                    self.connect_btn.config(state="normal", text="Disconnect")
                    self.status_label.config(text="Connected", fg="green")
                    self.on_connect(self.j2534)

                self.after(0, on_connected)

            except Exception as e:
                def on_failed():
                    self.connect_btn.config(state="normal", text="Connect")
                    self.refresh_btn.config(state="normal")
                    self.device_combo.config(state="readonly")
                    self.status_label.config(text="Disconnected", fg="red")
                    messagebox.showerror("Connection Failed", str(e))
                    if self.j2534:
                        try:
                            self.j2534.close()
                        except Exception:
                            pass
                        self.j2534 = None

                self.after(0, on_failed)

        threading.Thread(target=connect_thread, daemon=True).start()

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
