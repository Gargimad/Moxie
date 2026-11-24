"""
login.py — Unified login screen for volunteers and organizations.

Flow:
    1. User picks Volunteer or Organization tab.
    2. Enters email + password.
    3. db.authenticate() verifies credentials.
    4. If the account has mfa_enabled, an OTP is emailed and a modal
       prompts for it. Only on success does on_login_success fire.
    5. If mfa_enabled is 0, on_login_success fires immediately.

on_login_success receives the dict from db.authenticate() (keys:
userID, email, role, mfa_enabled, and role-specific profile fields).
landing.py routes based on user['role'].
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QCursor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import Events.theme as theme
from Authentication.otp import generate_otp, send_otp_email, verify_via_otp


class Login(QWidget):
    def __init__(self, db, on_login_success=None, on_back_click=None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName(theme.LOGIN_CARD)
        self.db = db
        self.on_login_success = on_login_success
        self.on_back_click = on_back_click

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName(theme.LOGIN_CARD)
        card.setFixedWidth(420)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(35, 35, 35, 35)
        card_layout.setSpacing(14)

        title = QLabel("Welcome Back")
        title.setObjectName(theme.FORM_TITLE)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Log in to your Moxie account")
        subtitle.setObjectName(theme.FORM_SUBTITLE)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ── Role toggle ───────────────────────────────────────────────────
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(0)

        self.vol_btn = QPushButton("Volunteer")
        self.org_btn = QPushButton("Organization")
        for b in (self.vol_btn, self.org_btn):
            b.setObjectName(theme.VIEW_TOGGLE_BTN)
            b.setCheckable(True)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.vol_btn.setChecked(True)

        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.vol_btn)
        group.addButton(self.org_btn)

        toggle_row.addWidget(self.vol_btn)
        toggle_row.addWidget(self.org_btn)

        # ── Inputs ────────────────────────────────────────────────────────
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Email address")
        self.email_input.returnPressed.connect(self._attempt_login)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self._attempt_login)

        self.toggle_pwd = QAction("👁", self.password_input)
        self.toggle_pwd.setCheckable(True)
        self.toggle_pwd.triggered.connect(self._toggle_pwd)
        self.password_input.addAction(
            self.toggle_pwd, QLineEdit.ActionPosition.TrailingPosition
        )

        # ── Buttons ───────────────────────────────────────────────────────
        login_btn = QPushButton("Log In")
        login_btn.setObjectName(theme.PRIMARY_BTN)
        login_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        login_btn.clicked.connect(self._attempt_login)

        back_btn = QPushButton("← Back")
        back_btn.setObjectName(theme.BACK_BTN)
        back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if self.on_back_click:
            back_btn.clicked.connect(self.on_back_click)

        activate_btn = QPushButton("Activate imported account")
        activate_btn.setObjectName(theme.BACK_BTN)
        activate_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        activate_btn.clicked.connect(self._activate_imported_account)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addWidget(back_btn)
        top_row.addStretch(1)
        card_layout.addLayout(top_row)
        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(4)
        card_layout.addLayout(toggle_row)
        card_layout.addWidget(self.email_input)
        card_layout.addWidget(self.password_input)
        card_layout.addSpacing(6)
        card_layout.addWidget(login_btn)
        card_layout.addWidget(activate_btn)

        outer.addWidget(card)

    # ── Helpers ───────────────────────────────────────────────────────────
    def _toggle_pwd(self, checked):
        mode = (QLineEdit.EchoMode.Normal if checked
                else QLineEdit.EchoMode.Password)
        self.password_input.setEchoMode(mode)

    def _selected_role(self):
        return "volunteer" if self.vol_btn.isChecked() else "org"

    def clear_inputs(self):
        self.email_input.clear()
        self.password_input.clear()
        self.toggle_pwd.setChecked(False)
        self._toggle_pwd(False)

    def _activate_imported_account(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Activate volunteer account")
        layout = QVBoxLayout(dlg)
        form = QFormLayout()
        email = QLineEdit()
        email.setPlaceholderText("Email address")
        code = QLineEdit()
        code.setPlaceholderText("8-digit email code")
        code.setMaxLength(8)
        password = QLineEdit()
        password.setPlaceholderText("At least 8 characters")
        password.setEchoMode(QLineEdit.EchoMode.Password)
        confirm = QLineEdit()
        confirm.setPlaceholderText("Confirm password")
        confirm.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Email", email)
        form.addRow("Activation code", code)
        form.addRow("New password", password)
        form.addRow("Confirm password", confirm)
        layout.addLayout(form)

        actions = QHBoxLayout()
        cancel = QPushButton("Cancel")
        activate = QPushButton("Activate")
        activate.setObjectName(theme.PRIMARY_BTN)
        actions.addStretch(1)
        actions.addWidget(cancel)
        actions.addWidget(activate)
        layout.addLayout(actions)
        cancel.clicked.connect(dlg.reject)

        def submit():
            address = email.text().strip()
            activation_code = code.text().strip()
            new_password = password.text()
            if not address or len(activation_code) != 8:
                QMessageBox.warning(
                    dlg, "Missing information",
                    "Enter your email address and the 8-digit code."
                )
                return
            if len(new_password) < 8:
                QMessageBox.warning(
                    dlg, "Password too short",
                    "Choose a password with at least 8 characters."
                )
                return
            if new_password != confirm.text():
                QMessageBox.warning(
                    dlg, "Passwords don't match",
                    "Enter the same password in both fields."
                )
                return
            if not self.db.activate_imported_volunteer(
                    address, activation_code, new_password):
                QMessageBox.warning(
                    dlg, "Activation failed",
                    "The email or code is incorrect, expired, or has "
                    "already been used. Ask your organization to resend "
                    "the invitation."
                )
                return
            dlg.accept()

        activate.clicked.connect(submit)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            QMessageBox.information(
                self, "Account activated",
                "Your account is active. You can now log in with your "
                "email and new password."
            )

    # ── Auth ──────────────────────────────────────────────────────────────
    def _attempt_login(self):
        email = self.email_input.text().strip()
        password = self.password_input.text()

        if not email or not password:
            QMessageBox.warning(
                self, "Missing info", "Enter email and password."
            )
            return

        user = self.db.authenticate(email, password)
        if not user:
            QMessageBox.warning(
                self, "Login failed",
                "Email or password is incorrect."
            )
            self.password_input.clear()
            return

        # Role mismatch: almost always a misclick on the toggle.
        if user["role"] != self._selected_role():
            expected = ("Volunteer" if user["role"] == "volunteer"
                        else "Organization")
            QMessageBox.information(
                self, "Wrong account type",
                f"This account is registered as an {expected}. "
                f"Please select the {expected} tab and try again."
            )
            return

        # ── MFA ───────────────────────────────────────────────────────────
        if user.get("mfa_enabled"):
            code = generate_otp()
            if not send_otp_email(user["email"], code):
                QMessageBox.critical(
                    self, "Email error",
                    "Could not send the verification code. Check your "
                    "internet connection, or disable MFA on this account."
                )
                return
            if not verify_via_otp(self, user["email"], code):
                # User cancelled or closed the dialog.
                return

        if self.on_login_success:
            self.on_login_success(user)
