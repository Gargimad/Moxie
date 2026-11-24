"""
eventCard.py — The opportunity card used on the home carousels and the
volunteer listing page.

Two card variants, styled entirely by QSS:
    • "EventCard"       imported orgs (Volunteer Connector)
    • "EventCardMoxie"  Moxie-registered orgs, with a "Verified on Moxie"
                        pill and a "Sign up" button label

Rounded corners and card colors live in lightMode.qss / darkMode.qss.
This file only decides *which* object name to use.
"""

import hashlib
import os
import urllib.error
import urllib.request

from PyQt6.QtCore import QByteArray, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import Events.theme as theme
from Events.dateFormat import format_event_when

FALLBACK_IMAGE = theme.asset("noThumbnail.png")
THUMB_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".thumb_cache"
)

_PIXMAP_CACHE = {}
_PIXMAP_CACHE_LIMIT = 300

USER_AGENT = "Moxie/1.0"

# Corner radius used when we round the image itself.
THUMB_RADIUS = 13

# Inline style for the "Verified on Moxie" pill. Kept in Python because
# it's a one-off element whose color depends on the accent, not the
# theme. If you'd rather move it to QSS, add a rule for #VerifiedPill.
VERIFIED_PILL_STYLE = """
QLabel {
    background-color: #B1A2A8;
    color: #2D1A3E;
    border-radius: 9px;
    padding: 3px 9px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
}
"""


def clear_thumbnail_cache():
    _PIXMAP_CACHE.clear()


def _cache_path_for(url: str) -> str:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"):
        ext = ".img"
    return os.path.join(THUMB_CACHE_DIR, h + ext)


def _fetch_remote_bytes(url: str, timeout: int = 8) -> bytes:
    os.makedirs(THUMB_CACHE_DIR, exist_ok=True)
    cache_path = _cache_path_for(url)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                return f.read()
        except OSError:
            pass
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f"[thumb] fetch failed for {url[:60]}: {e}")
        return b""
    try:
        with open(cache_path, "wb") as f:
            f.write(data)
    except OSError as e:
        print(f"[thumb] cache write failed: {e}")
    return data


def _fit_centered(pixmap, width, height, radius=None):
    """
    Scale pixmap to fit inside (width, height), center it on a canvas of
    that size, and optionally round the canvas corners.
    """
    scaled = pixmap.scaled(
        width, height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    canvas = QPixmap(width, height)
    canvas.fill(Qt.GlobalColor.transparent)

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    if radius:
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(0, 0, width, height), radius, radius
        )
        painter.setClipPath(path)

    painter.drawPixmap(
        (width - scaled.width()) // 2,
        (height - scaled.height()) // 2,
        scaled,
    )
    painter.end()
    return canvas


def load_thumbnail_pixmap(blob, width, height, key=None, radius=None):
    cache_key = (key, width, height, radius) if key is not None else None
    if cache_key and cache_key in _PIXMAP_CACHE:
        return _PIXMAP_CACHE[cache_key]

    pixmap = QPixmap()
    if isinstance(blob, str) and blob:
        if blob.startswith("http://") or blob.startswith("https://"):
            data = _fetch_remote_bytes(blob)
            if data:
                pixmap.loadFromData(QByteArray(data))
        elif blob.startswith("//"):
            data = _fetch_remote_bytes("https:" + blob)
            if data:
                pixmap.loadFromData(QByteArray(data))
        else:
            pixmap = QPixmap(blob)
    elif isinstance(blob, (bytes, bytearray)) and blob:
        pixmap.loadFromData(QByteArray(bytes(blob)))

    if pixmap.isNull() and os.path.exists(FALLBACK_IMAGE):
        pixmap = QPixmap(FALLBACK_IMAGE)
    if pixmap.isNull():
        return None

    result = _fit_centered(pixmap, width, height, radius=radius)

    if cache_key:
        if len(_PIXMAP_CACHE) >= _PIXMAP_CACHE_LIMIT:
            _PIXMAP_CACHE.pop(next(iter(_PIXMAP_CACHE)))
        _PIXMAP_CACHE[cache_key] = result
    return result


def truncate_text(text, max_len):
    if not text:
        return ""
    text = " ".join(str(text).split())
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "…"


def build_badges(category, is_remote, location, status):
    labels = []
    if category:
        cat = QLabel(category)
        cat.setObjectName(theme.EVENT_CATEGORY_BADGE)
        cat.setAlignment(Qt.AlignmentFlag.AlignCenter)
        labels.append(cat)

    loc_text = "Remote" if is_remote else (location or "Location TBD")
    loc = QLabel(loc_text)
    loc.setObjectName(theme.EVENT_LOCATION_BADGE)
    loc.setAlignment(Qt.AlignmentFlag.AlignCenter)
    labels.append(loc)

    if status and status != "open":
        st = QLabel(status.upper())
        st.setObjectName(theme.EVENT_STATUS_BADGE)
        st.setAlignment(Qt.AlignmentFlag.AlignCenter)
        labels.append(st)
    return labels


