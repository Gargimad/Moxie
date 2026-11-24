"""
orgReportsPage.py - Customizable reports for the org dashboard.

Filters: date range, volunteer, opportunity.
Views:   hours by volunteer, hours by opportunity, hours by month.
Output:  on-screen table + CSV export.
"""

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
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


class OrgReportsPage(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.org = None
        self.rows = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 20, 40, 20)
        outer.setSpacing(12)

        heading = QLabel("Reports")
        heading.setObjectName(theme.SECTION_TITLE)
        outer.addWidget(heading)

        sub = QLabel(
            "Filter by date, volunteer, or opportunity. Export any "
            "report to CSV for grant reporting or board updates."
        )
        sub.setObjectName(theme.EVENT_META_VALUE)
        sub.setWordWrap(True)
        outer.addWidget(sub)

        # ── Filters ────────────────────────────────────────────────
        filters = QHBoxLayout()
        filters.setSpacing(8)

        today = QDate.currentDate()
        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDisplayFormat("yyyy-MM-dd")
        self.from_date.setDate(today.addMonths(-3))
        self.from_date.dateChanged.connect(self._refresh)
        filters.addWidget(QLabel("From"))
        filters.addWidget(self.from_date)

        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDisplayFormat("yyyy-MM-dd")
        self.to_date.setDate(today.addMonths(3))
        self.to_date.dateChanged.connect(self._refresh)
        filters.addWidget(QLabel("To"))
        filters.addWidget(self.to_date)

        self.volunteer_combo = QComboBox()
        self.volunteer_combo.currentIndexChanged.connect(self._refresh)
        filters.addWidget(self.volunteer_combo, 1)

        self.opportunity_combo = QComboBox()
        self.opportunity_combo.currentIndexChanged.connect(self._refresh)
        filters.addWidget(self.opportunity_combo, 1)

        clear_btn = QPushButton("Reset")
        clear_btn.setObjectName(theme.SECONDARY_BTN)
        clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clear_btn.clicked.connect(self._reset_filters)
        filters.addWidget(clear_btn)

        outer.addLayout(filters)

        # ── Summary tiles ──────────────────────────────────────────
        self.summary_row = QHBoxLayout()
        self.summary_row.setSpacing(10)
        outer.addLayout(self.summary_row)

        # ── Report body ────────────────────────────────────────────
        body = QHBoxLayout()
        body.setSpacing(12)

        # Left: hours by volunteer
        left_col = QVBoxLayout()
        left_title = QLabel("Hours by volunteer")
        left_title.setObjectName(theme.EVENT_TITLE_LIST)
        left_col.addWidget(left_title)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        left_scroll.setObjectName(theme.HOME_SCROLL)
        left_content = QWidget()
        self.left_layout = QVBoxLayout(left_content)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(6)
        self.left_layout.addStretch(1)
        left_scroll.setWidget(left_content)
        left_col.addWidget(left_scroll, 1)
        body.addLayout(left_col, 1)

        # Right: hours by opportunity
        right_col = QVBoxLayout()
        right_title = QLabel("Hours by opportunity")
        right_title.setObjectName(theme.EVENT_TITLE_LIST)
        right_col.addWidget(right_title)
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        right_scroll.setObjectName(theme.HOME_SCROLL)
        right_content = QWidget()
        self.right_layout = QVBoxLayout(right_content)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(6)
        self.right_layout.addStretch(1)
        right_scroll.setWidget(right_content)
        right_col.addWidget(right_scroll, 1)
        body.addLayout(right_col, 1)

        outer.addLayout(body, 1)

        # ── Export ─────────────────────────────────────────────────
        export_row = QHBoxLayout()
        export_row.addStretch(1)
        self.export_btn = QPushButton("Export detailed CSV")
        self.export_btn.setObjectName(theme.PRIMARY_BTN)
        self.export_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.export_btn.clicked.connect(self._export_csv)
        export_row.addWidget(self.export_btn)
        outer.addLayout(export_row)

    # ── Lifecycle ──────────────────────────────────────────────────
    def set_org(self, org):
        self.org = org
        self._populate_filter_combos()
        self.refresh()

    def refresh(self):
        if not self.org:
            return
        self._refresh()

    def _populate_filter_combos(self):
        # Volunteers
        self.volunteer_combo.blockSignals(True)
        self.volunteer_combo.clear()
        self.volunteer_combo.addItem("All volunteers", None)
        vols = self._db("getOrgVolunteers", self.org["orgID"],
                        default=[]) or []
        for v in vols:
            name = " ".join(
                x for x in [v["first_name"], v["last_name"]] if x
            ) or v["email"]
            self.volunteer_combo.addItem(name, v["userID"])
        self.volunteer_combo.blockSignals(False)

        # Opportunities
        self.opportunity_combo.blockSignals(True)
        self.opportunity_combo.clear()
        self.opportunity_combo.addItem("All opportunities", None)
        opps = self._db("getOpportunitiesByOrg", self.org["orgID"],
                        default=[]) or []
        for o in opps:
            self.opportunity_combo.addItem(
                str(o["title"] or "Untitled"), o["opportunityID"]
            )
        self.opportunity_combo.blockSignals(False)

    def _reset_filters(self):
        today = QDate.currentDate()
        self.from_date.setDate(today.addMonths(-3))
        self.to_date.setDate(today.addMonths(3))
        self.volunteer_combo.setCurrentIndex(0)
        self.opportunity_combo.setCurrentIndex(0)
        self._refresh()

    # ── Data ──────────────────────────────────────────────────────
    def _refresh(self, *_):
        if not self.org:
            return
        date_from = self.from_date.date().toString("yyyy-MM-dd")
        date_to = self.to_date.date().toString("yyyy-MM-dd")
        vol_id = self.volunteer_combo.currentData()
        opp_id = self.opportunity_combo.currentData()

        self.rows = self._db(
            "getOrgHoursReport", self.org["orgID"],
            date_from, date_to, vol_id, opp_id, default=[],
        ) or []

        self._render_summary()
        self._render_left()
        self._render_right()

    def _render_summary(self):
        self._clear_layout(self.summary_row)
        total_hours = sum(float(r["hours_logged"] or 0)
                          for r in self.rows if not r["no_show"])
        verified = sum(float(r["hours_logged"] or 0)
                       for r in self.rows
                       if r["verified"] and not r["no_show"])
        uniq_vols = len({r["userID"] for r in self.rows})
        no_shows = sum(1 for r in self.rows if r["no_show"])
        volunteer_counts = {}
        for row in self.rows:
            volunteer_counts[row["userID"]] = (
                volunteer_counts.get(row["userID"], 0) + 1
            )
        repeat_volunteers = sum(
            1 for count in volunteer_counts.values() if count > 1
        )
        opportunities = self._db(
            "getOpportunitiesByOrg", self.org["orgID"], default=[]
        ) or []
        capped_opportunities = [
            row for row in opportunities
            if row["capacity"] and
            (row["status"] or "").lower() != "cancelled"
        ]
        capacity = sum(int(row["capacity"]) for row in capped_opportunities)
        signups = sum(
            int(row["registered_count"] or 0) for row in capped_opportunities
        )
        fill_rate = f"{round(100 * signups / capacity)}%" if capacity else "—"

        for label, value in (
            ("Total hours", f"{total_hours:.1f}"),
            ("Verified hours", f"{verified:.1f}"),
            ("Volunteers", str(uniq_vols)),
            ("Repeat volunteers", str(repeat_volunteers)),
            ("No-shows", str(no_shows)),
            ("Overall capacity filled", fill_rate),
        ):
            tile = QFrame()
            tile.setObjectName(theme.EVENT_CARD)
            tl = QVBoxLayout(tile)
            tl.setContentsMargins(14, 10, 14, 10)
            val = QLabel(value)
            val.setStyleSheet("font-size: 22px; font-weight: bold;")
            cap = QLabel(label)
            cap.setObjectName(theme.EVENT_META_VALUE)
            tl.addWidget(val)
            tl.addWidget(cap)
            self.summary_row.addWidget(tile, 1)

    def _render_left(self):
        self._clear(self.left_layout)
        totals = {}
        for r in self.rows:
            if r["no_show"]:
                continue
            key = r["userID"]
            name = " ".join(
                x for x in [r["first_name"], r["last_name"]] if x
            ) or r["email"]
            totals.setdefault(key, {"name": name, "hours": 0.0,
                                    "events": 0})
            totals[key]["hours"] += float(r["hours_logged"] or 0)
            totals[key]["events"] += 1

        if not totals:
            self._empty(self.left_layout, "No hours in this range.")
            return

        ranked = sorted(totals.values(), key=lambda t: -t["hours"])
        for entry in ranked:
            self.left_layout.insertWidget(
                self.left_layout.count() - 1,
                self._make_bar_row(entry["name"], entry["hours"],
                                   entry["events"]),
            )

    def _render_right(self):
        self._clear(self.right_layout)
        totals = {}
        for r in self.rows:
            if r["no_show"]:
                continue
            key = r["opportunityID"]
            totals.setdefault(key, {
                "name": str(r["title"] or "Untitled"),
                "hours": 0.0, "events": 1,
            })
            totals[key]["hours"] += float(r["hours_logged"] or 0)

        if not totals:
            self._empty(self.right_layout, "No hours in this range.")
            return

        ranked = sorted(totals.values(), key=lambda t: -t["hours"])
        for entry in ranked:
            self.right_layout.insertWidget(
                self.right_layout.count() - 1,
                self._make_bar_row(entry["name"], entry["hours"],
                                   entry["events"]),
            )

    def _make_bar_row(self, name, hours, events):
        card = QFrame()
        card.setObjectName(theme.EVENT_CARD)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        label = QLabel(name)
        label.setWordWrap(True)
        lay.addWidget(label, 3)

        meta = QLabel(f"{events} event{'s' if events != 1 else ''}")
        meta.setObjectName(theme.EVENT_META_VALUE)
        lay.addWidget(meta, 1)

        val = QLabel(f"{hours:.1f} h")
        val.setStyleSheet("font-weight: bold;")
        lay.addWidget(val, 0)
        return card

    # ── Export ────────────────────────────────────────────────────
    def _export_csv(self):
        if not self.rows:
            QMessageBox.information(self, "Nothing to export",
                                    "No rows in this range.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export report",
            f"report_{self.org['orgID']}.csv", "CSV (*.csv)",
        )
        if not path:
            return
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    "Volunteer", "Email", "Opportunity", "Event date",
                    "Check-in", "Check-out", "Hours", "Verified",
                    "No-show",
                ])
                for r in self.rows:
                    name = " ".join(
                        x for x in [r["first_name"], r["last_name"]] if x
                    ) or ""
                    w.writerow([
                        name,
                        r["email"] or "",
                        r["title"] or "",
                        r["event_date"] or "",
                        r["check_in_time"] or "",
                        r["check_out_time"] or "",
                        f"{float(r['hours_logged'] or 0):.2f}",
                        "yes" if r["verified"] else "no",
                        "yes" if r["no_show"] else "no",
                    ])
            QMessageBox.information(self, "Exported", f"Saved to:\n{path}")
        except OSError as e:
            QMessageBox.warning(self, "Export failed", str(e))

    # ── Helpers ───────────────────────────────────────────────────
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

    def _clear(self, layout):
        while layout.count() > 1:
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _empty(self, layout, text):
        lbl = QLabel(text)
        lbl.setObjectName(theme.VOLUNTEER_EMPTY)
        lbl.setWordWrap(True)
        layout.insertWidget(0, lbl)
