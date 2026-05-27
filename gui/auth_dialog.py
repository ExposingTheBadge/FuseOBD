"""Sign-in / sign-up dialog shown on first launch.

Two tabs: Sign in / Create account. Shares the same Fuse OBD palette
as the rest of the app. Closes itself on success. The user can still
dismiss the dialog with the window's X — closing it just means they
don't sign in this session (Free-tier features that don't require an
account are still usable; the AI Mechanic stays locked).
"""
from __future__ import annotations

import time
import webbrowser
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from modules import account
from gui import theme as gui_theme


class _AuthWorker(QThread):
    """Runs login() or register() off the UI thread so the dialog
    doesn't freeze while the server is reached."""
    done = pyqtSignal(bool, str, object)  # ok, message, user_dict

    def __init__(self, mode: str, email: str, password: str):
        super().__init__()
        self.mode = mode
        self.email = email
        self.password = password

    def run(self):
        try:
            if self.mode == "register":
                user = account.register(self.email, self.password)
            else:
                user = account.login(self.email, self.password)
            self.done.emit(True, "OK", user)
        except account.AccountError as e:
            self.done.emit(False, e.message, None)
        except Exception as e:
            self.done.emit(False, str(e), None)


class _GoogleProbeWorker(QThread):
    """Async check: is Google OAuth configured server-side?"""
    done = pyqtSignal(bool)

    def run(self):
        try:
            self.done.emit(account.google_available())
        except Exception:
            self.done.emit(False)


class _GoogleBeginWorker(QThread):
    """Starts a Google desktop OAuth flow and emits the kickoff payload."""
    done = pyqtSignal(bool, object, str)  # ok, payload, error

    def run(self):
        try:
            self.done.emit(True, account.google_begin(), "")
        except account.AccountError as e:
            self.done.emit(False, None, e.message)
        except Exception as e:
            self.done.emit(False, None, str(e))


class _GooglePollWorker(QThread):
    """Single poll request — emits status."""
    done = pyqtSignal(str, object, str)  # status ("pending"|"complete"|"error"), user, error

    def __init__(self, device_code: str):
        super().__init__()
        self.device_code = device_code

    def run(self):
        try:
            user = account.google_poll(self.device_code)
            if user is None:
                self.done.emit("pending", None, "")
            else:
                self.done.emit("complete", user, "")
        except account.AccountError as e:
            self.done.emit("error", None, e.message)
        except Exception as e:
            self.done.emit("error", None, str(e))


