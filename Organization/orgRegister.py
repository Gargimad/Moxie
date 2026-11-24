"""
orgRegister.py — Organization signup.

Mirrors volunteerRegister.py: minimal required fields, optional details,
captcha, OTP via the shared modal, then a single transaction that creates
the user (role='org') and its organizations row.

Required:
    org_name, email, password, confirm_password, captcha

Optional:
    website_link, country, city (city is a free-text field; the country
    dropdown stays consistent with the volunteer form)

Note: org_name lives on organizations.org_name, not on users. The users
row is purely an identity row — one email, one password, one role.
"""

import random
import string

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QAction, QCursor, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
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


class OrganizationRegistration(QWidget):
    CARD_WIDTH = 640

    def __init__(self, db, on_success=None, on_back_click=None, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.REGISTER_CARD)
        self.db = db
        self.on_success = on_success
        self.on_back_click = on_back_click

        self.captcha_text = ""

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
        card_layout.setContentsMargins(48, 40, 48, 44)
        card_layout.setSpacing(16)

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
        title = QLabel("Register Organization")
        title.setObjectName(theme.FORM_TITLE)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel(
            "Connect your nonprofit or community program with volunteers. "
            "Only the organization name, email, and password are required."
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
        layout.addSpacing(6)

        def labeled(label_text, widget):
            col = QVBoxLayout()
            col.setSpacing(6)
            lbl = QLabel(label_text)
            lbl.setObjectName(theme.FIELD_LABEL)
            col.addWidget(lbl)
            col.addWidget(widget)
            return col

        # ── Org name ──────────────────────────────────────────────────────
        self.org_name_input = QLineEdit()
        self.org_name_input.setPlaceholderText("e.g. Riverside Food Bank")
        layout.addLayout(labeled("Organization Name *", self.org_name_input))

        # ── Description ───────────────────────────────────────────────────
        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText(
            "A short description of your organization's mission and work"
        )
        self.description_input.setFixedHeight(90)
        layout.addLayout(labeled("Description", self.description_input))

        # ── Website ───────────────────────────────────────────────────────
        self.website_input = QLineEdit()
        self.website_input.setPlaceholderText("https://example.org")
        layout.addLayout(labeled("Website", self.website_input))

        # ── Location ──────────────────────────────────────────────────────
        self.country_input = QComboBox()
        self.country_input.addItems(COUNTRY_CHOICES)

        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("City")

        location_row = QHBoxLayout()
        location_row.setSpacing(20)
        location_row.addLayout(
            labeled("Country", self.country_input), stretch=2)
        location_row.addLayout(labeled("City", self.city_input), stretch=1)
        layout.addLayout(location_row)

        # ── Credentials ───────────────────────────────────────────────────
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("contact@example.org")
        layout.addLayout(labeled("Contact Email *", self.email_input))

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

        submit_btn = QPushButton("Create Organization Account")
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

    def _toggle_password_visibility(self, checked):
        mode = (QLineEdit.EchoMode.Normal if checked
                else QLineEdit.EchoMode.Password)
        self.pass_input.setEchoMode(mode)
        self.confirmPass_input.setEchoMode(mode)

    # ── Submit ────────────────────────────────────────────────────────────
    def _validate(self):
        org_name = self.org_name_input.text().strip()
        email = self.email_input.text().strip().lower()
        pw = self.pass_input.text()
        pw2 = self.confirmPass_input.text()
        captcha_in = self.captcha_input.text().strip()

        if not org_name:
            QMessageBox.warning(self, "Input error",
                                "Organization name is required.")
            return None
        if not email or "@" not in email:
            QMessageBox.warning(self, "Input error",
                                "Enter a valid contact email.")
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

        country = self.country_input.currentText()
        if country == "Select Country":
            country = ""

        return {
            "org_name": org_name,
            "email": email,
            "password": pw,
            "description": self.description_input.toPlainText().strip(),
            "website_link": self.website_input.text().strip(),
            "country": country,
            "city": self.city_input.text().strip(),
        }

    def _submit(self):
        data = self._validate()
        if not data:
            return

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
            return

        user_id = self.db.register_user(
            email=data["email"],
            password=data["password"],
            role="org",
            org_name=data["org_name"],
            description=data["description"],
            website_link=data["website_link"],
            country=data["country"],
            city=data["city"],
        )

        if not user_id:
            QMessageBox.critical(
                self, "Registration failed",
                "Could not create the organization account. "
                "It may already exist."
            )
            return

        QMessageBox.information(
            self, "Welcome to Moxie",
            f"Organization account created for {data['org_name']}."
        )

        self._reset_form()
        if self.on_success:
            self.on_success(user_id)

    # ── Reset ─────────────────────────────────────────────────────────────
    def _reset_form(self):
        for w in (self.org_name_input, self.email_input, self.pass_input,
                  self.confirmPass_input, self.website_input,
                  self.city_input, self.captcha_input):
            w.clear()
        self.description_input.clear()
        self.country_input.setCurrentIndex(0)
        self.toggle_pwd.setChecked(False)
        self._toggle_password_visibility(False)
        self.generate_captcha()
