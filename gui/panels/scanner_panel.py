from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from core.protocols import FordNetwork
from core.vehicle import ModuleInfo
from gui.qt_helpers import BasePanel, CancelToken, run_thread


_NETWORK_LABEL = {
    FordNetwork.HS_CAN:     "HS CAN",
    FordNetwork.MS_CAN:     "MS CAN",
    FordNetwork.HS_CAN_EXT: "HS CAN 29",
    FordNetwork.ISO:        "ISO9141",
    FordNetwork.SCP:        "SCP",
}


class ScannerPanel(BasePanel):
    def __init__(self, parent: QWidget, get_vehicle):
        super().__init__(parent)
        self.get_vehicle = get_vehicle
        self._cancel: CancelToken | None = None
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setSpacing(4)

        tb = QHBoxLayout()
        self.scan_btn = QPushButton("Full Scan")
        self.scan_btn.clicked.connect(self._full_scan)
        tb.addWidget(self.scan_btn)
        self.vin_label = QLabel("VIN: --")
        self.vin_label.setStyleSheet("font-family: Consolas, monospace; font-size: 11pt; font-weight: bold; margin-left: 15px;")
        tb.addWidget(self.vin_label)
        tb.addStretch(1)
        self.count_label = QLabel("")
        tb.addWidget(self.count_label)
        v.addLayout(tb)

        prog_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        prog_row.addWidget(self.progress, stretch=1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_scan)
        prog_row.addWidget(self.cancel_btn)
        v.addLayout(prog_row)

        self.status_label = QLabel("Ready")
        v.addWidget(self.status_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([
            "Module", "Name", "CAN ID", "Network",
            "Part Number", "Software", "Cal ID", "Assembly", "Hardware",
        ])
        self.tree.setAlternatingRowColors(True)
        for col, w in enumerate([60, 220, 70, 80, 130, 140, 90, 90, 130]):
            self.tree.setColumnWidth(col, w)
        self.tree.setUniformRowHeights(True)
        v.addWidget(self.tree, stretch=1)

    def _full_scan(self):
        vehicle = self.get_vehicle()
        if not vehicle:
            return

        self.scan_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.tree.clear()
        self.progress.setValue(0)
        self._cancel = CancelToken()
        token = self._cancel

        def thread():
            try:
                vin = vehicle.read_vin()
                self.after(0, lambda: self.vin_label.setText(f"VIN: {vin or 'Not found'}"))
                if token.cancelled:
                    self.after(0, lambda: self.status_label.setText("Scan cancelled."))
                    return

                def progress_cb(name, current, total):
                    pct = int((current / total) * 100) if total else 0
                    self.after(0, lambda: self.progress.setValue(pct))
                    self.after(0, lambda: self.status_label.setText(f"Scanning {name}..."))

                modules = vehicle.scan_modules(callback=progress_cb, cancel=token)
                self.after(0, lambda: self._populate_results(modules))
                if token.cancelled:
                    self.after(0, lambda: self.status_label.setText(
                        f"Scan cancelled. Found {len(modules)} modules before stop."
                    ))
                else:
                    self.after(0, lambda: self.status_label.setText(
                        f"Scan complete. Found {len(modules)} modules."
                    ))
            except Exception as e:
                self.after(0, lambda: self.status_label.setText(f"Error: {e}"))
            finally:
                self.after(0, lambda: self.scan_btn.setEnabled(True))
                self.after(0, lambda: self.cancel_btn.setEnabled(False))
                self.after(0, lambda: self.progress.setValue(100))

        run_thread(thread)

    def _cancel_scan(self):
        if self._cancel:
            self._cancel.cancel()
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("Cancelling — will stop after the current module...")

    def _populate_results(self, modules: list[ModuleInfo]):
        self.tree.clear()
        for m in modules:
            item = QTreeWidgetItem([
                m.module.abbreviation,
                m.module.name,
                f"0x{m.module.tx_id:03X}",          # tx CAN ID — what users see on the bus
                _NETWORK_LABEL.get(m.module.network, "?"),
                m.part_number or "--",
                m.software_pn or "--",
                m.calibration_id or "--",
                m.assembly_pn or "--",
                m.hardware_pn or "--",
            ])
            for col in (0, 2, 3):
                item.setTextAlignment(col, Qt.AlignmentFlag.AlignCenter)
            self.tree.addTopLevelItem(item)
        self.count_label.setText(f"{len(modules)} modules found")
