"""eventCard.py — The opportunity card used on the home carousels and
the volunteer listing page."""
import hashlib
import os
import urllib.error
import urllib.request

from PyQt6.QtCore import QByteArray, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QPainter, QPainterPath, QPixmap
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
from Events.dateFormat import (
    format_date_short,
    format_time,
    format_weekday,
)

FALLBACK_IMAGE = theme.asset("noThumbnail.png")
THUMB_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".thumb_cache"
)

_PIXMAP_CACHE = {}
_PIXMAP_CACHE_LIMIT = 300

USER_AGENT = "Moxie/1.0"
THUMB_RADIUS = 0


# ── Compact date formatting for the narrow card column ───────────────
def _short_when(row):
    """
    'Wed, Nov 11 · 8 AM – 3 PM' — compact enough for the card.
    Falls back to whatever `format_event_when` would produce when the
    date can't be parsed.
    """
    def g(key, default=""):
        try:
            v = row[key]
        except (KeyError, IndexError, TypeError):
            return default
        return default if v is None else v

    start = g("event_date")
    end = g("event_end_date")
    t_start = g("start_time")
    t_end = g("end_time")

    if not start:
        return "TBD"

    # Date part
    weekday = format_weekday(start)          # "Wed"
    day_short = format_date_short(start)     # "Nov 11"

    if end and str(end)[:10] != str(start)[:10]:
        end_short = format_date_short(end)
        date_part = f"{weekday}, {day_short}–{end_short}"
    else:
        date_part = f"{weekday}, {day_short}"

    # Time part — trim " AM"/" PM" to just " AM"/" PM" but with
    # en dash between them and no space.
    def compact_time(hhmm):
        t = format_time(hhmm)     # "8:00 AM"
        if not t:
            return ""
        # "8:00 AM" -> "8 AM" when minutes are :00
        if t.endswith(":00 AM"):
            return t[:-5] + " AM"
        if t.endswith(":00 PM"):
            return t[:-5] + " PM"
        return t

    s = compact_time(t_start)
    e = compact_time(t_end)
    if s and e:
        time_part = f"{s}–{e}"
    else:
        time_part = s or e

    if time_part:
        return f"{date_part} · {time_part}"
    return date_part


# ── Thumbnail loading (supports http/https URLs) ─────────────────────
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
        path.addRoundedRect(QRectF(0, 0, width, height), radius, radius)
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
        elif blob.startswith("/"):
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
    return cut + "..."


# ── Badge builders ───────────────────────────────────────────────────
def build_badges(category, is_remote, location, status):
    """
    Category gets the blue badge (#EventCategoryBadge), location gets
    the outlined badge, status gets the purple badge. Never returns
    plain text — every label goes through a named theme constant so
    QSS can style it.
    """
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


