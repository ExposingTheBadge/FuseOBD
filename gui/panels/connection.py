import subprocess
import tempfile
import traceback
from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from core.j2534 import J2534, J2534Device, enumerate_devices
from gui.qt_helpers import BasePanel, run_thread, warn, info, error, confirm


def _log(msg: str) -> None:
    try:
        with open(tempfile.gettempdir() + "/fuse_debug.log", "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass


class ConnectionPanel(BasePanel):
    def __init__(self, parent: QWidget, on_connect: Callable, on_disconnect: Callable):
        super().__init__(parent)
        self.on_connect_cb = on_connect
        self.on_disconnect_cb = on_disconnect
        self.devices: list[J2534Device] = []
        self.j2534: Optional[J2534] = None
        self.connected = False
        self._build_ui()
        self.refresh_devices()

    # ── UI ──

    def _build_ui(self):
        box = QGroupBox("Connection", self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 12, 10, 10)
        v.setSpacing(4)

        # Row 1 — adapter selector
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Adapter:"))
        self.device_combo = QComboBox()
        self.device_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        r1.addWidget(self.device_combo, stretch=1)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_devices)
        r1.addWidget(self.refresh_btn)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_connection)
        r1.addWidget(self.connect_btn)
        v.addLayout(r1)

        # Row 2 — WiFi manual entry
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("WiFi IP:"))
        self.wifi_ip = QLineEdit("192.168.0.10")
        self.wifi_ip.setFixedWidth(120)
        r2.addWidget(self.wifi_ip)
        r2.addWidget(QLabel("Port:"))
        self.wifi_port = QLineEdit("35000")
        self.wifi_port.setFixedWidth(70)
        r2.addWidget(self.wifi_port)
        self.wifi_btn = QPushButton("Add WiFi")
        self.wifi_btn.clicked.connect(self._add_wifi_adapter)
        r2.addWidget(self.wifi_btn)
        r2.addStretch(1)
        v.addLayout(r2)

        # Row 3 — Bluetooth
        r3 = QHBoxLayout()
        self.bt_btn = QPushButton("Bluetooth Devices")
        self.bt_btn.clicked.connect(self._scan_bluetooth)
        r3.addWidget(self.bt_btn)
        r3.addStretch(1)
        v.addLayout(r3)

        # Row 4 — status / version / voltage
        r4 = QHBoxLayout()
        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("color: #ff4444; font-weight: bold;")
        r4.addWidget(self.status_label)
        r4.addStretch(1)
        self.version_label = QLabel("")
        r4.addWidget(self.version_label)
        self.voltage_label = QLabel("")
        self.voltage_label.setStyleSheet("margin-left: 15px;")
        r4.addWidget(self.voltage_label)
        v.addLayout(r4)

    # ── Device enumeration ──

    def refresh_devices(self):
        try:
            self.devices = enumerate_devices()
            self._update_combo()
            _log(f"REFRESH: found {len(self.devices)} devices")
        except Exception as e:
            _log(f"REFRESH ERROR: {e}\n{traceback.format_exc()}")

    def _update_combo(self):
        self.device_combo.clear()
        for d in self.devices:
            if d.is_wifi:
                self.device_combo.addItem(f"{d.name} ({d.host}:{d.tcp_port})")
            elif d.is_serial:
                self.device_combo.addItem(f"{d.name} ({d.port})")
            else:
                self.device_combo.addItem(f"{d.name} ({d.vendor})")
        if self.devices:
            self.device_combo.setCurrentIndex(0)

    def _add_wifi_adapter(self):
        ip = self.wifi_ip.text().strip()
        port_str = self.wifi_port.text().strip()
        if not ip:
            warn(self, "Error", "Enter a WiFi IP address")
            return
        try:
            port = int(port_str) if port_str else 35000
        except ValueError:
            port = 35000

        for d in self.devices:
            if d.host == ip and d.tcp_port == port:
                for i in range(self.device_combo.count()):
                    if ip in self.device_combo.itemText(i):
                        self.device_combo.setCurrentIndex(i)
                        return
                return

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
        self.device_combo.setCurrentIndex(self.device_combo.count() - 1)

    # ── Bluetooth scan ──

    def _scan_bluetooth(self):
        self.bt_btn.setEnabled(False)
        self.bt_btn.setText("Scanning...")

        def fetch():
            devs = self._list_bluetooth_devices()
            self.after(0, lambda: self._show_bt_popup(devs))

        run_thread(fetch)

    def _list_bluetooth_devices(self) -> list[tuple[str, str]]:
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
        devices: list[tuple[str, str]] = []
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
        self.bt_btn.setEnabled(True)
        self.bt_btn.setText("Bluetooth Devices")

        dlg = QDialog(self)
        dlg.setWindowTitle("Bluetooth Devices")
        dlg.resize(500, 400)
        v = QVBoxLayout(dlg)

        head = QLabel("Select a Bluetooth OBD adapter:")
        head.setStyleSheet("font-size: 11pt; font-weight: bold;")
        v.addWidget(head)
        v.addWidget(QLabel("Tip: Pair your adapter in Windows Bluetooth settings first"))

        tree = QTreeWidget()
        tree.setHeaderLabels(["Paired Bluetooth Devices"])
        tree.setColumnWidth(0, 440)
        v.addWidget(tree, stretch=1)
        for name, _dev_id in devices:
            item = QTreeWidgetItem([name])
            if name.startswith("⚠") or name.startswith("No"):
                item.setForeground(0, Qt.GlobalColor.red)
            tree.addTopLevelItem(item)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        sel_btn = QPushButton("Select")
        sel_btn.setFixedWidth(110)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(80)
        btn_row.addWidget(sel_btn)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        def do_select():
            items = tree.selectedItems()
            if not items:
                return
            name = items[0].text(0)
            if name.startswith("⚠") or name.startswith("No"):
                return
            device = J2534Device(
                name=f"{name} (Bluetooth)",
                vendor="Bluetooth ELM327",
                dll_path="",
                is_serial=False,
            )
            self.devices.append(device)
            self._update_combo()
            self.device_combo.setCurrentIndex(self.device_combo.count() - 1)
            dlg.accept()

        sel_btn.clicked.connect(do_select)
        cancel_btn.clicked.connect(dlg.reject)
        tree.itemDoubleClicked.connect(lambda *_: do_select())
        dlg.exec()

    # ── Connect / disconnect ──

    def _toggle_connection(self):
        _log(f"TOGGLE called: connected={self.connected}, devices={len(self.devices)}")
        try:
            if self.connected:
                self._disconnect()
            else:
                self._connect()
        except Exception as e:
            _log(f"ERROR: {e}\n{traceback.format_exc()}")
            error(self, "Connection Error", str(e))

    def _connect(self):
        idx = self.device_combo.currentIndex()
        if idx < 0 or idx >= len(self.devices):
            _log(f"CONNECT ABORT: idx={idx}, len={len(self.devices)}")
            warn(self, "Error", "Select an adapter first")
            return

        device = self.devices[idx]
        _log(f"CONNECT to: {device.name} port={device.port} serial={device.is_serial}")
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("Connecting...")
        self.refresh_btn.setEnabled(False)
        self.device_combo.setEnabled(False)
        self.status_label.setText("Connecting...")
        self.status_label.setStyleSheet("color: #ffaa00; font-weight: bold;")

        def connect_thread():
            _log(f"THREAD START: port={device.port} host={device.host}")
            try:
                _log("Creating J2534...")
                self.j2534 = J2534(device)
                _log("J2534 created, opening...")
                self.j2534.open()
                _log("Open OK, reading version...")
                fw, dll, api = self.j2534.read_version()
                _log(f"Version: FW={fw} DLL={dll} API={api}")
                voltage = 0.0
                try:
                    voltage = self.j2534.read_battery_voltage()
                    _log(f"Voltage: {voltage:.1f}V")
                except Exception as ve:
                    _log(f"Voltage error: {ve}")

                def on_connected():
                    self.version_label.setText(f"FW: {fw}  API: {api}")
                    if voltage > 0:
                        self.voltage_label.setText(f"Battery: {voltage:.1f}V")
                    self.connected = True
                    self.connect_btn.setEnabled(True)
                    self.connect_btn.setText("Disconnect")
                    self.status_label.setText("Connected")
                    self.status_label.setStyleSheet("color: #55ff55; font-weight: bold;")
                    self.on_connect_cb(self.j2534)

                self.after(0, on_connected)
                _log("Connect success - UI updated")
            except Exception as e:
                _log(f"CONNECT ERROR: {e}\n{traceback.format_exc()}")

                def on_failed():
                    self.connect_btn.setEnabled(True)
                    self.connect_btn.setText("Connect")
                    self.refresh_btn.setEnabled(True)
                    self.device_combo.setEnabled(True)
                    self.status_label.setText("Disconnected")
                    self.status_label.setStyleSheet("color: #ff4444; font-weight: bold;")
                    error(self, "Connection Failed", str(e))
                    if self.j2534:
                        try:
                            self.j2534.close()
                        except Exception:
                            pass
                        self.j2534 = None

                self.after(0, on_failed)

        run_thread(connect_thread)

    def _disconnect(self):
        self.on_disconnect_cb()
        if self.j2534:
            try:
                self.j2534.close()
            except Exception:
                pass
            self.j2534 = None
        self.connected = False
        self.connect_btn.setText("Connect")
        self.status_label.setText("Disconnected")
        self.status_label.setStyleSheet("color: #ff4444; font-weight: bold;")
        self.version_label.setText("")
        self.voltage_label.setText("")
        self.device_combo.setEnabled(True)
        self.refresh_btn.setEnabled(True)
