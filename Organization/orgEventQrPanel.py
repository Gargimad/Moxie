"""orgEventQrPanel.py — list of the org's events with check-in QR codes."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import Events.theme as theme
from Events.dateFormat import format_event_when
from Events.qrEventDialog import QREventDialog, get_event_status


class OrgEventQrPanel(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.org = None

        v = QVBoxLayout(self)
        v.setContentsMargins(40, 20, 40, 20)
        v.setSpacing(12)

        heading = QLabel("Event check-in codes")
        heading.setObjectName(theme.SECTION_TITLE)
        v.addWidget(heading)

        sub = QLabel(
            "Each event's QR code only works while the event is live. "
            "Outside the event window, check-in is disabled."
        )
        sub.setObjectName(theme.EVENT_META_VALUE)
        sub.setWordWrap(True)
        v.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setObjectName(theme.HOME_SCROLL)
        content = QWidget()
        self.list_layout = QVBoxLayout(content)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch(1)
        scroll.setWidget(content)
        v.addWidget(scroll, 1)

    def set_org(self, org):
        self.org = org

    def refresh(self):
        if not self.org:
            return
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        rows = self.db.get_opportunities_by_org(self.org["orgID"]) or []
        rows = [r for r in rows if (r["status"] or "open") != "cancelled"]

        if not rows:
            empty = QLabel("No events yet.")
            empty.setObjectName(theme.VOLUNTEER_EMPTY)
            self.list_layout.insertWidget(0, empty)
            return

        for r in rows:
            self.list_layout.insertWidget(
                self.list_layout.count() - 1, self._card(r)
            )

    def _card(self, r):
        card = QFrame()
        card.setObjectName(theme.EVENT_CARD)
        h = QHBoxLayout(card)
        h.setContentsMargins(16, 12, 16, 12)
        h.setSpacing(10)

        col = QVBoxLayout()
        t = QLabel(r["title"] or "Untitled")
        t.setObjectName(theme.EVENT_TITLE_LIST)
        col.addWidget(t)
        meta = QLabel(format_event_when(r))
        meta.setObjectName(theme.EVENT_META_VALUE)
        col.addWidget(meta)

        status = get_event_status(r)
        status_lbl = QLabel({
            "open": "● Live now",
            "upcoming": "○ Not started",
            "ended": "○ Ended",
            "unknown": "○ No date",
        }.get(status, "○"))
        status_lbl.setObjectName(theme.EVENT_META_VALUE)
        col.addWidget(status_lbl)

        h.addLayout(col, 1)

        btn = QPushButton("Open check-in")
        btn.setObjectName(theme.PRIMARY_BTN)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.clicked.connect(
            lambda _, ev=r: QREventDialog(self.db, ev, parent=self).exec()
        )
        h.addWidget(btn)
        return card
