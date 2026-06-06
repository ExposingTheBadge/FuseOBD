import subprocess
import traceback
from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from core.j2534 import J2534, J2534Device, enumerate_devices
from gui.qt_helpers import BasePanel, run_thread, warn, info, error, confirm
from modules import issues_log


def _log(msg: str) -> None:
    """Mirror connection-panel events into the single app log file."""
    try:
        issues_log.log_connection(msg)
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
            # Also surface any adapters whose USB device is plugged in
            # but whose driver isn't bound — these would otherwise be
            # invisible (no COM port appears, so enumerate_devices()
            # doesn't see them) and the user would be left wondering
            # why their adapter doesn't show up.
            try:
                from core.drivers import needs_driver_install
                missing = needs_driver_install()
                if missing:
                    msgs = []
                    for s in missing:
                        msgs.append(f"{s.adapter.name} ({s.adapter.driver}) — {s.adapter.driver_url or 'no URL'}")
                    _log("DRIVER MISSING: " + " | ".join(msgs))
                    try:
                        from modules import issues_log
                        issues_log.add_issue(
                            title=f"{len(missing)} adapter(s) need a driver",
                            kind=issues_log.KIND_CONNECTION,
                            severity=issues_log.SEVERITY_MED,
                            summary_simple=(
                                "Found USB OBD adapter(s) plugged in that don't have a "
                                "working Windows driver. The adapter won't appear in the "
                                "Connect dropdown until you install the right one.\n\n"
                                + "\n".join("• " + m for m in msgs)
                            ),
                            summary_technical="\n".join(
                                f"{s.adapter.name}: needs {s.adapter.driver}, "
                                f"VID/PID {s.vid_pid}, instance {s.instance_id}, "
                                f"driver URL {s.adapter.driver_url}"
                                for s in missing
                            ),
                            source="connection_panel.refresh_devices",
                            context={"missing_count": len(missing)},
                        )
                    except Exception:
                        pass
            except Exception as e:
                _log(f"driver-check skipped: {e}")
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
        """List Bluetooth devices Windows knows about.

        Uses Get-PnpDevice — built into Windows 10/11, always present,
        no WinRT/admin tricks. We grab two classes:

          * Class 'Bluetooth' — every paired/known BT peripheral
          * Class 'Ports'     — virtual COM ports (this is what an
                                ELM327 actually shows up as once it's
                                paired; the user will pick the COM
                                port for connecting)

        Both are merged so the user sees BOTH the friendly device name
        and the COM-port-side entry that they'll actually open.
        """
        import base64
        import os

        # Filtering rules (applied inside PowerShell so noise never leaves
        # the shell):
        #   - Skip BTH\*           — Microsoft kernel-level BT stubs
        #     (RFCOMM TDI, Enumerator, MS_BTHLE, etc.)
        #   - Skip USB\*           — that's the host radio dongle itself
        #   - Skip BTHENUM\{...    — per-profile service enumerations on a
        #                            classic-BT peer (AVRCP, OPP, PAN, PBAP,
        #                            Headset AG, etc.) — the peer's parent
        #                            entry (BTHENUM\DEV_<MAC>) is the one
        #                            we keep
        #   - Skip BTHLEDEVICE\{0000...
        #                          — standard BT-SIG GATT services that
        #                            duplicate per BLE device (GAP/GATT)
        ps_script = (
            "$ErrorActionPreference = 'SilentlyContinue'; "
            "$out = @(); "
            "Get-PnpDevice -Class Bluetooth | Where-Object { "
            "  $_.FriendlyName -and "
            "  -not ($_.InstanceId -like 'BTH\\*') -and "
            "  -not ($_.InstanceId -like 'USB\\*') -and "
            "  -not ($_.InstanceId -like 'BTHENUM\\{*') -and "
            "  -not ($_.InstanceId -like 'BTHLEDEVICE\\{*') "
            "} | ForEach-Object { $out += \"BT|||$($_.FriendlyName)|||$($_.InstanceId)|||$($_.Status)\" }; "
            "Get-PnpDevice -Class Ports | Where-Object { "
            "  $_.InstanceId -like 'BTHENUM*' -or "
            "  $_.FriendlyName -match 'Bluetooth' -or "
            "  $_.FriendlyName -match 'OBD' "
            "} | ForEach-Object { $out += \"PORT|||$($_.FriendlyName)|||$($_.InstanceId)|||$($_.Status)\" }; "
            "$out -join \"`n\""
        )
        encoded = base64.b64encode(ps_script.encode("utf-16-le")).decode("ascii")

        creation_flags = 0
        if os.name == "nt":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                capture_output=True, text=True, timeout=15,
                creationflags=creation_flags,
            )
        except subprocess.TimeoutExpired:
            _log("BT scan: PowerShell timed out after 15s")
            return [("⚠ Bluetooth scan timed out (15s)", "")]
        except FileNotFoundError:
            _log("BT scan: powershell.exe not found on PATH")
            return [("⚠ PowerShell not found on PATH", "")]
        except Exception as e:
            _log(f"BT scan: launch error: {e}")
            return [(f"⚠ Could not launch PowerShell: {e}", "")]

        if result.returncode != 0:
            err_msg = (result.stderr or "").strip().splitlines()
            short = err_msg[0][:120] if err_msg else f"exit {result.returncode}"
            _log(f"BT scan: PowerShell failed (rc={result.returncode}): {short}")
            return [(f"⚠ PowerShell error: {short}", "")]

        devices: list[tuple[str, str]] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or "|||" not in line:
                continue
            parts = line.split("|||")
            if len(parts) < 3:
                continue
            kind = parts[0]
            name = parts[1].strip()
            inst = parts[2].strip()
            status = parts[3].strip() if len(parts) > 3 else ""
            if not name:
                continue
            label = name
            if kind == "PORT":
                label = f"{name}  [COM-port]"
            if status and status.upper() not in ("OK", "UNKNOWN", ""):
                label = f"{label}  [{status}]"
            devices.append((label, inst))

        # De-dupe while preserving order.
        seen = set()
        unique: list[tuple[str, str]] = []
        for d in devices:
            key = d[0].lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(d)

        if not unique:
            _log("BT scan: no Bluetooth devices reported by Get-PnpDevice")
            return [("No paired Bluetooth devices found "
                     "(pair your adapter in Windows Bluetooth settings first)", "")]
        _log(f"BT scan: found {len(unique)} Bluetooth/related device(s)")
        return unique

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

                # Classify the adapter from its ATI / version response
                # so the dropdown shows "OBDLink MX+ r5.4.2" instead of
                # "OBD Adapter (COM7)". The combined fw+dll string gives
                # us the best chance of catching vendor variants.
                from core.adapter_id import identify
                ident = identify(f"{fw} {dll}".strip())
                friendly = ident.label()
                _log(f"Identified: kind={ident.kind} vendor={ident.vendor} model={ident.model} fw={ident.firmware}")

                voltage = 0.0
                try:
                    voltage = self.j2534.read_battery_voltage()
                    _log(f"Voltage: {voltage:.1f}V")
                except Exception as ve:
                    _log(f"Voltage error: {ve}")

                def on_connected():
                    # Surface the identified adapter wherever the
                    # generic "OBD Adapter (COMx)" was previously shown.
                    if friendly and friendly != device.name:
                        device.name = friendly
                        # Refresh the dropdown label for the current
                        # selection so the user sees what they connected
                        # to next time the dialog opens.
                        cur = self.device_combo.currentIndex()
                        if cur >= 0:
                            port_suffix = f"  ({device.port})" if device.port else ""
                            self.device_combo.setItemText(cur, friendly + port_suffix)
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
                try:
                    issues_log.add_issue(
                        title=f"Adapter connect failed: {device.name}",
                        kind=issues_log.KIND_CONNECTION,
                        severity=issues_log.SEVERITY_MED,
                        summary_simple=(
                            f"Fuse OBD couldn't open the OBD adapter \"{device.name}\".\n\n"
                            f"Short reason: {e}\n\n"
                            "Try the AI Mechanic — it can check Windows Device Manager, "
                            "look at other adapters, and walk you through a fix."
                        ),
                        summary_technical=(
                            f"Device: {device.name}\n"
                            f"Vendor: {device.vendor}\n"
                            f"Port: {device.port}  Host: {device.host}\n"
                            f"Serial: {device.is_serial}  WiFi: {device.is_wifi}\n"
                            f"DLL: {device.dll_path}\n\n"
                            f"Exception: {e!r}\n\n"
                            f"{traceback.format_exc()}"
                        ),
                        source="connection_panel._connect",
                        context={"adapter": device.name, "port": device.port,
                                 "host": device.host},
                    )
                except Exception:
                    pass

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