# ── EventCard ────────────────────────────────────────────────────────
class EventCard(QFrame):
    open_link_requested = pyqtSignal(str)
    rsvp_requested = pyqtSignal(int)
    details_requested = pyqtSignal(object)

    GRID_WIDTH = 300
    GRID_THUMB_H = 150
    GRID_FIXED_HEIGHT = 545
    LIST_THUMB_W = 220
    LIST_THUMB_H = 160
    LIST_MIN_HEIGHT = 160

    def __init__(self, row, view_mode="grid", parent=None,
                 current_volunteer_id=None, bookmarked_ids=None):
        super().__init__(parent)

        self.row = row
        self.view_mode = view_mode
        self.current_volunteer_id = current_volunteer_id
        self._bookmarked_ids = set(bookmarked_ids or set())
        self._bookmark_cb = None

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

    # ── Thumbnail with source pill + bookmark overlay ────────────────
    def _make_thumbnail(self, w, h):
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

        # Source pill (top-left of thumbnail)
        pill = QLabel(
            "Moxie" if self.is_moxie_org else "External", wrap
        )
        pill.setObjectName(
            theme.EVENT_SOURCE_MOXIE if self.is_moxie_org
            else theme.EVENT_SOURCE_EXTERNAL
        )
        pill.adjustSize()
        pill.move(10, 10)
        pill.raise_()

        # Bookmark button (top-right of thumbnail)
        bm = self._make_bookmark_button(wrap)
        bm.move(w - bm.width() - 10, 10)
        bm.raise_()

        return wrap

    # ── Buttons ──────────────────────────────────────────────────────
    def _make_link_button(self):
        btn = QPushButton("Link" if self.website_link else "No link")
        btn.setObjectName(theme.EVENT_LINK_BTN)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setEnabled(bool(self.website_link))
        btn.clicked.connect(self.open_link)
        return btn

    def _rsvp_label(self):
        if self.status == "open":
            action = "Sign up" if self.is_moxie_org else "RSVP"
            if not self.current_volunteer_id:
                return f"Log in to {action}"
            return action
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

    def _make_details_button(self):
        btn = QPushButton("Open Details")
        btn.setObjectName(theme.EVENT_DETAILS_BTN)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setToolTip("See the full event description and metadata")
        btn.setMinimumHeight(34)
        btn.clicked.connect(self.request_details)
        return btn

    # ── Bookmark ─────────────────────────────────────────────────────
    def _is_bookmarked(self):
        if not self.current_volunteer_id or not self._bookmarked_ids:
            return False
        return self.opportunity_id in self._bookmarked_ids

    def set_bookmark_callback(self, fn):
        self._bookmark_cb = fn

    def _make_bookmark_button(self, parent):
        on = self._is_bookmarked()
        btn = QPushButton("★" if on else "☆", parent)
        btn.setObjectName(
            theme.EVENT_BOOKMARK_BTN_ON if on else theme.EVENT_BOOKMARK_BTN
        )
        btn.setFixedSize(34, 34)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setToolTip("Remove bookmark" if on else "Bookmark this event")
        btn.setEnabled(bool(self.current_volunteer_id))
        if not self.current_volunteer_id:
            btn.setToolTip("Log in as a volunteer to bookmark events")
        btn.clicked.connect(self._toggle_bookmark)
        return btn

    def _toggle_bookmark(self):
        if not self.current_volunteer_id:
            return
        emit_add = self.opportunity_id not in self._bookmarked_ids
        if emit_add:
            self._bookmarked_ids.add(self.opportunity_id)
        else:
            self._bookmarked_ids.discard(self.opportunity_id)
        on = self._is_bookmarked()
        self._refresh_bookmark_button()
        if self._bookmark_cb:
            self._bookmark_cb(self.opportunity_id, on)

    def _refresh_bookmark_button(self):
        for b in self.findChildren(QPushButton):
            if b.objectName() in (
                theme.EVENT_BOOKMARK_BTN,
                theme.EVENT_BOOKMARK_BTN_ON,
            ):
                on = self._is_bookmarked()
                b.setText("★" if on else "☆")
                b.setObjectName(
                    theme.EVENT_BOOKMARK_BTN_ON if on
                    else theme.EVENT_BOOKMARK_BTN
                )
                b.setToolTip(
                    "Remove bookmark" if on else "Bookmark this event"
                )
                b.style().unpolish(b)
                b.style().polish(b)
                return

    # ── Meta rows ────────────────────────────────────────────────────
    def _date_text(self):
        """Compact enough to fit the card's narrow date column."""
        return _short_when(self.row)

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
        return f"{left} of {self.capacity} spots"

    def _make_date_line(self):
        """
        Two-column meta row: DATE | WHERE.
        The date label wraps onto a second line if the string is long,
        so nothing gets clipped.
        """
        box = QHBoxLayout()
        box.setSpacing(14)
        box.setContentsMargins(0, 0, 0, 0)

        # DATE column
        date_col = QVBoxLayout()
        date_col.setSpacing(2)
        date_col.setContentsMargins(0, 0, 0, 0)
        date_key = QLabel("DATE")
        date_key.setObjectName(theme.EVENT_META_KEY)
        date_val = QLabel(self._date_text())
        date_val.setObjectName(theme.EVENT_META_VALUE)
        date_val.setWordWrap(True)
        date_col.addWidget(date_key)
        date_col.addWidget(date_val)

        # WHERE column
        where_col = QVBoxLayout()
        where_col.setSpacing(2)
        where_col.setContentsMargins(0, 0, 0, 0)
        where_key = QLabel("WHERE")
        where_key.setObjectName(theme.EVENT_META_KEY)
        where_text = ("Remote" if self.is_remote
                      else (self.location or "Location TBD"))
        where_val = QLabel(where_text)
        where_val.setObjectName(theme.EVENT_META_VALUE)
        where_val.setWordWrap(True)
        where_col.addWidget(where_key)
        where_col.addWidget(where_val)

        box.addLayout(date_col, 3)
        box.addLayout(where_col, 2)
        return box

    def _make_spots_line(self):
        spots = self._spots_text()
        if not spots:
            return None
        row = QHBoxLayout()
        row.setSpacing(6)
        row.setContentsMargins(0, 0, 0, 0)
        k = QLabel("SPOTS")
        k.setObjectName(theme.EVENT_META_KEY)
        v = QLabel(spots)
        v.setObjectName(theme.EVENT_META_VALUE)
        row.addWidget(k)
        row.addWidget(v, 1)
        return row

    def _make_org_line(self):
        lbl = QLabel(f"by {self.org_name}")
        lbl.setObjectName(theme.EVENT_ORG)
        lbl.setWordWrap(True)
        return lbl

    # ── Grid layout ──────────────────────────────────────────────────
    def _build_grid_layout(self):
        self.setFixedWidth(self.GRID_WIDTH)
        self.setFixedHeight(self.GRID_FIXED_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(
            self._make_thumbnail(self.GRID_WIDTH, self.GRID_THUMB_H)
        )

        content = QVBoxLayout()
        content.setContentsMargins(16, 14, 16, 14)
        content.setSpacing(10)

        # Blue category badge + outlined location badge + status badge
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

        spots_row = self._make_spots_line()
        if spots_row is not None:
            content.addLayout(spots_row)

        content.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self._make_rsvp_button(), 1)
        actions.addWidget(self._make_link_button(), 1)
        content.addLayout(actions)

        content.addWidget(self._make_details_button())

        layout.addLayout(content)

    # ── Badge row ────────────────────────────────────────────────────
    def _make_badges(self, with_org=False):
        row = QHBoxLayout()
        row.setSpacing(6)
        row.setContentsMargins(0, 0, 0, 0)
        for lbl in build_badges(
            self.category, self.is_remote, self.location, self.status
        ):
            row.addWidget(lbl)
        if with_org:
            org = QLabel(f"by {self.org_name}")
            org.setObjectName(theme.EVENT_ORG)
            row.addWidget(org)
        row.addStretch(1)
        return row

    # ── List layout ──────────────────────────────────────────────────
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

        # Top row: title on the left, action buttons + Open Details
        # stacked on the right.
        top = QHBoxLayout()
        top.setSpacing(16)

        title_lbl = QLabel(self.title)
        title_lbl.setObjectName(theme.EVENT_TITLE_LIST)
        title_lbl.setWordWrap(True)

        # Right column: Link + RSVP on top, small Open Details below
        right_col = QVBoxLayout()
        right_col.setSpacing(6)
        right_col.setContentsMargins(0, 0, 0, 0)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self._make_link_button())
        actions.addWidget(self._make_rsvp_button())
        actions.addStretch(1)

        details_row = QHBoxLayout()
        details_row.setContentsMargins(0, 0, 0, 0)
        details_row.addStretch(1)
        details_row.addWidget(self._make_details_button())

        right_col.addLayout(actions)
        right_col.addLayout(details_row)

        top.addWidget(title_lbl, 1)
        top.addLayout(right_col, 0)
        content.addLayout(top)

        # Badges row (source / category / location / status / org)
        content.addLayout(self._make_badges(with_org=True))

        desc_lbl = QLabel(truncate_text(self.description, 260))
        desc_lbl.setObjectName(theme.EVENT_DESCRIPTION)
        desc_lbl.setWordWrap(True)
        desc_lbl.setMaximumHeight(60)
        content.addWidget(desc_lbl)

        content.addLayout(self._make_date_line())
        content.addStretch(1)

        layout.addLayout(content, 1)
    # ── Events ───────────────────────────────────────────────────────

    def open_link(self):
        if self.website_link:
            self.open_link_requested.emit(self.website_link)

    def request_rsvp(self):
        if self.opportunity_id:
            self.rsvp_requested.emit(self.opportunity_id)

    def request_details(self):
        self.details_requested.emit(self)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if (event.button() == Qt.MouseButton.LeftButton and
                self.rect().contains(event.position().toPoint())):
            self.details_requested.emit(self)
        super().mouseReleaseEvent(event)
    detailsRequested = property(lambda self: self.details_requested)  # noqa: N815
    openLinkRequested = property(lambda self: self.open_link_requested)  # noqa: N815
    rsvpRequested = property(lambda self: self.rsvp_requested)  # noqa: N815
