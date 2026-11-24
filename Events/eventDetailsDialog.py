"""
eventDetailsDialog.py — Modal opened when a card is clicked.

Shows the full, untruncated description along with the same badges and
metadata the card carries (date, time, spots, location, org). The RSVP
and link buttons reuse the card's own methods so behaviour stays
identical between card and dialog.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import Events.theme as theme
from Events.eventCard import build_badges, make_meta_row


class EventDetailsDialog(QDialog):
    def __init__(self, card, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.EVENT_DETAILS_DIALOG)
        self.setWindowTitle(card.title)
        self.setModal(True)
        self.setMinimumWidth(540)
        self.setMinimumHeight(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        # ── badge row ─────────────────────────────────────────────────────
        badges = QHBoxLayout()
        badges.setSpacing(6)
        for lbl in build_badges(card.category, card.is_remote,
                                card.location, card.status):
            badges.addWidget(lbl)
        badges.addStretch(1)
        layout.addLayout(badges)

        # ── title + org ───────────────────────────────────────────────────
        title = QLabel(card.title)
        title.setObjectName(theme.EVENT_TITLE_LIST)
        title.setWordWrap(True)
        layout.addWidget(title)

        org = QLabel(f"by {card.org_name}")
        org.setObjectName(theme.EVENT_ORG)
        layout.addWidget(org)

        # ── meta rows ─────────────────────────────────────────────────────
        layout.addLayout(make_meta_row("Date", card._date_text()))
        where = "Remote" if card.is_remote else (
            card.location or "Location TBD")
        layout.addLayout(make_meta_row("Where", where))
        spots = card._spots_text()
        if spots:
            layout.addLayout(make_meta_row("Spots", spots))

        # ── scrollable description ────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setObjectName(theme.DETAILS_SCROLL)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        content = QWidget()
        content.setObjectName(theme.DETAILS_SCROLL_CONTENT)
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 6, 0, 0)

        desc = QLabel(card.description or "No description provided.")
        desc.setObjectName(theme.DETAILS_DESCRIPTION)
        desc.setWordWrap(True)
        desc.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        desc.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        cl.addWidget(desc)
        cl.addStretch(1)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # ── action buttons ────────────────────────────────────────────────
        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        close_btn = QPushButton("Close")
        close_btn.setObjectName(theme.DETAILS_CLOSE_BTN)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.clicked.connect(self.reject)

        link_btn = card._make_link_button()
        rsvp_btn = card._make_rsvp_button()
        # Card's RSVP emits a signal to the listing page; the dialog just
        # closes so the page's message box is visible on top.
        rsvp_btn.clicked.connect(self.accept)

        buttons.addWidget(close_btn)
        buttons.addStretch(1)
        buttons.addWidget(link_btn)
        buttons.addWidget(rsvp_btn)
        layout.addLayout(buttons)
