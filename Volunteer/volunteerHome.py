"""
volunteerHome.py — Volunteer dashboard.

Tabs in a QStackedWidget. Tab buttons live in landing.py's top nav bar.
    0. Dashboard       summary + statistics + first-time welcome
    1. Calendar        month view, color-coded by organization
    2. My Events       signups with check-in / check-out / cancel
    3. Organizations   join / leave organizations
    4. Notifications   list of notifications for this user
    5. Help            AI chatbot (Anthropic API)
    6. Profile         edit profile, notification setting, password
"""

import calendar
import csv
import html
import json
import os
import urllib.error
import urllib.request
import zlib
from datetime import date, datetime, time, timedelta

from PyQt6.QtCore import Qt, QPointF, QRectF, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPalette, QCursor
from PyQt6.QtWidgets import(
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QStackedWidget, QScrollArea, QMessageBox,
    QCalendarWidget, QLineEdit, QCheckBox, QFormLayout,
    QGridLayout, QProgressBar, QFileDialog,
)

import Events.theme as theme
from Chatbot.chatBubble import ChatView
from Events.dateFormat import format_range, format_time_range, format_event_when
from Volunteer.volunteerNotifications import VolunteerNotifications
from Events.moxieCharts import (
    KpiTile, HBarChart, AreaChart, DonutChart, section_label,
)


# ── Constants ─────────────────────────────────────────────────────────────
ISO = "yyyy-MM-dd"

ORG_PALETTE = [
    "#2E86DE", "#E67E22", "#27AE60", "#C0392B", "#8E44AD",
    "#16A085", "#D4AC0D", "#E84393", "#5D6D7E", "#00A8CC",
]
INDEPENDENT_COLOR = "#7F8C8D"

CLAUDE_MODEL = "openai/gpt-oss-20b"
CLAUDE_URL = "https://api.groq.com/openai/v1/chat/completions"

TAB_DASHBOARD, TAB_CALENDAR, TAB_EVENTS, TAB_ORGS = 0, 1, 2, 3
TAB_NOTIFS, TAB_HELP, TAB_PROFILE = 4, 5, 6

MAX_RANGE_DAYS = 90


# ── Small helpers ─────────────────────────────────────────────────────────
def rget(row, key, default=None):
    try:
        val = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if val is None else val


def org_color(org_name):
    if not org_name:
        return INDEPENDENT_COLOR
    return ORG_PALETTE[zlib.crc32(org_name.encode("utf-8")) % len(ORG_PALETTE)]


def time_range(row):
    t = format_time_range(
        rget(row, "start_time", ""),
        rget(row, "end_time", ""),
    )
    return f" · {t}" if t else ""


def date_range(row):
    return format_range(
        rget(row, "event_date", ""),
        rget(row, "event_end_date", ""),
    )


def expand_to_days(start_str, end_str):
    if not start_str:
        return
    try:
        start = date.fromisoformat(str(start_str)[:10])
    except ValueError:
        return
    end = start
    if end_str:
        try:
            end = date.fromisoformat(str(end_str)[:10])
        except ValueError:
            end = start
    if (end - start).days > MAX_RANGE_DAYS:
        end = start

    cur = start
    while cur <= end:
        yield cur.isoformat()
        cur += timedelta(days=1)


