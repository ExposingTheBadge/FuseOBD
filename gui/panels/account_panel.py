"""Account tab — current sign-in, tier, AI quota, machines, upgrade.

All data comes from modules.account. Refreshes itself on a 30-second
timer and immediately whenever AuthDialog is dismissed.
"""
from __future__ import annotations

import webbrowser
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from modules import account
from gui.auth_dialog import AuthDialog


# Feature display names — must match server-side keys exactly.
_FEATURE_LABELS = [
    ("vin_read",        "VIN read"),
    ("dtc_read",        "DTC read"),
    ("dtc_clear",       "DTC clear"),
    ("module_scanner",  "Module Scanner"),
    ("pats",            "Key Programming (PATS)"),
    ("asbuilt",         "Factory Settings (As-Built)"),
    ("live_data",       "Live Data Monitor"),
    ("security_access", "Security Access (UDS 0x27)"),
    ("ai_mechanic",     "AI Mechanic"),
    ("bus_monitor",     "Bus Monitor"),
]


class _RefreshThread(QThread):
    done = pyqtSignal(bool, object, str)  # ok, user_dict_or_None, error_message

    def run(self):
        try:
            user = account.refresh()
            self.done.emit(True, user, "")
        except account.AccountError as e:
            self.done.emit(False, None, e.message)
        except Exception as e:
            self.done.emit(False, None, str(e))


class _UpgradeRequestThread(QThread):
    done = pyqtSignal(bool, str)

    def __init__(self, note: str):
        super().__init__()
        self.note = note

    def run(self):
        try:
            account.request_upgrade(self.note)
            self.done.emit(True, "")
        except account.AccountError as e:
            self.done.emit(False, e.message)
        except Exception as e:
            self.done.emit(False, str(e))


