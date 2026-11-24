"""
FAQ.py — Moxie FAQ page, styled after the Bolt FAQ pattern:

  [big centered title]
  [centered subtitle]
  [thin search bar]
  [category pills]
  [bold category heading]
  [pill cards, question on left, circular +/− toggle on right]
  [answer appears inside the same card when expanded]
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import Events.theme as theme

categories = [
    "Getting Started",
    "For Volunteers",
    "For Organizations",
    "Hours & Impact",
    "Account & Support",
]

FAQ_DATA = [
    # ── Getting Started ───────────────────────────────────────────────
    {
        "category": "Getting Started",
        "question": "What is Moxie?",
        "answer": (
            "Moxie is a platform that connects volunteers with local "
            "organizations, community projects, and nonprofits. "
            "Volunteers can browse opportunities, RSVP to events they "
            "care about, and track the hours they contribute. "
            "Organizations get a dashboard to post opportunities, manage "
            "their roster, verify hours, and communicate with their "
            "volunteers — all in one place."
        ),
    },
    {
        "category": "Getting Started",
        "question": "Do I need an account to browse opportunities?",
        "answer": (
            "No. Anyone can browse the guest home page and search the "
            "listing without signing up. You only need an account when "
            "you want to RSVP to an event, track hours, or contact an "
            "organization. Creating an account is free and takes under "
            "a minute — you just need an email address and a password."
        ),
    },
    {
        "category": "Getting Started",
        "question": (
            "How do I know which events are hosted by Moxie organizations?"
        ),
        "answer": (
            "Every opportunity card carries a small label near the top: "
            "'Moxie' if the organization registered directly on the "
            "platform, or 'External' if the listing was imported from an "
            "outside source like the Volunteer Connector. Moxie-hosted "
            "events also show a 'Verified on Moxie' pill on the "
            "thumbnail and use a 'Sign up' button, while imported events "
            "use 'RSVP' and link back to the original posting."
        ),
    },

    # ── For Volunteers ────────────────────────────────────────────────
    {
        "category": "For Volunteers",
        "question": "How do I sign up as a volunteer?",
        "answer": (
            "Click the Register dropdown in the navigation bar and "
            "choose 'Register as a Volunteer'. Fill in your name, email, "
            "and a password of at least eight characters, then verify "
            "your email with the six-digit code we send you. Everything "
            "else — date of birth, city, high school, zip code, and "
            "skills — is optional and can be added later from your "
            "profile page."
        ),
    },
    {
        "category": "For Volunteers",
        "question": "Is using Moxie free for volunteers?",
        "answer": (
            "Yes, Moxie is completely free for volunteers. There are no "
            "subscriptions, no hidden fees, and no charges for RSVPing "
            "to events or tracking your hours. The only thing you need "
            "is an email address so we can verify your account and send "
            "you event reminders."
        ),
    },
    {
        "category": "For Volunteers",
        "question": "How do I find opportunities near me?",
        "answer": (
            "Open the Discover group in the nav bar and choose 'Browse "
            "Events'. Use the filter row at the top to search by keyword, "
            "pick one or more Causes (career clusters) you care about, "
            "choose your Georgia city from the dropdown, or type your "
            "ZIP code. You can also narrow the list by school or date "
            "range under 'More filters'."
        ),
    },
    {
        "category": "For Volunteers",
        "question": "What happens after I RSVP to an event?",
        "answer": (
            "The opportunity immediately appears in your 'My Events' tab "
            "with the date, time, and organization listed. You'll also "
            "receive a reminder notification within 24 hours of the "
            "event start. When you arrive, tap Check In; when you leave, "
            "tap Check Out and Moxie will calculate your hours "
            "automatically. If your plans change, you can cancel from "
            "the same tab at any time."
        ),
    },

    # ── For Organizations ─────────────────────────────────────────────
    {
        "category": "For Organizations",
        "question": "How can my nonprofit post opportunities?",
        "answer": (
            "Register your organization from the Register dropdown on "
            "the home page, verify your email, and log in. Your "
            "dashboard gives you a full set of tools: create, edit, and "
            "cancel opportunities; post announcements to your "
            "volunteers; review signups and check-ins; verify hours; and "
            "export reports for grant applications or board updates."
        ),
    },
    {
        "category": "For Organizations",
        "question": "Are there any fees for organizations?",
        "answer": (
            "Basic posting and organization listings are free. You can "
            "publish as many opportunities as you like, invite "
            "volunteers, track their hours, and export reports at no "
            "cost. If we introduce optional paid features in the future, "
            "they'll be clearly marked and completely optional — the "
            "core volunteer-management tools will always remain free."
        ),
    },
    {
        "category": "For Organizations",
        "question": "Can I import my existing volunteer roster?",
        "answer": (
            "Yes. Open the 'Data migration' tab in your organization "
            "dashboard and choose 'Choose file'. Moxie accepts CSV and "
            "Excel (.xlsx) rosters with columns for email, first name, "
            "last name, and any other profile fields you already track. "
            "Each imported volunteer receives a one-time activation code "
            "by email and chooses their own password the first time they "
            "log in. You can download a starter template from the same "
            "screen."
        ),
    },
    {
        "category": "For Organizations",
        "question": "How do I manage volunteers who have signed up?",
        "answer": (
            "The 'Volunteers' tab lists everyone who has ever signed up "
            "for one of your events, sorted by total hours. Click any "
            "row to see their full history with your organization, leave "
            "private notes or tags, and — if needed — ban them from "
            "future signups. From 'Reports' you can filter by date "
            "range, volunteer, or opportunity, and export the results "
            "to CSV."
        ),
    },

    # ── Hours & Impact ────────────────────────────────────────────────
    {
        "category": "Hours & Impact",
        "question": "How do I check in and check out of an event?",
        "answer": (
            "Open 'My Events' from the nav bar. At the start of the "
            "event tap Check In; when you finish, tap Check Out. Moxie "
            "records both timestamps and calculates the hours you "
            "contributed. If the organization has a check-in code open "
            "on their event page, scanning that QR code performs the "
            "same action."
        ),
    },
    {
        "category": "Hours & Impact",
        "question": "How do verified hours work?",
        "answer": (
            "After you check out, the hours you logged appear as "
            "'pending' until the organization verifies them. Once an "
            "organizer opens the event in their dashboard and clicks "
            "'Verify hours', that entry is marked verified and locked. "
            "Verified hours appear on your impact record and on any "
            "report your organization runs."
        ),
    },
    {
        "category": "Hours & Impact",
        "question": "Can I export my volunteering history?",
        "answer": (
            "Yes. From the Account group in the nav bar choose "
            "'Export my data'. You can export your hours log, event "
            "registrations, or bookmarked events as either a CSV "
            "spreadsheet or a formatted PDF report. Exports only ever "
            "contain your own information."
        ),
    },

    # ── Account & Support ─────────────────────────────────────────────
    {
        "category": "Account & Support",
        "question": "I forgot my password. How do I reset it?",
        "answer": (
            "Password reset is not automated yet. Email "
            "support@moxiecommunity.org from the address on your account "
            "and tell us you'd like a reset — we'll reply with a link to "
            "set a new password. If you're already logged in, you can "
            "change your password yourself from Profile & Settings "
            "without contacting support."
        ),
    },
    {
        "category": "Account & Support",
        "question": "How do I change my email or profile details?",
        "answer": (
            "Log in and open the 'Profile' tab in the navigation bar. "
            "You can update your first and last name, phone number, "
            "city, state, high school, skills, and notification "
            "preferences, then click Save Changes. Changing the email on "
            "your account isn't supported from the app yet — contact "
            "support and we'll update it for you."
        ),
    },
    {
        "category": "Account & Support",
        "question": (
            "What is two-factor authentication and is it required?"
        ),
        "answer": (
            "Two-factor authentication (2FA) sends a one-time six-digit "
            "code to your email every time you log in, on top of your "
            "password. It's on by default because it's the single "
            "easiest way to keep an account safe. It is not required — "
            "you can turn it off from Profile & Settings if you'd "
            "rather log in with just a password."
        ),
    },
    {
        "category": "Account & Support",
        "question": "How do I contact support?",
        "answer": (
            "Email support@moxiecommunity.org with a short description "
            "of the issue and, if it's about a specific event or "
            "account, the email address associated with it. We aim to "
            "reply within one business day. For quick questions about "
            "using the app, you can also ask the built-in assistant "
            "from the Help tab in your volunteer dashboard."
        ),
    },
]


class FAQItem(QFrame):
    """A single question card: pill shape, question on the left, a
    circular +/− toggle on the right, and the answer revealed inline."""

    def __init__(self, question: str, answer: str, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.FAQ_ITEM)
        self.is_expanded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 16, 16)
        layout.setSpacing(0)

        # Header row: question + circular toggle
        header = QWidget()
        header.setObjectName(theme.FAQ_HEADER)
        header.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(16)

        self.lbl_question = QLabel(question)
        self.lbl_question.setObjectName(theme.FAQ_QUESTION)
        self.lbl_question.setWordWrap(True)

        self.btn_toggle = QPushButton("+")
        self.btn_toggle.setObjectName(theme.FAQ_TOGGLE_BTN)
        self.btn_toggle.setFixedSize(32, 32)
        self.btn_toggle.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.btn_toggle.clicked.connect(self.toggle)

        header_layout.addWidget(self.lbl_question, 1)
        header_layout.addWidget(
            self.btn_toggle, 0, Qt.AlignmentFlag.AlignVCenter
        )

        # Answer (hidden by default)
        self.lbl_answer = QLabel(answer)
        self.lbl_answer.setObjectName(theme.FAQ_ANSWER)
        self.lbl_answer.setWordWrap(True)
        self.lbl_answer.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.lbl_answer.setVisible(False)

        layout.addWidget(header)
        layout.addWidget(self.lbl_answer)

        header.mousePressEvent = lambda e: self.toggle()

    def toggle(self):
        self.is_expanded = not self.is_expanded
        self.lbl_answer.setVisible(self.is_expanded)
        self.btn_toggle.setText("−" if self.is_expanded else "+")
        # Tell QSS so it can swap the circle color on open.
        self.btn_toggle.setProperty(
            "expanded", "true" if self.is_expanded else "false"
        )
        self.btn_toggle.style().unpolish(self.btn_toggle)
        self.btn_toggle.style().polish(self.btn_toggle)


class FAQPage(QWidget):
    def __init__(self, on_back_click=None, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.FAQ_PAGE)
        self.on_back_click = on_back_click
        self._active_category = "All"

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Top row: back button ──────────────────────────────────────
        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(40, 16, 40, 0)
        back_btn = QPushButton("← Back")
        back_btn.setObjectName(theme.BACK_BTN)
        back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if self.on_back_click:
            back_btn.clicked.connect(self.on_back_click)
        top_layout.addWidget(back_btn)
        top_layout.addStretch(1)
        main_layout.addWidget(top)

        # ── Scrollable content ────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setObjectName(theme.FAQ_SCROLL_AREA)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll = scroll

        content = QWidget()
        content.setObjectName(theme.FAQ_SCROLL_CONTENT)
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(60, 10, 60, 60)
        self.content_layout.setSpacing(10)

        # ── Title + subtitle ──────────────────────────────────────────
        title = QLabel("Frequently Asked Questions")
        title.setObjectName(theme.FAQ_TITLE)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(title)

        subtitle = QLabel(
            "New to Moxie or want to get the most out of your "
            "volunteering? This guide covers the answers volunteers and "
            "organizations ask for most."
        )
        subtitle.setObjectName(theme.FAQ_SUBTITLE)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        self.content_layout.addWidget(subtitle)

        self.content_layout.addSpacing(20)

        # ── Search bar (centered, thin) ───────────────────────────────
        search_row = QHBoxLayout()
        search_row.addStretch(1)
        self.search_input = QLineEdit()
        self.search_input.setObjectName(theme.FAQ_searchInput)
        self.search_input.setPlaceholderText(
            "Search questions, keywords, or answers..."
        )
        self.search_input.setFixedWidth(520)
        self.search_input.textChanged.connect(self._apply_filters)
        search_row.addWidget(self.search_input)
        search_row.addStretch(1)
        self.content_layout.addLayout(search_row)

        self.content_layout.addSpacing(6)

        # ── Category pills ────────────────────────────────────────────
        cat_row = QHBoxLayout()
        cat_row.setSpacing(8)
        cat_row.addStretch(1)
        self._cat_group = QButtonGroup(self)
        self._cat_group.setExclusive(True)

        self._cat_buttons = {}
        for cat in ["All"] + categories:
            btn = QPushButton(cat)
            btn.setObjectName(theme.FAQ_CAT_PILL)
            btn.setCheckable(True)
            btn.setChecked(cat == "All")
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.clicked.connect(
                lambda _checked, c=cat: self._set_category(c)
            )
            self._cat_group.addButton(btn)
            self._cat_buttons[cat] = btn
            cat_row.addWidget(btn)

        cat_row.addStretch(1)
        self.content_layout.addLayout(cat_row)

        self.content_layout.addSpacing(24)

        # ── Grouped FAQ list ──────────────────────────────────────────
        self.category_headings = {}
        self.faq_widgets = []

        for cat in categories:
            heading = QLabel(cat)
            heading.setObjectName(theme.FAQ_CATEGORY)
            self.content_layout.addWidget(heading)
            self.category_headings[cat] = heading

            for faq in FAQ_DATA:
                if faq["category"] != cat:
                    continue
                item = FAQItem(faq["question"], faq["answer"])
                self.content_layout.addWidget(item)
                self.faq_widgets.append((faq, item))

            self.content_layout.addSpacing(20)

        self.lbl_no_results = QLabel(
            "No matching FAQ questions found. Try a different keyword "
            "or pick another category."
        )
        self.lbl_no_results.setObjectName(theme.FAQ_NO_RESULTS)
        self.lbl_no_results.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_no_results.setWordWrap(True)
        self.lbl_no_results.setVisible(False)
        self.content_layout.addWidget(self.lbl_no_results)

        self.content_layout.addStretch(1)
        scroll.setWidget(content)
        main_layout.addWidget(scroll, 1)

    # ── Filtering ─────────────────────────────────────────────────────
    def _set_category(self, category: str):
        self._active_category = category
        self._apply_filters()

    def filter_faqs(self, query: str):
        """Kept for backwards compatibility with older callers."""
        self._apply_filters()

    def _apply_filters(self):
        query = self.search_input.text().lower().strip()
        active = self._active_category

        visible_per_cat = {c: 0 for c in categories}

        for faq, widget in self.faq_widgets:
            matches_query = (
                not query or
                query in faq["question"].lower() or
                query in faq["answer"].lower()
            )
            matches_cat = (active == "All" or
                           faq["category"] == active)
            visible = matches_query and matches_cat
            widget.setVisible(visible)
            if visible:
                visible_per_cat[faq["category"]] += 1

        for cat, heading in self.category_headings.items():
            heading.setVisible(visible_per_cat[cat] > 0)

        total_visible = sum(visible_per_cat.values())
        self.lbl_no_results.setVisible(total_visible == 0)
        self.scroll.setVisible(total_visible > 0)


faqData = FAQ_DATA  # noqa: N816
