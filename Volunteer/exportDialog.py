"""
exportDialog.py - Volunteer data export (CSV + PDF).

Hours dataset has a "Verified only" toggle so volunteers can produce a
clean record for NHS, honor societies, or award applications.
"""
import csv
from datetime import datetime

from PyQt6.QtCore import Qt, QRectF, QDate
from PyQt6.QtGui import QPainter, QPdfWriter, QPageSize, QFont, QPageLayout
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QDateEdit, QMessageBox, QFileDialog, QFrame, QCheckBox,
)

import Events.theme as theme


class ExportDialog(QDialog):
    DATASETS = [
        ("hours", "Hours log"),
        ("registrations", "Event registrations"),
        ("bookmarks", "Bookmarked events"),
    ]

    def __init__(self, db, userID, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.EXPORT_DIALOG)
        self.setWindowTitle("Export my Moxie data")
        self.setMinimumWidth(460)
        self.db = db
        self.userID = userID

        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(12)

        title = QLabel("Export my data")
        title.setObjectName(theme.EVENT_TITLE_LIST)
        v.addWidget(title)

        sub = QLabel(
            "Pick a dataset, a date range, and a format. Exports only "
            "include your own information."
        )
        sub.setObjectName(theme.EVENT_META_VALUE)
        sub.setWordWrap(True)
        v.addWidget(sub)

        card = QFrame()
        card.setObjectName(theme.EXPORT_SECTION)
        cv = QVBoxLayout(card)
        cv.setContentsMargins(18, 14, 18, 14)
        cv.setSpacing(8)

        cv.addWidget(QLabel("Dataset"))
        self.dataset_combo = QComboBox()
        for key, label in self.DATASETS:
            self.dataset_combo.addItem(label, key)
        self.dataset_combo.setAccessibleName("Export dataset")
        cv.addWidget(self.dataset_combo)

        self.verified_only = QCheckBox(
            "Verified hours only (for NHS, honor societies, awards)"
        )
        self.verified_only.setAccessibleName(
            "Only include verified hours in the export"
        )
        cv.addWidget(self.verified_only)

        cv.addWidget(QLabel("Format"))
        self.format_combo = QComboBox()
        self.format_combo.addItem("CSV (.csv)", "csv")
        self.format_combo.addItem("PDF report (.pdf)", "pdf")
        self.format_combo.setAccessibleName("Export format")
        cv.addWidget(self.format_combo)

        cv.addWidget(QLabel("From"))
        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDisplayFormat("yyyy-MM-dd")
        self.from_date.setDate(QDate.currentDate().addMonths(-6))
        self.from_date.setAccessibleName("Export from date")
        cv.addWidget(self.from_date)

        cv.addWidget(QLabel("To"))
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDisplayFormat("yyyy-MM-dd")
        self.to_date.setDate(QDate.currentDate())
        self.to_date.setAccessibleName("Export to date")
        cv.addWidget(self.to_date)

        v.addWidget(card)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName(theme.SECONDARY_BTN)
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        export = QPushButton("Export")
        export.setObjectName(theme.PRIMARY_BTN)
        export.clicked.connect(self._export)
        row.addWidget(export)
        v.addLayout(row)

        self.dataset_combo.currentIndexChanged.connect(
            self._on_dataset_changed
        )
        self._on_dataset_changed()

    def _on_dataset_changed(self):
        is_hours = self.dataset_combo.currentData() == "hours"
        self.verified_only.setVisible(is_hours)

    def _export(self):
        ds = self.dataset_combo.currentData()
        fmt = self.format_combo.currentData()
        d_from = self.from_date.date().toString("yyyy-MM-dd")
        d_to = self.to_date.date().toString("yyyy-MM-dd")

        rows, headers = self._fetch(ds, d_from, d_to)
        if not rows:
            QMessageBox.information(
                self, "Nothing to export", "No rows in that date range."
            )
            return

        if fmt == "csv":
            path, _ = QFileDialog.getSaveFileName(
                self, "Save CSV", f"moxie-{ds}.csv", "CSV (*.csv)",
            )
            if not path:
                return
            self._write_csv(path, headers, rows)
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save PDF", f"moxie-{ds}.pdf", "PDF (*.pdf)",
            )
            if not path:
                return
            self._write_pdf(path, ds, headers, rows)

        QMessageBox.information(
            self, "Export complete",
            f"Saved {len(rows)} rows to:\n{path}"
        )
        self.accept()

    def _fetch(self, ds, d_from, d_to):
        if ds == "hours":
            only_verified = self.verified_only.isChecked()
            headers = ["Date", "Event", "Organization", "Hours", "Verified"]
            rows = []
            signups = self.db.getSignupsForVolunteer(self.userID) or []
            for r in signups:
                d = str(r["event_date"] or "")[:10]
                if not d or d < d_from or d > d_to:
                    continue
                if r["no_show"]:
                    continue
                if only_verified and not r["verified"]:
                    continue
                rows.append([
                    d,
                    r["title"] or "",
                    r["org_name"] or "Independent",
                    f"{float(r['hours_logged'] or 0):.2f}",
                    "yes" if r["verified"] else "no",
                ])
            return rows, headers

        if ds == "registrations":
            headers = ["Signup date", "Event", "Event date", "Org", "Status"]
            rows = []
            signups = self.db.getSignupsForVolunteer(self.userID) or []
            for r in signups:
                sd = str(r["signup_time"] or "")[:10]
                if sd and (sd < d_from or sd > d_to):
                    continue
                rows.append([
                    sd,
                    r["title"] or "",
                    str(r["event_date"] or "")[:10],
                    r["org_name"] or "Independent",
                    r["status"] or "registered",
                ])
            return rows, headers

        headers = ["Bookmarked at", "Event", "Event date", "Org", "Clusters"]
        rows = []
        marks = self.db.getBookmarkedOpportunities(self.userID) or []
        for r in marks:
            clusters = self.db.getOpportunityClusters(
                r["opportunityID"]
            ) or []
            rows.append([
                "",
                r["title"] or "",
                str(r["event_date"] or "")[:10],
                r["org_name"] or "Independent",
                ", ".join(clusters),
            ])
        return rows, headers

    def _write_csv(self, path, headers, rows):
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for row in rows:
                w.writerow(row)

    def _write_pdf(self, path, ds, headers, rows):
        writer = QPdfWriter(path)
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
        writer.setPageMargins(QPageLayout().margins())
        writer.setResolution(150)

        painter = QPainter(writer)   # begins implicitly, do NOT call begin()
        try:
            base = QFont("Helvetica", 10)
            heading = QFont("Helvetica", 16, QFont.Weight.Bold)
            sub = QFont("Helvetica", 10, QFont.Weight.Normal)

            painter.setFont(heading)
            painter.drawText(
                QRectF(0, 0, writer.width(), 400),
                Qt.AlignmentFlag.AlignLeft,
                "Moxie data export",
            )
            painter.setFont(sub)
            painter.drawText(
                QRectF(0, 300, writer.width(), 200),
                Qt.AlignmentFlag.AlignLeft,
                f"{ds} - generated {datetime.now():%Y-%m-%d %H:%M}",
            )

            painter.setFont(base)
            col_w = writer.width() // max(1, len(headers))
            y = 600
            row_h = 260

            for i, h in enumerate(headers):
                painter.drawText(
                    QRectF(i * col_w, y, col_w, row_h),
                    Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignVCenter,
                    str(h),
                )
            y += row_h

            for row in rows:
                if y > writer.height() - 400:
                    writer.newPage()
                    y = 300
                for i, cell in enumerate(row):
                    painter.drawText(
                        QRectF(i * col_w, y, col_w, row_h),
                        Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter,
                        str(cell),
                    )
                y += row_h
        finally:
            painter.end()