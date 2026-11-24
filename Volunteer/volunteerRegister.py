"""
volunteerRegister.py — Volunteer signup.

Per the "minimal signup" decision: this collects only what the app
actually uses at account-creation time, and drops everything else into
volunteer_profiles as optional fields the user can fill in later.

Required at signup:
    first_name, last_name, email, password, confirm_password, captcha

Optional but shown (skippable — blank is stored as empty string):
    gender, country, zipcode, dob

Collected later via profile (not on this form):
    skills, phone

Flow:
    1. Fill form, solve captcha.
    2. Click "Continue to Email Verification" → sends OTP.
    3. Enter code in a modal (reused from otp.py).
    4. On success: db.register_user(..., role='volunteer') inserts the
       user + volunteer_profiles row in one transaction.
    5. Call on_success (usually routes the user to login or straight in).
"""

import os
import random
import string

from PyQt6.QtCore import QByteArray, QDate, Qt
from PyQt6.QtGui import QAction, QCursor, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:
    from captcha.image import ImageCaptcha
    _HAS_CAPTCHA = True
except ImportError:
    _HAS_CAPTCHA = False

import Events.theme as theme
from Authentication.otp import generate_otp, send_otp_email, verify_via_otp

COUNTRY_CHOICES = [
    "Select Country",
    "United States", "Canada", "United Kingdom", "Australia",
    "Germany", "France", "Japan", "Other",
]


