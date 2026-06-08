from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QListWidget, QPlainTextEdit,
    QProgressBar, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from core.protocols import FORD_MODULES
from modules.asbuilt import AsBuiltReader, ModuleAsBuilt
from gui.qt_helpers import BasePanel, CancelToken, run_thread, warn, confirm, error


class AsBuiltPanel(BasePanel):
    def __init__(self, parent: QWidget, get_vehicle):
        super().__init__(parent)
        self.get_vehicle = get_vehicle
        self.asbuilt_data: list[ModuleAsBuilt] = []
        self._cancel: CancelToken | None = None
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)

        tb = QHBoxLayout()
        self.read_btn = QPushButton("Read Factory Settings")
        self.read_btn.clicked.connect(self._read_all)
        tb.addWidget(self.read_btn)

        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self._export)
        tb.addWidget(self.export_btn)

        self.import_btn = QPushButton("Import & Write")
        self.import_btn.clicked.connect(self._import_write)
        tb.addWidget(self.import_btn)

        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        tb.addWidget(self.progress)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_read)
        tb.addWidget(self.cancel_btn)

        tb.addStretch(1)
        v.addLayout(tb)

        self.status_label = QLabel("Ready")
        v.addWidget(self.status_label)

        split = QSplitter(Qt.Orientation.Horizontal)
        v.addWidget(split, stretch=1)

        self.module_list = QListWidget()
        self.module_list.setFont(_mono())
        self.module_list.setFixedWidth(220)
        self.module_list.currentRowChanged.connect(self._on_module_select)
        split.addWidget(self.module_list)

        self.data_text = QPlainTextEdit()
        self.data_text.setReadOnly(True)
        self.data_text.setFont(_mono())
        self.data_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        split.addWidget(self.data_text)
        split.setStretchFactor(1, 3)

    def _read_all(self):
        vehicle = self.get_vehicle()
        if not vehicle:
            return
        self.read_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self._cancel = CancelToken()
        token = self._cancel

        def thread():
            try:
                reader = AsBuiltReader(vehicle)

                def progress_cb(name, current, total):
                    pct = int((current / total) * 100) if total else 0
                    self.after(0, lambda: self.progress.setValue(pct))
                    self.after(0, lambda: self.status_label.setText(f"Reading {name}..."))

                # Restrict the read to modules that actually answered on
                # the bus. Without this we shotgun all 55 candidate
                # addresses; on a CD3 with ~6 live modules that wastes
                # ~5 minutes of NRC waits.
                if not vehicle.vehicle_info.modules and not token.cancelled:
                    self.after(0, lambda: self.status_label.setText(
                        "Discovering modules on the bus..."))
                    vehicle.scan_modules(cancel=token)
                discovered = [info.module for info in vehicle.vehicle_info.modules]

                self.asbuilt_data = reader.read_all_modules(
                    callback=progress_cb, modules=discovered, cancel=token)
                self.after(0, self._populate_module_list)
                if token.cancelled:
                    msg = f"Cancelled — {len(self.asbuilt_data)} module(s) read"
                else:
                    msg = f"Read {len(self.asbuilt_data)} modules"
                self.after(0, lambda m=msg: self.status_label.setText(m))
            except Exception as e:
                self.after(0, lambda: self.status_label.setText(f"Error: {e}"))
            finally:
                self.after(0, lambda: self.read_btn.setEnabled(True))
                self.after(0, lambda: self.cancel_btn.setEnabled(False))
                self.after(0, lambda: self.progress.setValue(100))

        run_thread(thread)

    def _cancel_read(self):
        if self._cancel:
            self._cancel.cancel()
        self.cancel_btn.setEnabled(False)

    def _populate_module_list(self):
        self.module_list.clear()
        for mod in self.asbuilt_data:
            self.module_list.addItem(f"{mod.module_abbrev} ({len(mod.blocks)} blocks)")

    def _on_module_select(self, idx: int):
        if 0 <= idx < len(self.asbuilt_data):
            mod = self.asbuilt_data[idx]
            self.data_text.setPlainText(mod.to_asbuilt_text())

    def _export(self):
        if not self.asbuilt_data:
            warn(self, "Export", "Read factory settings first")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Factory Settings", "",
            "As-Built Profile (*.abt);;Text (*.txt);;All Files (*.*)"
        )
        if not path:
            return
        try:
            profile = AsBuiltReader.export_profile(self.asbuilt_data)
            with open(path, "w") as f:
                f.write(profile)
            self.status_label.setText(f"Exported to {path}")
        except Exception as e:
            error(self, "Export Failed", str(e))

    def _import_write(self):
        vehicle = self.get_vehicle()
        if not vehicle:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Factory Settings", "",
            "As-Built Profile (*.abt);;Text (*.txt);;All Files (*.*)"
        )
        if not path:
            return
        try:
            with open(path, "r") as f:
                text = f.read()
            profile = AsBuiltReader.parse_profile(text)
        except Exception as e:
            error(self, "Import Failed", str(e))
            return

        module_list = ", ".join(profile.keys())
        block_count = sum(len(v) for v in profile.values())
        msg = (
            f"Write factory settings to vehicle?\n\n"
            f"Modules: {module_list}\n"
            f"Total blocks: {block_count}\n\n"
            f"WARNING: Writing incorrect factory settings can cause modules to malfunction."
        )
        if not confirm(self, "Write Factory Settings", msg):
            return

        self.import_btn.setEnabled(False)

        def thread():
            reader = AsBuiltReader(vehicle)
            written = 0
            errors = 0
            for abbrev, blocks in profile.items():
                module = next((m for m in FORD_MODULES if m.abbreviation == abbrev), None)
                if not module:
                    self.after(0, lambda a=abbrev: self.status_label.setText(
                        f"Unknown module: {a}"))
                    continue
                for did, data in blocks:
                    try:
                        reader.write_block(module, did, data)
                        written += 1
                    except Exception:
                        errors += 1
            self.after(0, lambda: self.status_label.setText(
                f"Written {written} blocks, {errors} errors"))
            self.after(0, lambda: self.import_btn.setEnabled(True))

        run_thread(thread)


def _mono(size: int = 10):
    f = QFont("Consolas")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(size)
    return f
