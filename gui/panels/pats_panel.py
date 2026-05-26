from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from modules.pats import PATSManager, PATSInfo
from utils.ford_crypto import compute_incode, PATSType
from gui.qt_helpers import BasePanel, run_thread, warn, confirm, info, error


PATS_CHOICES = [
    "Auto (from vehicle)",
    "PATS I/II (1996-2005)",
    "PATS III (2005-2010)",
    "PATS IV/V (2010+)",
]


class PATSPanel(BasePanel):
    def __init__(self, parent: QWidget, get_vehicle):
        super().__init__(parent)
        self.get_vehicle = get_vehicle
        self.pats_manager: PATSManager | None = None
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setSpacing(4)

        # ── Toolbar ──
        tb = QHBoxLayout()
        self.read_btn = QPushButton("Read PATS Info")
        self.read_btn.clicked.connect(self._read_info)
        tb.addWidget(self.read_btn)
        self.program_btn = QPushButton("Program Key")
        self.program_btn.clicked.connect(self._program_key)
        tb.addWidget(self.program_btn)
        self.erase_btn = QPushButton("Erase All Keys")
        self.erase_btn.clicked.connect(self._erase_keys)
        tb.addWidget(self.erase_btn)
        tb.addStretch(1)
        v.addLayout(tb)

        self.status_label = QLabel("Connect to vehicle and read PATS info first")
        v.addWidget(self.status_label)

        # ── Calculator ──
        calc = QGroupBox("Incode → Outcode Calculator (Offline)")
        v.addWidget(calc)
        g = QGridLayout(calc)

        g.addWidget(QLabel("Incode (hex):"), 0, 0)
        self.calc_incode = QLineEdit()
        self.calc_incode.setFont(_mono())
        self.calc_incode.setFixedWidth(160)
        g.addWidget(self.calc_incode, 0, 1)

        g.addWidget(QLabel("PATS Type:"), 0, 2)
        self.calc_pats = QComboBox()
        self.calc_pats.addItems(PATS_CHOICES)
        self.calc_pats.setFixedWidth(180)
        g.addWidget(self.calc_pats, 0, 3)

        g.addWidget(QLabel("Module ID (hex):"), 1, 0)
        self.calc_modid = QLineEdit("0000")
        self.calc_modid.setFont(_mono())
        self.calc_modid.setFixedWidth(80)
        g.addWidget(self.calc_modid, 1, 1)

        g.addWidget(QLabel("Algo Variant:"), 1, 2)
        self.calc_algo = QLineEdit("0")
        self.calc_algo.setFont(_mono())
        self.calc_algo.setFixedWidth(60)
        g.addWidget(self.calc_algo, 1, 3)

        self.calc_btn = QPushButton("Calculate Outcode")
        self.calc_btn.clicked.connect(self._calc_outcode)
        g.addWidget(self.calc_btn, 1, 4)

        g.addWidget(QLabel("Outcode:"), 1, 5)
        self.calc_result = QLabel("----")
        self.calc_result.setStyleSheet("font-family: Consolas, monospace; font-size: 14pt; font-weight: bold; color: #55ff55;")
        g.addWidget(self.calc_result, 1, 6)

        # ── Split: info | log ──
        split = QSplitter(Qt.Orientation.Horizontal)
        v.addWidget(split, stretch=1)

        info_box = QGroupBox("PATS Configuration")
        info_grid = QGridLayout(info_box)
        self.info_fields: dict[str, QLabel] = {}
        fields = [
            ("PATS Type", "pats_type"),
            ("PATS Enabled", "pats_enabled"),
            ("Master Key", "master_key"),
            ("Min Keys Required", "min_keys"),
            ("Keys Programmed", "num_keys_programmed"),
            ("Spare Key Available", "spare_key"),
            ("Unlock Key", "unlock_key"),
            ("Anti-Scan", "anti_scan"),
            ("Timed Delay (min)", "timed_delay"),
            ("Cycle Key Time (sec)", "cycle_key_time"),
            ("Reset Type", "reset_type"),
            ("PCM ID", "pcm_id"),
            ("Algorithm Variant", "algo_variant"),
        ]
        for i, (label_text, name) in enumerate(fields):
            lbl = QLabel(f"{label_text}:")
            info_grid.addWidget(lbl, i, 0)
            val = QLabel("--")
            val.setFont(_mono())
            info_grid.addWidget(val, i, 1)
            self.info_fields[name] = val
        info_grid.setColumnStretch(1, 1)
        split.addWidget(info_box)

        log_box = QGroupBox("Key Programming Log")
        log_v = QVBoxLayout(log_box)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(_mono(9))
        log_v.addWidget(self.log_text)
        split.addWidget(log_box)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)

    # ── Calculator ──

    def _calc_outcode(self):
        raw = self.calc_incode.text().strip().replace(" ", "")
        if not raw:
            warn(self, "Calculator", "Enter an incode value")
            return
        try:
            incode_int = int(raw, 16)
        except ValueError:
            warn(self, "Calculator", "Incode must be hex (e.g. A3F1)")
            return

        pats_sel = self.calc_pats.currentText()
        if pats_sel.startswith("Auto"):
            if self.pats_manager and self.pats_manager.pats_info.pats_type > 0:
                ptype = self.pats_manager.pats_info.pats_type
            else:
                ptype = PATSType.PATS_3
        elif "I/II" in pats_sel:
            ptype = PATSType.PATS_1
        elif "III" in pats_sel:
            ptype = PATSType.PATS_3
        else:
            ptype = PATSType.PATS_4

        try:
            mod_id = int(self.calc_modid.text().strip(), 16)
        except ValueError:
            mod_id = 0
        try:
            algo = int(self.calc_algo.text().strip())
        except ValueError:
            algo = 0

        try:
            outcode = compute_incode(incode_int, ptype, mod_id, algo)
            if ptype in (PATSType.PATS_4, PATSType.PATS_5):
                self.calc_result.setText(f"{outcode:08X}")
            else:
                self.calc_result.setText(f"{outcode:04X}")
            self._log(f"Incode 0x{raw.upper()} → Outcode 0x{self.calc_result.text()}  "
                      f"(PATS {ptype}, mod=0x{mod_id:04X}, algo={algo})")
        except Exception as e:
            self.calc_result.setText("ERROR")
            self._log(f"Calculator error: {e}")

    def _log(self, message: str):
        self.after(0, lambda: self.log_text.appendPlainText(message))

    # ── Info read ──

    def _read_info(self):
        vehicle = self.get_vehicle()
        if not vehicle:
            return
        self.read_btn.setEnabled(False)
        self.status_label.setText("Reading PATS configuration...")

        def thread():
            try:
                self.pats_manager = PATSManager(vehicle)
                info_val = self.pats_manager.read_pats_info()
                self.after(0, lambda: self._display_info(info_val))
                self.after(0, lambda: self.status_label.setText("PATS info read successfully"))
                self._log("PATS configuration read successfully")
            except Exception as e:
                self.after(0, lambda: self.status_label.setText(f"Error: {e}"))
                self._log(f"Error reading PATS: {e}")
            finally:
                self.after(0, lambda: self.read_btn.setEnabled(True))

        run_thread(thread)

    def _display_info(self, info: PATSInfo):
        def fmt(val, special=None):
            if val == -1:
                return "N/A"
            if special == "bool":
                return "Yes" if val == 1 else "No" if val == 0 else str(val)
            if special == "hex":
                return f"0x{val:04X}" if val > 0 else str(val)
            return str(val)

        self.info_fields["pats_type"].setText(PATSManager.pats_type_name(info.pats_type))
        self.info_fields["pats_enabled"].setText(fmt(info.pats_enabled, "bool"))
        self.info_fields["master_key"].setText(fmt(info.master_key, "bool"))
        self.info_fields["min_keys"].setText(fmt(info.min_keys))
        self.info_fields["num_keys_programmed"].setText(fmt(info.num_keys_programmed))
        self.info_fields["spare_key"].setText(fmt(info.spare_key, "bool"))
        self.info_fields["unlock_key"].setText(fmt(info.unlock_key, "bool"))
        self.info_fields["anti_scan"].setText(fmt(info.anti_scan, "bool"))
        self.info_fields["timed_delay"].setText(fmt(info.timed_delay))
        self.info_fields["cycle_key_time"].setText(fmt(info.cycle_key_time))
        self.info_fields["reset_type"].setText(fmt(info.reset_type))
        self.info_fields["pcm_id"].setText(fmt(info.pcm_id, "hex"))
        self.info_fields["algo_variant"].setText(fmt(info.algo_variant))

        if info.pcm_id > 0:
            self.calc_modid.setText(f"{info.pcm_id:04X}")
        if info.algo_variant >= 0:
            self.calc_algo.setText(str(info.algo_variant))
        if info.pats_type > 0:
            pats_map = {1: "PATS I/II (1996-2005)", 2: "PATS I/II (1996-2005)",
                        3: "PATS III (2005-2010)", 4: "PATS IV/V (2010+)",
                        5: "PATS IV/V (2010+)"}
            label = pats_map.get(info.pats_type, "Auto (from vehicle)")
            idx = self.calc_pats.findText(label)
            if idx >= 0:
                self.calc_pats.setCurrentIndex(idx)

    # ── Programming / erase ──

    def _program_key(self):
        if not self.pats_manager:
            warn(self, "PATS", "Read PATS info first")
            return
        msg = (
            "KEY PROGRAMMING PROCEDURE\n\n"
            "1. Make sure you have the new key ready\n"
            "2. Security access will be requested\n"
            "3. You will need to cycle the ignition with the new key\n"
            "4. Follow the on-screen instructions\n\n"
            "Continue?"
        )
        if not confirm(self, "Program Key", msg):
            return
        self.program_btn.setEnabled(False)
        self.erase_btn.setEnabled(False)

        def thread():
            try:
                self.pats_manager.program_key(callback=self._log)
                self._log("Key programming sequence initiated successfully")
                self.after(0, lambda: info(self, "Success",
                    "Key learn initiated. Cycle the ignition with the new key now."))
            except Exception as e:
                self._log(f"Key programming failed: {e}")
                self.after(0, lambda: error(self, "Failed", str(e)))
            finally:
                self.after(0, lambda: self.program_btn.setEnabled(True))
                self.after(0, lambda: self.erase_btn.setEnabled(True))

        run_thread(thread)

    def _erase_keys(self):
        if not self.pats_manager:
            warn(self, "PATS", "Read PATS info first")
            return
        msg = (
            "WARNING: ERASE ALL KEYS\n\n"
            "This will erase ALL programmed keys from the vehicle.\n"
            "You MUST have at least 2 keys ready to program afterward.\n"
            "If you lose all keys, the vehicle will not start.\n\n"
            "Are you absolutely sure?"
        )
        if not confirm(self, "Erase Keys", msg):
            return
        if not confirm(self, "Final Confirmation", "Last chance. Erase ALL keys?"):
            return
        self.program_btn.setEnabled(False)
        self.erase_btn.setEnabled(False)

        def thread():
            try:
                self.pats_manager.erase_keys(callback=self._log)
                self._log("All keys erased successfully")
            except Exception as e:
                self._log(f"Key erase failed: {e}")
                self.after(0, lambda: error(self, "Failed", str(e)))
            finally:
                self.after(0, lambda: self.program_btn.setEnabled(True))
                self.after(0, lambda: self.erase_btn.setEnabled(True))

        run_thread(thread)


def _mono(size: int = 10):
    from PyQt6.QtGui import QFont
    f = QFont("Consolas")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(size)
    return f
