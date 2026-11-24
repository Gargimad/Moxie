"""
otp.py — Shared email OTP send/verify used by login and both registration
flows.

Exposes:
    generate_otp() -> str                six-digit numeric string
    send_otp_email(to, code) -> bool     SMTP send; True on success
    verify_via_otp(parent, email, code) -> bool
                                         modal dialog that prompts for the
                                         code and returns True if it matches

Environment (loaded from .env via python-dotenv, once at import):
    SENDER_EMAIL     the Gmail address that sends the code
    SENDER_PASSWORD  a Gmail app password (NOT the account password)
    DISPLAY_NAME     optional; defaults to "Moxie"
"""

import os
import secrets
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

import Events.theme as theme

load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# Sending
# ─────────────────────────────────────────────────────────────────────────────
def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def generate_activation_code() -> str:
    return f"{secrets.randbelow(100_000_000):08d}"


def send_otp_email(recipient_email: str, otp_code: str) -> bool:
    """
    Sends the 6-digit code via SMTP over SSL. Returns True on success.
    Prints a diagnostic and returns False on any failure (missing env,
    network error, bad credentials) — callers show the user a QMessageBox.
    """
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    display_name = os.getenv("DISPLAY_NAME", "Moxie")

    if not sender_email or not sender_password:
        print("[otp] SENDER_EMAIL or SENDER_PASSWORD not set in environment.")
        return False

    msg = MIMEMultipart()
    msg["From"] = f"{display_name} <{sender_email}>"
    msg["To"] = recipient_email
    msg["Subject"] = "Your Moxie verification code"

    body = (
        f"Hello,\n\n"
        f"Your Moxie verification code is: {otp_code}\n\n"
        f"This code expires when you close the app. If you did not attempt "
        f"to log in or register, you can safely ignore this message.\n\n"
        f"— Moxie"
    )
    msg.attach(MIMEText(body, "plain"))

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(
                "smtp.gmail.com", 465, context=context, timeout=15) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[otp] SMTP error: {e}")
        return False


def send_volunteer_activation_email(recipient_email: str, code: str,
                                    organization_name: str) -> bool:
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    display_name = os.getenv("DISPLAY_NAME", "Moxie")
    if not sender_email or not sender_password:
        print("[otp] SENDER_EMAIL or SENDER_PASSWORD not set in environment.")
        return False

    msg = MIMEMultipart()
    msg["From"] = f"{display_name} <{sender_email}>"
    msg["To"] = recipient_email
    msg["Subject"] = "Activate your Moxie volunteer account"
    msg.attach(MIMEText(
        f"Hello,\n\n{organization_name} added you as a volunteer on Moxie.\n"
        f"Open the Moxie app, choose “Activate imported account”, and enter "
        f"this code:\n\n{code}\n\n"
        "The code expires in 24 hours. You will choose your password in "
        "the app. If you were not expecting this invitation, you can ignore "
        "this email.\n\n— Moxie",
        "plain",
    ))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
                "smtp.gmail.com", 465, context=context, timeout=15) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[otp] Activation email error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Dialog
# ─────────────────────────────────────────────────────────────────────────────
class OTPDialog(QDialog):
    """
    Modal 6-digit code prompt. Call .exec() and check the return value:
        QDialog.DialogCode.Accepted  → code matched
        QDialog.DialogCode.Rejected  → user cancelled or closed
    """

    def __init__(self, parent, email: str, expected_code: str):
        super().__init__(parent)
        self.setObjectName(theme.LOGIN_CARD)
        self.setWindowTitle("Verify your email")
        self.setModal(True)
        self.setMinimumWidth(380)
        self.expected_code = expected_code

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("Verify your email")
        title.setObjectName(theme.FORM_TITLE)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        info = QLabel(f"We sent a 6-digit code to:\n{email}")
        info.setObjectName(theme.FORM_SUBTITLE)
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setWordWrap(True)

        self.code_input = QLineEdit()
        self.code_input.setObjectName(theme.OTP_INPUT)
        self.code_input.setPlaceholderText("000000")
        self.code_input.setMaxLength(6)
        self.code_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_input.returnPressed.connect(self._try_submit)

        verify_btn = QPushButton("Verify")
        verify_btn.setObjectName(theme.PRIMARY_BTN)
        verify_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        verify_btn.clicked.connect(self._try_submit)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName(theme.SECONDARY_BTN)
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(verify_btn)

        layout.addWidget(title)
        layout.addWidget(info)
        layout.addSpacing(6)
        layout.addWidget(self.code_input)
        layout.addLayout(btn_row)

        self.code_input.setFocus()

    def _try_submit(self):
        entered = self.code_input.text().strip()
        if not entered:
            QMessageBox.warning(self, "Missing code",
                                "Enter the 6-digit code from your email.")
            return
        if entered == self.expected_code:
            self.accept()
        else:
            QMessageBox.warning(self, "Incorrect code",
                                "That code doesn't match. Please try again.")
            self.code_input.clear()
            self.code_input.setFocus()


# ─────────────────────────────────────────────────────────────────────────────
# Convenience wrapper
# ─────────────────────────────────────────────────────────────────────────────
def verify_via_otp(parent, email: str, expected_code: str) -> bool:
    """
    Pops the modal, returns True if the user entered the right code.
    Returns False on cancel, close, or wrong code after retries are exhausted
    (the user can retry as many times as they want while the dialog is open,
    since we only reject on explicit Cancel).
    """
    dlg = OTPDialog(parent, email, expected_code)
    return dlg.exec() == QDialog.DialogCode.Accepted
