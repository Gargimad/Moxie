"""
orgDashboard.py - Organization dashboard.

Eight views in a QStackedWidget:
    0  Overview          stats, next up, recent activity, needs attention
    1  List              the org's own opportunities
    2  Form              create or edit an opportunity (NOT in the nav)
    3  Announcements     post + manage announcements
    4  Volunteers        roster with notes, tags, ban/unban
    5  Reports           hours by volunteer / opportunity, CSV export
    6  Data migration    import roster from CSV/Excel
    7  Recommendations   AI-ranked volunteers for each open event

landing.py builds the nav bar from TAB_LABELS. Because the form page
is not a nav destination, TAB_LABELS and stack indices are not the
same list - NAV_TO_STACK bridges them.
"""

import sqlite3
from datetime import datetime

from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QComboBox, QDateEdit, QCheckBox, QSpinBox,
    QListWidget, QListWidgetItem, QMessageBox, QFrame, QScrollArea,
    QGridLayout, QStackedWidget, QFileDialog, QDialog,
)
from Events.dateFormat import format_date, format_range, format_event_when
import Events.theme as theme
from Events.eventCard import clear_thumbnail_cache
from Events.moxieCharts import (
    KpiTile, HBarChart, VBarChart, AreaChart, DonutChart,
    section_label,
)


TAB_OVERVIEW, TAB_LIST, TAB_FORM, TAB_ANNOUNCEMENTS = 0, 1, 2, 3
TAB_VOLUNTEERS, TAB_REPORTS = 4, 5
TAB_MIGRATION = 6
TAB_RECOMMENDATIONS = 7


