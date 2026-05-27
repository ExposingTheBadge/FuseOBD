"""Change-password dialog for signed-in users.

Used in two situations:
  1. The user opens it themselves from the Account tab to rotate
     their password.
  2. The app launches it automatically right after sign-in when the
     server has flagged `must_change_password=True` (admin reset). In
     that mode the dialog is non-skippable.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QWidget,
)

from modules import account


class _ChangeWorker(QThread):
    done = pyqtSignal(bool, str)  # ok, message

    def __init__(self, current_pw: str, new_pw: str):
        super().__init__()
        self.current_pw = current_pw
        self.new_pw = new_pw

    def run(self):
        try:
            account.change_password(self.current_pw, self.new_pw)
            self.done.emit(True, "Password updated.")
        except account.AccountError as e:
            self.done.emit(False, e.message)
        except Exception as e:
            self.done.emit(False, str(e))


class ChangePasswordDialog(QDialog):
    """Modal dialog. Returns QDialog.DialogCode.Accepted on success."""

    def __init__(self, parent: Optional[QWidget] = None, *, forced: bool = False):
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowTitle(
            "Set a new password" if forced else "Change password"
        )
        # `forced` means the server admin reset this user's password and
        # the user must set a new one before continuing. In that mode we
        # disable the close button so the user can't slip past it. They
        # can still log out from the previous screen if they want to.
        self._forced = forced
        if forced:
            self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self._worker: Optional[_ChangeWorker] = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(10)

        title = QLabel(
            "Set a new password" if self._forced else "Change your password"
        )
        tf = QFont(); tf.setPointSize(15); tf.setBold(True)
        title.setFont(tf)
        root.addWidget(title)

        if self._forced:
            note = QLabel(
                "An administrator reset your account password. Choose a "
                "new password below to continue."
            )
        else:
            note = QLabel(
                "Choose a strong password. After saving, every other "
                "device signed into this account will be signed out."
            )
        note.setStyleSheet("color:#888; font-size:12px;")
        note.setWordWrap(True)
        root.addWidget(note)

        root.addWidget(_field_label("Current password" if not self._forced
                                    else "Temporary password from admin"))
        self.current_pw = QLineEdit()
        self.current_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.current_pw.setPlaceholderText(
            "What you used to sign in"
        )
        self._style_input(self.current_pw)
        root.addWidget(self.current_pw)

        root.addWidget(_field_label("New password (min 10 characters)"))
        self.new_pw = QLineEdit()
        self.new_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._style_input(self.new_pw)
        root.addWidget(self.new_pw)

        root.addWidget(_field_label("Confirm new password"))
        self.confirm_pw = QLineEdit()
        self.confirm_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._style_input(self.confirm_pw)
        root.addWidget(self.confirm_pw)

        # Show/hide passwords toggle (single switch toggles all three).
        toggle_row = QHBoxLayout()
        self.show_pw = QPushButton("Show passwords")
        self.show_pw.setCheckable(True)
        self.show_pw.setFlat(True)
        self.show_pw.setStyleSheet(
            "QPushButton { color:#888; padding:4px; }"
            "QPushButton:checked { color:#ff8800; }"
        )
        self.show_pw.toggled.connect(self._toggle_show)
        toggle_row.addWidget(self.show_pw)
        toggle_row.addStretch(1)
        root.addLayout(toggle_row)

        self.error = QLabel("")
        self.error.setStyleSheet("color:#ff5555; font-size:12px;")
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        root.addWidget(self.error)

        # Buttons
        btn_row = QHBoxLayout()
        if not self._forced:
            self.cancel_btn = QPushButton("Cancel")
            self.cancel_btn.setFlat(True)
            self.cancel_btn.setStyleSheet("color:#888; padding:6px 12px;")
            self.cancel_btn.clicked.connect(self.reject)
            btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch(1)
        self.go = QPushButton("Update password")
        self.go.setMinimumHeight(36)
        self.go.setStyleSheet(
            "QPushButton { background:#ff8800; color:#0a0a0b; font-weight:700; "
            "border:none; border-radius:6px; padding:6px 18px; }"
            "QPushButton:hover:!disabled { background:#ff9c1f; }"
            "QPushButton:disabled { background:#5a3a1a; color:#a08868; }"
        )
        self.go.clicked.connect(self._submit)
        btn_row.addWidget(self.go)
        root.addLayout(btn_row)

        for w in (self.current_pw, self.new_pw, self.confirm_pw):
            w.textChanged.connect(self._validate)
            w.returnPressed.connect(self._submit)
        self._validate()

    @staticmethod
    def _style_input(le: QLineEdit) -> None:
        le.setStyleSheet(
            "QLineEdit { padding:10px 12px; background:#15151a; color:#fff; "
            "border:1px solid #2a2a32; border-radius:6px; font-size:13px; }"
            "QLineEdit:focus { border-color:#ff8800; }"
            "QLineEdit:disabled { background:#0e0e12; color:#666; }"
        )

    def _toggle_show(self, checked: bool):
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.current_pw.setEchoMode(mode)
        self.new_pw.setEchoMode(mode)
        self.confirm_pw.setEchoMode(mode)
        self.show_pw.setText("Hide passwords" if checked else "Show passwords")

    def _validate(self):
        cur = self.current_pw.text()
        new = self.new_pw.text()
        conf = self.confirm_pw.text()
        ok = bool(cur) and len(new) >= 10 and new == conf and new != cur
        self.go.setEnabled(ok)
        if conf and conf != new:
            self.error.setText("New password and confirmation don't match.")
            self.error.setVisible(True)
        elif new and new == cur and cur:
            self.error.setText("New password must be different from the current one.")
            self.error.setVisible(True)
        else:
            self.error.setVisible(False)

    def _submit(self):
        if not self.go.isEnabled():
            return
        self.error.setVisible(False)
        self.go.setEnabled(False)
        self.go.setText("Updating…")
        for w in (self.current_pw, self.new_pw, self.confirm_pw):
            w.setEnabled(False)
        self._worker = _ChangeWorker(
            self.current_pw.text(), self.new_pw.text())
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_done(self, ok: bool, message: str):
        for w in (self.current_pw, self.new_pw, self.confirm_pw):
            w.setEnabled(True)
        self.go.setText("Update password")
        self._validate()
        if ok:
            self.accept()
        else:
            self.error.setText(message)
            self.error.setVisible(True)

    # Forced mode: swallow Esc so users can't bypass the dialog.
    def keyPressEvent(self, event):
        if self._forced and event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color:#888; font-size:11px; letter-spacing:1px; "
                      "text-transform:uppercase; margin-top:6px;")
    return lbl