class AuthDialog(QDialog):
    """Modal sign-in / sign-up dialog.

    Result codes:
        QDialog.DialogCode.Accepted   — user signed in (account.is_signed_in() == True)
        QDialog.DialogCode.Rejected   — user dismissed / skipped
    """

    def __init__(self, parent: Optional[QWidget] = None, allow_skip: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Fuse OBD — Sign in")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.resize(460, 520)
        # `allow_skip` kept for API back-compat but no longer surfaces
        # a visible button — the user can still close the window via X.
        self._allow_skip = allow_skip
        self._worker: Optional[_AuthWorker] = None
        self._google_begin_worker: Optional[_GoogleBeginWorker] = None
        self._google_poll_worker: Optional[_GooglePollWorker] = None
        self._google_device_code: Optional[str] = None
        self._google_poll_timer: Optional[QTimer] = None
        self._google_expires_at: float = 0.0
        self._mode = "login"  # must exist before _build_ui() runs _validate()
        self._build_ui()
        self._show_signin()
        self._probe_google()

    # ── UI ──
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 22)
        root.setSpacing(14)

        # Brand row — brand label centered, theme toggle in the right
        # corner. The toggle flips the whole app theme (so the change
        # persists once the user closes the dialog).
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(0, 0, 0, 0)

        # Left spacer (matches the toggle button on the right so the
        # brand label stays optically centered).
        left_spacer = QLabel("")
        left_spacer.setFixedWidth(36)
        brand_row.addWidget(left_spacer)

        brand_row.addStretch(1)
        brand = QLabel("FUSE · OBD")
        bf = QFont(); bf.setPointSize(11); bf.setBold(True)
        brand.setFont(bf)
        brand.setStyleSheet("color:#ff8800; letter-spacing:3px;")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_row.addWidget(brand)
        brand_row.addStretch(1)

        self.theme_btn = QPushButton(self._theme_glyph())
        self.theme_btn.setFixedSize(36, 28)
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.setToolTip(self._theme_tooltip())
        self.theme_btn.setStyleSheet(
            "QPushButton { background:transparent; border:1px solid #2a2a32; "
            "border-radius:6px; font-size:14px; color:#888; }"
            "QPushButton:hover { color:#fff; border-color:#3a3a44; }"
        )
        self.theme_btn.clicked.connect(self._toggle_theme)
        brand_row.addWidget(self.theme_btn)

        root.addLayout(brand_row)

        self.title = QLabel("Sign in")
        tf = QFont(); tf.setPointSize(18); tf.setBold(True)
        self.title.setFont(tf)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.title)

        self.subtitle = QLabel("Required to use the AI Mechanic.")
        self.subtitle.setStyleSheet("color:#888;")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.subtitle)

        # Mode tabs
        tabs = QHBoxLayout()
        self.tab_signin = QPushButton("Sign in")
        self.tab_signup = QPushButton("Create account")
        for b in (self.tab_signin, self.tab_signup):
            b.setCheckable(True)
            b.setFlat(True)
            b.setStyleSheet(
                "QPushButton { padding:8px 14px; color:#888; border:none; "
                "border-bottom:2px solid #333; background:transparent; font-weight:600; }"
                "QPushButton:checked { color:#ff8800; border-bottom:2px solid #ff8800; }"
                "QPushButton:hover:!checked { color:#fff; }"
            )
        self.tab_signin.clicked.connect(self._show_signin)
        self.tab_signup.clicked.connect(self._show_signup)
        tabs.addWidget(self.tab_signin)
        tabs.addWidget(self.tab_signup)
        root.addLayout(tabs)

        # Google button (hidden until /google/config says it's available)
        self.google_box = QFrame()
        gb_layout = QVBoxLayout(self.google_box)
        gb_layout.setContentsMargins(0, 8, 0, 0)
        gb_layout.setSpacing(8)

        self.google_btn = QPushButton("  Continue with Google")
        self.google_btn.setMinimumHeight(40)
        self.google_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.google_btn.setStyleSheet(
            "QPushButton { background:#ffffff; color:#1f1f1f; font-weight:600; "
            "border:1px solid #ffffff; border-radius:6px; font-size:13px; padding:4px 12px; "
            "text-align:center; }"
            "QPushButton:hover:!disabled { background:#f5f5f5; }"
            "QPushButton:disabled { background:#2a2a32; color:#888; border-color:#2a2a32; }"
        )
        self.google_btn.clicked.connect(self._google_start)
        gb_layout.addWidget(self.google_btn)

        self.google_help = QLabel("")
        self.google_help.setStyleSheet("color:#888; font-size:11px;")
        self.google_help.setWordWrap(True)
        self.google_help.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gb_layout.addWidget(self.google_help)

        divider_row = QHBoxLayout()
        dl1 = QFrame(); dl1.setFrameShape(QFrame.Shape.HLine); dl1.setStyleSheet("color:#2a2a32;")
        dl2 = QFrame(); dl2.setFrameShape(QFrame.Shape.HLine); dl2.setStyleSheet("color:#2a2a32;")
        divider_lbl = QLabel("OR USE EMAIL")
        divider_lbl.setStyleSheet("color:#5d5d68; font-size:10px; letter-spacing:2px;")
        divider_row.addWidget(dl1, 1); divider_row.addWidget(divider_lbl); divider_row.addWidget(dl2, 1)
        gb_layout.addLayout(divider_row)

        self.google_box.setVisible(False)
        root.addWidget(self.google_box)

        # Form
        self.email = QLineEdit()
        self.email.setPlaceholderText("you@example.com")
        self.email.setStyleSheet(
            "QLineEdit { padding:10px 12px; background:#15151a; color:#fff; "
            "border:1px solid #2a2a32; border-radius:6px; font-size:13px; }"
            "QLineEdit:focus { border-color:#ff8800; }"
        )
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw.setStyleSheet(self.email.styleSheet())

        root.addWidget(_field_label("Email"))
        root.addWidget(self.email)
        root.addWidget(_field_label("Password"))
        root.addWidget(self.pw)

        self.error = QLabel("")
        self.error.setStyleSheet("color:#ff5555; font-size:12px;")
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        root.addWidget(self.error)

        # Primary button
        self.go = QPushButton("Sign in")
        self.go.setMinimumHeight(40)
        self.go.setStyleSheet(
            "QPushButton { background:#ff8800; color:#0a0a0b; font-weight:700; "
            "border:none; border-radius:6px; font-size:13px; }"
            "QPushButton:hover:!disabled { background:#ff9c1f; }"
            "QPushButton:disabled { background:#5a3a1a; color:#a08868; }"
        )
        self.go.clicked.connect(self._submit)
        root.addWidget(self.go)

        # Footer — pricing link only. The "Skip for now" button was
        # removed; the user can still close the dialog with the window's
        # X if they don't want to sign in this session.
        root.addStretch(1)
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.pricing_btn = QPushButton("View pricing")
        self.pricing_btn.setFlat(True)
        self.pricing_btn.setStyleSheet("color:#888; padding:6px;")
        self.pricing_btn.clicked.connect(
            lambda: webbrowser.open(account.base_url() + "/pricing"))
        footer.addWidget(self.pricing_btn)
        footer.addStretch(1)
        root.addLayout(footer)

        # Hook Enter on either field to fire submit.
        self.email.returnPressed.connect(self._submit)
        self.pw.returnPressed.connect(self._submit)

        # Live-validate
        for w in (self.email, self.pw):
            w.textChanged.connect(self._validate)
        self._validate()

    # ── Theme toggle ──
    def _theme_glyph(self) -> str:
        # We're "showing what you'll switch to" — sun glyph when in
        # dark mode (clicking switches to light), moon when in light.
        return "\u2600" if gui_theme.current_theme() == "dark" else "\u263E"

    def _theme_tooltip(self) -> str:
        nxt = "light" if gui_theme.current_theme() == "dark" else "dark"
        return f"Switch to {nxt} theme"

    def _toggle_theme(self):
        app = QApplication.instance()
        if app is None:
            return
        gui_theme.toggle_theme(app)
        self.theme_btn.setText(self._theme_glyph())
        self.theme_btn.setToolTip(self._theme_tooltip())

    def _show_signin(self):
        self.title.setText("Sign in")
        self.subtitle.setText("Required to use the AI Mechanic. Free accounts available.")
        self.go.setText("Sign in")
        self.tab_signin.setChecked(True)
        self.tab_signup.setChecked(False)
        self._mode = "login"
        self._validate()

    def _show_signup(self):
        self.title.setText("Create account")
        self.subtitle.setText("Free tier — 25 AI messages / month. No credit card.")
        self.go.setText("Create account")
        self.tab_signin.setChecked(False)
        self.tab_signup.setChecked(True)
        self._mode = "register"
        self._validate()

    def _validate(self):
        email_ok = "@" in self.email.text() and "." in self.email.text().split("@")[-1]
        pw_ok = (len(self.pw.text()) >= 10) if self._mode == "register" else bool(self.pw.text())
        self.go.setEnabled(email_ok and pw_ok)

    def _submit(self):
        if not self.go.isEnabled():
            return
        self.error.setVisible(False)
        self.go.setEnabled(False)
        self.go.setText("Working…")
        self.email.setEnabled(False)
        self.pw.setEnabled(False)
        self._worker = _AuthWorker(self._mode, self.email.text().strip(), self.pw.text())
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_done(self, ok: bool, message: str, _user: object):
        self.email.setEnabled(True)
        self.pw.setEnabled(True)
        self._validate()
        self.go.setText("Sign in" if self._mode == "login" else "Create account")
        if ok:
            # If an admin reset this user's password, force them through
            # a password-change dialog before we let them in.
            if account.must_change_password():
                self._force_password_change()
            self.accept()
        else:
            self.error.setText(message)
            self.error.setVisible(True)

    def _force_password_change(self):
        # Local import keeps this dialog optional/lazy and avoids any
        # circular-import risk when the change-password dialog ever
        # grows its own AuthDialog usage.
        from gui.change_password_dialog import ChangePasswordDialog
        from PyQt6.QtWidgets import QMessageBox
        while account.must_change_password():
            dlg = ChangePasswordDialog(self, forced=True)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                # User dismissed the forced dialog (shouldn't be
                # possible given the close-button is disabled — but be
                # defensive). Sign them out so they can't proceed with
                # the temporary password still active.
                try: account.logout()
                except Exception: pass
                QMessageBox.information(
                    self, "Password change required",
                    "You must change the temporary password before you "
                    "can use Fuse OBD. Signing you out.",
                )
                return

    # ── Google OAuth desktop flow ──
    def _probe_google(self):
        self._google_probe = _GoogleProbeWorker()
        self._google_probe.done.connect(self._on_google_probe_done)
        self._google_probe.start()

    def _on_google_probe_done(self, available: bool):
        self.google_box.setVisible(bool(available))

    def _google_start(self):
        if self._google_begin_worker and self._google_begin_worker.isRunning():
            return
        self.error.setVisible(False)
        self.google_btn.setEnabled(False)
        self.google_btn.setText("  Opening browser…")
        self.google_help.setText("")
        self._google_begin_worker = _GoogleBeginWorker()
        self._google_begin_worker.done.connect(self._on_google_begin)
        self._google_begin_worker.start()

    def _on_google_begin(self, ok: bool, payload, err: str):
        if not ok or not payload:
            self.google_btn.setEnabled(True)
            self.google_btn.setText("  Continue with Google")
            self.error.setText(err or "Could not start Google sign-in.")
            self.error.setVisible(True)
            return
        self._google_device_code = payload.get("device_code")
        self._google_expires_at = time.time() + (int(payload.get("expires_in_ms", 600000)) / 1000.0)
        interval = max(1500, int(payload.get("poll_interval_ms", 2000)))
        try:
            webbrowser.open(payload.get("authorize_url", ""))
        except Exception:
            pass
        self.google_help.setText("Finish in your browser. We'll detect it automatically.")
        self.google_btn.setText("  Waiting for browser…")
        # Start polling
        if self._google_poll_timer:
            self._google_poll_timer.stop()
        self._google_poll_timer = QTimer(self)
        self._google_poll_timer.setInterval(interval)
        self._google_poll_timer.timeout.connect(self._poll_once)
        self._google_poll_timer.start()
        self._poll_once()

    def _poll_once(self):
        if not self._google_device_code:
            return
        if time.time() > self._google_expires_at:
            self._end_google_flow("Sign-in window expired. Try again.")
            return
        if self._google_poll_worker and self._google_poll_worker.isRunning():
            return  # don't overlap requests
        self._google_poll_worker = _GooglePollWorker(self._google_device_code)
        self._google_poll_worker.done.connect(self._on_google_poll)
        self._google_poll_worker.start()

    def _on_google_poll(self, status: str, user_obj, err: str):
        if status == "complete":
            self._end_google_flow(None)
            if account.must_change_password():
                self._force_password_change()
            self.accept()
            return
        if status == "error":
            self._end_google_flow(err or "Google sign-in failed.")
            return
        # status == "pending" — keep polling

    def _end_google_flow(self, error_msg):
        if self._google_poll_timer:
            self._google_poll_timer.stop()
            self._google_poll_timer = None
        self._google_device_code = None
        self.google_btn.setEnabled(True)
        self.google_btn.setText("  Continue with Google")
        self.google_help.setText("")
        if error_msg:
            self.error.setText(error_msg)
            self.error.setVisible(True)


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color:#888; font-size:11px; letter-spacing:1px; "
                      "text-transform:uppercase; margin-top:6px;")
    return lbl


def ensure_signed_in(parent: Optional[QWidget] = None, require: bool = False) -> bool:
    """Show the sign-in dialog if the user isn't signed in. Returns
    True if signed-in by the end of the call.

    `require` is accepted for back-compat but no longer changes the UI
    (there is no Skip button in either mode now)."""
    if account.is_signed_in():
        return True
    dlg = AuthDialog(parent)
    res = dlg.exec()
    return res == QDialog.DialogCode.Accepted and account.is_signed_in()