class OrgDashboard(QWidget):
    TAB_LABELS = [
        "Overview",
        "My opportunities",
        "Volunteers",
        "Reports",
        "Announcements",
        "Data migration",
        "Recommendations",
    ]

    # nav index -> stack index
    NAV_TO_STACK = [
        TAB_OVERVIEW,
        TAB_LIST,
        TAB_VOLUNTEERS,
        TAB_REPORTS,
        TAB_ANNOUNCEMENTS,
        TAB_MIGRATION,
        TAB_RECOMMENDATIONS,
    ]

    def __init__(self, db, on_logout_click=None, on_back_click=None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName(theme.ORG_DASHBOARD)
        self.db = db
        self.on_logout_click = on_logout_click
        self.on_back_click = on_back_click
        self.org = None
        self.editing_id = None
        self._pending_thumbnail = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_overview_page())       # 0
        self.stack.addWidget(self._build_list_page())           # 1
        self.stack.addWidget(self._build_form_page())           # 2
        self.stack.addWidget(self._build_announcements_page())  # 3

        from Organization.orgVolunteersPage import OrgVolunteersPage
        from Organization.orgReportsPage import OrgReportsPage
        from Organization.orgMigrationPage import OrgMigrationPage
        from Organization.orgRecommendationsPage import (
            OrgRecommendationsPage,
        )
        self.volunteersPage = OrgVolunteersPage(self.db)
        self.reportsPage = OrgReportsPage(self.db)
        self.migrationPage = OrgMigrationPage(self.db)
        self.recommendationsPage = OrgRecommendationsPage(self.db)
        self.stack.addWidget(self.volunteersPage)          # 4
        self.stack.addWidget(self.reportsPage)             # 5
        self.stack.addWidget(self.migrationPage)           # 6
        self.stack.addWidget(self.recommendationsPage)     # 7

        outer.addWidget(self.stack, 1)

    # ── Lifecycle ──────────────────────────────────────────────────
    def set_org_data(self, org_data):
        self.org = org_data
        self.volunteersPage.set_org(org_data)
        self.reportsPage.set_org(org_data)
        self.migrationPage.set_org_data(org_data)
        self.recommendationsPage.set_org(org_data)
        self.show_tab(TAB_OVERVIEW)

    def current_tab(self):
        return self.stack.currentIndex()

    def show_tab(self, idx):
        if idx < 0 or idx >= self.stack.count():
            return
        self.stack.setCurrentIndex(idx)
        if idx == TAB_OVERVIEW:
            self._refresh_overview()
        elif idx == TAB_LIST:
            self._refresh_list()
        elif idx == TAB_ANNOUNCEMENTS:
            self._refresh_announcements()
        elif idx == TAB_VOLUNTEERS:
            self.volunteersPage.refresh()
        elif idx == TAB_REPORTS:
            self.reportsPage.refresh()
        elif idx == TAB_MIGRATION:
            self.migrationPage.refresh()
        elif idx == TAB_RECOMMENDATIONS:
            self.recommendationsPage.refresh()

    def show_nav_tab(self, nav_idx):
        if nav_idx < 0 or nav_idx >= len(self.NAV_TO_STACK):
            return
        self.show_tab(self.NAV_TO_STACK[nav_idx])

    def current_nav_tab(self):
        stack_idx = self.stack.currentIndex()
        try:
            return self.NAV_TO_STACK.index(stack_idx)
        except ValueError:
            return -1

    # ── 0. Overview ────────────────────────────────────────────────
    def _build_overview_page(self):
        page = QWidget()
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

        # ── Hero header ─────────────────────────────────────────────
        hero = QHBoxLayout()
        hero.setSpacing(16)

        hero_col = QVBoxLayout()
        hero_col.setSpacing(4)
        self.org_title = QLabel("Organization dashboard")
        self.org_title.setObjectName("MoxieHeroTitle")
        self.org_title.setWordWrap(True)
        hero_col.addWidget(self.org_title)

        self.org_subtitle = QLabel("")
        self.org_subtitle.setObjectName("MoxieHeroSub")
        self.org_subtitle.setWordWrap(True)
        hero_col.addWidget(self.org_subtitle)
        hero.addLayout(hero_col, 1)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        new_btn = QPushButton("+ New opportunity")
        new_btn.setObjectName("MoxieHeroAction")
        new_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        new_btn.clicked.connect(self._start_new)
        actions.addWidget(new_btn)

        ann_btn = QPushButton("Post announcement")
        ann_btn.setObjectName("MoxieHeroActionSecondary")
        ann_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        ann_btn.clicked.connect(
            lambda: self.show_tab(TAB_ANNOUNCEMENTS)
        )
        actions.addWidget(ann_btn)
        hero.addLayout(actions)
        lay.addLayout(hero)

        # ── KPI row ─────────────────────────────────────────────────
        lay.addWidget(section_label("At a glance"))
        self.tile_widgets = {}
        kpis = QHBoxLayout()
        kpis.setSpacing(14)
        for key, caption in [
            ("open", "Open opportunities"),
            ("total", "Total posted"),
            ("signups", "Total signups"),
            ("volunteers", "Unique volunteers"),
            ("hours", "Hours logged"),
            ("announce", "Announcements"),
        ]:
            tile = KpiTile(caption, value="-")
            self.tile_widgets[key] = tile
            kpis.addWidget(tile, 1)
        lay.addLayout(kpis)

        # ── Charts row 1: signups trend + status breakdown ──────────
        lay.addWidget(section_label("Trends"))
        chart_row = QHBoxLayout()
        chart_row.setSpacing(16)

        # Left: signups over time
        left_card = QFrame()
        left_card.setObjectName("MoxieChartCard")
        lv = QVBoxLayout(left_card)
        lv.setContentsMargins(20, 16, 20, 16)
        lv.setSpacing(10)
        lt = QLabel("Signups over time")
        lt.setObjectName("MoxieSectionTitle")
        lv.addWidget(lt)
        self._chart_signups = AreaChart()
        lv.addWidget(self._chart_signups, 1)
        chart_row.addWidget(left_card, 2)

        # Right: status donut
        right_card = QFrame()
        right_card.setObjectName("MoxieChartCard")
        rv = QVBoxLayout(right_card)
        rv.setContentsMargins(20, 16, 20, 16)
        rv.setSpacing(10)
        rt = QLabel("Status breakdown")
        rt.setObjectName("MoxieSectionTitle")
        rv.addWidget(rt)
        self._chart_status = DonutChart()
        rv.addWidget(self._chart_status, 1)
        chart_row.addWidget(right_card, 1)
        lay.addLayout(chart_row)

        # ── Row 2: attention / next up / activity ───────────────────
        lay.addWidget(section_label("Today"))

        row3 = QHBoxLayout()
        row3.setSpacing(16)

        card_attn, self.overview_attention = self._dash_card(
            "Needs attention", "Open reports", TAB_REPORTS
        )
        row3.addWidget(card_attn, 1)

        card_next, self.overview_next = self._dash_card(
            "Next up", "All opportunities", TAB_LIST
        )
        row3.addWidget(card_next, 1)

        card_act, self.overview_activity = self._dash_card(
            "Recent activity", "All opportunities", TAB_LIST
        )
        row3.addWidget(card_act, 1)
        lay.addLayout(row3)

        # ── Row 4: leaderboard + data actions ───────────────────────
        lay.addWidget(section_label("Top volunteers"))

        lead_row = QHBoxLayout()
        lead_row.setSpacing(16)

        lead_card = QFrame()
        lead_card.setObjectName("MoxieChartCard")
        ll = QVBoxLayout(lead_card)
        ll.setContentsMargins(20, 16, 20, 16)
        ll.setSpacing(10)
        lt2 = QLabel("Hours contributed")
        lt2.setObjectName("MoxieSectionTitle")
        ll.addWidget(lt2)
        self._chart_leaderboard = HBarChart()
        ll.addWidget(self._chart_leaderboard, 1)
        lead_row.addWidget(lead_card, 2)

        data_card = QFrame()
        data_card.setObjectName("MoxieChartCard")
        dv = QVBoxLayout(data_card)
        dv.setContentsMargins(20, 16, 20, 16)
        dv.setSpacing(10)
        dt = QLabel("Data tools")
        dt.setObjectName("MoxieSectionTitle")
        dv.addWidget(dt)
        dv.addWidget(self._helper_text(
            "Back up or restore your organization's local Moxie data."
        ))
        dv.addStretch(1)

        backup_btn = QPushButton("Back up local data")
        backup_btn.setObjectName(theme.SECONDARY_BTN)
        backup_btn.clicked.connect(self._backup_database)
        dv.addWidget(backup_btn)

        restore_btn = QPushButton("Restore from backup")
        restore_btn.setObjectName(theme.SECONDARY_BTN)
        restore_btn.clicked.connect(self._restore_database)
        dv.addWidget(restore_btn)

        lead_row.addWidget(data_card, 1)
        lay.addLayout(lead_row)

        lay.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        return page

    def _helper_text(self, text):
        lbl = QLabel(text)
        lbl.setObjectName(theme.EVENT_META_VALUE)
        lbl.setWordWrap(True)
        return lbl
    def _dash_card(self, title, link_text=None, tab=None):
        card = QFrame()
        card.setObjectName(theme.EVENT_CARD)
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)

        head = QHBoxLayout()
        t = QLabel(title)
        t.setObjectName(theme.EVENT_TITLE_LIST)
        head.addWidget(t)
        head.addStretch(1)

        if tab is not None:
            b = QPushButton(f"{link_text} →")
            b.setFlat(True)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setObjectName("OrgCardLink")
            b.clicked.connect(lambda _, i=tab: self.show_tab(i))
            head.addWidget(b)

        v.addLayout(head)
        body = QVBoxLayout()
        body.setSpacing(8)
        v.addLayout(body)
        return card, body

    def _clear_all(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _overview_text(self, text):
        lbl = QLabel(text)
        lbl.setObjectName(theme.VOLUNTEER_EMPTY)
        lbl.setWordWrap(True)
        return lbl

    def _overview_row(self, main, sub=""):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        col = QVBoxLayout()
        col.setSpacing(2)
        m = QLabel(main)
        m.setObjectName("OrgRowMain")
        m.setWordWrap(True)
        col.addWidget(m)
        if sub:
            sl = QLabel(sub)
            sl.setObjectName("OrgRowSub")
            sl.setWordWrap(True)
            col.addWidget(sl)
        h.addLayout(col, 1)
        return w

    def _refresh_overview(self):
        if not self.org:
            return

        self.org_title.setText(self.org.get("org_name", "Organization"))
        self.org_subtitle.setText(
            self.org.get("description", "")
            or "Manage your opportunities"
        )

        for lay in (self.overview_attention, self.overview_next,
                    self.overview_activity):
            self._clear_all(lay)

        stats = self._db_call("getOrgStats", self.org["orgID"],
                              default={}) or {}
        open_count = stats.get("open_opportunities", 0)
        total = stats.get("total_opportunities", 0)
        signups = stats.get("total_signups", 0)
        volunteers = stats.get("unique_volunteers", 0)
        hours = stats.get("total_hours", 0.0)

        anns = self._db_call(
            "getAnnouncementsForOrg", self.org["orgID"], default=[]
        ) or []

        self.tile_widgets["open"].set_value(open_count)
        self.tile_widgets["total"].set_value(total)
        self.tile_widgets["signups"].set_value(signups)
        self.tile_widgets["volunteers"].set_value(volunteers)
        self.tile_widgets["hours"].set_value(f"{hours:.1f}")
        self.tile_widgets["announce"].set_value(len(anns))

        # Signups over time — last 6 months
        import calendar as _cal
        from datetime import date as _date
        today = _date.today()
        monthly = {}
        try:
            all_signups = []
            ops = self.db.getOpportunitiesByOrg(self.org["orgID"]) or []
            for op in ops:
                for s in (self.db.getSignupsForOpportunity(
                    op["opportunityID"]) or []):
                    all_signups.append(s)
        except Exception:
            all_signups = []
        for s in all_signups:
            raw = str(s["signup_time"] or "")[:7]
            if len(raw) == 7:
                monthly[raw] = monthly.get(raw, 0) + 1

        trend = []
        for back in range(5, -1, -1):
            yy, mm = today.year, today.month - back
            while mm <= 0:
                mm += 12
                yy -= 1
            key = f"{yy:04d}-{mm:02d}"
            trend.append((_cal.month_abbr[mm], monthly.get(key, 0)))
        self._chart_signups.set_data(trend)

        # Status donut
        try:
            rows = self.db.getOpportunitiesByOrg(self.org["orgID"]) or []
        except Exception:
            rows = []
        status_counts = {}
        for r in rows:
            key = (r["status"] or "open").capitalize()
            status_counts[key] = status_counts.get(key, 0) + 1
        slices = sorted(status_counts.items(), key=lambda t: -t[1])
        self._chart_status.set_data(
            slices or [("No events", 1)],
            center_label=str(sum(v for _, v in slices)) or "0",
        )

        # Needs attention
        report_rows = self._db_call(
            "getOrgHoursReport", self.org["orgID"],
            None, None, None, None, default=[],
        ) or []
        pending_count = sum(
            1 for r in report_rows
            if not r["verified"] and not r["no_show"]
        )
        if pending_count:
            self.overview_attention.addWidget(self._overview_row(
                f"{pending_count} hour entr"
                f"{'y' if pending_count == 1 else 'ies'} "
                f"waiting to be verified",
                "Open Reports to review and approve.",
            ))

        upcoming_for_attn = self._db_call(
            "getUpcomingForOrg", self.org["orgID"], default=[]
        ) or []
        for r in upcoming_for_attn:
            cap = r["capacity"]
            reg = r["registered_count"] or 0
            if cap and reg < cap * 0.5:
                self.overview_attention.addWidget(self._overview_row(
                    f"{r['title']} is under 50% full",
                    f"{reg}/{cap} signed up — consider sharing it.",
                ))

        if self.overview_attention.count() == 0:
            self.overview_attention.addWidget(self._overview_text(
                "Nothing needs your attention right now."
            ))

        # Next up
        upcoming = self._db_call(
            "getUpcomingForOrg", self.org["orgID"], default=[]
        ) or []
        if not upcoming:
            self.overview_next.addWidget(self._overview_text(
                "No upcoming opportunities. Post one to get started."
            ))
        for r in upcoming[:4]:
            title = r["title"] or "Untitled"
            date_txt = format_event_when(r)
            cap = r["capacity"]
            reg = r["registered_count"] or 0
            if cap:
                spots = (f"{reg}/{cap} signed up — "
                         f"{max(0, cap - reg)} spots left")
            else:
                spots = f"{reg} signed up"
            self.overview_next.addWidget(self._overview_row(
                title, f"{date_txt} · {spots}"
            ))

        # Recent activity
        recent = self._db_call(
            "getRecentSignupsForOrg", self.org["orgID"], default=[]
        ) or []
        if not recent:
            self.overview_activity.addWidget(self._overview_text(
                "No signups yet. Volunteers who RSVP will show up here."
            ))
        for r in recent[:6]:
            name = " ".join(
                x for x in [r["first_name"], r["last_name"]] if x
            ) or r["email"] or "A volunteer"
            title = r["title"] or "an event"
            self.overview_activity.addWidget(self._overview_row(
                f"{name} signed up for {title}",
                str(r["signup_time"] or "")[:19],
            ))

        # Leaderboard
        lead = self._db_call(
            "getOrgVolunteerLeaderboard", self.org["orgID"],
            default=[],
        ) or []
        rows = []
        for r in lead[:6]:
            name = " ".join(
                x for x in [r["first_name"], r["last_name"]] if x
            ) or r["email"]
            rows.append((name, f"{float(r['hours'] or 0):.1f}h"))
        if not rows:
            rows = [("No hours logged yet", "0h")]
        self._chart_leaderboard.set_data(rows)
    # ── 1. List ────────────────────────────────────────────────────
    def _build_list_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(40, 24, 40, 24)
        lay.setSpacing(12)

        header = QHBoxLayout()
        heading = QLabel("My Opportunities")
        heading.setObjectName(theme.SECTION_TITLE)
        header.addWidget(heading)
        header.addStretch(1)

        new_btn = QPushButton("+ New opportunity")
        new_btn.setObjectName(theme.PRIMARY_BTN)
        new_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        new_btn.clicked.connect(self._start_new)
        header.addWidget(new_btn)
        lay.addLayout(header)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName(theme.ORG_OPP_LIST)
        self.list_widget.itemDoubleClicked.connect(self._edit_selected)
        lay.addWidget(self.list_widget, 1)

        row = QHBoxLayout()
        row.addStretch()

        for label, handler in (
            ("View signups", self._view_signups_selected),
            ("Copy share details", self._copy_share_details),
            ("Edit selected", self._edit_selected),
            ("Cancel selected", self._cancel_selected),
        ):
            b = QPushButton(label)
            b.setObjectName(theme.SECONDARY_BTN)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.clicked.connect(handler)
            row.addWidget(b)

        lay.addLayout(row)
        return page

    def _refresh_list(self):
        self.list_widget.clear()
        if not self.org:
            return
        try:
            rows = self.db.getOpportunitiesByOrg(self.org["orgID"])
        except Exception as e:
            print("Org opportunities query failed:", e)
            return
        if not rows:
            item = QListWidgetItem(
                "No opportunities yet — click \"+ New opportunity\" "
                "to create one."
            )
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(item)
            return

        for r in rows:
            cap = r["capacity"]
            reg = r["registered_count"] or 0
            spots = f" · {reg}/{cap}" if cap else f" · {reg} signed up"
            label = (
                f"{r['title']} · {format_date(r['event_date'])}"
                f" · {r['status'] or 'open'}{spots}"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, r["opportunityID"])
            self.list_widget.addItem(item)

    # ── 2. Form ────────────────────────────────────────────────────
    def _build_form_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(40, 24, 40, 24)
        outer.setSpacing(12)

        self.form_title = QLabel("New Opportunity")
        self.form_title.setObjectName(theme.SECTION_TITLE)
        outer.addWidget(self.form_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setObjectName(theme.HOME_SCROLL)

        scroll_content = QWidget()
        form = QGridLayout(scroll_content)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.f_title = QLineEdit()
        self.f_title.setPlaceholderText("e.g. Saturday park cleanup")

        self.f_description = QTextEdit()
        self.f_description.setPlaceholderText(
            "What will volunteers be doing?"
        )
        self.f_description.setFixedHeight(90)

        self.f_location = QLineEdit()
        self.f_location.setPlaceholderText("Where (free text)")

        self.f_address = QLineEdit()
        self.f_address.setPlaceholderText("Street address (optional)")

        self.f_remote = QCheckBox("Remote")

        self.f_date = QDateEdit()
        self.f_date.setCalendarPopup(True)
        self.f_date.setDate(QDate.currentDate())
        self.f_date.setDisplayFormat("yyyy-MM-dd")

        self.f_end_date = QDateEdit()
        self.f_end_date.setCalendarPopup(True)
        self.f_end_date.setDate(QDate.currentDate())
        self.f_end_date.setDisplayFormat("yyyy-MM-dd")

        self.f_start = QLineEdit()
        self.f_start.setPlaceholderText("HH:MM (e.g. 09:00)")

        self.f_end = QLineEdit()
        self.f_end.setPlaceholderText("HH:MM (e.g. 12:00)")

        self.f_capacity = QSpinBox()
        self.f_capacity.setRange(0, 9999)
        self.f_capacity.setSpecialValueText("Unlimited")

        self.f_status = QComboBox()
        self.f_status.addItems(["open", "full", "cancelled", "completed"])

        self.f_skills = QLineEdit()
        self.f_skills.setPlaceholderText("Comma-separated (optional)")

        self.f_contact_name = QLineEdit()
        self.f_contact_name.setPlaceholderText("Contact name")

        self.f_contact_email = QLineEdit()
        self.f_contact_email.setPlaceholderText("Contact email")

        r = 0
        form.addWidget(QLabel("Title *"), r, 0)
        form.addWidget(self.f_title, r, 1, 1, 3); r += 1

        form.addWidget(QLabel("Description"), r, 0)
        form.addWidget(self.f_description, r, 1, 1, 3); r += 1

        form.addWidget(QLabel("Status"), r, 0)
        form.addWidget(self.f_status, r, 1)
        form.addWidget(QLabel("Capacity"), r, 2)
        form.addWidget(self.f_capacity, r, 3); r += 1

        form.addWidget(QLabel("Location"), r, 0)
        form.addWidget(self.f_location, r, 1)
        form.addWidget(QLabel("Address"), r, 2)
        form.addWidget(self.f_address, r, 3); r += 1

        form.addWidget(QLabel("Start date"), r, 0)
        form.addWidget(self.f_date, r, 1)
        form.addWidget(QLabel("End date"), r, 2)
        form.addWidget(self.f_end_date, r, 3); r += 1

        form.addWidget(self.f_remote, r, 0)
        form.addWidget(QLabel("Start time"), r, 2)
        form.addWidget(self.f_start, r, 3); r += 1

        form.addWidget(QLabel("End time"), r, 0)
        form.addWidget(self.f_end, r, 1)
        r += 1

        form.addWidget(QLabel("Required skills"), r, 0)
        form.addWidget(self.f_skills, r, 1, 1, 3); r += 1

        form.addWidget(QLabel("Contact name"), r, 0)
        form.addWidget(self.f_contact_name, r, 1)
        form.addWidget(QLabel("Contact email"), r, 2)
        form.addWidget(self.f_contact_email, r, 3); r += 1

        self.thumb_lbl = QLabel("No image attached")
        self.thumb_lbl.setObjectName(theme.EVENT_META_VALUE)

        pick_btn = QPushButton("Choose image…")
        pick_btn.setObjectName(theme.SECONDARY_BTN)
        pick_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        pick_btn.clicked.connect(self._pick_thumbnail)

        clear_btn = QPushButton("Remove image")
        clear_btn.setObjectName(theme.SECONDARY_BTN)
        clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clear_btn.clicked.connect(self._clear_thumbnail)

        thumb_row = QHBoxLayout()
        thumb_row.addWidget(pick_btn)
        thumb_row.addWidget(clear_btn)
        thumb_row.addWidget(self.thumb_lbl, 1)

        form.addWidget(QLabel("Thumbnail"), r, 0)
        form.addLayout(thumb_row, r, 1, 1, 4); r += 1

        scroll.setWidget(scroll_content)
        outer.addWidget(scroll, 1)

        row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName(theme.SECONDARY_BTN)
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.clicked.connect(lambda: self.show_tab(TAB_LIST))

        save_btn = QPushButton("Save")
        save_btn.setObjectName(theme.PRIMARY_BTN)
        save_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        save_btn.clicked.connect(self._save)

        row.addStretch()
        row.addWidget(cancel_btn)
        row.addWidget(save_btn)
        outer.addLayout(row)
        return page

    def _start_new(self):
        self.editing_id = None
        self._pending_thumbnail = None
        self.form_title.setText("New Opportunity")
        for w in (self.f_title, self.f_description, self.f_location,
                  self.f_address, self.f_skills, self.f_contact_name,
                  self.f_contact_email, self.f_start, self.f_end):
            try:
                w.clear()
            except Exception:
                pass
        self.f_remote.setChecked(False)
        self.f_date.setDate(QDate.currentDate())
        self.f_end_date.setDate(QDate.currentDate())
        self.f_capacity.setValue(0)
        self.f_status.setCurrentText("open")
        self.thumb_lbl.setText("No image attached")
        self.show_tab(TAB_FORM)

    def _edit_selected(self, *_):
        item = self.list_widget.currentItem()
        if not item:
            return
        oid = item.data(Qt.ItemDataRole.UserRole)
        if not oid:
            return
        row = self.db.getOpportunityByID(oid)
        if not row:
            QMessageBox.warning(self, "Not found",
                                "That opportunity no longer exists.")
            self._refresh_list()
            return

        self.editing_id = oid
        self._pending_thumbnail = row["thumbnail"]
        self.form_title.setText("Edit Opportunity")
        self.f_title.setText(row["title"] or "")
        self.f_description.setPlainText(row["description"] or "")
        self.f_location.setText(row["location"] or "")
        self.f_address.setText(row["address"] or "")
        self.f_remote.setChecked(bool(row["is_remote"]))
        if row["event_date"]:
            d = QDate.fromString(str(row["event_date"])[:10],
                                 "yyyy-MM-dd")
            if d.isValid():
                self.f_date.setDate(d)
        if row["event_end_date"]:
            d = QDate.fromString(str(row["event_end_date"])[:10],
                                 "yyyy-MM-dd")
            if d.isValid():
                self.f_end_date.setDate(d)
        else:
            self.f_end_date.setDate(self.f_date.date())
        self.f_start.setText(row["start_time"] or "")
        self.f_end.setText(row["end_time"] or "")
        self.f_capacity.setValue(row["capacity"] or 0)
        self.f_status.setCurrentText(row["status"] or "open")
        self.f_skills.setText(row["required_skills"] or "")
        self.f_contact_name.setText(row["contact_name"] or "")
        self.f_contact_email.setText(row["contact_email"] or "")
        self.thumb_lbl.setText(
            self._pending_thumbnail or "No image attached"
        )
        self.show_tab(TAB_FORM)

    def _pick_thumbnail(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose thumbnail", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if path:
            self._pending_thumbnail = path
            self.thumb_lbl.setText(path)

    def _clear_thumbnail(self):
        self._pending_thumbnail = None
        self.thumb_lbl.setText("No image attached")

    def _cancel_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        oid = item.data(Qt.ItemDataRole.UserRole)
        if not oid:
            return
        if QMessageBox.question(
            self, "Cancel opportunity",
            "Mark this opportunity as cancelled? Volunteers who signed "
            "up will be notified."
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            signups = self.db.getSignupsForOpportunity(oid)
        except Exception as e:
            print("getSignupsForOpportunity failed:", e)
            signups = []
        row = self.db.getOpportunityByID(oid)
        title = row["title"] if row else "an event"

        self.db.updateOpportunity(oid, status="cancelled")

        for s in signups:
            if (s["status"] or "") != "registered":
                continue
            try:
                self.db.addNotification(
                    s["userID"],
                    f"{title} has been cancelled by the organization.",
                    "opportunity_cancelled",
                    oid,
                )
            except Exception as e:
                print("addNotification failed:", e)

        self._refresh_list()

    def _view_signups_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.information(
                self, "View signups",
                "Select an opportunity in the list first."
            )
            return
        oid = item.data(Qt.ItemDataRole.UserRole)
        if not oid:
            return
        row = self.db.getOpportunityByID(oid)
        if not row:
            QMessageBox.warning(self, "Not found",
                                "That opportunity no longer exists.")
            self._refresh_list()
            return
        from Organization.attendanceDialog import AttendanceDialog
        AttendanceDialog(self.db, self.org, row, parent=self).exec()
        self._refresh_list()

    def _copy_share_details(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.information(
                self, "Share opportunity",
                "Select an opportunity in the list first.",
            )
            return
        opportunity_id = item.data(Qt.ItemDataRole.UserRole)
        if not opportunity_id:
            return
        row = self.db.getOpportunityByID(opportunity_id)
        if not row:
            return
        details = [
            str(row["title"] or "Volunteer opportunity"),
            format_event_when(row),
            str(row["location"] or "Location to be confirmed"),
        ]
        if row["website_link"]:
            details.append(str(row["website_link"]))
        QApplication.clipboard().setText("\n".join(details))
        QMessageBox.information(
            self, "Copied",
            "Opportunity details are ready to paste into a message.",
        )

    def _backup_database(self):
        default_name = f"moxie-backup-{datetime.now():%Y%m%d-%H%M%S}.db"
        path, _ = QFileDialog.getSaveFileName(
            self, "Back up Moxie data", default_name,
            "SQLite database (*.db)",
        )
        if not path:
            return
        try:
            self.db.backupTo(path)
        except (OSError, sqlite3.Error, ValueError) as exc:
            QMessageBox.warning(
                self, "Backup failed",
                f"Could not back up local data:\n{exc}",
            )
            return
        QMessageBox.information(
            self, "Backup complete", f"Saved the database backup to:\n{path}"
        )

    def _restore_database(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Restore Moxie data", "",
            "SQLite database (*.db *.sqlite *.sqlite3)",
        )
        if not path:
            return
        if QMessageBox.warning(
            self, "Replace local data?",
            "Restoring replaces the current Moxie database. "
            "A safety backup of the current data will be created first. "
            "Moxie will close after a successful restore.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        ) != QMessageBox.StandardButton.Yes:
            return

        safety_path = (
            f"{self.db.db_path}.before-restore-"
            f"{datetime.now():%Y%m%d-%H%M%S}.db"
        )
        try:
            self.db.backupTo(safety_path)
            self.db.restoreFrom(path)
        except (OSError, sqlite3.Error, ValueError) as exc:
            QMessageBox.warning(
                self, "Restore failed",
                f"Could not restore the selected backup:\n{exc}\n\n"
                f"The current database backup is at:\n{safety_path}",
            )
            return
        QMessageBox.information(
            self, "Restore complete",
            "Moxie will now close. Reopen it to use the restored data.",
        )
        app = QApplication.instance()
        if app:
            app.quit()

    def _save(self):
        if not self.org:
            return

        title = self.f_title.text().strip()
        if not title:
            QMessageBox.warning(self, "Missing title",
                                "Title is required.")
            return

        start_date = self.f_date.date()
        end_date = self.f_end_date.date()
        if end_date < start_date:
            QMessageBox.warning(
                self, "Invalid dates",
                "End date can't be before the start date."
            )
            return

        end_iso = end_date.toString("yyyy-MM-dd")
        start_iso = start_date.toString("yyyy-MM-dd")
        stored_end = None if end_iso == start_iso else end_iso

        payload = dict(
            title=title,
            description=self.f_description.toPlainText().strip(),
            location=self.f_location.text().strip(),
            address=self.f_address.text().strip(),
            is_remote=self.f_remote.isChecked(),
            event_date=start_iso,
            event_end_date=stored_end,
            start_time=self.f_start.text().strip() or None,
            end_time=self.f_end.text().strip() or None,
            capacity=self.f_capacity.value() or None,
            status=self.f_status.currentText(),
            required_skills=self.f_skills.text().strip() or None,
            contact_name=self.f_contact_name.text().strip() or None,
            contact_email=self.f_contact_email.text().strip() or None,
            thumbnail=self._pending_thumbnail,
        )

        if self.editing_id:
            ok = self.db.updateOpportunity(self.editing_id, **payload)
            if not ok:
                QMessageBox.warning(self, "Save failed",
                                    "Could not update opportunity.")
                return
        else:
            new_id = self.db.addOpportunity(
                orgID=self.org["orgID"],
                **payload,
            )
            if not new_id:
                QMessageBox.warning(self, "Save failed",
                                    "Could not create opportunity.")
                return
            # Notify matching volunteers (best-effort).
            try:
                n = self.db.notifyVolunteersAboutOpportunity(new_id)
                print(f"[org] notified {n} matching volunteers")
            except Exception as e:
                print("notifyVolunteersAboutOpportunity failed:", e)

        clear_thumbnail_cache()
        self._refresh_list()
        self.show_tab(TAB_LIST)

    # ── 3. Announcements ───────────────────────────────────────────
    def _build_announcements_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(40, 24, 40, 24)
        outer.setSpacing(14)

        heading = QLabel("Post an update")
        heading.setObjectName(theme.SECTION_TITLE)

        sub = QLabel(
            "Announcements go to everyone who follows your org — "
            "members and volunteers who've signed up for your events. "
            "They'll show up in their notifications tab."
        )
        sub.setObjectName(theme.EVENT_META_VALUE)
        sub.setWordWrap(True)

        outer.addWidget(heading)
        outer.addWidget(sub)

        compose = QFrame()
        compose.setObjectName(theme.EVENT_CARD)
        cl = QVBoxLayout(compose)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.setSpacing(10)

        self.ann_title = QLineEdit()
        self.ann_title.setPlaceholderText(
            "Headline — e.g. Saturday cleanup moved to Sunday"
        )
        cl.addWidget(self.ann_title)

        self.ann_body = QTextEdit()
        self.ann_body.setPlaceholderText(
            "Write the details volunteers need to know…"
        )
        self.ann_body.setFixedHeight(80)
        cl.addWidget(self.ann_body)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.ann_pinned = QCheckBox("Pin to the top of the feed")
        row.addWidget(self.ann_pinned)
        row.addStretch(1)

        post_btn = QPushButton("Post announcement")
        post_btn.setObjectName(theme.PRIMARY_BTN)
        post_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        post_btn.clicked.connect(self._post_announcement)
        row.addWidget(post_btn)
        cl.addLayout(row)

        outer.addWidget(compose)

        past_lbl = QLabel("Past announcements")
        past_lbl.setObjectName(theme.EVENT_TITLE_LIST)
        outer.addWidget(past_lbl)

        self.ann_scroll = QScrollArea()
        self.ann_scroll.setWidgetResizable(True)
        self.ann_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.ann_scroll.setObjectName(theme.HOME_SCROLL)

        content = QWidget()
        self.ann_layout = QVBoxLayout(content)
        self.ann_layout.setContentsMargins(0, 0, 0, 0)
        self.ann_layout.setSpacing(10)
        self.ann_layout.addStretch(1)
        self.ann_scroll.setWidget(content)

        outer.addWidget(self.ann_scroll, 1)
        return page

    def _refresh_announcements(self):
        self._clear_all(self.ann_layout)
        if not self.org:
            return
        rows = self._db_call(
            "getAnnouncementsForOrg", self.org["orgID"], default=[]
        ) or []

        if not rows:
            self.ann_layout.insertWidget(0, self._overview_text(
                "No announcements yet. Post one above to reach volunteers."
            ))
            return

        for r in rows:
            card = QFrame()
            card.setObjectName(theme.EVENT_CARD)
            v = QVBoxLayout(card)
            v.setContentsMargins(18, 14, 18, 14)
            v.setSpacing(6)

            header = QHBoxLayout()
            title = QLabel(r["title"])
            title.setObjectName(theme.EVENT_TITLE_LIST)
            header.addWidget(title)
            if r["pinned"]:
                pin = QLabel("PINNED")
                pin.setObjectName(theme.EVENT_STATUS_BADGE)
                header.addWidget(pin)
            header.addStretch(1)

            ts = QLabel(str(r["created_at"] or "")[:19])
            ts.setObjectName(theme.EVENT_META_VALUE)
            header.addWidget(ts)
            v.addLayout(header)

            body = QLabel(r["body"])
            body.setObjectName(theme.EVENT_META_VALUE)
            body.setWordWrap(True)
            v.addWidget(body)

            row = QHBoxLayout()
            row.addStretch(1)

            pin_btn = QPushButton("Unpin" if r["pinned"] else "Pin")
            pin_btn.setObjectName(theme.SECONDARY_BTN)
            pin_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            pin_btn.clicked.connect(
                lambda _, aid=r["announcementID"],
                       p=not r["pinned"]: self._toggle_pin(aid, p)
            )
            row.addWidget(pin_btn)

            del_btn = QPushButton("Delete")
            del_btn.setObjectName(theme.SECONDARY_BTN)
            del_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            del_btn.clicked.connect(
                lambda _, aid=r["announcementID"]:
                    self._delete_announcement(aid)
            )
            row.addWidget(del_btn)

            v.addLayout(row)
            self.ann_layout.insertWidget(
                self.ann_layout.count() - 1, card
            )

    def _post_announcement(self):
        if not self.org:
            return
        title = self.ann_title.text().strip()
        body = self.ann_body.toPlainText().strip()
        if not title or not body:
            QMessageBox.warning(
                self, "Missing fields",
                "Both a title and a message are required."
            )
            return

        ann_id = self._db_call(
            "addAnnouncement",
            self.org["orgID"], title, body,
            1 if self.ann_pinned.isChecked() else 0,
            default=None,
        )
        if not ann_id:
            QMessageBox.warning(
                self, "Post failed",
                "Could not post the announcement."
            )
            return

        self.ann_title.clear()
        self.ann_body.clear()
        self.ann_pinned.setChecked(False)
        QMessageBox.information(
            self, "Posted", "Your volunteers have been notified."
        )
        self._refresh_announcements()

    def _toggle_pin(self, announcementID, pin):
        self._db_call("setAnnouncementPinned", announcementID, pin)
        self._refresh_announcements()

    def _delete_announcement(self, announcementID):
        if QMessageBox.question(
            self, "Delete announcement",
            "Delete this announcement? This cannot be undone."
        ) != QMessageBox.StandardButton.Yes:
            return
        self._db_call("deleteAnnouncement", announcementID)
        self._refresh_announcements()

    # ── DB wrapper ─────────────────────────────────────────────────
    def _db_call(self, method, *args, default=None):
        fn = getattr(self.db, method, None) if self.db else None
        if fn is None:
            print(f"Database.{method}() is not implemented yet")
            return default
        try:
            return fn(*args)
        except Exception as e:
            print(f"Database.{method}() failed:", e)
            return default