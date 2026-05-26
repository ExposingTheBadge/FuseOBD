from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSplitter,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from modules.pid import (
    PIDMonitor, PIDReading, PIDDefinition, STANDARD_PIDS, FORD_EXTENDED_PIDS,
)
from gui.qt_helpers import BasePanel


class MonitorPanel(BasePanel):
    def __init__(self, parent: QWidget, get_vehicle):
        super().__init__(parent)
        self.get_vehicle = get_vehicle
        self.monitor: PIDMonitor | None = None
        self._pid_map: dict[str, PIDDefinition] = {}
        self._build_ui()
        self._populate_available()

    def _build_ui(self):
        v = QVBoxLayout(self)

        tb = QHBoxLayout()
        self.start_btn = QPushButton("Start Monitor")
        self.start_btn.clicked.connect(self._toggle_monitor)
        tb.addWidget(self.start_btn)
        tb.addWidget(QLabel("Update interval:"))
        self.interval_combo = QComboBox()
        self.interval_combo.addItems(["50", "100", "200", "500", "1000"])
        self.interval_combo.setCurrentText("200")
        self.interval_combo.setFixedWidth(80)
        tb.addWidget(self.interval_combo)
        tb.addWidget(QLabel("ms"))
        tb.addStretch(1)
        self.status_label = QLabel("")
        tb.addWidget(self.status_label)
        v.addLayout(tb)

        split = QSplitter(Qt.Orientation.Horizontal)
        v.addWidget(split, stretch=1)

        avail_box = QGroupBox("Available PIDs")
        avail_v = QVBoxLayout(avail_box)
        self.avail_tree = QTreeWidget()
        self.avail_tree.setHeaderLabels(["Name", "Unit", "Module"])
        self.avail_tree.setColumnWidth(0, 180)
        self.avail_tree.setColumnWidth(1, 50)
        self.avail_tree.setColumnWidth(2, 50)
        self.avail_tree.setAlternatingRowColors(True)
        self.avail_tree.itemDoubleClicked.connect(lambda *_: self._add_pid())
        avail_v.addWidget(self.avail_tree)
        split.addWidget(avail_box)

        # Buttons column
        btn_col = QWidget()
        btn_v = QVBoxLayout(btn_col)
        btn_v.addStretch(1)
        add_btn = QPushButton("Add >>")
        add_btn.clicked.connect(self._add_pid)
        add_btn.setFixedWidth(110)
        btn_v.addWidget(add_btn)
        rm_btn = QPushButton("<< Remove")
        rm_btn.clicked.connect(self._remove_pid)
        rm_btn.setFixedWidth(110)
        btn_v.addWidget(rm_btn)
        all_btn = QPushButton("Add All")
        all_btn.clicked.connect(self._add_all)
        all_btn.setFixedWidth(110)
        btn_v.addWidget(all_btn)
        btn_v.addStretch(1)
        btn_col.setFixedWidth(130)
        split.addWidget(btn_col)

        live_box = QGroupBox("Live Data")
        live_v = QVBoxLayout(live_box)
        self.live_tree = QTreeWidget()
        self.live_tree.setHeaderLabels(["Parameter", "Value", "Raw", "Unit"])
        self.live_tree.setColumnWidth(0, 180)
        self.live_tree.setColumnWidth(1, 100)
        self.live_tree.setColumnWidth(2, 80)
        self.live_tree.setColumnWidth(3, 60)
        self.live_tree.setAlternatingRowColors(True)
        self.live_tree.itemDoubleClicked.connect(lambda *_: self._remove_pid())
        live_v.addWidget(self.live_tree)
        split.addWidget(live_box)

        split.setStretchFactor(0, 1)
        split.setStretchFactor(2, 2)

    def _populate_available(self):
        self._pid_map.clear()
        for pid in STANDARD_PIDS + FORD_EXTENDED_PIDS:
            iid = f"pid_{pid.did:04X}"
            item = QTreeWidgetItem([pid.name, pid.unit, pid.module])
            item.setData(0, Qt.ItemDataRole.UserRole, iid)
            self.avail_tree.addTopLevelItem(item)
            self._pid_map[iid] = pid

    def _live_has(self, pid_name: str) -> bool:
        for i in range(self.live_tree.topLevelItemCount()):
            if self.live_tree.topLevelItem(i).text(0) == pid_name:
                return True
        return False

    def _add_pid(self):
        for sel in self.avail_tree.selectedItems():
            iid = sel.data(0, Qt.ItemDataRole.UserRole)
            pid = self._pid_map.get(iid)
            if pid and not self._live_has(pid.name):
                item = QTreeWidgetItem([pid.name, "--", "--", pid.unit])
                item.setData(0, Qt.ItemDataRole.UserRole, f"live_{pid.did:04X}")
                self.live_tree.addTopLevelItem(item)

    def _remove_pid(self):
        for sel in self.live_tree.selectedItems():
            idx = self.live_tree.indexOfTopLevelItem(sel)
            if idx >= 0:
                self.live_tree.takeTopLevelItem(idx)

    def _add_all(self):
        for _iid, pid in self._pid_map.items():
            if not self._live_has(pid.name):
                item = QTreeWidgetItem([pid.name, "--", "--", pid.unit])
                item.setData(0, Qt.ItemDataRole.UserRole, f"live_{pid.did:04X}")
                self.live_tree.addTopLevelItem(item)

    def _toggle_monitor(self):
        if self.monitor and self.monitor.is_running:
            self.monitor.stop()
            self.start_btn.setText("Start Monitor")
            self.status_label.setText("Stopped")
            return

        vehicle = self.get_vehicle()
        if not vehicle:
            return

        self.monitor = PIDMonitor(vehicle)
        all_pids = {f"live_{p.did:04X}": p for p in STANDARD_PIDS + FORD_EXTENDED_PIDS}
        for i in range(self.live_tree.topLevelItemCount()):
            iid = self.live_tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
            pid = all_pids.get(iid)
            if pid:
                self.monitor.add_pid(pid)

        if not self.monitor.active_pids:
            self.status_label.setText("Add PIDs to monitor first")
            return

        interval = int(self.interval_combo.currentText()) / 1000.0
        self.monitor.start(callback=self._on_readings, interval=interval)
        self.start_btn.setText("Stop Monitor")
        self.status_label.setText("Monitoring...")

    def _on_readings(self, readings: dict[int, PIDReading]):
        def update():
            # Build a lookup by iid
            id_to_idx: dict[str, int] = {}
            for i in range(self.live_tree.topLevelItemCount()):
                item = self.live_tree.topLevelItem(i)
                iid = item.data(0, Qt.ItemDataRole.UserRole)
                id_to_idx[iid] = i
            for did, reading in readings.items():
                iid = f"live_{did:04X}"
                idx = id_to_idx.get(iid)
                if idx is None:
                    continue
                item = self.live_tree.topLevelItem(idx)
                item.setText(0, reading.pid.name)
                item.setText(1, str(reading.display_value))
                item.setText(2, f"0x{reading.raw_value:04X}")
                item.setText(3, reading.pid.unit)

        self.after(0, update)

    def stop_monitor(self):
        if self.monitor and self.monitor.is_running:
            self.monitor.stop()
