"""
qrEventDialog.py — QR + time-gated event page (organization side).

Generates a QR code for the event, but only while the event is
actually happening. Outside the window the dialog shows a status
message ("Opens Oct 15 at 9:00 AM" / "This event has ended")
instead of the QR.
"""
import hashlib
import hmac
import os
import tempfile
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCursor, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

import Events.theme as theme
from Events.dateFormat import format_date, format_time

try:
    import qrcode
    _HAS_QR = True
except ImportError:
    _HAS_QR = False

QR_SECRET = os.environ.get("MOXIE_QR_SECRET", "moxie-default-hmac-key")


def _event_token(event):
    """HMAC over (opportunityID, start, end) so tokens can't be reused."""
    oid = str(event["opportunityID"])
    start = f"{event['event_date']} {event['start_time'] or ''}"
    end = f"{event['event_end_date'] or event['event_date']} " \
          f"{event['end_time'] or ''}"
    msg = f"{oid}|{start}|{end}".encode("utf-8")
    return hmac.new(QR_SECRET.encode(), msg, hashlib.sha256).hexdigest()[:16]


def get_event_status(event, now=None):
    """Return 'upcoming' | 'open' | 'ended' | 'unknown'."""
    now = now or datetime.now()
    d = str(event["event_date"] or "").strip()
    if not d:
        return "unknown"
    try:
        start_date = datetime.fromisoformat(d[:10]).date()
    except ValueError:
        return "unknown"

    start_txt = (event["start_time"] or "00:00")[:5]
    end_txt = (event["end_time"] or "23:59")[:5]
    try:
        sh, sm = map(int, start_txt.split(":"))
        eh, em = map(int, end_txt.split(":"))
    except (ValueError, AttributeError):
        sh, sm, eh, em = 0, 0, 23, 59

    end_d = event.get("event_end_date") or d
    try:
        end_date = datetime.fromisoformat(str(end_d)[:10]).date()
    except (ValueError, TypeError):
        end_date = start_date

    start_dt = datetime.combine(start_date, datetime.min.time()) \
        .replace(hour=sh, minute=sm)
    end_dt = datetime.combine(end_date, datetime.min.time()) \
        .replace(hour=eh, minute=em)

    if now < start_dt:
        return "upcoming"
    if now > end_dt:
        return "ended"
    return "open"


class QREventDialog(QDialog):
    """Shows the QR code while the event is open."""

    def __init__(self, db, event, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.EVENT_QR_DIALOG)
        self.setWindowTitle(f"Check-in — {event['title']}")
        self.setMinimumWidth(420)
        self.db = db
        self.event = event
        self._qr_path = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(12)

        title = QLabel(event["title"] or "Event")
        title.setObjectName(theme.EVENT_TITLE_LIST)
        title.setWordWrap(True)
        outer.addWidget(title)

        self.window_lbl = QLabel("")
        self.window_lbl.setObjectName(theme.EVENT_QR_WINDOW)
        self.window_lbl.setWordWrap(True)
        outer.addWidget(self.window_lbl)

        self.qr_lbl = QLabel()
        self.qr_lbl.setObjectName(theme.EVENT_QR_IMAGE)
        self.qr_lbl.setFixedSize(280, 280)
        self.qr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.qr_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName(theme.EVENT_QR_STATUS)
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setWordWrap(True)
        outer.addWidget(self.status_lbl)

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName(theme.DETAILS_CLOSE_BTN)
        close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close.clicked.connect(self.reject)
        row.addWidget(close)
        outer.addLayout(row)

        # Refresh every 30s so the state changes live as the window opens.
        self._timer = QTimer(self)
        self._timer.setInterval(30_000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

        self._refresh()

    def _refresh(self):
        e = self.event
        start_txt = format_time(e["start_time"]) or "start time"
        end_txt = format_time(e["end_time"]) or "end time"
        date_txt = format_date(e["event_date"]) or "TBD"
        self.window_lbl.setText(
            f"Runs {date_txt} · {start_txt} – {end_txt}"
        )

        status = get_event_status(e)
        if status == "open":
            self._render_qr()
            self.status_lbl.setText(
                "Check-in is open. Volunteers can scan this QR code."
            )
            self.qr_lbl.setVisible(True)
        elif status == "upcoming":
            self._clear_qr()
            self.status_lbl.setText(
                f"Check-in opens on {date_txt} at {start_txt}."
            )
            self.qr_lbl.setVisible(False)
        elif status == "ended":
            self._clear_qr()
            self.status_lbl.setText(
                "This event has ended. Check-in is closed."
            )
            self.qr_lbl.setVisible(False)
        else:
            self._clear_qr()
            self.status_lbl.setText(
                "Set the event date and time to enable check-in."
            )
            self.qr_lbl.setVisible(False)

    def _clear_qr(self):
        self.qr_lbl.clear()
        if self._qr_path and os.path.exists(self._qr_path):
            try:
                os.remove(self._qr_path)
            except OSError:
                pass
            self._qr_path = None

    def _render_qr(self):
        if not _HAS_QR:
            self.qr_lbl.setText("Install qrcode[pil]\nto render a QR code")
            return
        payload = (
            f"moxie://checkin/{self.event['opportunityID']}"
            f"?t={_event_token(self.event)}"
        )
        img = qrcode.make(payload)
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        img.save(path)
        self._qr_path = path
        pix = QPixmap(path).scaled(
            260, 260,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.qr_lbl.setPixmap(pix)
