"""
heroSection.py — Editorial split-panel hero for Moxie's guest home.

Mirrors a magazine layout:
    [left]   colored panel with three overlapping volunteer photos
    [right]  big wordmark, headline, mission line, Learn More button
    [bottom] solid brand bar spanning the full width

Positions are expressed as fractions of the hero's current size so
the layout scales cleanly on resize.
"""
import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QCursor, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QSizePolicy, QGraphicsDropShadowEffect,
)

import Events.theme as theme


class HeroPhoto(QLabel):
    """A single photo tile with a soft drop shadow."""

    def __init__(self, filename, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.HERO_PHOTO)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._source = QPixmap()

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 16)
        shadow.setColor(QColor(45, 26, 62, 120))
        self.setGraphicsEffect(shadow)

        self.load(filename)

    def load(self, filename):
        path = (filename if os.path.isabs(filename)
                else theme.asset(filename))
        if not os.path.exists(path):
            path = theme.asset("noThumbnail.png")
        self._source = QPixmap(path)
        self._rescale()

    def _rescale(self):
        if self._source.isNull():
            return
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        scaled = self._source.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (scaled.width() - w) // 2
        y = (scaled.height() - h) // 2
        self.setPixmap(scaled.copy(x, y, w, h))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()


class HeroSection(QWidget):
    """Editorial hero: colored left panel with three photos, wordmark
    headline + mission on the right, solid bar across the bottom."""

    learnMoreRequested = pyqtSignal()

    # Photos are positioned as fractions of the LEFT PANEL's size.
    # (x, y, w, h, filename). Later entries render on top of earlier.
    PHOTO_LAYOUT = [
        # back layer: bottom-right, largest
        (0.28, 0.44, 0.40, 0.44, "hero1.jpg"),
        # top-left, separate
        (0.05, 0.16, 0.38, 0.32, "discoverOpportunitiesImg.jpg"),
        # front layer: overlaps the top-left of the bottom image
        (0.12, 0.50, 0.26, 0.24, "trackVolunteers.jpg"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.heroSection)
        self.setMinimumHeight(600)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Preferred)

        # Background panels — added first so they sit behind photos
        self.left_panel = QFrame(self)
        self.left_panel.setObjectName(theme.HERO_LEFT_PANEL)

        self.bottom_bar = QFrame(self)
        self.bottom_bar.setObjectName(theme.HERO_BOTTOM_BAR)

        # Photos on the left
        self._photos = [
            HeroPhoto(filename, self)
            for (_x, _y, _w, _h, filename) in self.PHOTO_LAYOUT
        ]

        # Text panel on the right
        self.text_panel = QWidget(self)
        self.text_panel.setObjectName(theme.HERO_RIGHT_PANEL)
        self._build_text_panel()

        self.left_panel.lower()
        self.bottom_bar.lower()

    # ── Text panel ────────────────────────────────────────────────────
    def _build_text_panel(self):
        v = QVBoxLayout(self.text_panel)
        v.setContentsMargins(56, 44, 56, 44)
        v.setSpacing(18)

        self.wordmark = QLabel()
        self.wordmark.setObjectName(theme.HERO_WORDMARK)
        self.wordmark.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        v.addWidget(self.wordmark)

        headline = QLabel("Volunteering that fits\nwho you're becoming.")
        headline.setObjectName(theme.HERO_HEADLINE)
        headline.setWordWrap(True)
        v.addWidget(headline)

        sub = QLabel(
            "Moxie connects Georgia students to local nonprofits "
            "through the career clusters they're already curious about."
        )
        sub.setObjectName(theme.HERO_SUB)
        sub.setWordWrap(True)
        v.addWidget(sub)

        v.addSpacing(8)

        btn_row = QHBoxLayout()
        learn = QPushButton("Learn More")
        learn.setObjectName(theme.HERO_LEARN_BTN)
        learn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        learn.setFixedSize(180, 54)
        learn.clicked.connect(self.learnMoreRequested.emit)
        btn_row.addWidget(learn)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        v.addStretch(1)

        self._load_wordmark(False)

    def _load_wordmark(self, is_dark):
        filename = "logoFullLight.png" if is_dark else "logoFullDark.png"
        path = theme.asset(filename)
        if os.path.exists(path):
            pix = QPixmap(path)
            self.wordmark.setPixmap(
                pix.scaledToHeight(
                    96, Qt.TransformationMode.SmoothTransformation
                )
            )
        else:
            self.wordmark.setText("Moxie")
            self.wordmark.setStyleSheet(
                "font-size: 84px; font-weight: 900;"
                " letter-spacing: -3px;"
            )

    def set_theme(self, is_dark):
        """Called by landing when the theme toggles."""
        self._load_wordmark(is_dark)

    # ── Resize ────────────────────────────────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        bar_h = int(h * 0.14)
        card_h = h - bar_h
        left_w = int(w * 0.52)

        # Background panels
        self.left_panel.setGeometry(0, 0, left_w, card_h)
        self.bottom_bar.setGeometry(0, card_h, w, bar_h)
        self.text_panel.setGeometry(left_w, 0, w - left_w, card_h)

        # Photos
        for photo, (fx, fy, fw, fh, _name) in zip(
            self._photos, self.PHOTO_LAYOUT
        ):
            px = int(fx * left_w)
            py = int(fy * card_h)
            pw = int(fw * left_w)
            ph = int(fh * card_h)
            photo.setGeometry(px, py, pw, ph)
            photo.show()

        # Re-stack so later PHOTO_LAYOUT entries render on top,
        # then bring the text panel back up so it can't be covered.
        for photo in self._photos:
            photo.raise_()
        self.text_panel.raise_()