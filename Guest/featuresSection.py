"""
featuresSection.py - The three-card "what Moxie offers" section.
"""
import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QCursor
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
)

import Events.theme as theme


class _FeatureImage(QLabel):
    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._source = QPixmap(path) if path else QPixmap()
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("padding: 0; border: none;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        if self._source.isNull():
            self.setText("[ image ]")
            return
        scaled = self._source.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (scaled.width() - w) // 2
        y = (scaled.height() - h) // 2
        self.setPixmap(scaled.copy(x, y, w, h))


class FeatureCard(QFrame):
    clicked = pyqtSignal()
    MIN_WIDTH = 260
    MIN_HEIGHT = 320

    def __init__(self, image_filename, title, description, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.FEATURE_CARD)
        self.setMinimumWidth(self.MIN_WIDTH)
        self.setMinimumHeight(self.MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Preferred)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setAccessibleName(title)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        path = (image_filename if os.path.isabs(image_filename)
                else theme.asset(image_filename))
        if not os.path.exists(path):
            path = theme.asset("noThumbnail.png")
        self.image = _FeatureImage(path, self)
        layout.addWidget(self.image, 1)

        text_wrap = QVBoxLayout()
        text_wrap.setContentsMargins(22, 16, 22, 22)
        text_wrap.setSpacing(8)

        self.titleLabel = QLabel(title)
        self.titleLabel.setObjectName(theme.FEATURE_TITLE)
        self.titleLabel.setWordWrap(True)

        self.desLabel = QLabel(description)
        self.desLabel.setObjectName(theme.FEATURE_DESC)
        self.desLabel.setWordWrap(True)

        text_wrap.addWidget(self.titleLabel)
        text_wrap.addWidget(self.desLabel)
        text_wrap.addStretch(1)
        layout.addLayout(text_wrap)

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class FeaturesSection(QWidget):
    discoverRequested = pyqtSignal()
    postRequested = pyqtSignal()
    manageRequested = pyqtSignal()

    CARDS = [
        ("discoverOpportunitiesImg.jpg",
         "Discover Volunteering Opportunities",
         "Browse volunteering opportunities and events from "
         "organizations near you or fully remote."),
        ("postVolunteerOpportunities.jpg",
         "Post Volunteering Opportunities",
         "Post volunteering opportunities and events for your "
         "organization in minutes."),
        ("trackVolunteers.jpg",
         "Manage Volunteers Seamlessly",
         "Recruit, manage, and communicate with your volunteer team."),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.FEATURES_SECTION)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Preferred)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 50, 40, 50)
        outer.setSpacing(28)

        section_title = QLabel("What Moxie Offers")
        section_title.setObjectName(theme.SECTION_TITLE)
        section_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(22)

        self.cards = []
        for idx, (filename, title, desc) in enumerate(self.CARDS):
            card = FeatureCard(filename, title, desc)
            card.clicked.connect(self._emit_for(idx))
            self.cards.append(card)
            cards_row.addWidget(card, 1)

        outer.addWidget(section_title)
        outer.addLayout(cards_row, 1)

    def _emit_for(self, idx):
        if idx == 0:
            return self.discoverRequested.emit
        if idx == 1:
            return self.postRequested.emit
        return self.manageRequested.emit