def make_meta_row(key, value):
    row = QHBoxLayout()
    row.setSpacing(6)
    row.setContentsMargins(0, 0, 0, 0)
    k = QLabel(f"{key}")
    k.setObjectName(theme.EVENT_META_KEY)
    v = QLabel(value)
    v.setObjectName(theme.EVENT_META_VALUE)
    v.setWordWrap(True)
    row.addWidget(k)
    row.addWidget(v, 1)
    return row


class EventCard(QFrame):
    open_link_requested = pyqtSignal(str)
    rsvp_requested = pyqtSignal(int)
    details_requested = pyqtSignal(object)

    GRID_WIDTH = 300
    GRID_THUMB_H = 150
    GRID_FIXED_HEIGHT = 465
    LIST_THUMB_W = 220
    LIST_THUMB_H = 160
    LIST_MIN_HEIGHT = 160

    def __init__(self, row, view_mode="grid", parent=None,
                 current_volunteer_id=None):
        super().__init__(parent)

        # Which QSS variant? Moxie orgs get the accent border.
        self.row = row
        self.view_mode = view_mode
        self.current_volunteer_id = current_volunteer_id

        def g(key, default=""):
            try:
                v = row[key]
            except (KeyError, IndexError, TypeError):
                return default
            return v if v is not None else default

        try:
            self.is_moxie_org = bool(int(g("is_moxie_org", 0) or 0))
        except (TypeError, ValueError):
            self.is_moxie_org = False

        self.setObjectName(
            "EventCardMoxie" if self.is_moxie_org else theme.EVENT_CARD
        )
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.opportunity_id = g("opportunityID", 0)
        self.title = g("title", "Untitled event")
        self.description = g("description", "")
        self.category = g("category", "")
        self.location = g("location", "")
        self.is_remote = bool(g("is_remote", 0))
        self.event_date = g("event_date", "")
        self.event_end_date = g("event_end_date", "")
        self.start_time = g("start_time", "")
        self.end_time = g("end_time", "")
        self.capacity = g("capacity", None)
        self.status = g("status", "open") or "open"
        self.org_name = g("org_name", "Independent")
        self.thumbnail = g("thumbnail", None)
        self.website_link = g("website_link", "")
        try:
            self.registered_count = int(g("registered_count", 0) or 0)
        except (TypeError, ValueError):
            self.registered_count = 0

        if (self.status == "open" and self.capacity and
                self.registered_count >= self.capacity):
            self.status = "full"

        if view_mode == "list":
            self._build_list_layout()
        else:
            self._build_grid_layout()

    # ── shared sub-builders ───────────────────────────────────────────────
    def _make_thumbnail(self, w, h):
        """
        Returns a widget containing the (rounded) image and, for Moxie
        orgs, a small "Verified on Moxie" pill overlaid on the top-left.
        """
        wrap = QWidget()
        wrap.setFixedSize(w, h)
        wrap.setStyleSheet("background: transparent;")

        thumb = QLabel(wrap)
        thumb.setObjectName(theme.EVENT_THUMB)
        thumb.setGeometry(0, 0, w, h)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setScaledContents(False)

        pixmap = load_thumbnail_pixmap(
            self.thumbnail, w, h,
            key=self.opportunity_id or None,
            radius=THUMB_RADIUS,
        )
        if pixmap is not None:
            thumb.setPixmap(pixmap)
        else:
            thumb.setText("No image")

        if self.is_moxie_org:
            pill = QLabel("✓ Verified on Moxie", wrap)
            pill.setStyleSheet(VERIFIED_PILL_STYLE)
            pill.adjustSize()
            pill.move(10, 10)
            pill.raise_()

        return wrap

    def _make_badges(self, with_org=False):
        row = QHBoxLayout()
        row.setSpacing(6)
        row.setContentsMargins(0, 0, 0, 0)
        for lbl in build_badges(self.category, self.is_remote,
                                self.location, self.status):
            row.addWidget(lbl)
        if with_org:
            org = QLabel(f"by {self.org_name}")
            org.setObjectName(theme.EVENT_ORG)
            row.addWidget(org)
        row.addStretch(1)
        return row

    def _make_link_button(self):
        btn = QPushButton("Open link" if self.website_link else "No link")
        btn.setObjectName(theme.EVENT_LINK_BTN)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setEnabled(bool(self.website_link))
        btn.clicked.connect(self.open_link)
        return btn

    def _rsvp_label(self):
        if self.status == "open":
            return "Sign up" if self.is_moxie_org else "RSVP"
        if self.status == "full":
            return "Full"
        return self.status.capitalize()

    def _make_rsvp_button(self):
        btn = QPushButton(self._rsvp_label())
        btn.setObjectName(theme.EVENT_RSVP_BTN)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if self.status == "open":
            btn.setEnabled(True)
            btn.setToolTip(
                "Sign up for this event" if self.current_volunteer_id
                else "Log in as a volunteer to sign up"
            )
        else:
            btn.setEnabled(False)
            btn.setToolTip(f"This event is {self.status}")
        btn.clicked.connect(self.request_rsvp)
        return btn

    def _date_text(self):
        return format_event_when(self.row)

    def _spots_text(self):
        if not self.capacity:
            return ""
        left = max(0, self.capacity - self.registered_count)
        if left == 0:
            return "Full"
        if left == 1:
            return "1 spot left"
        if left <= 3:
            return f"Only {left} spots left"
        return f"{left} of {self.capacity} left"

    def _make_date_line(self):
        box = QVBoxLayout()
        box.setSpacing(4)
        box.setContentsMargins(0, 0, 0, 0)
        box.addLayout(make_meta_row("Date", self._date_text()))
        spots = self._spots_text()
        if spots:
            box.addLayout(make_meta_row("Spots", spots))
        return box

    def _make_org_line(self):
        lbl = QLabel(f"by {self.org_name}")
        lbl.setObjectName(theme.EVENT_ORG)
        lbl.setWordWrap(True)
        return lbl

    # ── grid layout ───────────────────────────────────────────────────────
    def _build_grid_layout(self):
        self.setFixedWidth(self.GRID_WIDTH)
        self.setFixedHeight(self.GRID_FIXED_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(
            self._make_thumbnail(self.GRID_WIDTH, self.GRID_THUMB_H)
        )

        content = QVBoxLayout()
        content.setContentsMargins(16, 14, 16, 14)
        content.setSpacing(10)

        content.addLayout(self._make_badges())

        title_lbl = QLabel(truncate_text(self.title, 60))
        title_lbl.setObjectName(theme.EVENT_TITLE)
        title_lbl.setWordWrap(True)
        title_lbl.setMaximumHeight(44)
        title_lbl.setToolTip(self.title)
        content.addWidget(title_lbl)

        content.addWidget(self._make_org_line())

        desc_lbl = QLabel(truncate_text(self.description, 120))
        desc_lbl.setObjectName(theme.EVENT_DESCRIPTION)
        desc_lbl.setWordWrap(True)
        desc_lbl.setMinimumHeight(50)
        desc_lbl.setMaximumHeight(58)
        content.addWidget(desc_lbl)

        content.addLayout(self._make_date_line())
        content.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self._make_link_button())
        actions.addWidget(self._make_rsvp_button())
        content.addLayout(actions)

        layout.addLayout(content)

    # ── list layout ───────────────────────────────────────────────────────
    def _build_list_layout(self):
        self.setMinimumHeight(self.LIST_MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Minimum)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(
            self._make_thumbnail(self.LIST_THUMB_W, self.LIST_THUMB_H)
        )

        content = QVBoxLayout()
        content.setContentsMargins(20, 16, 20, 16)
        content.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(16)

        title_lbl = QLabel(self.title)
        title_lbl.setObjectName(theme.EVENT_TITLE_LIST)
        title_lbl.setWordWrap(True)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self._make_link_button())
        actions.addWidget(self._make_rsvp_button())

        top.addWidget(title_lbl, 1)
        top.addLayout(actions)
        content.addLayout(top)

        content.addLayout(self._make_badges(with_org=True))

        desc_lbl = QLabel(truncate_text(self.description, 260))
        desc_lbl.setObjectName(theme.EVENT_DESCRIPTION)
        desc_lbl.setWordWrap(True)
        desc_lbl.setMaximumHeight(60)
        content.addWidget(desc_lbl)

        content.addLayout(self._make_date_line())
        content.addStretch(1)

        layout.addLayout(content, 1)

    # ── events ────────────────────────────────────────────────────────────
    def open_link(self):
        if self.website_link:
            self.open_link_requested.emit(self.website_link)

    def request_rsvp(self):
        if self.opportunity_id:
            self.rsvp_requested.emit(self.opportunity_id)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if (event.button() == Qt.MouseButton.LeftButton and
                self.rect().contains(event.position().toPoint())):
            self.details_requested.emit(self)
        super().mouseReleaseEvent(event)
    detailsRequested = property(lambda self: self.details_requested)  # noqa: N815
    openLinkRequested = property(lambda self: self.open_link_requested)  # noqa: N815
    rsvpRequested = property(lambda self: self.rsvp_requested)  # noqa: N815