class AccountPanel(QWidget):
    """Account tab. Always present; content depends on sign-in state."""

    # Emitted when sign-in state changes (sign-in, sign-out, tier change).
    # Main window connects to this so it can refresh tab-locking.
    state_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._refresh_thread: Optional[_RefreshThread] = None
        self._upgrade_thread: Optional[_UpgradeRequestThread] = None
        self._build_ui()

        # Auto-refresh every 30 s while the tab is visible.
        self._timer = QTimer(self)
        self._timer.setInterval(30000)
        self._timer.timeout.connect(self._refresh_async)
        self._timer.start()

        # First render.
        self.render_state()

    # ── UI ──
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        inner = QWidget()
        scroll.setWidget(inner)
        self._inner = QVBoxLayout(inner)
        self._inner.setContentsMargins(28, 22, 28, 22)
        self._inner.setSpacing(18)

        # ── Signed-out view ──
        self.signed_out_box = QFrame()
        so = QVBoxLayout(self.signed_out_box)
        so.setContentsMargins(0, 0, 0, 0)
        so.setSpacing(10)

        lbl = QLabel("Not signed in")
        f = QFont(); f.setPointSize(18); f.setBold(True)
        lbl.setFont(f)
        so.addWidget(lbl)

        msg = QLabel(
            "Sign in to use the AI Mechanic and unlock Pro features.\n"
            "Free accounts include VIN read, DTC read, and DTC clear."
        )
        msg.setStyleSheet("color:#aaa;")
        msg.setWordWrap(True)
        so.addWidget(msg)

        btn_row = QHBoxLayout()
        self.signin_btn = QPushButton("Sign in / Create account")
        self.signin_btn.setMinimumHeight(40)
        self.signin_btn.setStyleSheet(
            "QPushButton { background:#ff8800; color:#0a0a0b; font-weight:700; "
            "border:none; border-radius:6px; padding:8px 18px; font-size:13px; }"
            "QPushButton:hover { background:#ff9c1f; }"
        )
        self.signin_btn.clicked.connect(self._open_auth_dialog)
        btn_row.addWidget(self.signin_btn)

        self.pricing_btn = QPushButton("View pricing")
        self.pricing_btn.setMinimumHeight(40)
        self.pricing_btn.setStyleSheet(
            "QPushButton { background:transparent; color:#ccc; border:1px solid #2e2e36; "
            "border-radius:6px; padding:8px 18px; font-size:13px; }"
            "QPushButton:hover { background:#15151a; color:#fff; }"
        )
        self.pricing_btn.clicked.connect(self._open_pricing)
        btn_row.addWidget(self.pricing_btn)
        btn_row.addStretch(1)
        so.addLayout(btn_row)

        self._inner.addWidget(self.signed_out_box)

        # ── Signed-in view ──
        self.signed_in_box = QFrame()
        self.signed_in_box.setVisible(False)
        si = QVBoxLayout(self.signed_in_box)
        si.setContentsMargins(0, 0, 0, 0)
        si.setSpacing(14)

        # Greeting + email
        self.greet = QLabel("Welcome.")
        gf = QFont(); gf.setPointSize(18); gf.setBold(True)
        self.greet.setFont(gf)
        si.addWidget(self.greet)

        self.email_lbl = QLabel("")
        self.email_lbl.setStyleSheet("color:#8a8a92; font-family:Consolas,monospace;")
        si.addWidget(self.email_lbl)

        # Tier card
        self.tier_card = QFrame()
        self.tier_card.setStyleSheet(
            "QFrame { background:#15151a; border:1px solid #22222a; border-radius:10px; }"
        )
        tc = QGridLayout(self.tier_card)
        tc.setContentsMargins(20, 18, 20, 18)
        tc.setHorizontalSpacing(20)
        tc.setVerticalSpacing(8)

        self.tier_badge = QLabel("Free")
        self.tier_badge.setStyleSheet(self._badge_style("free"))
        self.tier_badge.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.tier_title = QLabel("Free plan")
        ttf = QFont(); ttf.setPointSize(16); ttf.setBold(True)
        self.tier_title.setFont(ttf)

        self.tier_tag = QLabel("VIN, DTC read, and DTC clear.")
        self.tier_tag.setStyleSheet("color:#8a8a92;")

        tc.addWidget(self.tier_badge, 0, 0, alignment=Qt.AlignmentFlag.AlignLeft)
        tc.addWidget(self.tier_title, 1, 0, 1, 2)
        tc.addWidget(self.tier_tag, 2, 0, 1, 2)

        # Quota row
        self.quota_lbl = QLabel("AI Mechanic this month:")
        self.quota_lbl.setStyleSheet("color:#8a8a92; font-family:Consolas,monospace; "
                                      "font-size:11px; margin-top:10px;")
        tc.addWidget(self.quota_lbl, 3, 0, 1, 2)

        self.quota_bar = QProgressBar()
        self.quota_bar.setTextVisible(False)
        self.quota_bar.setFixedHeight(8)
        self.quota_bar.setStyleSheet(
            "QProgressBar { background:#0a0a0b; border:none; border-radius:4px; }"
            "QProgressBar::chunk { background:#ff8800; border-radius:4px; }"
        )
        tc.addWidget(self.quota_bar, 4, 0, 1, 2)

        # Upgrade / manage row
        self.upgrade_btn = QPushButton("Upgrade to Pro — $9.99/mo")
        self.upgrade_btn.setMinimumHeight(36)
        self.upgrade_btn.setStyleSheet(
            "QPushButton { background:#ff8800; color:#0a0a0b; font-weight:700; "
            "border:none; border-radius:6px; padding:6px 16px; }"
            "QPushButton:hover { background:#ff9c1f; }"
        )
        self.upgrade_btn.clicked.connect(self._open_pricing)
        tc.addWidget(self.upgrade_btn, 5, 0, 1, 2)

        self.manage_btn = QPushButton("Manage subscription")
        self.manage_btn.setMinimumHeight(36)
        self.manage_btn.setVisible(False)
        self.manage_btn.setStyleSheet(
            "QPushButton { background:transparent; color:#ccc; "
            "border:1px solid #2e2e36; border-radius:6px; padding:6px 16px; }"
            "QPushButton:hover { background:#15151a; color:#fff; }"
        )
        self.manage_btn.clicked.connect(self._open_account_page)
        tc.addWidget(self.manage_btn, 6, 0, 1, 2)

        si.addWidget(self.tier_card)

        # ── Features section
        feat_title = QLabel("What's unlocked")
        ttf2 = QFont(); ttf2.setPointSize(13); ttf2.setBold(True)
        feat_title.setFont(ttf2)
        feat_title.setStyleSheet("margin-top:6px;")
        si.addWidget(feat_title)

        self.feature_grid_box = QFrame()
        self.feature_grid = QGridLayout(self.feature_grid_box)
        self.feature_grid.setContentsMargins(0, 0, 0, 0)
        self.feature_grid.setSpacing(6)
        si.addWidget(self.feature_grid_box)

        # ── Devices section
        dev_title = QLabel("Devices")
        dev_title.setFont(ttf2)
        dev_title.setStyleSheet("margin-top:6px;")
        si.addWidget(dev_title)

        self.devices_lbl = QLabel("—")
        self.devices_lbl.setStyleSheet("color:#8a8a92; font-family:Consolas,monospace;")
        self.devices_lbl.setWordWrap(True)
        si.addWidget(self.devices_lbl)

        # ── Footer buttons
        foot = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setStyleSheet(
            "QPushButton { background:transparent; color:#ccc; "
            "border:1px solid #2e2e36; border-radius:6px; padding:6px 14px; }"
            "QPushButton:hover { background:#15151a; color:#fff; }"
        )
        self.refresh_btn.clicked.connect(self._refresh_async)
        foot.addWidget(self.refresh_btn)

        self.web_account_btn = QPushButton("Open in browser")
        self.web_account_btn.setStyleSheet(self.refresh_btn.styleSheet())
        self.web_account_btn.clicked.connect(self._open_account_page)
        foot.addWidget(self.web_account_btn)

        foot.addStretch(1)

        self.signout_btn = QPushButton("Sign out")
        self.signout_btn.setStyleSheet(
            "QPushButton { background:transparent; color:#ff5555; "
            "border:1px solid #4a2222; border-radius:6px; padding:6px 14px; }"
            "QPushButton:hover { background:#1f0a0a; color:#fff; }"
        )
        self.signout_btn.clicked.connect(self._sign_out)
        foot.addWidget(self.signout_btn)
        si.addLayout(foot)

        # Status line under footer
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color:#8a8a92; font-size:11px; margin-top:8px;")
        self.status_lbl.setWordWrap(True)
        si.addWidget(self.status_lbl)

        self._inner.addWidget(self.signed_in_box)
        self._inner.addStretch(1)

    @staticmethod
    def _badge_style(kind: str) -> str:
        base = "padding:4px 10px; border-radius:4px; font-family:Consolas,monospace; " \
               "font-size:11px; letter-spacing:1.5px; text-transform:uppercase;"
        if kind == "pro":
            return base + " background:rgba(255,106,0,0.12); color:#ff8800; " \
                          "border:1px solid rgba(255,106,0,0.25);"
        if kind == "admin":
            return base + " background:rgba(74,222,128,0.12); color:#4ade80; " \
                          "border:1px solid rgba(74,222,128,0.25);"
        return base + " background:rgba(138,138,146,0.15); color:#8a8a92;"

    # ── state rendering ──
    def render_state(self):
        if not account.is_signed_in():
            self.signed_out_box.setVisible(True)
            self.signed_in_box.setVisible(False)
            return

        self.signed_out_box.setVisible(False)
        self.signed_in_box.setVisible(True)

        u = account.current_user() or {}
        email = u.get("email", "")
        tier = u.get("tier", "free")
        is_admin = bool(u.get("is_admin"))

        # Greet + email
        self.greet.setText("Welcome, admin." if is_admin else "Welcome.")
        self.email_lbl.setText(email)

        # Tier badge / title / tag
        if is_admin:
            self.tier_badge.setText("Admin Pro · Lifetime")
            self.tier_badge.setStyleSheet(self._badge_style("admin"))
            self.tier_title.setText("Admin tier")
            self.tier_tag.setText("Lifetime Pro — granted automatically.")
            self.upgrade_btn.setVisible(False)
            self.manage_btn.setVisible(False)
        elif tier == "pro":
            self.tier_badge.setText("Pro")
            self.tier_badge.setStyleSheet(self._badge_style("pro"))
            self.tier_title.setText("Pro plan")
            self.tier_tag.setText("Everything unlocked. Unlimited AI Mechanic.")
            self.upgrade_btn.setVisible(False)
            self.manage_btn.setVisible(True)
        else:
            self.tier_badge.setText("Free")
            self.tier_badge.setStyleSheet(self._badge_style("free"))
            self.tier_title.setText("Free plan")
            self.tier_tag.setText("VIN, DTC read, DTC clear, and limited AI Mechanic.")
            self.upgrade_btn.setVisible(True)
            self.manage_btn.setVisible(False)

        # Quota bar
        q = u.get("ai_quota") or {}
        limit = q.get("limit")
        used = q.get("used") or 0
        if limit is None:
            self.quota_lbl.setText("AI Mechanic: unlimited")
            self.quota_bar.setRange(0, 1)
            self.quota_bar.setValue(1)
            self.quota_bar.setStyleSheet(
                "QProgressBar { background:#0a0a0b; border:none; border-radius:4px; }"
                "QProgressBar::chunk { background:#4ade80; border-radius:4px; }"
            )
        else:
            self.quota_lbl.setText(f"AI Mechanic this month: {used} / {limit}")
            self.quota_bar.setRange(0, max(1, int(limit)))
            self.quota_bar.setValue(min(int(used), int(limit)))
            color = "#ff5555" if used >= limit else "#ff8800"
            self.quota_bar.setStyleSheet(
                "QProgressBar { background:#0a0a0b; border:none; border-radius:4px; }"
                f"QProgressBar::chunk {{ background:{color}; border-radius:4px; }}"
            )

        # Features grid
        for i in reversed(range(self.feature_grid.count())):
            w = self.feature_grid.itemAt(i).widget()
            if w: w.setParent(None)
        feats = u.get("features") or {}
        for i, (key, label) in enumerate(_FEATURE_LABELS):
            on = bool(feats.get(key))
            pill = QLabel(("✓  " if on else "🔒  ") + label)
            pill.setStyleSheet(
                "QLabel { padding:8px 12px; background:#15151a; "
                f"border:1px solid {'#2a2a32' if on else '#22222a'}; "
                f"color:{'#f5f5f7' if on else '#8a8a92'}; "
                "border-radius:6px; font-family:Consolas,monospace; font-size:12px; }"
            )
            self.feature_grid.addWidget(pill, i // 2, i % 2)

        # Devices
        machines = u.get("machine_ids") or []
        if not machines:
            self.devices_lbl.setText("This is the first machine signed in to this account.")
        else:
            self.devices_lbl.setText(
                f"{len(machines)} machine(s):\n  " + "\n  ".join(machines)
            )

        # Notify the main window that gating may have changed.
        self.state_changed.emit()

    # ── actions ──
    def _open_auth_dialog(self):
        dlg = AuthDialog(self, allow_skip=True)
        dlg.exec()
        # render fresh regardless — user may have signed in OR skipped
        self.render_state()

    def _open_pricing(self):
        webbrowser.open(account.base_url() + "/pricing")

    def _open_account_page(self):
        webbrowser.open(account.base_url() + "/account")

    def _sign_out(self):
        reply = QMessageBox.question(
            self, "Sign out", "Sign out of your Fuse OBD account?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        account.logout()
        self.render_state()

    def _refresh_async(self):
        if not account.is_signed_in():
            return
        if self._refresh_thread and self._refresh_thread.isRunning():
            return
        self.status_lbl.setText("Refreshing…")
        self._refresh_thread = _RefreshThread()
        self._refresh_thread.done.connect(self._on_refresh_done)
        self._refresh_thread.start()

    def _on_refresh_done(self, ok: bool, _user, err: str):
        if ok:
            self.status_lbl.setText("")
            self.render_state()
        else:
            self.status_lbl.setText(f"Refresh failed: {err}")