class VolunteerRegistration(QWidget):
    CARD_WIDTH = 760

    def __init__(self, db, on_success=None, on_back_click=None, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.REGISTER_CARD)
        self.db = db
        self.on_success = on_success
        self.on_back_click = on_back_click

        self.captcha_text = ""

        # ── Outer scroll wrapper (rarely needed; card is sized to fit) ────
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        scroll = QScrollArea()
        scroll.setObjectName(theme.REGISTER_SCROLL)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        scroll_content = QWidget()
        scroll_content.setObjectName(theme.REGISTER_SCROLL_CONTENT)
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(24, 32, 24, 32)
        scroll_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName(theme.REGISTER_CARD)
        card.setFixedWidth(self.CARD_WIDTH)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(52, 42, 52, 46)
        card_layout.setSpacing(18)

        self._build_form(card_layout)

        scroll_layout.addWidget(card)
        scroll.setWidget(scroll_content)
        outer.addWidget(scroll)

        self.generate_captcha()

    # ── Form construction ─────────────────────────────────────────────────
    def _build_form(self, layout):

        back_btn = QPushButton("← Back")
        back_btn.setObjectName(theme.BACK_BTN)
        back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if self.on_back_click:
            back_btn.clicked.connect(self.on_back_click)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addWidget(back_btn)
        top_row.addStretch(1)
        layout.addLayout(top_row)
        title = QLabel("Join as a Volunteer")
        title.setObjectName(theme.FORM_TITLE)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel(
            "Start making an impact in your local community. "
            "Only your name, email, and password are required — "
            "you can add more later from your profile."
        )
        subtitle.setObjectName(theme.FORM_SUBTITLE)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addWidget(back_btn)
        top_row.addStretch(1)
        layout.addLayout(top_row)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)

        def labeled(label_text, widget):
            col = QVBoxLayout()
            col.setSpacing(6)
            lbl = QLabel(label_text)
            lbl.setObjectName(theme.FIELD_LABEL)
            col.addWidget(lbl)
            col.addWidget(widget)
            return col

        # ── Name ──────────────────────────────────────────────────────────
        self.firstNameInput = QLineEdit()
        self.firstNameInput.setPlaceholderText("First name")
        self.lastNameInput = QLineEdit()
        self.lastNameInput.setPlaceholderText("Last name")

        name_row = QHBoxLayout()
        name_row.setSpacing(20)
        name_row.addLayout(labeled("First Name *", self.firstNameInput))
        name_row.addLayout(labeled("Last Name *", self.lastNameInput))
        layout.addLayout(name_row)

        # ── Email + password ──────────────────────────────────────────────
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("name@example.com")
        layout.addLayout(labeled("Email Address *", self.email_input))

        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setPlaceholderText("At least 8 characters")

        self.confirmPass_input = QLineEdit()
        self.confirmPass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirmPass_input.setPlaceholderText("Re-enter password")

        self.toggle_pwd = QAction("👁", self.pass_input)
        self.toggle_pwd.setCheckable(True)
        self.toggle_pwd.triggered.connect(self._toggle_password_visibility)
        self.pass_input.addAction(
            self.toggle_pwd, QLineEdit.ActionPosition.TrailingPosition
        )

        pass_row = QHBoxLayout()
        pass_row.setSpacing(20)
        pass_row.addLayout(labeled("Password *", self.pass_input))
        pass_row.addLayout(
            labeled("Confirm Password *", self.confirmPass_input))
        layout.addLayout(pass_row)

        # ── Optional profile details ──────────────────────────────────────
        optional_hdr = QLabel("Optional — add now or later")
        optional_hdr.setObjectName(theme.FORM_SUBTITLE)
        layout.addWidget(optional_hdr)

        self.dob_input = QDateEdit()
        self.dob_input.setCalendarPopup(True)
        self.dob_input.setDisplayFormat("yyyy-MM-dd")
        self.dob_input.setDate(QDate.currentDate().addYears(-18))

        self.gender_input = QComboBox()
        self.gender_input.addItems([
            "Prefer not to say", "Female", "Male", "Non-binary",
        ])

        dob_gender_row = QHBoxLayout()
        dob_gender_row.setSpacing(20)
        dob_gender_row.addLayout(labeled("Date of Birth", self.dob_input))
        dob_gender_row.addLayout(labeled("Gender", self.gender_input))
        layout.addLayout(dob_gender_row)

        self.country_input = QComboBox()
        self.country_input.addItems(COUNTRY_CHOICES)
        self.zipcode_input = QLineEdit()
        self.zipcode_input.setPlaceholderText("e.g. 90210")

        location_row = QHBoxLayout()
        location_row.setSpacing(20)
        location_row.addLayout(
            labeled("Country", self.country_input), stretch=2)
        location_row.addLayout(
            labeled("Zip Code", self.zipcode_input), stretch=1)
        layout.addLayout(location_row)

        # ── Captcha ───────────────────────────────────────────────────────
        captcha_container = QVBoxLayout()
        captcha_container.setSpacing(6)
        captcha_lbl = QLabel("Verification *")
        captcha_lbl.setObjectName(theme.FIELD_LABEL)
        captcha_container.addWidget(captcha_lbl)

        captcha_row = QHBoxLayout()
        captcha_row.setSpacing(10)

        self.captcha_image_label = QLabel()
        self.captcha_image_label.setObjectName(theme.CAPTCHA_IMAGE)
        self.captcha_image_label.setFixedSize(204, 64)
        self.captcha_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.refresh_captcha_btn = QPushButton("↻")
        self.refresh_captcha_btn.setObjectName(theme.CAPTCHA_REFRESH)
        self.refresh_captcha_btn.setFixedSize(46, 64)
        self.refresh_captcha_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.refresh_captcha_btn.clicked.connect(self.generate_captcha)

        self.captcha_input = QLineEdit()
        self.captcha_input.setPlaceholderText("Enter the code shown")

        captcha_row.addWidget(self.captcha_image_label)
        captcha_row.addWidget(self.refresh_captcha_btn)
        captcha_row.addWidget(
            self.captcha_input, 1, Qt.AlignmentFlag.AlignVCenter
        )
        captcha_container.addLayout(captcha_row)
        layout.addLayout(captcha_container)

        # ── Actions ───────────────────────────────────────────────────────
        layout.addSpacing(6)

        submit_btn = QPushButton("Create Account")
        submit_btn.setObjectName(theme.PRIMARY_BTN)
        submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        submit_btn.clicked.connect(self._submit)

        layout.addWidget(submit_btn)

    # ── Captcha ───────────────────────────────────────────────────────────
    def generate_captcha(self):
        if not _HAS_CAPTCHA:
            self.captcha_text = "TEST"
            self.captcha_image_label.setText("CAPTCHA module missing")
            return

        chars = string.ascii_uppercase + string.digits
        self.captcha_text = "".join(random.choices(chars, k=5))

        image_gen = ImageCaptcha(width=200, height=60)
        image_data = image_gen.generate(self.captcha_text)

        raw_bytes = image_data.getvalue()
        qba = QByteArray(bytes(raw_bytes))

        pixmap = QPixmap()
        pixmap.loadFromData(qba)
        self.captcha_image_label.setPixmap(pixmap)
        self.captcha_input.clear()

    # ── Password toggle ───────────────────────────────────────────────────
    def _toggle_password_visibility(self, checked):
        mode = (QLineEdit.EchoMode.Normal if checked
                else QLineEdit.EchoMode.Password)
        self.pass_input.setEchoMode(mode)
        self.confirmPass_input.setEchoMode(mode)

    # ── Submit ────────────────────────────────────────────────────────────
    def _validate(self):
        first = self.firstNameInput.text().strip()
        last = self.lastNameInput.text().strip()
        email = self.email_input.text().strip().lower()
        pw = self.pass_input.text()
        pw2 = self.confirmPass_input.text()
        captcha_in = self.captcha_input.text().strip()

        if not first or not last:
            QMessageBox.warning(self, "Input error",
                                "First and last name are required.")
            return None
        if not email or "@" not in email:
            QMessageBox.warning(self, "Input error",
                                "Enter a valid email address.")
            return None
        if len(pw) < 8:
            QMessageBox.warning(self, "Password too short",
                                "Password must be at least 8 characters.")
            return None
        if pw != pw2:
            QMessageBox.warning(self, "Password mismatch",
                                "Passwords do not match.")
            return None
        if not captcha_in:
            QMessageBox.warning(self, "Verification required",
                                "Enter the CAPTCHA code.")
            return None
        if captcha_in.upper() != self.captcha_text.upper():
            QMessageBox.warning(self, "CAPTCHA error",
                                "Incorrect code — try the new one.")
            self.generate_captcha()
            return None
        if self.db.email_exists(email):
            QMessageBox.warning(self, "Email already used",
                                "An account with this email already exists. "
                                "Try logging in instead.")
            return None

        gender = self.gender_input.currentText()
        if gender == "Prefer not to say":
            gender = ""

        country = self.country_input.currentText()
        if country == "Select Country":
            country = ""

        return {
            "first_name": first,
            "last_name": last,
            "email": email,
            "password": pw,
            "gender": gender,
            "country": country,
            "zipcode": self.zipcode_input.text().strip(),
            "dob": self.dob_input.date().toString("yyyy-MM-dd"),
        }

    def _submit(self):
        data = self._validate()
        if not data:
            return

        # Send OTP, then modal-verify before inserting anything.
        code = generate_otp()
        if not send_otp_email(data["email"], code):
            QMessageBox.critical(
                self, "Email error",
                "Could not send the verification code. Check your internet "
                "connection and that SENDER_EMAIL / SENDER_PASSWORD are set "
                "in your .env file."
            )
            return

        if not verify_via_otp(self, data["email"], code):
            # User cancelled the modal — leave the form filled in.
            return

        user_id = self.db.register_user(
            email=data["email"],
            password=data["password"],
            role="volunteer",
            first_name=data["first_name"],
            last_name=data["last_name"],
            country=data["country"],
            zipcode=data["zipcode"],
            dob=data["dob"],
            gender=data["gender"],
        )

        if not user_id:
            QMessageBox.critical(
                self, "Registration failed",
                "Could not create the account. It may already exist."
            )
            return

        QMessageBox.information(
            self, "Welcome to Moxie",
            f"Account created. Welcome, {data['first_name']}!"
        )

        self._reset_form()
        if self.on_success:
            self.on_success(user_id)

    # ── Reset ─────────────────────────────────────────────────────────────
    def _reset_form(self):
        for w in (self.firstNameInput, self.lastNameInput,
                  self.email_input, self.pass_input,
                  self.confirmPass_input, self.zipcode_input,
                  self.captcha_input):
            w.clear()
        self.gender_input.setCurrentIndex(0)
        self.country_input.setCurrentIndex(0)
        self.dob_input.setDate(QDate.currentDate().addYears(-18))
        self.toggle_pwd.setChecked(False)
        self._toggle_password_visibility(False)
        self.generate_captcha()
