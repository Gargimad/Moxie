"""
exportDialog.py - Volunteer data export (CSV + PDF).

Hours dataset has a "Verified only" toggle so volunteers can produce a
clean record for NHS, honor societies, or award applications.
"""
import csv
from datetime import datetime

from PyQt6.QtCore import Qt, QRectF, QDate, QMarginsF
from PyQt6.QtGui import (
    QColor, QFont, QFontMetricsF, QPainter, QPageLayout, QPageSize, QPdfWriter,
)
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
        writer.setPageMargins(
            QMarginsF(14, 14, 14, 14), QPageLayout.Unit.Millimeter
        )
        writer.setResolution(150)

        painter = QPainter(writer)   # begins implicitly, do NOT call begin()
        try:
            page_rect = writer.pageLayout().paintRectPixels(
                writer.resolution()
            )
            left = page_rect.x()
            right = page_rect.x() + page_rect.width()
            top = page_rect.y()
            footer_y = page_rect.y() + page_rect.height() - 32
            content_width = page_rect.width()

            title = {
                "hours": "Volunteer hours",
                "registrations": "Event registrations",
                "bookmarks": "Bookmarked events",
            }.get(ds, "Moxie data export")
            generated = datetime.now().strftime("%Y-%m-%d %H:%M")
            body_font = QFont("Helvetica", 9)
            header_font = QFont("Helvetica", 9, QFont.Weight.Bold)
            painter.setFont(body_font)
            metrics = QFontMetricsF(body_font)
            cell_flags = (
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignVCenter
                | Qt.TextFlag.TextWordWrap
            )
            padding = 10
            table_widths = {
                "hours": (0.14, 0.32, 0.27, 0.12, 0.15),
                "registrations": (0.15, 0.28, 0.16, 0.23, 0.18),
                "bookmarks": (0.16, 0.28, 0.15, 0.23, 0.18),
            }.get(ds, ())
            if len(table_widths) != len(headers):
                table_widths = tuple(
                    1 / max(1, len(headers)) for _ in headers
                )
            else:
                weight_total = sum(table_widths)
                table_widths = tuple(
                    weight / weight_total for weight in table_widths
                )
            column_widths = [
                content_width * weight for weight in table_widths
            ]

            def draw_table_header(y):
                painter.fillRect(
                    QRectF(left, y, content_width, 38),
                    QColor("#2D1A3E"),
                )
                painter.setFont(header_font)
                painter.setPen(QColor("#FFFFFF"))
                x = left
                for header, width in zip(headers, column_widths):
                    painter.drawText(
                        QRectF(x + padding, y, width - 2 * padding, 38),
                        Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter,
                        str(header),
                    )
                    x += width
                painter.setFont(body_font)
                painter.setPen(QColor("#2D1A3E"))
                return y + 38

            def draw_footer(page_number):
                painter.setPen(QColor("#D8CBC7"))
                painter.drawLine(
                    int(left), int(footer_y),
                    int(right), int(footer_y),
                )
                painter.setPen(QColor("#6B5B77"))
                painter.drawText(
                    QRectF(left, footer_y + 5, content_width / 2, 24),
                    Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignVCenter,
                    "Moxie volunteer impact record",
                )
                painter.drawText(
                    QRectF(
                        left + content_width / 2, footer_y + 5,
                        content_width / 2, 24,
                    ),
                    Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignVCenter,
                    f"Page {page_number}",
                )

            def draw_heading(first_page):
                painter.fillRect(
                    QRectF(left, top, 5, 74), QColor("#3D4BA8")
                )
                painter.setPen(QColor("#2D1A3E"))
                heading_font = QFont(
                    "Helvetica", 20 if first_page else 13,
                    QFont.Weight.Bold,
                )
                painter.setFont(heading_font)
                heading_y = top + (10 if first_page else 0)
                heading_height = 42 if first_page else 30
                heading_text = title if first_page else f"{title} (continued)"
                painter.drawText(
                    QRectF(left + 18, heading_y, content_width - 18, heading_height),
                    Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignVCenter,
                    heading_text,
                )
                if first_page:
                    painter.setFont(body_font)
                    painter.setPen(QColor("#6B5B77"))
                    painter.drawText(
                        QRectF(left + 18, top + 53, content_width - 18, 24),
                        Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter,
                        f"Generated {generated}",
                    )
                    summary = f"{len(rows)} records"
                    if ds == "hours" and len(headers) > 3:
                        total_hours = sum(
                            float(row[3] or 0) for row in rows
                        )
                        verified_count = sum(
                            1 for row in rows
                            if len(row) > 4 and str(row[4]).lower() == "yes"
                        )
                        summary += (
                            f"   |   {total_hours:.2f} total hours"
                            f"   |   {verified_count} verified"
                        )
                    summary_y = top + 91
                    painter.fillRect(
                        QRectF(left, summary_y, content_width, 38),
                        QColor("#F5F0EE"),
                    )
                    painter.setPen(QColor("#2D1A3E"))
                    painter.drawText(
                        QRectF(
                            left + padding, summary_y,
                            content_width - 2 * padding, 38,
                        ),
                        Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter,
                        summary,
                    )
                    return summary_y + 52
                return top + 42

            page_number = 1
            y = draw_table_header(draw_heading(first_page=True))
            for row_index, row in enumerate(rows):
                cells = [
                    str(row[index]) if index < len(row) else ""
                    for index in range(len(headers))
                ]
                cell_heights = []
                for index, cell in enumerate(cells):
                    text_rect = metrics.boundingRect(
                        QRectF(
                            0, 0, max(1, column_widths[index] - 2 * padding),
                            10000,
                        ),
                        cell_flags,
                        cell,
                    )
                    cell_heights.append(text_rect.height() + 2 * padding)
                row_height = max(38, max(cell_heights, default=38))
                if y + row_height > footer_y:
                    draw_footer(page_number)
                    writer.newPage()
                    page_number += 1
                    y = draw_table_header(draw_heading(first_page=False))

                painter.fillRect(
                    QRectF(left, y, content_width, row_height),
                    QColor("#F5F0EE" if row_index % 2 == 0 else "#FFFFFF"),
                )
                painter.setPen(QColor("#2D1A3E"))
                x = left
                for cell, width in zip(cells, column_widths):
                    painter.drawText(
                        QRectF(
                            x + padding, y + padding,
                            width - 2 * padding,
                            row_height - 2 * padding,
                        ),
                        cell_flags,
                        cell,
                    )
                    x += width
                painter.setPen(QColor("#E4DAD6"))
                painter.drawLine(
                    int(left), int(y + row_height),
                    int(right), int(y + row_height),
                )
                y += row_height

            draw_footer(page_number)
        finally:
            painter.end()