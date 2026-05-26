from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar,
    QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from core.protocols import FORD_MODULES
from modules.security import SecurityAccess, FORD_SESSIONS, BruteforceResult
from gui.qt_helpers import BasePanel, run_thread


LEVELS = [
    "0x01 — Read/Unlock",
    "0x03 — Write/Program",
    "0x11 — Module Config",
    "0x61 — Factory/EOL",
]


class SecurityPanel(BasePanel):
    def __init__(self, parent: QWidget, get_vehicle):
        super().__init__(parent)
        self.get_vehicle = get_vehicle
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)

        cfg = QGroupBox("Security Access Configuration")
        cfg_v = QVBoxLayout(cfg)
        v.addWidget(cfg)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Target Module:"))
        self.module_combo = QComboBox()
        for m in FORD_MODULES:
            self.module_combo.addItem(f"{m.abbreviation} — {m.name}")
        self.module_combo.setFixedWidth(280)
        row1.addWidget(self.module_combo)

        row1.addWidget(QLabel("Session:"))
        self.session_combo = QComboBox()
        for name in FORD_SESSIONS.keys():
            self.session_combo.addItem(name)
        if self.session_combo.count() > 2:
            self.session_combo.setCurrentIndex(2)
        self.session_combo.setFixedWidth(200)
        row1.addWidget(self.session_combo)

        row1.addWidget(QLabel("Security Level:"))
        self.level_combo = QComboBox()
        self.level_combo.addItems(LEVELS)
        self.level_combo.setFixedWidth(180)
        row1.addWidget(self.level_combo)
        row1.addStretch(1)
        cfg_v.addLayout(row1)

        row2 = QHBoxLayout()
        self.brute_btn = QPushButton("Bruteforce Security Access")
        self.brute_btn.clicked.connect(self._start_bruteforce)
        row2.addWidget(self.brute_btn)
        self.brute_all_btn = QPushButton("Scan All Modules")
        self.brute_all_btn.clicked.connect(self._scan_all)
        row2.addWidget(self.brute_all_btn)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        row2.addWidget(self.progress)
        row2.addStretch(1)
        self.status_label = QLabel("")
        row2.addWidget(self.status_label)
        cfg_v.addLayout(row2)

        split = QSplitter(Qt.Orientation.Horizontal)
        v.addWidget(split, stretch=1)

        results_box = QGroupBox("Results")
        rv = QVBoxLayout(results_box)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Module", "Session", "Level", "Seed", "Key Found", "Status"])
        for col, w in enumerate([70, 70, 60, 90, 130, 220]):
            self.tree.setColumnWidth(col, w)
        self.tree.setAlternatingRowColors(True)
        rv.addWidget(self.tree)
        split.addWidget(results_box)

        log_box = QGroupBox("Log")
        lv = QVBoxLayout(log_box)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        lv.addWidget(self.log_text)
        split.addWidget(log_box)

        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 1)

    # ── Helpers ──

    def _log(self, message: str):
        self.after(0, lambda: self.log_text.appendPlainText(message))

    def _get_selected_module(self):
        idx = self.module_combo.currentIndex()
        if idx < 0 or idx >= len(FORD_MODULES):
            return None
        return FORD_MODULES[idx]

    def _get_session(self) -> int:
        return FORD_SESSIONS.get(self.session_combo.currentText(), 0x01)

    def _get_level(self) -> int:
        return int(self.level_combo.currentText().split(" ")[0], 16)

    def _set_buttons(self, enabled: bool):
        self.brute_btn.setEnabled(enabled)
        self.brute_all_btn.setEnabled(enabled)

    def _add_result(self, result: BruteforceResult):
        if result.success:
            color = "#55ff55"
            key_str = result.key_found.decode("ascii", errors="replace") if result.key_found else ""
            status = f"UNLOCKED ({result.attempts} attempts)"
        elif result.error:
            color = "#ffaa00"
            key_str = ""
            status = result.error
        else:
            color = "#ff4444"
            key_str = ""
            status = f"LOCKED ({result.attempts} tried)"

        seed_str = f"0x{result.seed:06X}" if result.seed else "--"
        item = QTreeWidgetItem([
            result.module.abbreviation,
            f"0x{result.session:02X}",
            f"0x{result.security_level:02X}",
            seed_str,
            key_str,
            status,
        ])
        brush = QBrush(QColor(color))
        for col in range(item.columnCount()):
            item.setForeground(col, brush)
            if col in (0, 1, 2, 3):
                item.setTextAlignment(col, Qt.AlignmentFlag.AlignCenter)
        self.tree.addTopLevelItem(item)

    # ── Actions ──

    def _start_bruteforce(self):
        vehicle = self.get_vehicle()
        if not vehicle:
            return
        module = self._get_selected_module()
        if not module:
            return
        session = self._get_session()
        level = self._get_level()
        self._set_buttons(False)
        self._log(f"--- Bruteforcing {module.abbreviation} session=0x{session:02X} level=0x{level:02X} ---")

        def thread():
            sa = SecurityAccess(vehicle)
            result = sa.bruteforce_module(module, session=session, level=level, callback=self._log)
            self.after(0, lambda: self._add_result(result))
            if result.success:
                self._log(f"SUCCESS: {module.abbreviation} unlocked with key "
                          f"{result.key_found.decode('ascii', errors='replace')}")
            else:
                self._log(f"FAILED: {result.error}")
            self.after(0, lambda: self._set_buttons(True))
            self.after(0, lambda: self.status_label.setText(
                f"{'UNLOCKED' if result.success else 'Failed'}: {module.abbreviation}"))

        run_thread(thread)

    def _scan_all(self):
        vehicle = self.get_vehicle()
        if not vehicle:
            return
        session = self._get_session()
        level = self._get_level()
        wanted = ("PCM", "TCM", "ABS", "RCM", "IPC", "BCM", "SCCM", "HVAC",
                  "ACM", "APIM", "DDM", "PDM", "PAM", "GWM", "EPAS", "PSCM")
        common = [m for m in FORD_MODULES if m.abbreviation in wanted]
        self._set_buttons(False)
        self.tree.clear()
        self.progress.setValue(0)
        self._log(f"--- Scanning {len(common)} modules session=0x{session:02X} level=0x{level:02X} ---")

        def thread():
            sa = SecurityAccess(vehicle)
            for i, module in enumerate(common):
                pct = int((i / len(common)) * 100) if common else 0
                self.after(0, lambda p=pct: self.progress.setValue(p))
                self.after(0, lambda n=module.abbreviation: self.status_label.setText(
                    f"Trying {n}..."))
                self._log(f"\n[{module.abbreviation}] {module.name}")
                result = sa.bruteforce_module(module, session=session, level=level, callback=self._log)
                self.after(0, lambda r=result: self._add_result(r))
            self.after(0, lambda: self.progress.setValue(100))
            self.after(0, lambda: self._set_buttons(True))
            self.after(0, lambda: self.status_label.setText("Scan complete"))
            self._log("--- Scan complete ---")

        run_thread(thread)
