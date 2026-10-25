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
from Events.careerClusters import (
    CAREER_CLUSTERS, legacy_category_to_cluster,
)
from Events.gaLocations import GA_CITIES
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
        self._original_category = None
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
        page.setObjectName("OrgOverviewPage")
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
        content.setObjectName(theme.HOME_SCROLL_CONTENT)
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
            rows.append((name, float(r["hours"] or 0)))
        if not rows:
            rows = [("No hours logged yet", 0.0)]
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
        outer.setContentsMargins(36, 24, 36, 20)
        outer.setSpacing(16)

        header = QWidget()
        header.setMaximumWidth(1120)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        self.form_title = QLabel("New Opportunity")
        self.form_title.setObjectName("OpportunityFormTitle")
        header_layout.addWidget(self.form_title)

        subtitle = QLabel(
            "Create a welcoming opportunity and share the details "
            "volunteers need."
        )
        subtitle.setObjectName("OpportunityFormSubtitle")
        header_layout.addWidget(subtitle)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.addStretch(1)
        header_row.addWidget(header, 8)
        header_row.addStretch(1)
        outer.addLayout(header_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setObjectName(theme.HOME_SCROLL)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        scroll_content = QWidget()
        content_layout = QHBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addStretch(1)

        form_card = QFrame()
        form_card.setObjectName("OpportunityFormCard")
        form_card.setMaximumWidth(1120)
        card_layout = QVBoxLayout(form_card)
        card_layout.setContentsMargins(28, 24, 28, 28)
        card_layout.setSpacing(0)
        content_layout.addWidget(form_card, 8)
        content_layout.addStretch(1)

        self.f_title = QLineEdit()
        self.f_title.setPlaceholderText("e.g. Saturday park cleanup")

        self.f_category = QComboBox()
        self.f_category.addItem("Select a category")
        self.f_category.addItems(CAREER_CLUSTERS)

        self.f_description = QTextEdit()
        self.f_description.setPlaceholderText(
            "What will volunteers be doing?"
        )
        self.f_description.setFixedHeight(90)

        self.f_city = QComboBox()
        self.f_city.setEditable(True)
        self.f_city.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.f_city.addItem("")
        self.f_city.addItems(GA_CITIES)
        self.f_city.lineEdit().setPlaceholderText("Georgia city")

        self.f_location = QLineEdit()
        self.f_location.setPlaceholderText("Neighborhood or location name")

        self.f_address = QLineEdit()
        self.f_address.setPlaceholderText("Street address (optional)")

        self.f_high_school = QLineEdit()
        self.f_high_school.setPlaceholderText("School (optional)")

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

        self.f_website = QLineEdit()
        self.f_website.setPlaceholderText("https:// (optional)")

        self.f_min_age = QSpinBox()
        self.f_min_age.setRange(0, 120)
        self.f_min_age.setSpecialValueText("No minimum")

        self.f_max_age = QSpinBox()
        self.f_max_age.setRange(0, 120)
        self.f_max_age.setSpecialValueText("No maximum")

        self.f_min_grade = QLineEdit()
        self.f_min_grade.setPlaceholderText("e.g. 9th grade")

        self.f_max_grade = QLineEdit()
        self.f_max_grade.setPlaceholderText("e.g. 12th grade")

        self.f_meeting_point = QLineEdit()
        self.f_meeting_point.setPlaceholderText("Where to check in")

        self.f_parking = QLineEdit()
        self.f_parking.setPlaceholderText("Parking details (optional)")

        self.f_accessibility = QTextEdit()
        self.f_accessibility.setPlaceholderText(
            "Accessibility accommodations or site details (optional)"
        )
        self.f_accessibility.setFixedHeight(72)

        self.f_what_to_bring = QLineEdit()
        self.f_what_to_bring.setPlaceholderText(
            "e.g. Water bottle, work gloves"
        )

        self.f_dress_code = QLineEdit()
        self.f_dress_code.setPlaceholderText(
            "e.g. Closed-toe shoes, comfortable clothes"
        )

        self.f_meal_provided = QCheckBox("A meal will be provided")
        self.f_background_check = QCheckBox(
            "Background check required"
        )
        self.f_training_required = QCheckBox("Training required")

        self.f_training_description = QTextEdit()
        self.f_training_description.setPlaceholderText(
            "Training details (optional)"
        )
        self.f_training_description.setFixedHeight(72)

        def add_section(title, hint):
            section = QWidget()
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(0, 0, 0, 0)
            section_layout.setSpacing(12)

            heading = QLabel(title)
            heading.setObjectName("OpportunityFormSectionTitle")
            section_layout.addWidget(heading)

            if hint:
                description = QLabel(hint)
                description.setObjectName("OpportunityFormSectionHint")
                description.setWordWrap(True)
                section_layout.addWidget(description)

            card_layout.addWidget(section)
            return section_layout

        def add_field(grid, label_text, widget, row, column, span=1):
            field = QWidget()
            field_layout = QVBoxLayout(field)
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.setSpacing(6)

            label = QLabel(label_text)
            label.setObjectName("OpportunityFormLabel")
            field_layout.addWidget(label)
            field_layout.addWidget(widget)
            grid.addWidget(field, row, column, 1, span)

        def add_divider():
            divider = QFrame()
            divider.setObjectName("OpportunityFormDivider")
            divider.setFrameShape(QFrame.Shape.HLine)
            card_layout.addWidget(divider)
            card_layout.addSpacing(20)

        basics = add_section(
            "Opportunity details",
            "Give your opportunity a clear title and a short description.",
        )
        basics_grid = QGridLayout()
        basics_grid.setContentsMargins(0, 0, 0, 0)
        basics_grid.setHorizontalSpacing(20)
        basics_grid.setVerticalSpacing(16)
        add_field(basics_grid, "Title *", self.f_title, 0, 0)
        add_field(basics_grid, "Category *", self.f_category, 0, 1)
        add_field(basics_grid, "Description", self.f_description, 1, 0, 2)
        basics_grid.setColumnStretch(0, 1)
        basics_grid.setColumnStretch(1, 1)
        basics.addLayout(basics_grid)
        add_divider()

        logistics = add_section(
            "Time & location",
            "Let volunteers know when and where to meet.",
        )
        logistics_grid = QGridLayout()
        logistics_grid.setContentsMargins(0, 0, 0, 0)
        logistics_grid.setHorizontalSpacing(20)
        logistics_grid.setVerticalSpacing(16)
        add_field(logistics_grid, "Georgia city", self.f_city, 0, 0)
        add_field(logistics_grid, "Neighborhood or location",
                  self.f_location, 0, 1)
        add_field(logistics_grid, "Street address (optional)",
                  self.f_address, 1, 0, 2)
        add_field(logistics_grid, "Start date", self.f_date, 2, 0)
        add_field(logistics_grid, "End date", self.f_end_date, 2, 1)
        add_field(logistics_grid, "Start time", self.f_start, 3, 0)
        add_field(logistics_grid, "End time", self.f_end, 3, 1)
        add_field(logistics_grid, "School (optional)",
                  self.f_high_school, 4, 0, 2)
        logistics_grid.setColumnStretch(0, 1)
        logistics_grid.setColumnStretch(1, 1)
        logistics.addLayout(logistics_grid)
        logistics.addWidget(self.f_remote)
        add_divider()

        volunteers = add_section(
            "Volunteer details",
            "Set expectations and let volunteers know what to bring.",
        )
        volunteer_grid = QGridLayout()
        volunteer_grid.setContentsMargins(0, 0, 0, 0)
        volunteer_grid.setHorizontalSpacing(20)
        volunteer_grid.setVerticalSpacing(16)
        add_field(volunteer_grid, "Signup status", self.f_status, 0, 0)
        add_field(volunteer_grid, "Volunteer capacity",
                  self.f_capacity, 0, 1)
        add_field(volunteer_grid, "Required skills (optional)",
                  self.f_skills, 1, 0, 2)
        volunteer_grid.setColumnStretch(0, 1)
        volunteer_grid.setColumnStretch(1, 1)
        volunteers.addLayout(volunteer_grid)
        add_divider()

        eligibility = add_section(
            "Eligibility & requirements",
            "Optional age or grade limits help volunteers find the right fit.",
        )
        eligibility_grid = QGridLayout()
        eligibility_grid.setContentsMargins(0, 0, 0, 0)
        eligibility_grid.setHorizontalSpacing(20)
        eligibility_grid.setVerticalSpacing(16)
        add_field(eligibility_grid, "Minimum age", self.f_min_age, 0, 0)
        add_field(eligibility_grid, "Maximum age", self.f_max_age, 0, 1)
        add_field(eligibility_grid, "Minimum grade",
                  self.f_min_grade, 1, 0)
        add_field(eligibility_grid, "Maximum grade",
                  self.f_max_grade, 1, 1)
        eligibility_grid.setColumnStretch(0, 1)
        eligibility_grid.setColumnStretch(1, 1)
        eligibility.addLayout(eligibility_grid)
        eligibility.addWidget(self.f_background_check)
        eligibility.addWidget(self.f_training_required)
        training_grid = QGridLayout()
        training_grid.setContentsMargins(0, 0, 0, 0)
        add_field(training_grid, "Training details (optional)",
                  self.f_training_description, 0, 0, 2)
        eligibility.addLayout(training_grid)
        add_divider()

        onsite = add_section(
            "On-site details",
            "Share practical information so volunteers can prepare.",
        )
        onsite_grid = QGridLayout()
        onsite_grid.setContentsMargins(0, 0, 0, 0)
        onsite_grid.setHorizontalSpacing(20)
        onsite_grid.setVerticalSpacing(16)
        add_field(onsite_grid, "Meeting point", self.f_meeting_point, 0, 0)
        add_field(onsite_grid, "Parking", self.f_parking, 0, 1)
        add_field(onsite_grid, "What to bring", self.f_what_to_bring, 1, 0)
        add_field(onsite_grid, "Dress code", self.f_dress_code, 1, 1)
        add_field(onsite_grid, "Accessibility notes",
                  self.f_accessibility, 2, 0, 2)
        onsite_grid.setColumnStretch(0, 1)
        onsite_grid.setColumnStretch(1, 1)
        onsite.addLayout(onsite_grid)
        onsite.addWidget(self.f_meal_provided)
        add_divider()

        contact = add_section(
            "Contact & image",
            "Provide a point of contact and an optional opportunity image.",
        )
        contact_grid = QGridLayout()
        contact_grid.setContentsMargins(0, 0, 0, 0)
        contact_grid.setHorizontalSpacing(20)
        contact_grid.setVerticalSpacing(16)
        add_field(contact_grid, "Contact name (optional)",
                  self.f_contact_name, 0, 0)
        add_field(contact_grid, "Contact email (optional)",
                  self.f_contact_email, 0, 1)
        add_field(contact_grid, "Website (optional)",
                  self.f_website, 1, 0, 2)
        contact_grid.setColumnStretch(0, 1)
        contact_grid.setColumnStretch(1, 1)
        contact.addLayout(contact_grid)

        self.thumb_lbl = QLabel("No image attached")
        self.thumb_lbl.setObjectName("OpportunityFormImageStatus")

        pick_btn = QPushButton("Choose image…")
        pick_btn.setObjectName(theme.SECONDARY_BTN)
        pick_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        pick_btn.clicked.connect(self._pick_thumbnail)

        clear_btn = QPushButton("Remove image")
        clear_btn.setObjectName(theme.SECONDARY_BTN)
        clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clear_btn.clicked.connect(self._clear_thumbnail)

        thumb_row = QHBoxLayout()
        thumb_row.setContentsMargins(0, 0, 0, 0)
        thumb_row.setSpacing(8)
        thumb_row.addWidget(pick_btn)
        thumb_row.addWidget(clear_btn)
        thumb_row.addWidget(self.thumb_lbl, 1)

        thumbnail_label = QLabel("Opportunity thumbnail (optional)")
        thumbnail_label.setObjectName("OpportunityFormLabel")
        contact.addWidget(thumbnail_label)
        contact.addLayout(thumb_row)

        scroll.setWidget(scroll_content)
        outer.addWidget(scroll, 1)

        footer_divider = QFrame()
        footer_divider.setObjectName("OpportunityFormDivider")
        footer_divider.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(footer_divider)

        row = QHBoxLayout()
        row.setContentsMargins(0, 8, 0, 0)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName(theme.SECONDARY_BTN)
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.clicked.connect(lambda: self.show_tab(TAB_LIST))

        save_btn = QPushButton("Save")
        save_btn.setObjectName(theme.PRIMARY_BTN)
        save_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        save_btn.setMinimumWidth(112)
        save_btn.clicked.connect(self._save)

        row.addStretch()
        row.addWidget(cancel_btn)
        row.addWidget(save_btn)
        outer.addLayout(row)
        return page

    def _start_new(self):
        self.editing_id = None
        self._original_category = None
        self._pending_thumbnail = None
        self.form_title.setText("New Opportunity")
        for w in (self.f_title, self.f_description, self.f_location,
                  self.f_address, self.f_skills, self.f_contact_name,
                  self.f_contact_email, self.f_start, self.f_end,
                  self.f_high_school, self.f_website, self.f_min_grade,
                  self.f_max_grade, self.f_meeting_point, self.f_parking,
                  self.f_accessibility, self.f_what_to_bring,
                  self.f_dress_code, self.f_training_description):
            try:
                w.clear()
            except Exception:
                pass
        self.f_category.setCurrentIndex(0)
        self.f_city.setCurrentIndex(0)
        self.f_city.lineEdit().clear()
        self.f_remote.setChecked(False)
        self.f_date.setDate(QDate.currentDate())
        self.f_end_date.setDate(QDate.currentDate())
        self.f_capacity.setValue(0)
        self.f_min_age.setValue(0)
        self.f_max_age.setValue(0)
        self.f_status.setCurrentText("open")
        self.f_meal_provided.setChecked(False)
        self.f_background_check.setChecked(False)
        self.f_training_required.setChecked(False)
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
        category = legacy_category_to_cluster(row["category"])
        if not category:
            category = row["category"] or ""
        self._original_category = category
        category_index = self.f_category.findText(category)
        if category and category_index < 0:
            self.f_category.addItem(category)
            category_index = self.f_category.count() - 1
        self.f_category.setCurrentIndex(max(0, category_index))
        self.f_description.setPlainText(row["description"] or "")
        self.f_location.setText(row["location"] or "")
        self.f_address.setText(row["address"] or "")
        self.f_city.setCurrentText(row["city"] or "")
        self.f_high_school.setText(row["high_school"] or "")
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
        self.f_min_age.setValue(row["min_age"] or 0)
        self.f_max_age.setValue(row["max_age"] or 0)
        self.f_min_grade.setText(row["min_grade"] or "")
        self.f_max_grade.setText(row["max_grade"] or "")
        self.f_meeting_point.setText(row["meeting_point"] or "")
        self.f_parking.setText(row["parking_info"] or "")
        self.f_accessibility.setPlainText(
            row["accessibility_notes"] or ""
        )
        self.f_what_to_bring.setText(row["what_to_bring"] or "")
        self.f_dress_code.setText(row["dress_code"] or "")
        self.f_meal_provided.setChecked(bool(row["meal_provided"]))
        self.f_background_check.setChecked(
            bool(row["background_check_required"])
        )
        self.f_training_required.setChecked(
            bool(row["training_required"])
        )
        self.f_training_description.setPlainText(
            row["training_description"] or ""
        )
        self.f_contact_name.setText(row["contact_name"] or "")
        self.f_contact_email.setText(row["contact_email"] or "")
        self.f_website.setText(row["website_link"] or "")
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

        category = self.f_category.currentText().strip()
        if self.f_category.currentIndex() <= 0 or not category:
            QMessageBox.warning(
                self, "Missing category",
                "Choose a category for this opportunity.",
            )
            return

        start_date = self.f_date.date()
        end_date = self.f_end_date.date()
        if end_date < start_date:
            QMessageBox.warning(
                self, "Invalid dates",
                "End date can't be before the start date."
            )
            return

        min_age = self.f_min_age.value() or None
        max_age = self.f_max_age.value() or None
        if min_age and max_age and max_age < min_age:
            QMessageBox.warning(
                self, "Invalid age range",
                "Maximum age can't be lower than minimum age.",
            )
            return

        end_iso = end_date.toString("yyyy-MM-dd")
        start_iso = start_date.toString("yyyy-MM-dd")
        stored_end = None if end_iso == start_iso else end_iso

        payload = dict(
            title=title,
            description=self.f_description.toPlainText().strip(),
            category=category,
            location=self.f_location.text().strip(),
            address=self.f_address.text().strip(),
            is_remote=self.f_remote.isChecked(),
            city=self.f_city.currentText().strip() or None,
            state="GA",
            high_school=self.f_high_school.text().strip() or None,
            event_date=start_iso,
            event_end_date=stored_end,
            start_time=self.f_start.text().strip() or None,
            end_time=self.f_end.text().strip() or None,
            capacity=self.f_capacity.value() or None,
            status=self.f_status.currentText(),
            required_skills=self.f_skills.text().strip() or None,
            min_age=min_age,
            max_age=max_age,
            min_grade=self.f_min_grade.text().strip() or None,
            max_grade=self.f_max_grade.text().strip() or None,
            meeting_point=self.f_meeting_point.text().strip() or None,
            parking_info=self.f_parking.text().strip() or None,
            accessibility_notes=(
                self.f_accessibility.toPlainText().strip() or None
            ),
            what_to_bring=self.f_what_to_bring.text().strip() or None,
            dress_code=self.f_dress_code.text().strip() or None,
            meal_provided=self.f_meal_provided.isChecked(),
            background_check_required=(
                self.f_background_check.isChecked()
            ),
            training_required=self.f_training_required.isChecked(),
            training_description=(
                self.f_training_description.toPlainText().strip() or None
            ),
            contact_name=self.f_contact_name.text().strip() or None,
            contact_email=self.f_contact_email.text().strip() or None,
            website_link=self.f_website.text().strip() or None,
            thumbnail=self._pending_thumbnail,
        )
        category_cluster = (
            legacy_category_to_cluster(category)
            or (category if category in CAREER_CLUSTERS else None)
        )

        if self.editing_id:
            ok = self.db.updateOpportunity(self.editing_id, **payload)
            if not ok:
                QMessageBox.warning(self, "Save failed",
                                    "Could not update opportunity.")
                return
            opportunity_id = self.editing_id
        else:
            new_id = self.db.addOpportunity(
                orgID=self.org["orgID"],
                **payload,
            )
            if not new_id:
                QMessageBox.warning(self, "Save failed",
                                    "Could not create opportunity.")
                return
            opportunity_id = new_id
            # Notify matching volunteers (best-effort).
            try:
                n = self.db.notifyVolunteersAboutOpportunity(new_id)
                print(f"[org] notified {n} matching volunteers")
            except Exception as e:
                print("notifyVolunteersAboutOpportunity failed:", e)

        category_changed = (
            self.editing_id is None
            or category != self._original_category
        )
        if (
            category_cluster and category_changed
            and not self.db.setOpportunityClusters(
                opportunity_id, [category_cluster]
            )
        ):
            QMessageBox.warning(
                self, "Category update incomplete",
                "The opportunity was saved, but its category could not be "
                "applied to volunteer matching. Please edit and save it "
                "again, or contact support.",
            )

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