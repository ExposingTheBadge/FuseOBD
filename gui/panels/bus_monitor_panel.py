"""Bus Monitor — real-time view of every byte the app sends or receives.

Subscribes to `modules.issues_log` log-line events and streams them
into a colour-coded list view. Equivalent to running `tail -f` on
`fuse_obd.log` but inside the app, with category filters and a search
box.

Subscribers run in the writer thread; results are marshalled onto the
UI thread via a `pyqtSignal(object)`.
"""
from __future__ import annotations

import time
from collections import deque

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QFont, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from modules import issues_log


_TAG_COLOR = {
    "APP":  "#9aa3af",
    "ERR":  "#ff5c5c",
    "ADPT": "#ffaa55",
    "CONN": "#55ddaa",
    "TX":   "#88c4ff",
    "RX":   "#c389ff",
    "PROT": "#ffd166",
    "AI":   "#7afff0",
    "HTTP": "#ffc7e3",
    "GUI":  "#bfbfbf",
}


class _Bridge(QObject):
    """Cross-thread signal: the log writer emits, the UI receives."""
    incoming = pyqtSignal(object)


class BusMonitorPanel(QWidget):
    """Real-time log line viewer with filters and search."""

    _MAX_LINES = 5000  # keep memory bounded; older lines drop off the top

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridge = _Bridge()
        self._bridge.incoming.connect(self._append_line)
        self._buffer: deque[tuple[str, str, float]] = deque(maxlen=self._MAX_LINES)
        self._paused = False
        self._tag_visibility: dict[str, bool] = {t: True for t in _TAG_COLOR}
        self._search = ""
        self._build_ui()
        # Subscribe AFTER UI is built so any in-flight log lines have somewhere to land.
        issues_log.subscribe_log(self._on_log_line)

    # ── lifecycle ──

    def closeEvent(self, event):
        try:
            issues_log.unsubscribe_log(self._on_log_line)
        except Exception:
            pass
        super().closeEvent(event)

    # ── log subscriber (writer thread) ──

    def _on_log_line(self, tag: str, message: str, ts: float) -> None:
        # Marshal onto UI thread via signal.
        self._bridge.incoming.emit((tag, message, ts))

    # ── UI ──

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Top bar: title, pause, clear, open log
        top = QHBoxLayout()
        title = QLabel("Bus Monitor — live byte stream")
        f = QFont()
        f.setPointSize(11)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color:#ff8800;")
        top.addWidget(title)
        top.addSpacing(12)

        self.counter = QLabel("0 lines")
        self.counter.setStyleSheet("color:#888;")
        top.addWidget(self.counter)
        top.addStretch(1)

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self._on_pause)
        top.addWidget(self.pause_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._clear)
        top.addWidget(self.clear_btn)

        self.open_log_btn = QPushButton("Open Log File")
        self.open_log_btn.setToolTip("Open fuse_obd.log in your default text editor.")
        self.open_log_btn.clicked.connect(self._open_log)
        top.addWidget(self.open_log_btn)

        root.addLayout(top)

        # Filters row: one checkbox per tag + auto-scroll toggle
        filters = QHBoxLayout()
        filters.setSpacing(4)
        filters.addWidget(QLabel("Show:"))
        for tag in _TAG_COLOR:
            cb = QCheckBox(tag.strip())
            cb.setChecked(True)
            cb.setStyleSheet(
                f"QCheckBox {{ color:{_TAG_COLOR[tag]}; padding:2px 4px; }}"
            )
            cb.toggled.connect(lambda checked, t=tag: self._on_filter(t, checked))
            filters.addWidget(cb)
        filters.addStretch(1)
        self.autoscroll_cb = QCheckBox("Auto-scroll")
        self.autoscroll_cb.setChecked(True)
        self.autoscroll_cb.setStyleSheet("color:#cfcfcf;")
        filters.addWidget(self.autoscroll_cb)
        root.addLayout(filters)

        # Search box
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Find:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "Filter lines containing this text (case-insensitive). "
            "Leave blank for all."
        )
        self.search_edit.textChanged.connect(self._on_search)
        search_row.addWidget(self.search_edit, stretch=1)
        root.addLayout(search_row)

        # Main view: monospace, dark, scrollable
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.view.setUndoRedoEnabled(False)
        self.view.setMaximumBlockCount(self._MAX_LINES)
        self.view.setStyleSheet(
            "QPlainTextEdit { background:#0c0c0c; color:#d8d8d8; "
            "font-family: 'Cascadia Code', Consolas, monospace; "
            "font-size: 9.5pt; border:1px solid #333; }"
        )
        root.addWidget(self.view, stretch=1)

        # Footer hint
        hint = QLabel(
            "Tip: every adapter byte appears as [TX  ] / [RX  ]. "
            "Vehicle CAN frames show up as [PROT]. Errors are [ERR ]. "
            "AI Mechanic activity is [AI  ]."
        )
        hint.setStyleSheet("color:#666; font-size:8.5pt;")
        hint.setWordWrap(True)
        root.addWidget(hint)

    # ── line handling ──

    def _append_line(self, payload):
        tag, message, ts = payload
        self._buffer.append((tag, message, ts))
        self.counter.setText(f"{len(self._buffer)} lines")
        if self._paused:
            return
        if not self._tag_visibility.get(tag, True):
            return
        if self._search and self._search not in message.lower() and self._search not in tag.lower():
            return
        self._write_line(tag, message, ts)

    def _write_line(self, tag: str, message: str, ts: float):
        ts_str = time.strftime("%H:%M:%S", time.localtime(ts)) + f".{int((ts % 1) * 1000):03d}"
        color = _TAG_COLOR.get(tag, "#cfcfcf")
        # Use HTML so each line can be colour-coded.
        from html import escape as _esc
        line = (
            f"<span style='color:#666;'>{ts_str}</span> "
            f"<span style='color:{color}; font-weight:bold;'>[{tag:<4}]</span> "
            f"<span style='color:#d8d8d8;'>{_esc(message)}</span>"
        )
        self.view.appendHtml(line)
        if self.autoscroll_cb.isChecked():
            self.view.moveCursor(QTextCursor.MoveOperation.End)

    # ── controls ──

    def _on_pause(self, checked: bool):
        self._paused = checked
        self.pause_btn.setText("Resume" if checked else "Pause")
        if not checked:
            # Re-render the buffer when un-pausing so the view catches up.
            self._rerender()

    def _on_filter(self, tag: str, checked: bool):
        self._tag_visibility[tag] = checked
        self._rerender()

    def _on_search(self, text: str):
        self._search = (text or "").strip().lower()
        self._rerender()

    def _rerender(self):
        self.view.clear()
        for tag, message, ts in self._buffer:
            if not self._tag_visibility.get(tag, True):
                continue
            if self._search and self._search not in message.lower() and self._search not in tag.lower():
                continue
            self._write_line(tag, message, ts)

    def _clear(self):
        self._buffer.clear()
        self.view.clear()
        self.counter.setText("0 lines")

    def _open_log(self):
        import os, sys, subprocess
        path = issues_log.app_debug_log_path()
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass
