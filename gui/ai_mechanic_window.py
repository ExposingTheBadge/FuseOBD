"""Standalone AI Mechanic window — modern chat UI + live Issues pane.

The window:
  • is independent of the main app window, freely resizable & maximisable
  • does NOT require a vehicle to be connected (it can help connect *to* one)
  • shows a chat-bubble conversation on the left
  • shows a persistent Issues list on the right (clickable → detail dialog)
  • auto-refreshes the Issues pane whenever the AI logs a finding
"""
from __future__ import annotations

import threading
from html import escape
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QSize, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QIcon, QTextOption
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QTabWidget, QTextBrowser, QToolButton, QVBoxLayout,
    QWidget,
)

from modules import issues_log
from modules.issues_log import Issue
from modules.ai_chat import MechanicChat


# ── colours ─────────────────────────────────────────────────────────────────


_SEV_COLOR = {
    issues_log.SEVERITY_LOW:  "#5599dd",
    issues_log.SEVERITY_MED:  "#ffaa00",
    issues_log.SEVERITY_HIGH: "#ff7733",
    issues_log.SEVERITY_CRIT: "#ff4444",
}

_KIND_LABEL = {
    issues_log.KIND_VEHICLE:    "Vehicle",
    issues_log.KIND_APP:        "App",
    issues_log.KIND_CONNECTION: "Connection",
    issues_log.KIND_INFO:       "Info",
}


# ── chat bubble ─────────────────────────────────────────────────────────────


class _Bubble(QFrame):
    """A single chat bubble — left-aligned for mechanic, right for user."""

    def __init__(self, role: str, text: str, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Maximum)
        self.role = role

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(8)

        bubble = QFrame()
        bubble.setObjectName("bubble")
        bubble.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        inner = QVBoxLayout(bubble)
        inner.setContentsMargins(12, 8, 12, 8)
        inner.setSpacing(2)

        header = QLabel(self._header(role))
        f = QFont(); f.setBold(True)
        header.setFont(f)
        inner.addWidget(header)

        body = QLabel(self._format_body(text))
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setMaximumWidth(620)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setOpenExternalLinks(True)
        inner.addWidget(body)

        if role == "user":
            outer.addStretch(1)
            outer.addWidget(bubble)
            bubble.setStyleSheet("""
                QFrame#bubble {
                    background-color: #2c4a6e;
                    color: #eaf2ff;
                    border-radius: 12px;
                    border: 1px solid #3a5d87;
                }
                QLabel { color: #eaf2ff; background: transparent; }
            """)
        elif role == "system":
            outer.addStretch(1)
            outer.addWidget(bubble)
            outer.addStretch(1)
            bubble.setStyleSheet("""
                QFrame#bubble {
                    background-color: transparent;
                    border: none;
                }
                QLabel { color: #888; background: transparent; font-style: italic; }
            """)
        elif role == "tool":
            outer.addStretch(1)
            outer.addWidget(bubble)
            outer.addStretch(1)
            bubble.setStyleSheet("""
                QFrame#bubble {
                    background-color: #2a2f24;
                    border: 1px dashed #555;
                    border-radius: 8px;
                }
                QLabel { color: #c0d090; background: transparent; font-family: Consolas, monospace; font-size: 9pt; }
            """)
        elif role == "error":
            outer.addWidget(bubble)
            outer.addStretch(1)
            bubble.setStyleSheet("""
                QFrame#bubble {
                    background-color: #3a1f1f;
                    border: 1px solid #884444;
                    border-radius: 12px;
                }
                QLabel { color: #ffd0d0; background: transparent; }
            """)
        else:  # mechanic / assistant
            outer.addWidget(bubble)
            outer.addStretch(1)
            bubble.setStyleSheet("""
                QFrame#bubble {
                    background-color: #2f2f2f;
                    color: #f2f2f2;
                    border-radius: 12px;
                    border: 1px solid #444;
                }
                QLabel { color: #f2f2f2; background: transparent; }
            """)

    @staticmethod
    def _header(role: str) -> str:
        return {
            "user":     "You",
            "mechanic": "AI Mechanic",
            "system":   "",
            "tool":     "(tool)",
            "error":    "Error",
        }.get(role, role.title())

    @staticmethod
    def _format_body(text: str) -> str:
        if not text:
            return ""
        # Light markdown-ish: bold, code, line breaks, autolink http(s)
        body = escape(text)
        # Bold **x**
        import re as _re
        body = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", body, flags=_re.DOTALL)
        # Inline `code`
        body = _re.sub(
            r"`([^`]+)`",
            r"<code style='background:#1a1a1a;padding:1px 4px;border-radius:3px;'>\1</code>",
            body,
        )
        # Autolink URLs
        body = _re.sub(
            r"(https?://[^\s)]+)",
            r"<a href='\1' style='color:#66ccff;'>\1</a>",
            body,
        )
        body = body.replace("\n", "<br>")
        return body


# ── issues bridge (thread-safe pub/sub for the UI) ──────────────────────────


class _IssuesBridge(QObject):
    changed = pyqtSignal()


# ── window ──────────────────────────────────────────────────────────────────


class AIMechanicWindow(QMainWindow):
    """Stand-alone AI Mechanic window. Created once and reused."""

    closed = pyqtSignal()

    def __init__(self, parent_window: Optional[QWidget] = None,
                 state_provider: Optional[Callable[[], dict]] = None,
                 icon: Optional[QIcon] = None):
        super().__init__(None)  # detached top-level window
        self.setWindowTitle("AI Mechanic — Fuse OBD")
        if icon is not None:
            self.setWindowIcon(icon)
        elif parent_window is not None:
            self.setWindowIcon(parent_window.windowIcon())

        self.resize(1100, 720)
        self.setMinimumSize(700, 480)

        self._parent_window = parent_window
        self._state_provider = state_provider
        self.chat: Optional[MechanicChat] = None
        self._initialised = False

        self._bridge = _IssuesBridge()
        self._bridge.changed.connect(self._refresh_issues)

        self._build_ui()
        self._refresh_issues()
        issues_log.subscribe(self._on_log_event)

    # ── UI ──

    def _build_ui(self):
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # Header bar
        head = QHBoxLayout()
        title = QLabel("AI Mechanic")
        f = QFont(); f.setPointSize(14); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color:#ff8800;")
        head.addWidget(title)
        head.addSpacing(12)
        self.subtitle = QLabel("Diagnose your vehicle, your adapter, or the app itself")
        self.subtitle.setStyleSheet("color:#aaa;")
        head.addWidget(self.subtitle)
        head.addStretch(1)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#ffaa00;")
        head.addWidget(self.status_label)
        root.addLayout(head)

        # Main horizontal split
        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, stretch=1)

        # ── Chat pane ──
        chat_box = QWidget()
        chat_v = QVBoxLayout(chat_box)
        chat_v.setContentsMargins(0, 0, 0, 0)
        chat_v.setSpacing(4)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: 1px solid #444; background:#1a1a1a; }")

        bubbles_host = QWidget()
        bubbles_host.setStyleSheet("background:#1a1a1a;")
        self.bubbles_layout = QVBoxLayout(bubbles_host)
        self.bubbles_layout.setContentsMargins(10, 10, 10, 10)
        self.bubbles_layout.setSpacing(2)
        self.bubbles_layout.addStretch(1)
        self.scroll.setWidget(bubbles_host)
        chat_v.addWidget(self.scroll, stretch=1)

        # Composer
        composer = QFrame()
        composer.setStyleSheet("QFrame { background:#222; border-top:1px solid #444; }")
        comp_l = QHBoxLayout(composer)
        comp_l.setContentsMargins(8, 8, 8, 8)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(
            "Ask the AI Mechanic anything — about your car, your OBD adapter, "
            "or this app. Shift+Enter for newline, Enter to send."
        )
        self.input.setFixedHeight(80)
        self.input.setStyleSheet(
            "QPlainTextEdit { background:#1a1a1a; color:#eaeaea; border:1px solid #444; "
            "border-radius:4px; padding:6px; }"
        )
        self.input.installEventFilter(self)
        comp_l.addWidget(self.input, stretch=1)

        btn_col = QVBoxLayout()
        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedWidth(110)
        self.send_btn.setFixedHeight(36)
        self.send_btn.setStyleSheet(
            "QPushButton { background:#cc6a00; color:white; border:none; border-radius:4px; "
            "font-weight:bold; } QPushButton:hover { background:#ff8800; }"
        )
        self.send_btn.clicked.connect(self._send_message)
        btn_col.addWidget(self.send_btn)
        self.clear_btn = QPushButton("Reset Chat")
        self.clear_btn.setFixedWidth(110)
        self.clear_btn.clicked.connect(self._reset_chat)
        btn_col.addWidget(self.clear_btn)
        btn_col.addStretch(1)
        comp_l.addLayout(btn_col)
        chat_v.addWidget(composer)

        split.addWidget(chat_box)

        # ── Issues pane ──
        issues_box = QWidget()
        iv = QVBoxLayout(issues_box)
        iv.setContentsMargins(0, 0, 0, 0)
        iv.setSpacing(4)

        hdr = QHBoxLayout()
        ititle = QLabel("Issues & Findings")
        f2 = QFont(); f2.setBold(True); f2.setPointSize(11)
        ititle.setFont(f2)
        ititle.setStyleSheet("color:#ff8800;")
        hdr.addWidget(ititle)
        hdr.addStretch(1)
        self.issues_count = QLabel("0")
        self.issues_count.setStyleSheet(
            "color:#fff; background:#444; padding:1px 8px; border-radius:8px;"
        )
        hdr.addWidget(self.issues_count)
        clear_btn = QToolButton()
        clear_btn.setText("Clear All")
        clear_btn.setStyleSheet("color:#888;")
        clear_btn.clicked.connect(self._clear_issues)
        hdr.addWidget(clear_btn)
        iv.addLayout(hdr)

        self.issues_list = QListWidget()
        self.issues_list.setStyleSheet(
            "QListWidget { background:#1a1a1a; color:#e0e0e0; border:1px solid #444; }"
            "QListWidget::item { padding: 8px; border-bottom: 1px solid #2a2a2a; }"
            "QListWidget::item:hover { background:#252525; }"
            "QListWidget::item:selected { background:#2c4a6e; }"
        )
        self.issues_list.itemActivated.connect(self._open_issue_detail)
        self.issues_list.itemDoubleClicked.connect(self._open_issue_detail)
        iv.addWidget(self.issues_list, stretch=1)

        hint = QLabel("Click any item for a 'for nerds' / 'for dummies' explanation.")
        hint.setStyleSheet("color:#888; font-size:8.5pt;")
        hint.setWordWrap(True)
        iv.addWidget(hint)

        split.addWidget(issues_box)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([700, 300])

        self.setCentralWidget(central)

    def eventFilter(self, obj, event):
        # Enter sends, Shift+Enter inserts newline.
        if obj is self.input and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False
                self._send_message()
                return True
        return super().eventFilter(obj, event)

    # ── lifecycle ──

    def show_with_context(self, vehicle_info: Optional[dict] = None,
                          dtc_data: Optional[list] = None):
        """Open the window and (re)start a session with optional vehicle context."""
        was_hidden = self.isHidden()
        if was_hidden:
            self.show()
        self.raise_()
        self.activateWindow()

        # Start a fresh session whenever new context is provided OR there's no chat yet.
        needs_start = (
            not self._initialised
            or vehicle_info is not None
            or dtc_data is not None
        )
        if needs_start:
            self._initialised = True
            self._start_chat_session(vehicle_info, dtc_data)

    def closeEvent(self, event):
        try:
            issues_log.unsubscribe(self._on_log_event)
        except Exception:
            pass
        self.closed.emit()
        super().closeEvent(event)

    # ── chat actions ──

    def _start_chat_session(self, vehicle_info: Optional[dict],
                            dtc_data: Optional[list]):
        if not MechanicChat.is_configured():
            self._clear_bubbles()
            self._append_bubble(
                "error",
                "AI Mechanic is not configured.\n\n"
                "Set the environment variable MOD_ANTHROPIC_AUTH_TOKEN "
                "(or MOD_ANTHROPIC_API_KEY) in Windows system environment, "
                "then restart Fuse OBD.\n\n"
                "Optional vars: MOD_ANTHROPIC_BASE_URL, MOD_ANTHROPIC_MODEL, "
                "MOD_ANTHROPIC_DEFAULT_OPUS_MODEL."
            )
            self.status_label.setText("Not configured")
            return

        self._clear_bubbles()
        self._append_bubble("system", "Starting AI Mechanic session...")
        self.status_label.setText("Connecting...")
        self.send_btn.setEnabled(False)
        self.input.setEnabled(False)

        self.chat = MechanicChat(state_provider=self._state_provider,
                                 on_tool_call=self._on_tool_call)
        try:
            self.chat.start_session(vehicle_info or {}, dtc_data or [])
        except Exception as e:
            self._append_bubble("error", f"Could not start session: {e}")
            self.status_label.setText("Error")
            self.send_btn.setEnabled(True)
            self.input.setEnabled(True)
            return

        def worker():
            try:
                response = self.chat.kick_off()
            except Exception as e:
                response = f"Failed to start session: {e}"
            self._post_to_ui(lambda: self._on_assistant_reply(response, kicked_off=True))

        threading.Thread(target=worker, daemon=True).start()

    def _send_message(self):
        if not self.chat:
            self._start_chat_session(None, None)
            return
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        self._append_bubble("user", text)
        self.status_label.setText("Thinking...")
        self.send_btn.setEnabled(False)
        self.input.setEnabled(False)

        def worker():
            try:
                response = self.chat.send_message(text)
            except Exception as e:
                response = f"Error: {e}"
                issues_log.log_exception("AI Mechanic chat failure", e,
                                         kind=issues_log.KIND_APP,
                                         source="ai_mechanic_window")
            self._post_to_ui(lambda: self._on_assistant_reply(response))

        threading.Thread(target=worker, daemon=True).start()

    def _reset_chat(self):
        if QMessageBox.question(self, "Reset Chat",
                                "Start a new AI Mechanic conversation?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                ) != QMessageBox.StandardButton.Yes:
            return
        self.chat = None
        self._initialised = False
        self._clear_bubbles()
        self._append_bubble("system", "Chat reset. Type a question to begin.")
        self.status_label.setText("")

    def _on_assistant_reply(self, response: str, *, kicked_off: bool = False):
        if response:
            self._append_bubble("mechanic", response)
        self.status_label.setText("Ready")
        self.send_btn.setEnabled(True)
        self.input.setEnabled(True)
        self.input.setFocus()

    def _on_tool_call(self, tool_name: str, params: dict):
        # Surface tool calls as small status updates so the user sees the AI working.
        readable = {
            "search_web": f"searching the web for: {params.get('query','')}",
            "fetch_page": f"fetching {params.get('url','')}",
            "list_adapters": "listing OBD adapters",
            "list_windows_serial_devices": "querying Windows serial devices",
            "list_windows_usb_devices": "querying Windows USB devices",
            "scan_local_network_obd": "scanning for WiFi ELM327 adapters",
            "read_app_debug_log": "reading the app debug log",
            "get_app_info": "reading the app state",
            "log_issue": f"logging an issue — {params.get('title','')}",
        }.get(tool_name, tool_name)
        self._post_to_ui(lambda: self.status_label.setText(f"Mechanic is {readable}..."))

    # ── bubbles ──

    def _append_bubble(self, role: str, text: str):
        bubble = _Bubble(role, text)
        # insert before the trailing stretch
        index = self.bubbles_layout.count() - 1
        self.bubbles_layout.insertWidget(index, bubble)
        # auto-scroll to bottom
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        # one more time after layout settles
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    def _clear_bubbles(self):
        while self.bubbles_layout.count() > 1:
            item = self.bubbles_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    # ── issues pane ──

    def _on_log_event(self, _kind, _payload):
        # Marshal to UI thread.
        self._bridge.changed.emit()

    def _refresh_issues(self):
        issues = issues_log.load_issues(limit=200)
        self.issues_list.clear()
        for issue in issues:
            text = f"{issue.title}"
            item = QListWidgetItem(text)
            sev = _SEV_COLOR.get(issue.severity, "#888")
            kind_lbl = _KIND_LABEL.get(issue.kind, issue.kind.title())
            tooltip = (
                f"[{kind_lbl}] {issue.title}\n"
                f"Severity: {issue.severity}\n"
                f"Logged: {issue.time_str()}\n\n"
                f"{issue.summary_simple}"
            )
            item.setToolTip(tooltip)
            item.setData(Qt.ItemDataRole.UserRole, issue)
            # Compose a richer display via setText with metadata
            item.setText(f"●  {issue.title}\n   {kind_lbl} · {issue.severity.upper()} · {issue.time_str()}")
            item.setForeground(Qt.GlobalColor.lightGray)
            f = QFont(); f.setBold(True)
            item.setFont(f)
            # Severity dot color via item icon (simple coloured pixmap)
            from PyQt6.QtGui import QPixmap, QPainter, QColor
            pix = QPixmap(12, 12)
            pix.fill(Qt.GlobalColor.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QColor(sev))
            p.setPen(QColor(sev))
            p.drawEllipse(1, 1, 10, 10)
            p.end()
            item.setIcon(QIcon(pix))
            self.issues_list.addItem(item)
        self.issues_count.setText(str(len(issues)))

    def _open_issue_detail(self, item: QListWidgetItem):
        issue: Issue = item.data(Qt.ItemDataRole.UserRole)
        if issue is None:
            return
        dlg = _IssueDetailDialog(issue, self)
        dlg.exec()

    def _clear_issues(self):
        if QMessageBox.question(
            self, "Clear All Issues",
            "Remove every entry from the Issues log? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        issues_log.clear_issues()
        self._refresh_issues()

    # ── thread hop helper ──

    def _post_to_ui(self, fn: Callable):
        """Schedule a callable on the Qt main thread."""
        from PyQt6.QtCore import QMetaObject, Qt as _Qt
        # The cleanest cross-thread invocation is via a 0-shot QTimer
        # owned by a UI object (this window itself).
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, fn)


# ── issue detail dialog ─────────────────────────────────────────────────────


class _IssueDetailDialog(QDialog):
    """Small dialog with two tabs: 'For Dummies' and 'For Nerds'."""

    def __init__(self, issue: Issue, parent=None):
        super().__init__(parent)
        self.setWindowTitle(issue.title)
        self.resize(620, 460)

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 10)
        v.setSpacing(8)

        # Header
        head = QHBoxLayout()
        title = QLabel(issue.title)
        f = QFont(); f.setPointSize(13); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color:#ff8800;")
        title.setWordWrap(True)
        head.addWidget(title, stretch=1)
        v.addLayout(head)

        meta = QLabel(
            f"<span style='color:#aaa;'>"
            f"{_KIND_LABEL.get(issue.kind, issue.kind.title())} · "
            f"Severity: <b style='color:{_SEV_COLOR.get(issue.severity,'#aaa')};'>{issue.severity.upper()}</b> · "
            f"Logged {issue.time_str()}"
            f"</span>"
        )
        meta.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(meta)

        tabs = QTabWidget()

        simple = QTextBrowser()
        simple.setOpenExternalLinks(True)
        simple.setPlainText(issue.summary_simple or "(no plain-English summary)")
        simple.setStyleSheet("QTextBrowser { background:#1d1d1d; color:#eaeaea; border:1px solid #444; padding:8px; font-size:10pt; }")
        tabs.addTab(simple, "Plain English")

        nerd = QTextBrowser()
        nerd.setOpenExternalLinks(True)
        nerd.setPlainText(issue.summary_technical or "(no technical detail)")
        nerd.setStyleSheet("QTextBrowser { background:#101010; color:#c0e0c0; border:1px solid #444; padding:8px; font-family: Consolas, monospace; font-size:9pt; }")
        tabs.addTab(nerd, "For Nerds")

        if issue.context:
            ctx = QTextBrowser()
            import json as _json
            ctx.setPlainText(_json.dumps(issue.context, indent=2))
            ctx.setStyleSheet("QTextBrowser { background:#101010; color:#c0c0e0; border:1px solid #444; padding:8px; font-family: Consolas, monospace; font-size:9pt; }")
            tabs.addTab(ctx, "Context")

        v.addWidget(tabs, stretch=1)

        # Buttons
        row = QHBoxLayout()
        row.addStretch(1)
        delete_btn = QPushButton("Delete Issue")
        delete_btn.clicked.connect(lambda: self._delete(issue))
        row.addWidget(delete_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        v.addLayout(row)

    def _delete(self, issue: Issue):
        if QMessageBox.question(
            self, "Delete Issue",
            f"Remove '{issue.title}' from the issues log?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            issues_log.remove_issue(issue.id)
            self.accept()
