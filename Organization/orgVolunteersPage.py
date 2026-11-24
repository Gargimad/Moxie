"""
orgVolunteersPage.py - The org's volunteer roster.

Lists every volunteer who has ever signed up for one of this org's
opportunities, deduplicated. Supports:
  - live search by name / email / skill
  - filter by "all" / "active" / "banned"
  - sort by hours, name, last event
  - click a row to open the VolunteerProfileDialog

Owned by OrgDashboard; the dashboard hands it the org dict and the
Database instance.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import Events.theme as theme
from Volunteer.volunteerProfileDialog import VolunteerProfileDialog


class OrgVolunteersPage(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.org = None
        self._rows = []
        self._filtered = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 20, 40, 20)
        outer.setSpacing(12)

        # ── Header ─────────────────────────────────────────────────
        header = QHBoxLayout()
        heading = QLabel("Volunteers")
        heading.setObjectName(theme.SECTION_TITLE)
        header.addWidget(heading)
        header.addStretch(1)

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setObjectName(theme.SECONDARY_BTN)
        self.export_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.export_btn.clicked.connect(self._export_csv)
        header.addWidget(self.export_btn)
        outer.addLayout(header)

        sub = QLabel(
            "Everyone who has signed up for one of your opportunities. "
            "Click a volunteer to see their history, hours, and notes."
        )
        sub.setObjectName(theme.EVENT_META_VALUE)
        sub.setWordWrap(True)
        outer.addWidget(sub)

        # ── Filter row ─────────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search by name, email, or skill..."
        )
        self.search_input.textChanged.connect(self._apply_filters)
        filter_row.addWidget(self.search_input, 3)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["All volunteers", "Active (hours > 0)",
                                    "Banned"])
        self.status_combo.currentTextChanged.connect(self._apply_filters)
        filter_row.addWidget(self.status_combo, 1)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Sort: Hours (high → low)",
                                  "Sort: Hours (low → high)",
                                  "Sort: Name (A → Z)",
                                  "Sort: Last event (newest)"])
        self.sort_combo.currentTextChanged.connect(self._apply_filters)
        filter_row.addWidget(self.sort_combo, 1)

        outer.addLayout(filter_row)

        # ── Roster ─────────────────────────────────────────────────
        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName(theme.VOLUNTEER_RESULTS_COUNT)
        outer.addWidget(self.count_lbl)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setObjectName(theme.HOME_SCROLL)

        content = QWidget()
        self.list_layout = QVBoxLayout(content)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(content)
        outer.addWidget(self.scroll, 1)

    # ── Lifecycle ──────────────────────────────────────────────────
    def set_org(self, org):
        self.org = org

    def refresh(self):
        if not self.org:
            return
        self._rows = self._db("getOrgVolunteers", self.org["orgID"],
                              default=[]) or []
        self._apply_filters()

    # ── Filtering / sorting ────────────────────────────────────────
    def _apply_filters(self, *_):
        q = self.search_input.text().strip().lower()
        status = self.status_combo.currentText()

        rows = list(self._rows)

        if status == "Active (hours > 0)":
            rows = [r for r in rows if float(r["total_hours"] or 0) > 0]
        elif status == "Banned":
            rows = [r for r in rows if r["banned"]]

        if q:
            def matches(r):
                hay = " ".join([
                    str(r["first_name"] or ""),
                    str(r["last_name"] or ""),
                    str(r["email"] or ""),
                    str(r["skills"] or ""),
                ]).lower()
                return q in hay
            rows = [r for r in rows if matches(r)]

        sort = self.sort_combo.currentText()
        if sort.startswith("Sort: Hours (high"):
            rows.sort(key=lambda r: -float(r["total_hours"] or 0))
        elif sort.startswith("Sort: Hours (low"):
            rows.sort(key=lambda r: float(r["total_hours"] or 0))
        elif sort.startswith("Sort: Name"):
            rows.sort(key=lambda r: (
                str(r["last_name"] or "").lower(),
                str(r["first_name"] or "").lower(),
            ))
        elif sort.startswith("Sort: Last event"):
            rows.sort(key=lambda r: str(r["last_event_date"] or ""),
                      reverse=True)

        self._filtered = rows
        self._render()

    def _render(self):
        self._clear(self.list_layout)
        n = len(self._filtered)
        self.count_lbl.setText(
            f"{n} volunteer{'s' if n != 1 else ''}"
        )
        if not self._filtered:
            self._empty(self.list_layout, "No volunteers match.")
            return
        for r in self._filtered:
            self._add(self.list_layout, self._make_row(r))

    def _make_row(self, r):
        card = QFrame()
        card.setObjectName(theme.EVENT_CARD)
        card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        card.mousePressEvent = lambda e, row=r: self._open_profile(row)

        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(14)

        # Name + email block
        left = QVBoxLayout()
        left.setSpacing(2)
        name = " ".join(
            x for x in [r["first_name"], r["last_name"]] if x
        ) or "(no name)"
        if r["banned"]:
            name = f"{name}  •  BANNED"
        name_lbl = QLabel(name)
        name_lbl.setObjectName(theme.EVENT_TITLE_LIST)

        email = QLabel(str(r["email"] or ""))
        email.setObjectName(theme.EVENT_META_VALUE)

        left.addWidget(name_lbl)
        left.addWidget(email)
        lay.addLayout(left, 3)

        # Skills
        skills = QLabel(str(r["skills"] or "—"))
        skills.setObjectName(theme.EVENT_META_VALUE)
        skills.setWordWrap(True)
        lay.addWidget(skills, 2)

        # Stats
        stats = QVBoxLayout()
        stats.setSpacing(2)
        hours = QLabel(f"{float(r['total_hours'] or 0):.1f} h")
        hours.setStyleSheet("font-size: 18px; font-weight: bold;")
        events = QLabel(
            f"{r['total_signups']} signup"
            f"{'s' if r['total_signups'] != 1 else ''}" +
            (f"  •  {r['no_shows']} no-show"
             f"{'s' if r['no_shows'] != 1 else ''}"
             if r["no_shows"] else "")
        )
        events.setObjectName(theme.EVENT_META_VALUE)
        stats.addWidget(hours)
        stats.addWidget(events)
        lay.addLayout(stats, 1)

        return card

    # ── Actions ────────────────────────────────────────────────────
    def _open_profile(self, row):
        dlg = VolunteerProfileDialog(
            self.db, self.org, row["userID"], parent=self
        )
        dlg.exec()
        self.refresh()

    def _export_csv(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Export roster", "volunteers.csv", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    "First name", "Last name", "Email", "Phone",
                    "Skills", "Total hours", "Signups", "No-shows",
                    "Last event", "Banned",
                ])
                for r in self._filtered:
                    w.writerow([
                        r["first_name"] or "",
                        r["last_name"] or "",
                        r["email"] or "",
                        r["phone"] or "",
                        r["skills"] or "",
                        f"{float(r['total_hours'] or 0):.2f}",
                        r["total_signups"],
                        r["no_shows"],
                        r["last_event_date"] or "",
                        "yes" if r["banned"] else "no",
                    ])
            QMessageBox.information(
                self,
                "Exported",
                f"Saved {len(self._filtered)} rows to:\n{path}",
            )
        except OSError as e:
            QMessageBox.warning(self, "Export failed", str(e))

    # ── Small helpers (same pattern as OrgDashboard) ───────────────
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

    def _add(self, layout, widget):
        layout.insertWidget(layout.count() - 1, widget)

    def _empty(self, layout, text):
        lbl = QLabel(text)
        lbl.setObjectName(theme.VOLUNTEER_EMPTY)
        lbl.setWordWrap(True)
        layout.insertWidget(0, lbl)
