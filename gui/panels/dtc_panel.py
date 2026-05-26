import webbrowser

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QSplitter,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from core.protocols import FORD_MODULES
from modules.dtc import DTCReader, ModuleDTCs
from modules.vehicle_info import decode_vin, get_vehicle_image_url
from data.dtc_definitions import lookup_dtc
from gui.qt_helpers import BasePanel, run_thread, confirm


class DTCPanel(BasePanel):
    def __init__(self, parent: QWidget, get_vehicle):
        super().__init__(parent)
        self.get_vehicle = get_vehicle
        self.all_dtcs: list[ModuleDTCs] = []
        self.vehicle_info: dict = {}
        self.chat = None
        self._vehicle_image_url: str | None = None
        self._build_ui()

    # ───────────────────────── UI ─────────────────────────

    def _build_ui(self):
        v = QVBoxLayout(self)

        # Toolbar
        tb = QHBoxLayout()
        self.read_btn = QPushButton("Read All Faults")
        self.read_btn.clicked.connect(self._read_all)
        tb.addWidget(self.read_btn)

        self.clear_btn = QPushButton("Clear All Faults")
        self.clear_btn.clicked.connect(self._clear_all)
        tb.addWidget(self.clear_btn)

        self.ai_btn = QPushButton("AI Mechanic")
        self.ai_btn.clicked.connect(self._start_ai_session)
        self.ai_btn.setEnabled(False)
        tb.addWidget(self.ai_btn)

        self.progress = QProgressBar()
        self.progress.setFixedWidth(150)
        tb.addWidget(self.progress)
        tb.addStretch(1)
        self.count_label = QLabel("")
        tb.addWidget(self.count_label)
        v.addLayout(tb)

        self.status_label = QLabel("Ready")
        v.addWidget(self.status_label)

        # Main split
        main_split = QSplitter(Qt.Orientation.Horizontal)
        v.addWidget(main_split, stretch=1)

        # ── Left ──
        left = QWidget()
        left_v = QVBoxLayout(left)
        left_v.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Module", "Code", "Description", "Status", "Details"])
        self.tree.setAlternatingRowColors(True)
        for col, w in enumerate([60, 70, 220, 65, 180]):
            self.tree.setColumnWidth(col, w)
        left_v.addWidget(self.tree, stretch=2)

        chat_header = QHBoxLayout()
        chat_header.addWidget(self._bold("AI Mechanic Chat"))
        chat_header.addStretch(1)
        self.chat_status = QLabel("")
        chat_header.addWidget(self.chat_status)
        left_v.addLayout(chat_header)

        self.chat_text = QTextEdit()
        self.chat_text.setReadOnly(True)
        self.chat_text.setStyleSheet("background-color: #1a1a1a; color: #e0e0e0; border: 1px solid #444;")
        left_v.addWidget(self.chat_text, stretch=1)

        input_row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.returnPressed.connect(self._send_chat)
        self.chat_input.setEnabled(False)
        input_row.addWidget(self.chat_input)
        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedWidth(80)
        self.send_btn.clicked.connect(self._send_chat)
        input_row.addWidget(self.send_btn)
        left_v.addLayout(input_row)

        main_split.addWidget(left)

        # ── Right (vehicle info) ──
        right = QWidget()
        right.setFixedWidth(320)
        right_v = QVBoxLayout(right)
        right_v.setContentsMargins(0, 0, 0, 0)

        self.vehicle_image_label = QLabel(
            "Vehicle Image\n\nConnect & scan a vehicle\nto look up photos"
        )
        self.vehicle_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vehicle_image_label.setStyleSheet(
            "background-color: #1a1a1a; color: #888; padding: 20px; border: 1px solid #444;"
        )
        self.vehicle_image_label.setFixedHeight(200)
        self.vehicle_image_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vehicle_image_label.mousePressEvent = lambda _e: self._open_vehicle_url()
        right_v.addWidget(self.vehicle_image_label)

        head = QHBoxLayout()
        head.addWidget(self._bold("Vehicle Information"))
        head.addStretch(1)
        self.vin_label = QLabel("")
        self.vin_label.setStyleSheet("font-family: Consolas, monospace; color: #888;")
        head.addWidget(self.vin_label)
        right_v.addLayout(head)

        self.vehicle_info_text = QTextEdit()
        self.vehicle_info_text.setReadOnly(True)
        self.vehicle_info_text.setStyleSheet("background-color: #1a1a1a; color: #e0e0e0; border: 1px solid #444;")
        right_v.addWidget(self.vehicle_info_text, stretch=1)

        main_split.addWidget(right)
        main_split.setStretchFactor(0, 3)
        main_split.setStretchFactor(1, 1)

    @staticmethod
    def _bold(text: str) -> QLabel:
        lbl = QLabel(text)
        f = QFont()
        f.setBold(True)
        lbl.setFont(f)
        return lbl

    # ───────────────────────── Fault reading ─────────────────────────

    def _read_all(self):
        vehicle = self.get_vehicle()
        if not vehicle:
            return

        self.read_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.ai_btn.setEnabled(False)
        self.tree.clear()
        self.progress.setValue(0)
        self.all_dtcs = []

        def thread():
            try:
                vin = vehicle.read_vin()
            except Exception:
                vin = ""
            if vin:
                self.after(0, lambda: self._load_vehicle_info(vin))

            all_dtcs: list[ModuleDTCs] = []
            wanted = ("PCM", "TCM", "ABS", "RCM", "IPC", "BCM", "EPAS", "HVAC",
                      "ACM", "APIM", "DDM", "PDM", "PAM", "GWM", "TPMS", "HCM",
                      "PSCM", "ACC", "FSCM")
            modules = [m for m in FORD_MODULES if m.abbreviation in wanted]

            for i, module in enumerate(modules):
                pct = int((i / len(modules)) * 100)
                self.after(0, lambda p=pct: self.progress.setValue(p))
                self.after(0, lambda n=module.name: self.status_label.setText(f"Reading {n}..."))
                try:
                    client = vehicle.get_uds_client(module)
                    reader = DTCReader(client)
                    dtcs = reader.read_dtcs()
                    if dtcs:
                        all_dtcs.append(ModuleDTCs(
                            module_name=module.name,
                            module_abbrev=module.abbreviation,
                            dtcs=dtcs,
                        ))
                except Exception:
                    pass

            self.all_dtcs = all_dtcs
            total = sum(m.count for m in all_dtcs)
            self.after(0, lambda: self._populate_results(all_dtcs))
            self.after(0, lambda: self.count_label.setText(f"{total} faults found"))
            self.after(0, lambda: self.status_label.setText(
                f"Read complete. {total} faults. Click AI Mechanic to diagnose."))
            self.after(0, lambda: self.progress.setValue(100))
            self.after(0, lambda: self.read_btn.setEnabled(True))
            self.after(0, lambda: self.clear_btn.setEnabled(True))
            self.after(0, lambda: self.ai_btn.setEnabled(True))

        run_thread(thread)

    def _clear_all(self):
        vehicle = self.get_vehicle()
        if not vehicle:
            return
        if not confirm(self, "Clear Faults", "Clear ALL fault codes from ALL modules?"):
            return
        self.clear_btn.setEnabled(False)

        def thread():
            wanted = ("PCM", "TCM", "ABS", "BCM")
            modules = [m for m in FORD_MODULES if m.abbreviation in wanted]
            cleared = 0
            for module in modules:
                try:
                    client = vehicle.get_uds_client(module)
                    DTCReader(client).clear_dtcs()
                    cleared += 1
                except Exception:
                    pass
            self.after(0, lambda: self.status_label.setText(
                f"Faults cleared on {cleared} modules. Re-read to verify."))
            self.after(0, lambda: self.clear_btn.setEnabled(True))

        run_thread(thread)

    def _populate_results(self, all_dtcs: list[ModuleDTCs]):
        self.tree.clear()
        for mod in all_dtcs:
            for dtc in mod.dtcs:
                if dtc.is_active:
                    color, status = "#ff4444", "ACTIVE"
                elif dtc.is_pending:
                    color, status = "#ffaa00", "PENDING"
                else:
                    color, status = "#999999", "STORED"
                description = lookup_dtc(dtc.code)
                item = QTreeWidgetItem([
                    mod.module_abbrev, dtc.code, description, status, dtc.status_text,
                ])
                brush = QBrush(QColor(color))
                for col in range(item.columnCount()):
                    item.setForeground(col, brush)
                item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)
                item.setTextAlignment(3, Qt.AlignmentFlag.AlignCenter)
                self.tree.addTopLevelItem(item)

    # ───────────────────────── Vehicle info ─────────────────────────

    def _load_vehicle_info(self, vin: str):
        self.vin_label.setText(f"VIN: {vin}")
        self.vehicle_info_text.setHtml(
            '<i style="color:#888;">Decoding VIN...</i>'
        )

        def thread():
            info = decode_vin(vin)
            self.after(0, lambda: self._display_vehicle_info(info))
            img_url = get_vehicle_image_url(
                vin, info.get("make", ""), info.get("model", ""), info.get("year", "")
            )
            if img_url:
                self.after(0, lambda: self._show_vehicle_image_link(img_url))

        run_thread(thread)

    def _display_vehicle_info(self, info: dict):
        self.vehicle_info = info
        if info.get("error"):
            self.vehicle_info_text.setHtml(
                f'<b style="color:#cc6600;">VIN: {info.get("vin","?")}</b><br>'
                f'<i style="color:#888;">Could not decode: {info["error"]}</i>'
            )
            return

        html = []
        html.append('<h3 style="color:#ff8800;margin:0;">VIN Breakdown</h3>')
        html.append(f'<p style="color:#cc6600;"><b>VIN:</b> {info.get("vin","?")}</p>')
        year = info.get("year", "?")
        make = info.get("make", "?")
        model = info.get("model", "?")
        html.append(f'<h3 style="color:#ff8800;margin:6px 0;">{year} {make} {model}</h3>')

        sections = [
            ("Drivetrain", [
                ("Engine", info.get("engine")),
                ("Displacement", info.get("displacement_l") and f"{info['displacement_l']}L"),
                ("Cylinders", info.get("cylinders")),
                ("Horsepower", info.get("horsepower") and f"{info['horsepower']} hp"),
                ("Transmission", info.get("transmission")),
                ("Drive Type", info.get("drive_type")),
                ("Fuel Type", info.get("fuel_type")),
            ]),
            ("Body", [
                ("Type", info.get("body_class")),
                ("Doors", info.get("doors")),
                ("Trim", info.get("trim")),
                ("GVWR", info.get("gvwr") and f"{info['gvwr']} lbs"),
            ]),
            ("Manufacturing", [
                ("Built At", info.get("built_at")),
                ("Plant", info.get("plant_name")),
                ("Country", info.get("plant_country")),
            ]),
            ("Safety", [
                ("Brake Type", info.get("brake_type")),
                ("Front Airbags", info.get("airbags_front")),
                ("Side Airbags", info.get("airbags_side")),
            ]),
        ]
        for heading, fields in sections:
            visible = [(lbl, val) for lbl, val in fields if val]
            if not visible:
                continue
            html.append(f'<p style="color:#cc6600;margin-top:8px;"><b>{heading}</b></p>')
            for lbl, val in visible:
                html.append(f'<p style="margin:1px 0;"><b style="color:#cc6600;">&nbsp;&nbsp;{lbl}:</b> {val}</p>')
        if info.get("notes"):
            html.append(f'<p style="margin-top:8px;">Notes: {info["notes"]}</p>')

        self.vehicle_info_text.setHtml("".join(html))

    def _show_vehicle_image_link(self, url: str):
        self._vehicle_image_url = url
        if url.endswith(".jpg") or url.endswith(".png"):
            self.vehicle_image_label.setText("🖼  Vehicle Image Found\n\nClick to view in browser")
        else:
            self.vehicle_image_label.setText("🔍  Vehicle Lookup Page\n\nClick to open in browser")
        self.vehicle_image_label.setStyleSheet(
            "background-color: #1a1a1a; color: #44aaff; padding: 20px; border: 1px solid #444;"
        )

    def _open_vehicle_url(self):
        if self._vehicle_image_url:
            webbrowser.open(self._vehicle_image_url)

    # ───────────────────────── AI chat ─────────────────────────

    def _start_ai_session(self):
        self.ai_btn.setEnabled(False)
        self.chat_input.setEnabled(True)
        self.chat_text.clear()
        self._append_chat("system", "Starting AI Mechanic session...")
        self.chat_status.setText("Connecting...")

        def init_chat():
            try:
                from modules.ai_chat import MechanicChat
                dtc_data = []
                for mod in self.all_dtcs:
                    mod_dtcs = []
                    for d in mod.dtcs:
                        mod_dtcs.append({
                            "code": d.code,
                            "description": lookup_dtc(d.code),
                            "status": "ACTIVE" if d.is_active else ("PENDING" if d.is_pending else "STORED"),
                            "status_text": d.status_text,
                        })
                    dtc_data.append({
                        "module_name": mod.module_name,
                        "module_abbrev": mod.module_abbrev,
                        "dtcs": mod_dtcs,
                    })
                self.chat = MechanicChat()
                self.chat.start_session(self.vehicle_info, dtc_data)
                if dtc_data:
                    response = self.chat.send_message("Start the diagnosis. What do you see?")
                else:
                    response = self.chat.send_message(
                        "Introduce yourself briefly and ask what I'd like help with today."
                    )
                self.after(0, lambda: self._append_chat("mechanic", response))
                self.after(0, lambda: self.chat_status.setText("Connected — ask anything"))
                self.after(0, lambda: self.ai_btn.setEnabled(True))
            except Exception as e:
                self.after(0, lambda: self._append_chat("error", f"Failed to start AI session: {e}"))
                self.after(0, lambda: self.chat_status.setText("Error"))
                self.after(0, lambda: self.ai_btn.setEnabled(True))

        run_thread(init_chat)

    def _send_chat(self):
        if not self.chat:
            return
        user_text = self.chat_input.text().strip()
        if not user_text:
            return
        self.chat_input.clear()
        self.chat_input.setEnabled(False)
        self._append_chat("user", user_text)
        self.chat_status.setText("Thinking...")

        def thread():
            try:
                response = self.chat.send_message(user_text)
                self.after(0, lambda: self._append_chat("mechanic", response))
                self.after(0, lambda: self.chat_status.setText("Connected — ask anything"))
            except Exception as e:
                self.after(0, lambda: self._append_chat("error", f"Error: {e}"))
                self.after(0, lambda: self.chat_status.setText("Error"))
            finally:
                self.after(0, lambda: self.chat_input.setEnabled(True))
                self.after(0, lambda: self.chat_input.setFocus())

        run_thread(thread)

    def _append_chat(self, role: str, text: str):
        from html import escape
        if role == "mechanic":
            prefix = '<span style="color:#ff8800;font-weight:bold;">🔧 Mechanic:</span>'
        elif role == "user":
            prefix = '<span style="color:#44aaff;font-weight:bold;">👤 You:</span>'
        elif role == "error":
            prefix = '<span style="color:#ff4444;font-weight:bold;">⚠</span>'
        else:
            prefix = '<span style="color:#888;font-style:italic;"></span>'
        body = escape(text).replace("\n", "<br>")
        self.chat_text.append(f"<br>{prefix}<br>{body}")
        self.chat_text.verticalScrollBar().setValue(self.chat_text.verticalScrollBar().maximum())