# ── Calendar widget with colored dots ─────────────────────────────────────
class EventCalendar(QCalendarWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.events_by_date = {}
        self.setGridVisible(True)
        self.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        self.setHorizontalHeaderFormat(
            QCalendarWidget.HorizontalHeaderFormat.ShortDayNames
        )

    def set_events(self, events_by_date):
        self.events_by_date = events_by_date
        self.updateCells()

    def paintCell(self, painter, rect, d):
        super().paintCell(painter, rect, d)
        events = self.events_by_date.get(d.toString(ISO))
        if not events:
            return

        colors = []
        for e in events:
            c = org_color(rget(e, "org_name"))
            if c not in colors:
                colors.append(c)
        colors = colors[:4]

        radius, gap = 4.5, 3.0
        total = len(colors) * radius * 2 + (len(colors) - 1) * gap
        x = rect.center().x() - total / 2 + radius
        y = rect.bottom() - radius - 4

        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for c in colors:
            painter.setBrush(QColor(c))
            painter.drawEllipse(QPointF(x, y), radius, radius)
            x += radius * 2 + gap
        painter.restore()


# ── Small bar chart ───────────────────────────────────────────────────────
class MonthlyBars(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []
        self.setMinimumHeight(160)

    def set_data(self, data):
        self.data = data
        self.update()

    def paintEvent(self, event):
        if not self.data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = self.palette().color(QPalette.ColorRole.WindowText)

        w, h = self.width(), self.height()
        top, bottom = 18, 22
        n = len(self.data)
        slot = w / n
        bar_w = min(42.0, slot * 0.55)
        max_v = max(v for _, v in self.data) or 1.0

        for i, (label, v) in enumerate(self.data):
            bar_h = (h - top - bottom) * (v / max_v)
            x = slot * i + (slot - bar_w) / 2
            y = h - bottom - bar_h
            if v > 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#7B8BE0"))
                p.drawRoundedRect(QRectF(x, y, bar_w, bar_h), 4, 4)
                p.setPen(text)
                p.drawText(QRectF(slot * i, y - 16, slot, 14),
                           Qt.AlignmentFlag.AlignCenter, f"{v:.1f}")
            p.setPen(text)
            p.drawText(QRectF(slot * i, h - bottom + 3, slot, bottom - 3),
                       Qt.AlignmentFlag.AlignCenter, label)
        p.end()


# ── Background worker for the chatbot ─────────────────────────────────────
class ChatWorker(QThread):
    reply = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, messages, system, parent=None):
        super().__init__(parent)
        self.messages = messages
        self.system = system

    def run(self):
        from dotenv import load_dotenv
        load_dotenv()

        key = os.environ.get("GROQ_API_KEY")
        if not key:
            self.failed.emit(
                "The assistant isn't configured yet — add GROQ_API_KEY to your .env file."
            )
            return

        # Groq uses OpenAI's message format. Anthropic's "system" field
        # becomes the first message with role="system".
        messages = [{"role": "system", "content": self.system}] + self.messages

        body = json.dumps({
            "model": CLAUDE_MODEL,
            "max_tokens": 800,
            "messages": messages,
        }).encode("utf-8")

        req = urllib.request.Request(
            CLAUDE_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
                "User-Agent": "Moxie/1.0",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.load(resp)
            # OpenAI-style response: choices[0].message.content
            text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            self.reply.emit(text or "(No response)")
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            self.failed.emit(f"Assistant error {e.code}: {detail}")
        except Exception as e:
            self.failed.emit(f"Couldn't reach the assistant: {e}")

# ── Main widget ───────────────────────────────────────────────────────────
class VolunteerHome(VolunteerNotifications, QWidget):
    TAB_LABELS = [
        "Dashboard", "Calendar", "My Events", "Organizations",
        "Notifications", "Help", "Profile",
    ]

    tabChanged = pyqtSignal(int)

    # Emitted when the volunteer clicks "Browse opportunities" or
    # "Complete your profile" on the first-time welcome card.
    # landing.py connects these to navigation.
    browseOpportunitiesRequested = pyqtSignal()
    goToProfileRequested = pyqtSignal()

    def __init__(self, on_logout_click=None, db=None, parent=None):
        super().__init__(parent)
        self.on_logout_click = on_logout_click
        self.db = db
        self.user_data = None
        self.userID = None

        self._chat_history = []
        self._chat_worker = None
        self._signup_rows = []
        self._welcome_dismissed = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_overview_page())
        self.stack.addWidget(self._build_calendar_page())
        self.stack.addWidget(self._build_events_page())
        self.stack.addWidget(self._build_orgs_page())
        self.stack.addWidget(self._build_notifications_page())
        self.stack.addWidget(self._build_help_page())
        self.stack.addWidget(self._build_profile_page())
        outer.addWidget(self.stack, 1)

        outer.addWidget(self._build_slogan_bar(), 0)
        self._reminder_timer = QTimer(self)
        self._reminder_timer.setInterval(60_000)
        self._reminder_timer.timeout.connect(self._check_upcoming_reminders)
        self._reminder_timer.start()

    # ── DB access ─────────────────────────────────────────────────────────
    def _db(self, method, *args, default=None):
        fn = getattr(self.db, method, None) if self.db else None
        if fn is None:
            print(f"Database.{method}() is not implemented yet")
            return default
        try:
            return fn(*args)
        except Exception as e:
            print(f"Database.{method}() failed:", e)
            return default

    def _db_action(self, method, *args):
        fn = getattr(self.db, method, None) if self.db else None
        if fn is None:
            QMessageBox.information(
                self, "Not available",
                f"This feature needs Database.{method}() to be implemented."
            )
            return False
        try:
            ok = fn(*args)
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            return False
        return bool(ok)

    def _notify(self, message, type_=None, opportunity_id=None):
        """Best-effort notification. Never raises."""
        if not (self.db and self.userID):
            return
        try:
            self.db.addNotification(
                self.userID, message, type_, opportunity_id
            )
        except Exception as e:
            print("addNotification failed:", e)

    def _build_slogan_bar(self):
        bar = QWidget()
        bar.setObjectName(theme.BOTTOM_BAR)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 20, 20, 20)
        slogan = QLabel("Ready to make a difference in your community today?")
        slogan.setObjectName(theme.SLOGAN_TEXT)
        slogan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(slogan)
        return bar

    # ── Reusable page scaffolding ─────────────────────────────────────────
    def _scroll_page(self, heading_text, spacing=10):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(40, 20, 40, 20)
        lay.setSpacing(10)

        heading = QLabel(heading_text)
        heading.setObjectName(theme.SECTION_TITLE)
        lay.addWidget(heading)

        top = QVBoxLayout()
        top.setSpacing(8)
        lay.addLayout(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setObjectName(theme.HOME_SCROLL)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(spacing)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        lay.addWidget(scroll, 1)
        return page, content_layout, top

    def _clear(self, layout):
        while layout.count() > 1:
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _add(self, layout, widget):
        layout.insertWidget(layout.count() - 1, widget)

    def _empty(self, layout, text):
        lbl = QLabel(text)
        lbl.setObjectName(theme.VOLUNTEER_EMPTY)
        layout.insertWidget(0, lbl)

    @staticmethod
    def _swatch(color, size=12):
        s = QLabel()
        s.setFixedSize(size, size)
        s.setStyleSheet(
            f"background-color: {color}; border-radius: {size // 2}px;"
        )
        return s

    # ── 0. Dashboard ──────────────────────────────────────────────────────
    def _dash_card(self, title, link_text=None, tab=None):
        card = QFrame()
        card.setObjectName(theme.EVENT_CARD)
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)

        head = QHBoxLayout()
        t = QLabel(title)
        t.setObjectName(theme.EVENT_TITLE_LIST)
        head.addWidget(t)
        head.addStretch(1)
        if tab is not None:
            b = QPushButton(f"{link_text} →")
            b.setFlat(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                "QPushButton:hover { text-decoration: underline; }"
            )
            b.clicked.connect(lambda _, i=tab: self.show_tab(i))
            head.addWidget(b)
        v.addLayout(head)

        body = QVBoxLayout()
        body.setSpacing(6)
        v.addLayout(body)
        return card, body

    def _build_overview_page(self):
        page = QWidget()
        page.setObjectName(theme.VOLUNTEER_DASHBOARD)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setObjectName(theme.HOME_SCROLL)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(40, 28, 40, 28)
        lay.setSpacing(22)

        # Hero
        hero = QHBoxLayout()
        hero.setSpacing(16)
        hero_col = QVBoxLayout()
        hero_col.setSpacing(4)
        self.welcome_title = QLabel("Welcome Back!")
        self.welcome_title.setObjectName("MoxieHeroTitle")
        hero_col.addWidget(self.welcome_title)
        self.user_info_label = QLabel("")
        self.user_info_label.setObjectName("MoxieHeroSub")
        hero_col.addWidget(self.user_info_label)
        hero.addLayout(hero_col, 1)

        impact_btn = QPushButton("Export impact record")
        impact_btn.setObjectName("MoxieHeroAction")
        impact_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        impact_btn.clicked.connect(self._export_impact_record)
        hero.addWidget(impact_btn)
        lay.addLayout(hero)

        # First-time card
        self.first_time_card = self._build_first_time_card()
        lay.addWidget(self.first_time_card)

        # KPIs
        lay.addWidget(section_label("Your impact"))
        self.tile_widgets = {}
        kpis = QHBoxLayout()
        kpis.setSpacing(14)
        for key, caption in [
            ("hours", "Hours logged"),
            ("completed", "Events completed"),
            ("upcoming", "Upcoming events"),
            ("signups", "Total signups"),
            ("orgs", "Organizations"),
            ("rate", "Completion rate"),
        ]:
            tile = KpiTile(caption, value="–")
            self.tile_widgets[key] = tile
            kpis.addWidget(tile, 1)
        lay.addLayout(kpis)

        # Charts row
        lay.addWidget(section_label("Trends"))
        chart_row = QHBoxLayout()
        chart_row.setSpacing(16)

        left = QFrame()
        left.setObjectName("MoxieChartCard")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(20, 16, 20, 16)
        lv.setSpacing(10)
        lt = QLabel("Hours by month")
        lt.setObjectName("MoxieSectionTitle")
        lv.addWidget(lt)
        self.dash_area = AreaChart()
        lv.addWidget(self.dash_area, 1)
        chart_row.addWidget(left, 2)

        right = QFrame()
        right.setObjectName("MoxieChartCard")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(20, 16, 20, 16)
        rv.setSpacing(10)
        rt = QLabel("Hours by organization")
        rt.setObjectName("MoxieSectionTitle")
        rv.addWidget(rt)
        self.dash_donut = DonutChart()
        rv.addWidget(self.dash_donut, 1)
        chart_row.addWidget(right, 1)
        lay.addLayout(chart_row)

        # Upcoming + recommended
        lay.addWidget(section_label("For you"))
        grid = QGridLayout()
        grid.setSpacing(16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        card, self.dash_upcoming = self._dash_card(
            "Upcoming events", "View calendar", TAB_CALENDAR
        )
        grid.addWidget(card, 0, 0)

        card, self.dash_recommended = self._dash_card(
            "Recommended for you", "Browse all", TAB_DASHBOARD
        )
        grid.addWidget(card, 0, 1)
        lay.addLayout(grid)

        # Recent activity + help
        row = QHBoxLayout()
        row.setSpacing(16)

        card, self.dash_notifs = self._dash_card(
            "Recent notifications", "View all", TAB_NOTIFS
        )
        row.addWidget(card, 2)

        help_card = QFrame()
        help_card.setObjectName("MoxieChartCard")
        hl = QVBoxLayout(help_card)
        hl.setContentsMargins(20, 16, 20, 16)
        hl.setSpacing(10)
        ht = QLabel("Need a hand?")
        ht.setObjectName("MoxieSectionTitle")
        hl.addWidget(ht)
        hq = QLabel(
            "Ask Moxie about check-ins, hours, or finding events."
        )
        hq.setObjectName(theme.EVENT_META_VALUE)
        hq.setWordWrap(True)
        hl.addWidget(hq)
        hl.addStretch(1)
        ask = QPushButton("Ask the assistant")
        ask.setObjectName("MoxieHeroAction")
        ask.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        ask.clicked.connect(lambda: self.show_tab(TAB_HELP))
        hl.addWidget(ask)
        row.addWidget(help_card, 1)
        lay.addLayout(row)

        # Organizer nudge
        org_nudge = QFrame()
        org_nudge.setObjectName("MoxieChartCard")
        ol = QHBoxLayout(org_nudge)
        ol.setContentsMargins(20, 14, 20, 14)
        omsg = QLabel(
            "Part of an organization? Register one and switch to the "
            "organizer view."
        )
        omsg.setObjectName(theme.EVENT_META_VALUE)
        omsg.setWordWrap(True)
        o_btn = QPushButton("Set up an organization")
        o_btn.setObjectName("MoxieHeroActionSecondary")
        o_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        o_btn.clicked.connect(self._on_setup_org)
        ol.addWidget(omsg, 1)
        ol.addWidget(o_btn)
        lay.addWidget(org_nudge)

        lay.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        return page
    def _build_first_time_card(self):
        """
        Shown at the top of the Dashboard when the volunteer has no
        signups yet. Hidden otherwise.
        """
        card = QFrame()
        card.setObjectName(theme.EVENT_CARD)
        card.setStyleSheet(
            f"QFrame#{theme.EVENT_CARD} "
            "{ border-left: 6px solid #7B8BE0; }"
        )
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)

        title = QLabel("Welcome to Moxie! Here's how to get started.")
        title.setObjectName(theme.EVENT_TITLE_LIST)

        body = QLabel(
            "Browse volunteering opportunities, RSVP to events you care "
            "about, and track your hours. Add a few skills to your profile "
            "so our recommendations can find events that fit you."
        )
        body.setObjectName(theme.EVENT_META_VALUE)
        body.setWordWrap(True)

        row = QHBoxLayout()
        row.setSpacing(8)

        browse = QPushButton("Browse opportunities")
        browse.setObjectName(theme.PRIMARY_BTN)
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.clicked.connect(self.browseOpportunitiesRequested.emit)
        row.addWidget(browse)

        profile = QPushButton("Complete your profile")
        profile.setObjectName(theme.SECONDARY_BTN)
        profile.setCursor(Qt.CursorShape.PointingHandCursor)
        profile.clicked.connect(self.goToProfileRequested.emit)
        row.addWidget(profile)

        row.addStretch(1)

        dismiss = QPushButton("I'll look around")
        dismiss.setObjectName(theme.SECONDARY_BTN)
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.clicked.connect(self._dismiss_first_time)
        row.addWidget(dismiss)

        v.addWidget(title)
        v.addWidget(body)
        v.addLayout(row)

        card.setVisible(False)   # toggled by _refresh_dashboard
        return card

    def _dismiss_first_time(self):
        self._welcome_dismissed = True
        self.first_time_card.setVisible(False)

    def _on_setup_org(self):
        QMessageBox.information(
            self, "Organization setup",
            "To register an organization, log out and choose "
            "'Register ▾ → Register an Organization' from the home page. "
            "You'll use a separate email for the organization account."
        )

    # ── 1. Calendar ───────────────────────────────────────────────────────
    def _build_calendar_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(40, 20, 40, 20)
        lay.setSpacing(10)

        heading = QLabel("My Calendar")
        heading.setObjectName(theme.SECTION_TITLE)
        lay.addWidget(heading)

        body = QHBoxLayout()
        body.setSpacing(20)

        left = QVBoxLayout()
        self.calendar = EventCalendar()
        self.calendar.selectionChanged.connect(self._refresh_day_list)
        left.addWidget(self.calendar, 1)

        self.legend_layout = QHBoxLayout()
        self.legend_layout.setSpacing(14)
        left.addLayout(self.legend_layout)

        right = QVBoxLayout()
        self.day_heading = QLabel("")
        self.day_heading.setObjectName(theme.SECTION_TITLE)
        right.addWidget(self.day_heading)

        self.day_scroll = QScrollArea()
        self.day_scroll.setWidgetResizable(True)
        self.day_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.day_scroll.setObjectName(theme.HOME_SCROLL)
        day_content = QWidget()
        self.day_layout = QVBoxLayout(day_content)
        self.day_layout.setContentsMargins(0, 0, 0, 0)
        self.day_layout.setSpacing(8)
        self.day_layout.addStretch(1)
        self.day_scroll.setWidget(day_content)
        right.addWidget(self.day_scroll, 1)

        body.addLayout(left, 3)
        body.addLayout(right, 2)
        lay.addLayout(body, 1)
        return page

    def _refresh_calendar(self):
        rows = self._db("getSignupsForVolunteer", self.userID, default=[]) \
            if self.userID else []
        rows = [r for r in rows if (rget(r, "status", "") or "") != "cancelled"]
        self._signup_rows = rows

        by_date = {}
        orgs = {}
        for r in rows:
            start = str(rget(r, "event_date", "") or "")
            end = str(rget(r, "event_end_date", "") or "") or start
            for iso in expand_to_days(start, end):
                by_date.setdefault(iso, []).append(r)
            name = rget(r, "org_name") or "Independent"
            orgs[name] = org_color(rget(r, "org_name"))
        self.calendar.set_events(by_date)

        while self.legend_layout.count():
            item = self.legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for name in sorted(orgs):
            wrap = QWidget()
            wl = QHBoxLayout(wrap)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setSpacing(5)
            wl.addWidget(self._swatch(orgs[name]))
            wl.addWidget(QLabel(name))
            self.legend_layout.addWidget(wrap)
        self.legend_layout.addStretch(1)

        self._refresh_day_list()

    def _refresh_day_list(self):
        d = self.calendar.selectedDate()
        self.day_heading.setText(d.toString("dddd, MMMM d"))
        self._clear(self.day_layout)
        events = self.calendar.events_by_date.get(d.toString(ISO), [])
        if not events:
            self._empty(self.day_layout, "No events on this day.")
            return
        for r in events:
            self._add(self.day_layout, self._make_day_card(r))

    def _make_day_card(self, r):
        color = org_color(rget(r, "org_name"))
        card = QFrame()
        card.setObjectName(theme.EVENT_CARD)
        card.setStyleSheet(
            f"QFrame#{theme.EVENT_CARD} {{ border-left: 6px solid {color}; }}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(4)

        title = QLabel(rget(r, "title", "Untitled event"))
        title.setObjectName(theme.EVENT_TITLE_LIST)
        meta = QLabel(
            f"{date_range(r)} · {rget(r, 'org_name', 'Independent')}"
            f"{time_range(r)}"
        )
        meta.setObjectName(theme.EVENT_META_VALUE)
        meta.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(meta)
        return card

    # ── 2. My Events ──────────────────────────────────────────────────────
    def _build_events_page(self):
        page, self.events_layout, _ = self._scroll_page("My Registered Events")
        return page

    def _refresh_events(self):
        if not (self.db and self.userID):
            return
        self._clear(self.events_layout)
        rows = self._db("getSignupsForVolunteer", self.userID, default=[])

        if not rows:
            self._empty(self.events_layout,
                        "You haven't registered for anything yet.")
            return
        for r in rows:
            self._add(self.events_layout, self._make_signup_card(r))

    def _make_signup_card(self, r):
        color = org_color(rget(r, "org_name"))
        card = QFrame()
        card.setObjectName(theme.EVENT_CARD)
        card.setStyleSheet(
            f"QFrame#{theme.EVENT_CARD} {{ border-left: 6px solid {color}; }}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        title = QLabel(r["title"] or "Untitled event")
        title.setObjectName(theme.EVENT_TITLE_LIST)

        meta = QLabel(
            f"{date_range(r)}{time_range(r)}\n"
            f"{r['org_name'] or 'Independent'} · "
            f"status: {r['status'] or 'registered'}"
        )
        meta.setObjectName(theme.EVENT_META_VALUE)
        meta.setWordWrap(True)

        row = QHBoxLayout()
        row.setSpacing(8)

        if not r["check_in_time"]:
            ci = QPushButton("Check In")
            ci.setObjectName(theme.PRIMARY_BTN)
            ci.setCursor(Qt.CursorShape.PointingHandCursor)
            ci.clicked.connect(
                lambda _, oid=r["opportunityID"]: self._do_check_in(oid)
            )
            row.addWidget(ci)
        elif not r["check_out_time"]:
            co = QPushButton("Check Out")
            co.setObjectName(theme.PRIMARY_BTN)
            co.setCursor(Qt.CursorShape.PointingHandCursor)
            co.clicked.connect(
                lambda _, oid=r["opportunityID"]: self._do_check_out(oid)
            )
            row.addWidget(co)
        else:
            done = QLabel(f"✓ Logged {r['hours_logged'] or 0:.2f} hours")
            done.setObjectName(theme.EVENT_META_VALUE)
            row.addWidget(done)

        cancel = QPushButton("Cancel")
        cancel.setObjectName(theme.SECONDARY_BTN)
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(
            lambda _, oid=r["opportunityID"]: self._do_cancel(oid)
        )
        row.addStretch(1)
        row.addWidget(cancel)

        lay.addWidget(title)
        lay.addWidget(meta)
        lay.addLayout(row)
        return card

    def _do_check_in(self, opportunityID):
        if self.db.checkIn(self.userID, opportunityID):
            self._notify(
                "You checked in. Remember to check out when you're done.",
                "check_in", opportunityID,
            )
            self._after_signup_change()

    def _do_check_out(self, opportunityID):
        if self.db.checkOut(self.userID, opportunityID):
            self._notify(
                "You checked out. Your hours have been recorded.",
                "check_out", opportunityID,
            )
            self._after_signup_change()

    def _do_cancel(self, opportunityID):
        if QMessageBox.question(
            self, "Cancel RSVP", "Cancel your signup for this event?"
        ) != QMessageBox.StandardButton.Yes:
            return
        if self.db.cancelSignup(self.userID, opportunityID):
            self._notify(
                "You cancelled your signup for an event.",
                "cancel", opportunityID,
            )
            self._after_signup_change()

    def _after_signup_change(self):
        self._refresh_events()
        self._refresh_dashboard()

    def show_my_events(self):
        """
        Public entry point used by landing.py after a successful RSVP
        from the listing page. Jumps to the My Events tab.
        """
        self.show_tab(TAB_EVENTS)

    # ── 3. Organizations ──────────────────────────────────────────────────
    def _build_orgs_page(self):
        page, self.orgs_layout, top = self._scroll_page("Organizations")
        self.orgs_search = QLineEdit()
        self.orgs_search.setPlaceholderText("Search organizations…")
        self.orgs_search.setClearButtonEnabled(True)
        self.orgs_search.textChanged.connect(self._render_orgs)
        top.addWidget(self.orgs_search)
        self._org_rows = []
        return page

    def _refresh_orgs(self):
        if not (self.db and self.userID):
            return
        self._org_rows = self._db(
            "getOrganizations", self.userID, default=[]
        ) or []
        self._render_orgs()

    def _render_orgs(self):
        self._clear(self.orgs_layout)
        q = self.orgs_search.text().strip().lower()
        rows = [
            r for r in self._org_rows
            if not q or q in (
                f"{rget(r, 'name', '')} {rget(r, 'description', '')}".lower()
            )
        ]
        if not rows:
            self._empty(
                self.orgs_layout,
                "No matching organizations." if q
                else "No organizations available yet."
            )
            return
        rows.sort(key=lambda r: (not rget(r, "is_member", 0),
                                 str(rget(r, "name", "")).lower()))
        for r in rows:
            self._add(self.orgs_layout, self._make_org_card(r))

    def _make_org_card(self, r):
        name = rget(r, "name", "Unnamed organization")
        member = bool(rget(r, "is_member", 0))
        oid = r["organizationID"]

        card = QFrame()
        card.setObjectName(theme.EVENT_CARD)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(self._swatch(org_color(name), 14))
        title = QLabel(name)
        title.setObjectName(theme.EVENT_TITLE_LIST)
        head.addWidget(title)
        head.addStretch(1)
        lay.addLayout(head)

        desc = rget(r, "description")
        if desc:
            d = QLabel(desc)
            d.setObjectName(theme.EVENT_META_VALUE)
            d.setWordWrap(True)
            lay.addWidget(d)

        row = QHBoxLayout()
        if member:
            joined = QLabel("✓ Member")
            joined.setObjectName(theme.EVENT_META_VALUE)
            row.addWidget(joined)
            row.addStretch(1)
            leave = QPushButton("Leave")
            leave.setObjectName(theme.SECONDARY_BTN)
            leave.setCursor(Qt.CursorShape.PointingHandCursor)
            leave.clicked.connect(lambda _, o=oid, n=name: self._do_leave(o, n))
            row.addWidget(leave)
        else:
            row.addStretch(1)
            join = QPushButton("Join")
            join.setObjectName(theme.PRIMARY_BTN)
            join.setCursor(Qt.CursorShape.PointingHandCursor)
            join.clicked.connect(lambda _, o=oid: self._do_join(o))
            row.addWidget(join)
        lay.addLayout(row)
        return card

    def _do_join(self, orgID):
        if self._db_action("joinOrganization", self.userID, orgID):
            self._notify("You joined a new organization.", "join_org")
            self._refresh_orgs()

    def _do_leave(self, orgID, name):
        if QMessageBox.question(
            self, "Leave organization", f"Leave {name}?"
        ) != QMessageBox.StandardButton.Yes:
            return
        if self._db_action("leaveOrganization", self.userID, orgID):
            self._notify("You left an organization.", "leave_org")
            self._refresh_orgs()

    # ── 4. Notifications ──────────────────────────────────────────────────
    

    # ── 5. Help ───────────────────────────────────────────────────────────
    def _build_help_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(40, 20, 40, 20)
        lay.setSpacing(10)

        heading = QLabel("Help")
        heading.setObjectName(theme.SECTION_TITLE)
        sub = QLabel(
            "Ask anything about volunteering, checking in, hours, "
            "or how to use this app."
        )
        sub.setObjectName(theme.EVENT_META_VALUE)
        sub.setWordWrap(True)

        self.chat = ChatView(
            greeting="Hi! I'm Moxie — your volunteer sidekick. 🌱 "
                    "Ask me anything about events, hours, or this app!"
        )
        self.chat.set_system_prompt_provider(self._chat_system_prompt)
        self.chat.set_send_handler(self._dispatch_chat)

        lay.addWidget(heading)
        lay.addWidget(sub)
        lay.addWidget(self.chat, 1)
        return page
    def _chat_system_prompt(self):
        name = (self.user_data or {}).get("first_name") or "the volunteer"

        # Always pull fresh signups — do NOT rely on self._signup_rows,
        # which is only populated after visiting Calendar/Dashboard.
        rows = self._db("getSignupsForVolunteer", self.userID, default=[]) or []
        rows = [r for r in rows if (rget(r, "status", "") or "") != "cancelled"]

        today = date.today()
        upcoming = []
        for r in rows:
            raw = str(rget(r, "event_date", "") or "").strip()
            if not raw:
                continue
            try:
                # Accept ISO dates; ignore anything unparseable for the "upcoming" list
                d = date.fromisoformat(raw[:10])
            except ValueError:
                # Unparseable (imported free-text date) — include it, but flag it.
                upcoming.append(
                    f"- {rget(r, 'title', 'Untitled')} on {raw}"
                    f" ({rget(r, 'org_name', 'Independent')}) [date format unverified]"
                )
                continue

            end_raw = str(rget(r, "event_end_date", "") or "").strip()
            try:
                end = date.fromisoformat(end_raw[:10]) if end_raw else d
            except ValueError:
                end = d

            if end >= today:
                    upcoming.append(
                        f"- {rget(r, 'title', 'Untitled')} — "
                        f"{format_event_when(r)} "
                        f"({rget(r, 'org_name', 'Independent')})"
                    )

        upcoming_txt = "\n".join(upcoming[:15]) or "NONE (confirmed) — this user has no upcoming events."

        return (
            f"You are Moxie, a super friendly in-app help buddy for a volunteer "
            f"management app. You're chatting with {name}. "
            "Your vibe: warm, upbeat, encouraging, a tiny bit playful — "
            "like a helpful friend, not a corporate bot. "
            "\n\nTone rules:\n"
            "- Use contractions (you're, that's, let's).\n"
            "- Sprinkle in light emoji (✨ 🎉 🙌 💛 🌱) — 0-2 per reply.\n"
            "- Keep replies short: 1-3 sentences unless asked for detail.\n"
            "- Never say 'As an AI' or 'I am a language model'.\n"
            "\nIMPORTANT — upcoming events:\n"
            "The list below is the user's ACTUAL, current signup data pulled "
            "from the database right now. Do not invent events, do not guess, "
            "do not say they have none if the list is non-empty. If they ask "
            "about an event not in the list, tell them it isn't showing in "
            "their current signups and suggest checking My Events.\n"
            "Their upcoming events:\n" + upcoming_txt
        )

    def _dispatch_chat(self, text):
        # ChatView already appended the user bubble, set busy, and showed
        # the typing dots. We only need to kick off the request.
        self._chat_worker = ChatWorker(
            list(self.chat.history),
            self.chat.get_system_prompt(),
            self,
        )
        self._chat_worker.reply.connect(self.chat.on_reply)
        self._chat_worker.failed.connect(self._on_chat_failed)
        self._chat_worker.start()

    def _on_chat_failed(self, msg):
        # Pop the last user turn so a retry doesn't double up.
        if self.chat.history and self.chat.history[-1]["role"] == "user":
            self.chat.history.pop()
        self.chat.on_error(msg)

    # ── 6. Profile ────────────────────────────────────────────────────────
    def _build_profile_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(40, 20, 40, 20)
        outer.setSpacing(10)

        heading = QLabel("Profile & Settings")
        heading.setObjectName(theme.SECTION_TITLE)
        outer.addWidget(heading)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setObjectName(theme.HOME_SCROLL)
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, 0, 0, 0)
        inner_lay.setSpacing(16)

        details = QFrame()
        details.setObjectName(theme.EVENT_CARD)
        dl = QVBoxLayout(details)
        dl.setContentsMargins(20, 16, 20, 16)
        dt = QLabel("Your details")
        dt.setObjectName(theme.EVENT_TITLE_LIST)
        dl.addWidget(dt)

        form = QFormLayout()
        form.setSpacing(8)
        self.pf_first = QLineEdit()
        self.pf_last = QLineEdit()
        self.pf_email = QLineEdit()
        self.pf_phone = QLineEdit()
        self.pf_skills = QLineEdit()
        self.pf_skills.setPlaceholderText(
            "e.g. environment, teaching, logistics"
        )
        form.addRow("First name", self.pf_first)
        form.addRow("Last name", self.pf_last)
        form.addRow("Email", self.pf_email)
        form.addRow("Phone", self.pf_phone)
        form.addRow("Skills", self.pf_skills)
        dl.addLayout(form)

        self.pf_notify = QCheckBox("Email me about event updates and reminders")
        dl.addWidget(self.pf_notify)

        save_row = QHBoxLayout()
        self.pf_status = QLabel("")
        self.pf_status.setObjectName(theme.EVENT_META_VALUE)
        save = QPushButton("Save Changes")
        save.setObjectName(theme.PRIMARY_BTN)
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.clicked.connect(self._save_profile)
        save_row.addWidget(self.pf_status)
        save_row.addStretch(1)
        save_row.addWidget(save)
        dl.addLayout(save_row)
        inner_lay.addWidget(details)

        pw = QFrame()
        pw.setObjectName(theme.EVENT_CARD)
        pl = QVBoxLayout(pw)
        pl.setContentsMargins(20, 16, 20, 16)
        pt = QLabel("Change password")
        pt.setObjectName(theme.EVENT_TITLE_LIST)
        pl.addWidget(pt)

        pform = QFormLayout()
        pform.setSpacing(8)
        self.pw_old = QLineEdit()
        self.pw_new = QLineEdit()
        self.pw_confirm = QLineEdit()
        for f in (self.pw_old, self.pw_new, self.pw_confirm):
            f.setEchoMode(QLineEdit.EchoMode.Password)
        pform.addRow("Current password", self.pw_old)
        pform.addRow("New password", self.pw_new)
        pform.addRow("Confirm new", self.pw_confirm)
        pl.addLayout(pform)

        pw_row = QHBoxLayout()
        pw_row.addStretch(1)
        pw_btn = QPushButton("Update Password")
        pw_btn.setObjectName(theme.SECONDARY_BTN)
        pw_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pw_btn.clicked.connect(self._change_password)
        pw_row.addWidget(pw_btn)
        pl.addLayout(pw_row)
        inner_lay.addWidget(pw)

        inner_lay.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        return page

    def _refresh_profile(self):
        profile = None
        if self.userID:
            profile = self._db("getUserProfile", self.userID)
        src = profile or self.user_data or {}
        self.pf_first.setText(str(rget(src, "first_name", "")))
        self.pf_last.setText(str(rget(src, "last_name", "")))
        self.pf_email.setText(str(rget(src, "email", "")))
        self.pf_phone.setText(str(rget(src, "phone", "")))
        self.pf_skills.setText(str(rget(src, "skills", "")))
        self.pf_notify.setChecked(bool(rget(src, "notify_email", 1)))
        self.pf_status.setText("")

    def _save_profile(self):
        first = self.pf_first.text().strip()
        email = self.pf_email.text().strip()
        if not first:
            QMessageBox.warning(self, "Profile", "First name is required.")
            return
        if "@" not in email or "." not in email.split("@")[-1]:
            QMessageBox.warning(self, "Profile", "Enter a valid email address.")
            return

        fields = {
            "first_name": first,
            "last_name": self.pf_last.text().strip(),
            "email": email,
            "phone": self.pf_phone.text().strip(),
            "skills": self.pf_skills.text().strip(),
            "notify_email": 1 if self.pf_notify.isChecked() else 0,
        }
        if self._db_action("updateUserProfile", self.userID, fields):
            if self.user_data is not None:
                self.user_data.update(fields)
            self.welcome_title.setText(f"Welcome, {first}!")
            self.user_info_label.setText(f"Logged in as: {email}")
            self.pf_status.setText("✓ Saved")
            self._refresh_recommendations(self._signup_rows)
        else:
            self.pf_status.setText("Couldn't save changes.")

    def _change_password(self):
        old, new, conf = (self.pw_old.text(), self.pw_new.text(),
                          self.pw_confirm.text())
        if not (old and new and conf):
            QMessageBox.warning(self, "Password", "Fill in all three fields.")
            return
        if new != conf:
            QMessageBox.warning(self, "Password", "New passwords don't match.")
            return
        if len(new) < 8:
            QMessageBox.warning(
                self, "Password", "Use at least 8 characters."
            )
            return
        if self._db_action("changePassword", self.userID, old, new):
            for f in (self.pw_old, self.pw_new, self.pw_confirm):
                f.clear()
            QMessageBox.information(self, "Password", "Password updated.")
        else:
            QMessageBox.warning(
                self, "Password",
                "Couldn't update password. Check your current password."
            )

    # ── Tab switching ─────────────────────────────────────────────────────
    def current_tab(self):
        return self.stack.currentIndex()

    def show_tab(self, idx):
        self.stack.setCurrentIndex(idx)

        refresh = {
            TAB_DASHBOARD: self._refresh_dashboard,
            TAB_CALENDAR: self._refresh_calendar,
            TAB_EVENTS: self._refresh_events,
            TAB_ORGS: self._refresh_orgs,
            TAB_NOTIFS: self._refresh_notifications,
            TAB_PROFILE: self._refresh_profile,
        }.get(idx)
        if refresh:
            refresh()
        self.tabChanged.emit(idx)

    # ── User data ─────────────────────────────────────────────────────────
    def set_user_data(self, user_data):
        self.user_data = user_data
        if not user_data:
            return

        self.userID = user_data.get("userID") or user_data.get("id")
        first_name = user_data.get("first_name") or "Volunteer"
        email = user_data.get("email", "")

        self.welcome_title.setText(f"Welcome, {first_name}!")
        self.user_info_label.setText(f"Logged in as: {email}")

        self._chat_history = []
        self.chat.reset()
        self._signup_rows = []
        self._welcome_dismissed = False

        self.show_tab(TAB_DASHBOARD)

    # ── Dashboard data ────────────────────────────────────────────────────
    def _clear_all(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _dash_text(self, text):
        lbl = QLabel(text)
        lbl.setObjectName(theme.VOLUNTEER_EMPTY)
        lbl.setWordWrap(True)
        return lbl

    def _dash_row(self, color, main, sub=""):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        h.addWidget(self._swatch(color))
        col = QVBoxLayout()
        col.setSpacing(0)
        m = QLabel(main)
        m.setWordWrap(True)
        col.addWidget(m)
        if sub:
            sl = QLabel(sub)
            sl.setObjectName(theme.EVENT_META_VALUE)
            sl.setWordWrap(True)
            col.addWidget(sl)
        h.addLayout(col, 1)
        return w

    def _refresh_dashboard(self):
        for lay in (self.dash_upcoming, self.dash_org_hours
                    if hasattr(self, "dash_org_hours")
                    else self.dash_recommended,
                    self.dash_orgs
                    if hasattr(self, "dash_orgs")
                    else self.dash_recommended,
                    self.dash_notifs):
            try:
                self._clear_all(lay)
            except Exception:
                pass
        # Fall back — clear both recommended and notifs
        try:
            self._clear_all(self.dash_recommended)
        except Exception:
            pass

        if not (self.db and self.userID):
            return

        rows = self._db("getSignupsForVolunteer",
                        self.userID, default=[]) or []
        active = [r for r in rows
                  if (rget(r, "status", "") or "") != "cancelled"]
        self._signup_rows = active
        self._notify_upcoming_events(active)

        has_activity = bool(active)
        self.first_time_card.setVisible(
            not has_activity and not self._welcome_dismissed
        )

        today = date.today()
        today_s = today.isoformat()

        def day(r):
            return str(rget(r, "event_date", ""))[:10]

        def end_day(r):
            e = str(rget(r, "event_end_date", "") or "")[:10]
            return e or day(r)

        def hrs(r):
            return float(rget(r, "hours_logged", 0) or 0)

        completed = [r for r in active if rget(r, "check_out_time")]
        upcoming = sorted(
            (r for r in active
             if end_day(r) >= today_s and not rget(r, "check_out_time")),
            key=lambda r: (day(r), str(rget(r, "start_time", ""))),
        )
        past = [r for r in active if end_day(r) and end_day(r) < today_s]
        past_done = [r for r in past if rget(r, "check_out_time")]
        total_hours = sum(hrs(r) for r in active)

        org_rows = self._db("getOrganizations", self.userID, default=None)
        if org_rows is not None:
            joined = sorted(
                str(rget(r, "name", "")) for r in org_rows
                if rget(r, "is_member", 0)
            )
        else:
            joined = sorted({rget(r, "org_name") for r in active
                             if rget(r, "org_name")})

        self.tile_widgets["hours"].set_value(f"{total_hours:.1f}")
        self.tile_widgets["completed"].set_value(len(completed))
        self.tile_widgets["upcoming"].set_value(len(upcoming))
        self.tile_widgets["signups"].set_value(len(active))
        self.tile_widgets["orgs"].set_value(len(joined))
        self.tile_widgets["rate"].set_value(
            f"{round(100 * len(past_done) / len(past))}%" if past else "—"
        )

        self._refresh_recommendations(active)

        if not upcoming:
            self.dash_upcoming.addWidget(self._dash_text(
                "Nothing coming up — find events in the Volunteer tab."))
        for r in upcoming[:4]:
            self.dash_upcoming.addWidget(self._dash_row(
                org_color(rget(r, "org_name")),
                str(rget(r, "title", "Untitled event")),
                f"{date_range(r)}{time_range(r)} · "
                f"{rget(r, 'org_name', 'Independent')}",
            ))
        if len(upcoming) > 4:
            self.dash_upcoming.addWidget(
                self._dash_text(f"+ {len(upcoming) - 4} more"))

        # Area chart — hours by month
        monthly = {}
        for r in active:
            monthly[day(r)[:7]] = monthly.get(day(r)[:7], 0.0) + hrs(r)
        data = []
        for back in range(5, -1, -1):
            yy, mm = today.year, today.month - back
            while mm <= 0:
                mm += 12
                yy -= 1
            data.append((calendar.month_abbr[mm],
                         monthly.get(f"{yy:04d}-{mm:02d}", 0.0)))
        self.dash_area.set_data(data)

        # Donut — hours by org
        by_org = {}
        for r in active:
            name = rget(r, "org_name") or "Independent"
            by_org[name] = by_org.get(name, 0.0) + hrs(r)
        ranked = sorted(
            ((n, v) for n, v in by_org.items() if v > 0),
            key=lambda t: -t[1],
        )[:5]
        slices = [(n, round(v, 1)) for n, v in ranked]
        total_for_donut = sum(v for _, v in slices) or 1
        self.dash_donut.set_data(
            slices or [("No hours yet", 1)],
            center_label=f"{int(round(total_hours))}h",
        )

        notifs = self._db("getNotifications",
                          self.userID, default=[]) or []
        notifs = sorted(
            notifs,
            key=lambda r: str(rget(r, "created_at", "")),
            reverse=True,
        )[:3]
        if not notifs:
            self.dash_notifs.addWidget(
                self._dash_text("No notifications yet."))
        for r in notifs:
            lbl = QLabel(
                f"<b>{html.escape(str(rget(r, 'created_at', '')))}</b> — "
                f"{html.escape(str(rget(r, 'message', '')))}"
            )
            lbl.setObjectName(theme.EVENT_META_VALUE)
            lbl.setWordWrap(True)
            self.dash_notifs.addWidget(lbl)

        for lay in (self.dash_upcoming, self.dash_recommended,
                    self.dash_notifs):
            lay.addStretch(1)
        def day(r):
            return str(rget(r, "event_date", ""))[:10]

        def end_day(r):
            e = str(rget(r, "event_end_date", "") or "")[:10]
            return e or day(r)

        def hrs(r):
            return float(rget(r, "hours_logged", 0) or 0)

        completed = [r for r in active if rget(r, "check_out_time")]
        upcoming = sorted(
            (r for r in active
             if end_day(r) >= today_s and not rget(r, "check_out_time")),
            key=lambda r: (day(r), str(rget(r, "start_time", ""))),
        )
        past = [r for r in active if end_day(r) and end_day(r) < today_s]
        past_done = [r for r in past if rget(r, "check_out_time")]
        total_hours = sum(hrs(r) for r in active)

        org_rows = self._db("getOrganizations", self.userID, default=None)
        if org_rows is not None:
            joined = sorted(
                str(rget(r, "name", "")) for r in org_rows
                if rget(r, "is_member", 0)
            )
        else:
            joined = sorted({rget(r, "org_name") for r in active
                             if rget(r, "org_name")})

        self.tile_values["hours"].setText(f"{total_hours:.1f}")
        self.tile_values["completed"].setText(str(len(completed)))
        self.tile_values["upcoming"].setText(str(len(upcoming)))
        self.tile_values["signups"].setText(str(len(active)))
        self.tile_values["orgs"].setText(str(len(joined)))
        self.tile_values["rate"].setText(
            f"{round(100 * len(past_done) / len(past))}%" if past else "—"
        )

        self._refresh_recommendations(active)

        if not upcoming:
            self.dash_upcoming.addWidget(self._dash_text(
                "Nothing coming up — find events in the Volunteer tab."))
        for r in upcoming[:4]:
            self.dash_upcoming.addWidget(self._dash_row(
                org_color(rget(r, "org_name")),
                str(rget(r, "title", "Untitled event")),
                f"{date_range(r)}{time_range(r)} · "
                f"{rget(r, 'org_name', 'Independent')}",
            ))
        if len(upcoming) > 4:
            self.dash_upcoming.addWidget(
                self._dash_text(f"+ {len(upcoming) - 4} more"))

        totals = {}
        for r in active:
            totals[day(r)[:7]] = totals.get(day(r)[:7], 0.0) + hrs(r)
        data = []
        for back in range(5, -1, -1):
            yy, mm = today.year, today.month - back
            while mm <= 0:
                mm += 12
                yy -= 1
            data.append((calendar.month_abbr[mm],
                         totals.get(f"{yy:04d}-{mm:02d}", 0.0)))
        self.dash_chart.set_data(data)

        by_org = {}
        for r in active:
            name = rget(r, "org_name") or "Independent"
            by_org[name] = by_org.get(name, 0.0) + hrs(r)
        ranked = sorted(((n, v) for n, v in by_org.items() if v > 0),
                        key=lambda t: -t[1])[:5]
        if not ranked:
            self.dash_org_hours.addWidget(
                self._dash_text("No hours logged yet — check in at an event!"))
        top_val = ranked[0][1] if ranked else 1.0
        for name, v in ranked:
            color = org_color(None if name == "Independent" else name)
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)
            h.addWidget(self._swatch(color))
            lbl = QLabel(name)
            lbl.setFixedWidth(120)
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setValue(int(v / top_val * 1000))
            bar.setTextVisible(False)
            bar.setFixedHeight(10)
            bar.setStyleSheet(
                "QProgressBar { border: none; border-radius: 5px;"
                " background: rgba(127,127,127,50); }"
                f"QProgressBar::chunk {{ background-color: {color};"
                " border-radius: 5px; }"
            )
            hv = QLabel(f"{v:.1f} h")
            h.addWidget(lbl)
            h.addWidget(bar, 1)
            h.addWidget(hv)
            self.dash_org_hours.addWidget(row)

        if not joined:
            self.dash_orgs.addWidget(self._dash_text(
                "You haven't joined any organizations yet."))
        for name in joined[:6]:
            self.dash_orgs.addWidget(self._dash_row(org_color(name), name))
        if len(joined) > 6:
            self.dash_orgs.addWidget(
                self._dash_text(f"+ {len(joined) - 6} more"))

        notifs = self._db("getNotifications", self.userID, default=[]) or []
        notifs = sorted(notifs, key=lambda r: str(rget(r, "created_at", "")),
                        reverse=True)[:3]
        if not notifs:
            self.dash_notifs.addWidget(self._dash_text("No notifications yet."))
        for r in notifs:
            lbl = QLabel(
                f"<b>{html.escape(str(rget(r, 'created_at', '')))}</b> — "
                f"{html.escape(str(rget(r, 'message', '')))}"
            )
            lbl.setObjectName(theme.EVENT_META_VALUE)
            lbl.setWordWrap(True)
            self.dash_notifs.addWidget(lbl)

        for lay in (self.dash_upcoming, self.dash_org_hours,
                    self.dash_orgs, self.dash_notifs):
            lay.addStretch(1)

    # ── Recommendations ───────────────────────────────────────────────────
    def _refresh_recommendations(self, active_signups):
        self._clear_all(self.dash_recommended)

        try:
            from Volunteer.ml_recommender import explain_match, rank_opportunities
        except ImportError:
            self.dash_recommended.addWidget(self._dash_text(
                "Recommendations need scikit-learn. "
                "Run: pip install scikit-learn"
            ))
            return

        all_opps = self._db("getAllOpportunities", default=None)
        if all_opps is None:
            self.dash_recommended.addWidget(self._dash_text(
                "Add Database.getAllOpportunities() to enable recommendations."
            ))
            return

        user_profile = self._db("getUserProfile", self.userID) or self.user_data
        joined_orgs = self._db("getOrganizations", self.userID, default=[]) or []

        # If the profile has no skills, the vectorizer has nothing to
        # work with. Prompt instead of showing "no recommendations".
        skills = str(rget(user_profile, "skills", "") or "").strip()
        if not skills and not active_signups:
            lbl = QLabel(
                "Add a few skills to your profile to unlock recommendations."
            )
            lbl.setObjectName(theme.VOLUNTEER_EMPTY)
            lbl.setWordWrap(True)
            self.dash_recommended.addWidget(lbl)

            btn = QPushButton("Open profile →")
            btn.setObjectName(theme.SECONDARY_BTN)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda: self.show_tab(TAB_PROFILE))
            self.dash_recommended.addWidget(btn)
            return

        recs, scores = rank_opportunities(
            user_profile, active_signups, joined_orgs,
            list(all_opps), top_n=5,
        )

        if not recs:
            self.dash_recommended.addWidget(self._dash_text(
                "No new recommendations right now. "
                "Browse the Volunteer tab to find events."
            ))
            return

        for r, s in zip(recs, scores):
            sub = (
                f"{date_range(r)}{time_range(r)} · "
                f"{rget(r, 'org_name', 'Independent')}"
            )
            if s > 0:
                sub += f" · match {int(round(s * 100))}%"
                reasons = explain_match(user_profile, r)
                if reasons:
                    sub += " · " + ", ".join(reasons)
            self.dash_recommended.addWidget(self._dash_row(
                org_color(rget(r, "org_name")),
                str(rget(r, "title", "Untitled event")),
                sub,
            ))

    def _notify_upcoming_events(self, rows):
        now = datetime.now()
        for row in rows:
            if (rget(row, "reminder_sent", 0)
                    or rget(row, "check_out_time")
                    or rget(row, "no_show", 0)):
                continue
            try:
                event_date = date.fromisoformat(
                    str(rget(row, "event_date", ""))[:10]
                )
                start_text = str(rget(row, "start_time", "") or "09:00")
                start_time = time.fromisoformat(start_text[:8])
            except ValueError:
                continue
            starts_in = datetime.combine(event_date, start_time) - now
            if timedelta(0) <= starts_in <= timedelta(hours=24):
                self._db(
                    "notifyUpcomingSignup",
                    rget(row, "signupID"), self.userID,
                    rget(row, "opportunityID"),
                    rget(row, "title", "Your volunteer event"),
                    default=False,
                )

    def _check_upcoming_reminders(self):
        if not (self.userID and self.isVisible()):
            return
        rows = self._db(
            "getSignupsForVolunteer", self.userID, default=[]
        ) or []
        self._notify_upcoming_events([
            row for row in rows
            if (rget(row, "status", "") or "") != "cancelled"
        ])

    def _export_impact_record(self):
        rows = self._db(
            "getSignupsForVolunteer", self.userID, default=[]
        ) or []
        verified = [
            r for r in rows
            if rget(r, "verified", 0) and not rget(r, "no_show", 0)
        ]
        path, _ = QFileDialog.getSaveFileName(
            self, "Export impact record", "moxie-impact.csv",
            "CSV files (*.csv)",
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(["Moxie volunteer impact record"])
                writer.writerow([
                    "Verified hours",
                    f"{sum(float(rget(r, 'hours_logged', 0) or 0) for r in verified):.2f}",
                ])
                writer.writerow([])
                writer.writerow([
                    "Opportunity", "Organization", "Date",
                    "Verified hours",
                ])
                for row in verified:
                    writer.writerow([
                        rget(row, "title", ""),
                        rget(row, "org_name", "Independent"),
                        rget(row, "event_date", ""),
                        f"{float(rget(row, 'hours_logged', 0) or 0):.2f}",
                    ])
        except OSError as exc:
            QMessageBox.warning(
                self, "Export failed", f"Could not save the impact record:\n{exc}"
            )
            return
        QMessageBox.information(
            self, "Export complete",
            f"Saved {len(verified)} verified event records.",
        )